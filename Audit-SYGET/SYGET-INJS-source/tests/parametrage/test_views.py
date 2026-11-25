import pytest
from django.test import Client
from django.urls import reverse

from apps.parametrage.models import (
    Batiment,
    Grade,
    ModuleTypeFormation,
    PeriodeDisponibiliteSite,
    Salle,
    Site,
)
from apps.referentiels.models import Module, Specialite, TypeFormation


@pytest.fixture
def logged_client(db):
    from django.contrib.auth.models import User

    User.objects.create_superuser("paramuser", "param@example.com", "testpass123")
    client = Client()
    client.login(username="paramuser", password="testpass123")
    return client


@pytest.mark.django_db
class TestParametrageLieuxViews:
    def test_site_update(self, logged_client):
        site = Site.objects.create(nom="Ancien Site")
        resp = logged_client.post(
            reverse("parametrage:site_update", kwargs={"pk": site.pk}),
            {"nom": "Nouveau Site"},
        )
        assert resp.status_code == 302
        site.refresh_from_db()
        assert site.nom == "Nouveau Site"

    def test_batiment_update(self, logged_client):
        site_a = Site.objects.create(nom="Site A")
        site_b = Site.objects.create(nom="Site B")
        batiment = Batiment.objects.create(site=site_a, nom="BAT-OLD")
        resp = logged_client.post(
            reverse("parametrage:batiment_update", kwargs={"pk": batiment.pk}),
            {"site": site_b.pk, "nom": "BAT-NEW"},
        )
        assert resp.status_code == 302
        batiment.refresh_from_db()
        assert batiment.site_id == site_b.pk
        assert batiment.nom == "BAT-NEW"

    def test_salle_update(self, logged_client):
        site = Site.objects.create(nom="Site S")
        bat_a = Batiment.objects.create(site=site, nom="BAT-A")
        bat_b = Batiment.objects.create(site=site, nom="BAT-B")
        salle = Salle.objects.create(batiment=bat_a, nom="S-01", capacite_max=20)
        resp = logged_client.post(
            reverse("parametrage:salle_update", kwargs={"pk": salle.pk}),
            {"batiment": bat_b.pk, "nom": "S-01-B", "capacite_max": 35},
        )
        assert resp.status_code == 302
        salle.refresh_from_db()
        assert salle.batiment_id == bat_b.pk
        assert salle.nom == "S-01-B"
        assert salle.capacite_max == 35

    def test_site_toggle_actif(self, logged_client):
        site = Site.objects.create(nom="Site Toggle", actif=True)
        resp = logged_client.post(reverse("parametrage:site_toggle_actif", kwargs={"pk": site.pk}))
        assert resp.status_code == 302
        assert "#lieux-pedagogiques" in resp["Location"]
        site.refresh_from_db()
        assert site.actif is False

        resp = logged_client.post(reverse("parametrage:site_toggle_actif", kwargs={"pk": site.pk}))
        site.refresh_from_db()
        assert site.actif is True

    def test_site_toggle_actif_bloque_si_batiments_actifs(self, logged_client):
        site = Site.objects.create(nom="Site Bloque", actif=True)
        Batiment.objects.create(site=site, nom="Bat actif", actif=True)
        resp = logged_client.post(reverse("parametrage:site_toggle_actif", kwargs={"pk": site.pk}))
        assert resp.status_code == 302
        assert "#lieux-pedagogiques" not in resp["Location"]
        site.refresh_from_db()
        assert site.actif is True

    def test_periode_disponibilite_site_create(self, logged_client):
        site = Site.objects.create(nom="Site Periode", actif=True)
        resp = logged_client.post(
            reverse("parametrage:periode_disponibilite_site_create"),
            {
                "site": site.pk,
                "date_debut": "2025-09-01",
                "date_fin": "2025-12-15",
            },
        )
        assert resp.status_code == 302
        assert PeriodeDisponibiliteSite.objects.filter(site=site).count() == 1
        periode = PeriodeDisponibiliteSite.objects.get(site=site)
        assert str(periode.date_debut) == "2025-09-01"
        assert str(periode.date_fin) == "2025-12-15"


@pytest.mark.django_db
def test_module_create_recree_specialite_general_si_absente(logged_client):
    Specialite.objects.filter(code="GENERAL").delete()

    resp = logged_client.post(
        reverse("parametrage:module_create"),
        {"titre": "Nouveau Module VPS"},
    )

    assert resp.status_code == 302
    specialite = Specialite.objects.get(code="GENERAL")
    module = Module.objects.get(titre="Nouveau Module VPS")
    assert module.specialite_id == specialite.pk


@pytest.mark.django_db
class TestModuleAssocierMultiGrade:
    """Couvre la sélection multi-grades du formulaire « Associer un module à un type »."""

    @pytest.fixture
    def base(self, db):
        type_formation, _ = TypeFormation.objects.get_or_create(code="FAC", defaults={"libelle": "FAC"})
        specialite, _ = Specialite.objects.get_or_create(code="GENERAL", defaults={"libelle": "Général"})
        module, _ = Module.objects.get_or_create(titre="Culture Civique", defaults={"specialite": specialite})
        for libelle, ordre in [("A3", 1), ("A4", 2), ("B3", 3)]:
            Grade.objects.get_or_create(libelle=libelle, defaults={"ordre": ordre, "actif": True})
        return {"type_formation": type_formation, "module": module}

    def test_association_pour_plusieurs_grades_cree_une_ligne_par_grade(self, logged_client, base):
        resp = logged_client.post(
            reverse("parametrage:module_associer"),
            {
                "module": base["module"].pk,
                "type_formation": base["type_formation"].pk,
                "grade_cible": ["A3", "B3"],
                "volume_horaire_defaut": 20,
            },
        )

        assert resp.status_code == 302
        grades_crees = sorted(
            ModuleTypeFormation.objects.filter(
                module=base["module"], type_formation=base["type_formation"]
            ).values_list("grade_cible", flat=True)
        )
        assert grades_crees == ["A3", "B3"]

    def test_association_avec_tous_grades_cree_une_seule_ligne_generique(self, logged_client, base):
        resp = logged_client.post(
            reverse("parametrage:module_associer"),
            {
                "module": base["module"].pk,
                "type_formation": base["type_formation"].pk,
                "grade_cible": ["__ALL__", "A3"],
                "volume_horaire_defaut": 15,
            },
        )

        assert resp.status_code == 302
        assocs = list(ModuleTypeFormation.objects.filter(module=base["module"], type_formation=base["type_formation"]))
        assert len(assocs) == 1
        assert assocs[0].grade_cible == ""
        assert assocs[0].volume_horaire_defaut == 15

    def test_association_sans_grade_coche_equivaut_a_tous_grades(self, logged_client, base):
        resp = logged_client.post(
            reverse("parametrage:module_associer"),
            {
                "module": base["module"].pk,
                "type_formation": base["type_formation"].pk,
                "volume_horaire_defaut": 10,
            },
        )

        assert resp.status_code == 302
        assocs = list(ModuleTypeFormation.objects.filter(module=base["module"], type_formation=base["type_formation"]))
        assert len(assocs) == 1
        assert assocs[0].grade_cible == ""


@pytest.mark.django_db
class TestParametresParFormation:
    def test_modifier_une_formation_ne_modifie_pas_l_autre(self, logged_client, formation, type_formation):
        import datetime

        from apps.formations.repositories import FormationModuleRepository, FormationRepository
        from apps.formations.services import FormationService
        from apps.parametrage.models import ParametreFormation

        service = FormationService(FormationRepository(), FormationModuleRepository())
        formation_b = service.creer(
            type_formation_id=type_formation.pk,
            intitule="Formation B",
            vague="Vague 2",
            date_debut=datetime.date(2025, 6, 1),
            date_fin=datetime.date(2025, 8, 31),
        )

        params_a = ParametreFormation.get_for_formation(formation.pk)
        params_b = ParametreFormation.get_for_formation(formation_b.pk)
        params_a.max_auditeurs_groupe_defaut = 30
        params_a.save(update_fields=["max_auditeurs_groupe_defaut"])
        params_b.max_auditeurs_groupe_defaut = 15
        params_b.save(update_fields=["max_auditeurs_groupe_defaut"])

        resp = logged_client.post(
            reverse("parametrage:parametres_formation_update"),
            {
                "formation_id": formation.pk,
                "max_auditeurs_groupe_defaut": 40,
                "groupes_auto_mixage_grades": False,
                "matin_heure_debut_defaut": "08:00",
                "matin_heure_fin_defaut": "12:00",
                "soir_heure_debut_defaut": "13:00",
                "soir_heure_fin_defaut": "17:00",
                "duree_seance_defaut_minutes": 240,
                "max_seances_par_jour_defaut": 2,
                "max_salles_simultanees_module": 10,
                "tolerance_capacite_salle": 0,
                "verrouiller_salle_groupe_formation": False,
                "repartir_reliquat_sur_seances": False,
                "poids_score_ecart_capacite": 10,
                "poids_score_rotation_module": 2,
                "poids_score_equilibrage_global": 1,
                "jours_defaut": ["0", "1", "2", "3", "4"],
            },
        )
        assert resp.status_code == 302

        params_a.refresh_from_db()
        params_b.refresh_from_db()
        assert params_a.max_auditeurs_groupe_defaut == 40
        assert params_b.max_auditeurs_groupe_defaut == 15
