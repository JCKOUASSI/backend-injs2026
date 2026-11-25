"""
Tests des vues HTTP de gestion manuelle des séances.
"""

import datetime
from io import BytesIO

import pytest
from openpyxl import load_workbook
from django.test import Client
from django.urls import reverse

from apps.formations.models import FormationModule
from apps.groupes.models import ConfigGroupe, Groupe, JourCours
from apps.referentiels.models import Module
from apps.seances.models import PlanningAuditLog, Seance


@pytest.fixture
def logged_client(db):
    """Client Django authentifié avec un super-utilisateur."""
    from django.contrib.auth.models import User

    User.objects.create_superuser("seanceuser", "seance@example.com", "testpass123")
    client = Client()
    client.login(username="seanceuser", password="testpass123")
    return client


@pytest.fixture
def basic_client(db):
    """Client authentifié simple sans rôles planning."""
    from django.contrib.auth.models import User

    User.objects.create_user("basicuser", "basic@example.com", "testpass123")
    client = Client()
    client.login(username="basicuser", password="testpass123")
    return client


@pytest.fixture
def direction_client(db):
    """Client authentifié avec rôle lecture planning (direction).

    Les permissions Django sont alimentées via la commande `seed_roles`.
    """
    from django.contrib.auth.models import Group, User
    from django.core.management import call_command

    call_command("seed_roles")
    user = User.objects.create_user("directionuser", "dir@example.com", "testpass123")
    user.groups.add(Group.objects.get(name="DIRECTION_EDT"))
    client = Client()
    client.login(username="directionuser", password="testpass123")
    return client


@pytest.fixture
def gestion_client(db):
    """Client authentifié avec rôle gestionnaire planning (lecture + écriture)."""
    from django.contrib.auth.models import Group, User
    from django.core.management import call_command

    call_command("seed_roles")
    user = User.objects.create_user("gestionuser", "gestion@example.com", "testpass123")
    user.groups.add(Group.objects.get(name="GESTIONNAIRE_EDT"))
    client = Client()
    client.login(username="gestionuser", password="testpass123")
    return client


@pytest.fixture
def groupe_avec_module(formation, specialite_generale):
    """Crée un groupe prêt à recevoir des séances, avec un module de formation associé."""
    module = Module.objects.create(titre="Module HTTP", specialite=specialite_generale)
    FormationModule.objects.create(
        formation=formation,
        module=module,
        volume_horaire=8,
        date_debut=formation.date_debut,
        date_fin=formation.date_fin,
        site_nom="SITE-A",
        batiment_nom="BAT-A",
        salle_nom="SALLE-A",
    )
    groupe = Groupe.objects.create(formation=formation, nom="GRP-HTTP", max_auditeurs=25)
    ConfigGroupe.objects.create(
        groupe=groupe,
        matin_actif=True,
        matin_heure_debut=datetime.time(8, 0),
        matin_heure_fin=datetime.time(12, 0),
        soir_actif=True,
        soir_heure_debut=datetime.time(13, 0),
        soir_heure_fin=datetime.time(17, 0),
    )
    return groupe, module


@pytest.mark.django_db
class TestSeancesViews:
    def test_audit_list_accessible_pour_user_autorise(self, logged_client):
        url = reverse("seances:audit_list")
        resp = logged_client.get(url)
        assert resp.status_code == 200

    def test_audit_list_refuse_sans_role(self, basic_client):
        url = reverse("seances:audit_list")
        resp = basic_client.get(url)
        assert resp.status_code == 403

    def test_direction_peut_lire_mais_pas_generer(self, direction_client, groupe_avec_module):
        groupe, _ = groupe_avec_module
        url = reverse("seances:preview", kwargs={"groupe_pk": groupe.pk})
        resp_get = direction_client.get(url)
        assert resp_get.status_code == 200
        resp_post = direction_client.post(url)
        assert resp_post.status_code == 403

    def test_preview_refuse_acces_sans_role(self, basic_client, groupe_avec_module):
        groupe, _ = groupe_avec_module
        url = reverse("seances:preview", kwargs={"groupe_pk": groupe.pk})
        resp = basic_client.get(url)
        assert resp.status_code == 403

    def test_basic_user_refuse_actions_ecriture(self, basic_client, groupe_avec_module):
        """Un utilisateur connecté sans groupe planning est refusé partout."""
        groupe, _ = groupe_avec_module
        urls_403 = [
            reverse("seances:preview", kwargs={"groupe_pk": groupe.pk}),
            reverse("seances:create", kwargs={"groupe_pk": groupe.pk}),
            reverse("seances:export", kwargs={"groupe_pk": groupe.pk}),
            reverse("seances:export_pdf", kwargs={"groupe_pk": groupe.pk}),
            reverse("seances:audit_list"),
            reverse("seances:chevauchements"),
        ]
        for url in urls_403:
            resp = basic_client.get(url)
            assert resp.status_code == 403, f"Attendu 403 sur {url}, reçu {resp.status_code}"

    def test_direction_template_masque_actions_ecriture(self, direction_client, groupe_avec_module):
        """La page preview ne propose ni le formulaire de création ni le bouton Générer pour la direction."""
        groupe, _ = groupe_avec_module
        url = reverse("seances:preview", kwargs={"groupe_pk": groupe.pk})
        resp = direction_client.get(url)
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "Ajouter une séance manuellement" not in content
        assert 'value="generate"' not in content
        assert 'value="preview"' not in content
        assert "Emploi du temps PDF" in content
        assert "format=cours" in content

    def test_direction_peut_exporter_excel_et_pdf(self, direction_client, groupe_avec_module, formation):
        """L'export est une lecture : la direction peut télécharger sans droit d'écriture planning."""
        groupe, _ = groupe_avec_module
        for url in (
            reverse("seances:export", kwargs={"groupe_pk": groupe.pk}),
            reverse("seances:export_pdf", kwargs={"groupe_pk": groupe.pk}),
            reverse("seances:formation_export", kwargs={"formation_pk": formation.pk}),
            reverse("seances:formation_export_pdf", kwargs={"formation_pk": formation.pk}),
            reverse("seances:formation_export_pdf_zip", kwargs={"formation_pk": formation.pk}),
            reverse("seances:formation_export_zip", kwargs={"formation_pk": formation.pk}),
        ):
            resp = direction_client.get(url)
            assert resp.status_code == 200, f"Attendu 200 sur {url}, reçu {resp.status_code}"
            assert "attachment" in resp["Content-Disposition"].lower()

    def test_gestionnaire_peut_lire_et_ecrire(self, gestion_client, groupe_avec_module):
        """Le gestionnaire EDT a accès en lecture et en écriture au planning."""
        from django.contrib.auth.models import User

        groupe, _ = groupe_avec_module
        user = User.objects.get(username="gestionuser")
        formation = groupe.formation
        formation.responsable = user
        formation.save(update_fields=["responsable"])

        preview_url = reverse("seances:preview", kwargs={"groupe_pk": groupe.pk})
        resp_get = gestion_client.get(preview_url)
        assert resp_get.status_code == 200
        content = resp_get.content.decode()
        assert "Ajouter une séance manuellement" in content
        # Le gestionnaire doit pouvoir déclencher une prévisualisation.
        JourCours.objects.create(groupe=groupe, jour=0)
        resp_post = gestion_client.post(preview_url, {"mode": "preview"})
        assert resp_post.status_code == 200

    def test_preview_mode_ne_persiste_pas(self, logged_client, groupe_avec_module):
        """La prévisualisation calcule le planning sans enregistrer de séances."""
        groupe, _ = groupe_avec_module
        JourCours.objects.create(groupe=groupe, jour=0)
        url = reverse("seances:preview", kwargs={"groupe_pk": groupe.pk})
        resp = logged_client.post(url, {"mode": "preview"})
        assert resp.status_code == 200
        assert Seance.objects.filter(groupe=groupe).count() == 0
        messages_list = [m.message for m in resp.context["messages"]]
        assert any("Prévisualisation" in m for m in messages_list)
        assert any("Aucune séance n'a été enregistrée" in m for m in messages_list)
        assert resp.context["preview_mode"] is True
        assert resp.context["preview_total_seances"] >= 1
        assert resp.context["preview_total_heures"] >= 1
        assert len(resp.context["preview_module_report"]) >= 1
        assert "reason" in resp.context["preview_module_report"][0]

    def test_create_seance_manuel(self, logged_client, groupe_avec_module):
        groupe, module = groupe_avec_module
        url = reverse("seances:create", kwargs={"groupe_pk": groupe.pk})
        resp = logged_client.post(
            url,
            {
                "module": module.pk,
                "date": "2025-01-06",
                "heure_debut": "08:00",
                "heure_fin": "10:00",
                "site_nom": "SITE-A",
                "batiment_nom": "BAT-A",
                "salle_nom": "SALLE-A",
            },
        )
        assert resp.status_code == 302
        assert Seance.objects.filter(groupe=groupe).count() == 1
        assert Seance.objects.filter(groupe=groupe).first().duree_minutes == 120
        assert PlanningAuditLog.objects.filter(action=PlanningAuditLog.Action.CREATE).exists()

    def test_create_seance_refuse_chevauche_autre_groupe(self, logged_client, groupe_avec_module, formation):
        """Même date, salle et horaires qui se chevauchent : refus (plusieurs planificateurs / groupes)."""
        groupe1, module = groupe_avec_module
        Seance.objects.create(
            groupe=groupe1,
            module=module,
            date=datetime.date(2025, 1, 6),
            heure_debut=datetime.time(9, 0),
            heure_fin=datetime.time(11, 0),
            duree_minutes=120,
            salle_nom="SALLE-X",
            site_nom="SITE-A",
            batiment_nom="BAT-A",
        )
        groupe2 = Groupe.objects.create(formation=formation, nom="GRP-2", max_auditeurs=25)
        ConfigGroupe.objects.create(
            groupe=groupe2,
            matin_actif=True,
            matin_heure_debut=datetime.time(8, 0),
            matin_heure_fin=datetime.time(12, 0),
            soir_actif=False,
            soir_heure_debut=datetime.time(13, 0),
            soir_heure_fin=datetime.time(17, 0),
        )
        url = reverse("seances:create", kwargs={"groupe_pk": groupe2.pk})
        resp = logged_client.post(
            url,
            {
                "module": module.pk,
                "date": "2025-01-06",
                "heure_debut": "10:00",
                "heure_fin": "12:00",
                "site_nom": "SITE-A",
                "batiment_nom": "BAT-A",
                "salle_nom": "SALLE-X",
            },
            follow=True,
        )
        assert resp.status_code == 200
        messages_list = [m.message for m in resp.context["messages"]]
        assert any("créneau" in m.lower() or "erreur création" in m.lower() for m in messages_list)
        assert Seance.objects.filter(groupe=groupe2).count() == 0

    def test_update_seance_manuel(self, logged_client, groupe_avec_module):
        groupe, module = groupe_avec_module
        seance = Seance.objects.create(
            groupe=groupe,
            module=module,
            date=datetime.date(2025, 1, 6),
            heure_debut=datetime.time(8, 0),
            heure_fin=datetime.time(10, 0),
            duree_minutes=120,
            salle_nom="SALLE-A",
        )
        url = reverse("seances:update", kwargs={"pk": seance.pk})
        resp = logged_client.post(
            url,
            {
                "module": module.pk,
                "date": "2025-01-06",
                "heure_debut": "13:00",
                "heure_fin": "17:00",
                "site_nom": "SITE-A",
                "batiment_nom": "BAT-A",
                "salle_nom": "SALLE-A",
            },
        )
        assert resp.status_code == 302
        seance.refresh_from_db()
        assert seance.heure_debut == datetime.time(13, 0)
        assert seance.duree_minutes == 240

    def test_delete_seance_manuel(self, logged_client, groupe_avec_module):
        groupe, module = groupe_avec_module
        seance = Seance.objects.create(
            groupe=groupe,
            module=module,
            date=datetime.date(2025, 1, 6),
            heure_debut=datetime.time(8, 0),
            heure_fin=datetime.time(10, 0),
            duree_minutes=120,
            salle_nom="SALLE-A",
        )
        url = reverse("seances:delete", kwargs={"pk": seance.pk})
        resp = logged_client.post(url)
        assert resp.status_code == 302
        assert not Seance.objects.filter(pk=seance.pk).exists()

    def test_export_mode_seances(self, logged_client, groupe_avec_module):
        groupe, module = groupe_avec_module
        Seance.objects.create(
            groupe=groupe,
            module=module,
            date=datetime.date(2025, 1, 6),
            heure_debut=datetime.time(8, 0),
            heure_fin=datetime.time(12, 0),
            duree_minutes=240,
            salle_nom="SALLE-A",
        )
        url = reverse("seances:export", kwargs={"groupe_pk": groupe.pk})
        resp = logged_client.get(f"{url}?format=seances")
        assert resp.status_code == 200
        wb = load_workbook(BytesIO(resp.content), data_only=True)
        assert wb.sheetnames == ["Séances"]
        assert PlanningAuditLog.objects.filter(action=PlanningAuditLog.Action.EXPORT).exists()

    def test_export_formation_multi_groupes(self, logged_client, groupe_avec_module, formation):
        groupe1, module = groupe_avec_module
        groupe2 = Groupe.objects.create(formation=formation, nom="GRP-HTTP-2", max_auditeurs=25)
        Seance.objects.create(
            groupe=groupe1,
            module=module,
            date=datetime.date(2025, 1, 6),
            heure_debut=datetime.time(8, 0),
            heure_fin=datetime.time(12, 0),
            duree_minutes=240,
            salle_nom="SALLE-A",
        )
        Seance.objects.create(
            groupe=groupe2,
            module=module,
            date=datetime.date(2025, 1, 6),
            heure_debut=datetime.time(13, 0),
            heure_fin=datetime.time(17, 0),
            duree_minutes=240,
            salle_nom="SALLE-B",
        )

        url = reverse("seances:formation_export", kwargs={"formation_pk": formation.pk})
        resp = logged_client.get(f"{url}?format=seances")
        assert resp.status_code == 200
        wb = load_workbook(BytesIO(resp.content), data_only=True)
        ws = wb["Séances"]
        assert ws.max_row == 3

    def test_export_formation_mode_formateurs(self, logged_client, groupe_avec_module, formation):
        groupe, module = groupe_avec_module
        Seance.objects.create(
            groupe=groupe,
            module=module,
            formateur_nom="DUPONT",
            formateur_prenom="Marie",
            formateur_numero="+2250111111111",
            date=datetime.date(2025, 1, 6),
            heure_debut=datetime.time(8, 0),
            heure_fin=datetime.time(12, 0),
            duree_minutes=240,
            salle_nom="SALLE-A",
        )
        url = reverse("seances:formation_export", kwargs={"formation_pk": formation.pk})
        resp = logged_client.get(f"{url}?format=formateurs")
        assert resp.status_code == 200
        wb = load_workbook(BytesIO(resp.content), data_only=True)
        assert wb.sheetnames == ["Formateurs"]
        ws = wb["Formateurs"]
        assert ws.cell(2, 2).value == "DUPONT"
        assert ws.cell(2, 9).value == "GRP-HTTP"
        d = ws.cell(2, 10).value
        assert d is not None
        if isinstance(d, datetime.datetime):
            assert d.date() == datetime.date(2025, 1, 6)
        else:
            assert d == datetime.date(2025, 1, 6)
        assert ws.cell(2, 11).value == "Module HTTP"

    def test_export_mode_formateurs(self, logged_client, groupe_avec_module):
        groupe, module = groupe_avec_module
        Seance.objects.create(
            groupe=groupe,
            module=module,
            formateur_nom="FORMATEUR HTTP",
            formateur_prenom="TEST",
            formateur_numero="+225000000000",
            formateur_email="formateur.http@example.com",
            formateur_telephone="+2252721223344",
            formateur_organisation="CPFAE",
            date=datetime.date(2025, 1, 6),
            heure_debut=datetime.time(8, 0),
            heure_fin=datetime.time(12, 0),
            duree_minutes=240,
            salle_nom="SALLE-A",
        )
        url = reverse("seances:export", kwargs={"groupe_pk": groupe.pk})
        resp = logged_client.get(f"{url}?format=formateurs")
        assert resp.status_code == 200
        wb = load_workbook(BytesIO(resp.content), data_only=True)
        assert wb.sheetnames == ["Formateurs"]
        ws = wb["Formateurs"]
        assert ws.cell(2, 2).value == "FORMATEUR HTTP"
        assert ws.cell(2, 7).value in (None, "")
        assert ws.cell(2, 8).value in (None, "")
        assert ws.cell(2, 9).value == "GRP-HTTP"
        d = ws.cell(2, 10).value
        assert d is not None
        if isinstance(d, datetime.datetime):
            assert d.date() == datetime.date(2025, 1, 6)
        else:
            assert d == datetime.date(2025, 1, 6)
        assert ws.cell(2, 11).value == "Module HTTP"
