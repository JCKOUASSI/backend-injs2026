"""
Tests des vues (HTTP) — formations et inscriptions.
Vérifie les redirections, les codes de réponse et les accès protégés.
"""

from io import BytesIO

import pytest
from django.test import Client
from django.urls import reverse
from openpyxl import Workbook, load_workbook


@pytest.fixture
def logged_client(db):
    """Client Django authentifié avec un super-utilisateur."""
    from django.contrib.auth.models import User

    User.objects.create_superuser("testuser", "test@example.com", "testpass123")
    client = Client()
    client.login(username="testuser", password="testpass123")
    return client


@pytest.mark.django_db
class TestFormationsViews:
    """Tests d'intégration pour les vues formations."""

    def test_liste_formations_redirige_si_non_connecte(self):
        """Un utilisateur non connecté est redirigé vers le login."""
        client = Client()
        url = reverse("formations:list")
        resp = client.get(url)
        assert resp.status_code == 302
        assert "/login/" in resp["Location"]

    def test_liste_formations_accessible_si_connecte(self, logged_client):
        """La liste est accessible pour un utilisateur connecté."""
        resp = logged_client.get(reverse("formations:list"))
        assert resp.status_code == 200

    def test_creation_formation(self, logged_client, type_formation):
        """La création d'une formation redirige vers le détail."""
        data = {
            "type_formation": type_formation.pk,
            "intitule": "Formation de test HTTP",
            "vague": "",
            "date_debut": "2025-01-06",
            "date_fin": "2025-03-28",
            "rythme_mensuel": ["2"],
        }
        resp = logged_client.post(reverse("formations:create"), data)
        assert resp.status_code == 302
        assert "/formations/" in resp["Location"]

    def test_detail_formation(self, logged_client, formation):
        """La page détail d'une formation est accessible."""
        resp = logged_client.get(reverse("formations:detail", kwargs={"pk": formation.pk}))
        assert resp.status_code == 200
        assert formation.intitule.encode() in resp.content

    def test_detail_formation_inexistante(self, logged_client):
        """Une formation inexistante retourne 404."""
        resp = logged_client.get(reverse("formations:detail", kwargs={"pk": 99999}))
        assert resp.status_code == 404

    def test_export_auditeurs_formation_xlsx(self, logged_client, formation, auditeur):
        """Export Excel : auditeurs affectés à un groupe (comme après génération auto)."""
        from apps.groupes.models import Groupe, GroupeAuditeur

        g = Groupe.objects.create(formation=formation, nom="Groupe export", max_auditeurs=25)
        GroupeAuditeur.objects.create(groupe=g, auditeur=auditeur)
        url = reverse("formations:export_auditeurs", kwargs={"pk": formation.pk})
        resp = logged_client.get(url)
        assert resp.status_code == 200
        assert "spreadsheetml" in resp["Content-Type"]
        wb = load_workbook(BytesIO(resp.content), data_only=True)
        assert wb.sheetnames == ["Auditeurs"]
        ws = wb["Auditeurs"]
        assert ws.cell(1, 1).value == "Export auditeurs"
        assert ws.cell(3, 1).value == "N° d'inscription"
        assert ws.cell(4, 1).value == auditeur.matricule
        assert ws.cell(4, 2).value == auditeur.nom
        assert ws.cell(4, 14).value == "Groupe export"

    def test_export_auditeurs_colonne_groupe_sans_grade_redondant(self, logged_client, formation, auditeur):
        """« Groupe 10 A3 » en base + auditeur A3 → colonne Groupe « Groupe 10 »."""
        from apps.groupes.models import Groupe, GroupeAuditeur

        auditeur.grade = "A3"
        auditeur.save(update_fields=["grade"])
        g = Groupe.objects.create(formation=formation, nom="Groupe 10 A3", max_auditeurs=25)
        GroupeAuditeur.objects.create(groupe=g, auditeur=auditeur)
        resp = logged_client.get(reverse("formations:export_auditeurs", kwargs={"pk": formation.pk}))
        assert resp.status_code == 200
        wb = load_workbook(BytesIO(resp.content), data_only=True)
        ws = wb["Auditeurs"]
        assert ws.cell(4, 14).value == "Groupe 10"

    def test_export_auditeurs_sans_groupes_retourne_400(self, logged_client, formation):
        """Sans groupe, l'export auditeurs est refusé (prérequis : génération / affectation)."""
        resp = logged_client.get(reverse("formations:export_auditeurs", kwargs={"pk": formation.pk}))
        assert resp.status_code == 400
        assert "groupes" in resp.content.decode().lower()

    def test_export_auditeurs_formation_404_si_inexistante(self, logged_client):
        resp = logged_client.get(reverse("formations:export_auditeurs", kwargs={"pk": 999999}))
        assert resp.status_code == 404

    def test_edit_formation_get(self, logged_client, formation):
        """La page d'édition d'une formation est accessible."""
        url = reverse("formations:edit", kwargs={"pk": formation.pk})
        resp = logged_client.get(url)
        assert resp.status_code == 200

    def test_edit_formation_post(self, logged_client, formation, type_formation):
        """La mise à jour d'une formation redirige vers le détail."""
        url = reverse("formations:edit", kwargs={"pk": formation.pk})
        data = {
            "type_formation": type_formation.pk,
            "intitule": "Formation renommée",
            "vague": "",
            "date_debut": "2025-01-06",
            "date_fin": "2025-03-28",
            "rythme_mensuel": ["3"],
        }
        resp = logged_client.post(url, data)
        assert resp.status_code == 302
        formation.refresh_from_db()
        assert formation.intitule == "Formation renommée"
        assert formation.rythme_mensuel == "3"

    def test_supprimer_formation(self, logged_client, formation):
        """La suppression d'une formation redirige vers la liste."""
        url = reverse("formations:delete", kwargs={"pk": formation.pk})
        resp = logged_client.post(url)
        assert resp.status_code == 302

    def test_modifier_module_formation(self, logged_client, formation, module_referentiel):
        """Un module rattaché à une formation peut être modifié."""
        from apps.formations.models import FormationModule
        from apps.parametrage.models import Batiment, ModuleTypeFormation, Salle, Site

        site = Site.objects.create(nom="SITE-X", actif=True)
        bat = Batiment.objects.create(site=site, nom="BAT-X", actif=True)
        salle = Salle.objects.create(batiment=bat, nom="SALLE-X", capacite_max=25, actif=True)
        ModuleTypeFormation.objects.create(
            module=module_referentiel,
            type_formation=formation.type_formation,
            volume_horaire_defaut=20,
        )
        periode = formation.periodes.order_by("ordre", "date_debut").first()
        fm = FormationModule.objects.create(
            formation=formation,
            module=module_referentiel,
            volume_horaire=20,
            grade_cible="",
            site_nom=site.nom,
            batiment_nom=bat.nom,
            salle_nom=salle.nom,
            site_nombre=1,
            batiment_nombre=1,
            salle_nombre=1,
            date_debut=formation.date_debut,
            date_fin=formation.date_fin,
            periode=periode,
        )

        url = reverse("formations:module_edit", kwargs={"pk": formation.pk, "module_pk": fm.pk})
        resp = logged_client.post(
            url,
            {
                "module": module_referentiel.pk,
                "periode": periode.pk,
                "grade_cible": ["__ALL__"],
                "creneau_mode": "matin_et_soir",
                "date_debut": formation.date_debut.isoformat(),
                "date_fin": formation.date_fin.isoformat(),
                "sites": [site.pk],
                "batiments": [bat.pk],
                "salles": [salle.pk],
            },
        )
        assert resp.status_code == 302

    def test_import_formateurs_excel(self, logged_client, formation, module_referentiel):
        """Importe les formateurs dans le référentiel global (sans formation ni module)."""
        from django.core.files.uploadedfile import SimpleUploadedFile

        from apps.formations.models import Formateur, FormationModule

        fm = FormationModule.objects.create(
            formation=formation,
            module=module_referentiel,
            volume_horaire=20,
        )

        wb = Workbook()
        ws = wb.active
        ws.append(["numero", "nom", "prenom", "email", "telephone", "organisation", "specialites"])
        ws.append(
            [
                "+2250102030405",
                "KOUAME",
                "Jean",
                "kouame.jean@example.com",
                "+2252721223344",
                "CPFAE",
                "GENERAL",
            ]
        )
        content = BytesIO()
        wb.save(content)
        content.seek(0)
        upload = SimpleUploadedFile(
            "formateurs.xlsx",
            content.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        url = reverse("formations:formateurs_import_page")
        resp = logged_client.post(url, {"fichier": upload})
        assert resp.status_code == 302

        formateur = Formateur.objects.get(numero="+2250102030405")
        assert formateur.nom == "KOUAME"
        assert formateur.prenom == "Jean"
        assert formateur.email == "kouame.jean@example.com"
        assert formateur.telephone == "+2252721223344"
        assert formateur.organisation == "CPFAE"
        fm.refresh_from_db()
        assert fm.formateur_nom == ""

    def test_import_formateurs_colonne_specialites(self, logged_client, formation, module_referentiel):
        """La colonne obligatoire specialites rattache les codes au M2M du Formateur."""
        from django.core.files.uploadedfile import SimpleUploadedFile

        from apps.formations.models import Formateur, FormationModule
        from apps.referentiels.models import Specialite

        FormationModule.objects.create(
            formation=formation,
            module=module_referentiel,
            volume_horaire=4,
        )

        wb = Workbook()
        ws = wb.active
        ws.append(
            [
                "numero",
                "nom",
                "prenom",
                "email",
                "telephone",
                "organisation",
                "specialites",
            ]
        )
        ws.append(
            [
                "+2250102030999",
                "SPE",
                "CIAL",
                "sp@example.com",
                "+2250000000999",
                "ORG",
                "FIN, DROIT",
            ]
        )
        content = BytesIO()
        wb.save(content)
        content.seek(0)
        upload = SimpleUploadedFile(
            "formateurs_spec.xlsx",
            content.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        url = reverse("formations:formateurs_import_page")
        resp = logged_client.post(url, {"fichier": upload})
        assert resp.status_code == 302

        formateur = Formateur.objects.get(numero="+2250102030999")
        codes = set(formateur.specialites.values_list("code", flat=True))
        assert codes == {"FIN", "DROIT"}
        assert Specialite.objects.filter(code="FIN").exists()

    def test_import_formateurs_excel_deux_numeros_deux_referents(self, logged_client, formation, module_referentiel):
        """Deux lignes avec des numeros distincts créent deux formateurs référentiels."""
        from django.core.files.uploadedfile import SimpleUploadedFile

        from apps.formations.models import Formateur

        wb = Workbook()
        ws = wb.active
        ws.append(["numero", "nom", "prenom", "email", "telephone", "organisation", "specialites"])
        ws.append(
            [
                "+2250102030405",
                "FORMATEUR",
                "UN",
                "f1@example.com",
                "+225000000001",
                "ORG1",
                "GENERAL",
            ]
        )
        ws.append(
            [
                "+2250102030406",
                "FORMATEUR",
                "DEUX",
                "f2@example.com",
                "+225000000002",
                "ORG2",
                "GENERAL",
            ]
        )
        content = BytesIO()
        wb.save(content)
        content.seek(0)
        upload = SimpleUploadedFile(
            "formateurs_replace.xlsx",
            content.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        url = reverse("formations:formateurs_import_page")
        resp = logged_client.post(url, {"fichier": upload})
        assert resp.status_code == 302

        assert Formateur.objects.filter(numero__in=["+2250102030405", "+2250102030406"]).count() == 2


@pytest.mark.django_db
class TestInscriptionsViews:
    """Tests d'intégration pour les vues inscriptions."""

    def test_inscrire_auditeur(self, logged_client, formation, auditeur, module_referentiel):
        """POST sur inscription_add inscrit l'auditeur et redirige."""
        from apps.formations.models import FormationModule

        fm = FormationModule.objects.create(
            formation=formation,
            module=module_referentiel,
            volume_horaire=20,
        )
        url = reverse("formations:inscription_add", kwargs={"pk": formation.pk})
        resp = logged_client.post(url, {"module_id": fm.pk, "auditeur_ids": [auditeur.pk]})
        assert resp.status_code == 302
        formation.refresh_from_db()
        assert formation.nb_inscrits == 1

    def test_desinscrire_auditeur(self, logged_client, formation, auditeur, module_referentiel):
        """POST sur inscription_delete désinscrit l'auditeur."""
        from apps.formations.models import FormationModule, Inscription

        fm = FormationModule.objects.create(
            formation=formation,
            module=module_referentiel,
            volume_horaire=20,
        )
        Inscription.objects.create(formation=formation, formation_module=fm, auditeur=auditeur)

        url = reverse("formations:inscription_delete", kwargs={"pk": formation.pk, "auditeur_pk": auditeur.pk})
        resp = logged_client.post(url, {"module_id": fm.pk})
        assert resp.status_code == 302
        assert formation.inscriptions.count() == 0
