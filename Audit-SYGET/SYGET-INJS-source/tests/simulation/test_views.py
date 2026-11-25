"""
Tests de la vue Simulation : mode « calcul automatique » et override des jours/semaine.
"""

import datetime

import pytest
from django.test import Client
from django.urls import reverse


@pytest.fixture
def logged_client(db):
    """Client Django authentifié (LoginRequiredMixin sur SimulationView)."""
    from django.contrib.auth.models import User

    User.objects.create_superuser("simuser", "sim@example.com", "testpass123")
    client = Client()
    client.login(username="simuser", password="testpass123")
    return client


def _payload(**overrides) -> dict:
    """POST minimal valide pour un formset à une formation (prefix form-0-)."""
    base = {
        "form-TOTAL_FORMS": "1",
        "form-INITIAL_FORMS": "1",
        "form-MIN_NUM_FORMS": "0",
        "form-MAX_NUM_FORMS": "20",
        "form-0-nb_groupes": 4,
        "form-0-capacite_groupe": 50,
        "form-0-nb_modules": 5,
        "form-0-heures_par_module": 40,
        "form-0-nb_salles": 6,
        "form-0-capacite_salle_moyenne": 60,
        "form-0-tolerance_capacite_pct": 0,
        "form-0-creneaux_par_jour": 2,
        "form-0-duree_creneau_heures": 4,
        "form-0-max_salles_simultanees_module": 5,
    }
    remapped = {}
    for key, val in overrides.items():
        if key.startswith("form-"):
            remapped[key] = val
        else:
            remapped[f"form-0-{key}"] = val
    base.update(remapped)
    return base


@pytest.mark.django_db
class TestSimulationModeAuto:
    """Si l'utilisateur ne saisit pas jours_ouvres, on prend le minimum requis."""

    def test_post_sans_jours_ouvres_active_le_mode_auto(self, logged_client):
        """Soumission sans jours_ouvres → mode_auto, simulation avec la valeur recommandée."""
        resp = logged_client.post(reverse("simulation:index"), data=_payload())

        assert resp.status_code == 200
        assert resp.context["mode_auto"] is True
        resultat = resp.context["resultat"]
        assert resultat is not None
        assert resultat.jours_ouvres_minimum == 17
        assert resultat.jours_ouvres_recommandes == 21
        assert resultat.inputs.jours_ouvres == 21

    def test_post_avec_jours_ouvres_utilise_valeur_saisie(self, logged_client):
        """Si jours_ouvres est saisi, on ne passe PAS en mode auto."""
        payload = _payload(jours_ouvres=90)
        resp = logged_client.post(reverse("simulation:index"), data=payload)

        assert resp.status_code == 200
        assert resp.context["mode_auto"] is False
        resultat = resp.context["resultat"]
        assert resultat.inputs.jours_ouvres == 90

    def test_post_sans_jours_ouvres_omet_le_diagnostic_occupation(self, logged_client):
        """En mode auto, pas de faux warning « Faisable mais tendue » à 96 %."""
        resp = logged_client.post(reverse("simulation:index"), data=_payload())

        assert resp.context["mode_auto"] is True
        resultat = resp.context["resultat"]
        titres = [d.titre for d in resultat.diagnostics]
        assert "Occupation globale" not in titres
        assert resultat.statut == "ok"


@pytest.mark.django_db
class TestSimulationJoursSemaineOverride:
    """Le champ `jours_semaine` du formulaire surcharge le paramétrage par défaut."""

    def test_jours_semaine_du_form_remplace_parametrage(self, logged_client, parametres):
        parametres.jours_defaut = [0, 1, 2, 3, 4]
        parametres.save()

        payload = _payload(
            nb_groupes=3,
            capacite_groupe=8,
            nb_modules=1,
            heures_par_module=4,
            nb_salles=1,
            max_salles_simultanees_module=1,
            creneaux_par_jour=1,
            date_debut="2026-01-05",
            jours_semaine=["0", "1", "2", "3", "4", "5"],
        )
        resp = logged_client.post(reverse("simulation:index"), data=payload)

        assert resp.status_code == 200
        resultat = resp.context["resultat"]
        assert resultat.jours_ouvres_minimum == 3
        assert resultat.jours_ouvres_recommandes == 4
        assert resultat.date_fin_estimee == datetime.date(2026, 1, 8)

    def test_jours_semaine_dimanche_seulement_donne_dates_eparses(self, logged_client, parametres):
        parametres.jours_defaut = [0, 1, 2, 3, 4]
        parametres.save()

        payload = _payload(
            nb_groupes=1,
            capacite_groupe=8,
            nb_modules=1,
            heures_par_module=4,
            nb_salles=1,
            max_salles_simultanees_module=1,
            creneaux_par_jour=1,
            date_debut="2026-01-05",
            jours_semaine=["6"],
        )
        resp = logged_client.post(reverse("simulation:index"), data=payload)

        resultat = resp.context["resultat"]
        assert resultat.jours_ouvres_minimum == 1
        assert resultat.jours_ouvres_recommandes == 2
        assert resultat.date_fin_estimee == datetime.date(2026, 1, 18)


@pytest.mark.django_db
def test_get_index_avec_plusieurs_formations(db, logged_client, formation, module_referentiel, parametres):
    """Charger plusieurs formations crée un bloc de paramètres par formation."""
    from apps.formations.models import FormationModule
    from apps.formations.repositories import FormationModuleRepository, FormationRepository
    from apps.formations.services import FormationService

    FormationModule.objects.create(formation=formation, module=module_referentiel, volume_horaire=40)
    service = FormationService(FormationRepository(), FormationModuleRepository())
    f2 = service.creer(
        type_formation_id=formation.type_formation_id,
        intitule="Formation parallèle",
        vague="V2",
        date_debut=datetime.date(2025, 4, 1),
        date_fin=datetime.date(2025, 6, 30),
    )
    FormationModule.objects.create(
        formation=f2,
        module=module_referentiel,
        volume_horaire=20,
    )

    url = reverse("simulation:index") + f"?formations={formation.pk}&formations={f2.pk}"
    resp = logged_client.get(url)

    assert resp.status_code == 200
    assert len(resp.context["formations_chargees"]) == 2
    formset = resp.context["formset"]
    assert len(formset.forms) == 2
    assert formset.forms[0].initial.get("formation_id") == formation.pk
    assert formset.forms[1].initial.get("formation_id") == f2.pk
    assert formset.forms[0].initial.get("heures_par_module") == 40
    assert formset.forms[1].initial.get("heures_par_module") == 20


@pytest.mark.django_db
def test_post_simule_plusieurs_formations_independamment(db, logged_client, formation, module_referentiel, parametres):
    """Chaque formation est simulée avec ses propres paramètres."""
    from apps.formations.models import FormationModule
    from apps.formations.repositories import FormationModuleRepository, FormationRepository
    from apps.formations.services import FormationService

    FormationModule.objects.create(formation=formation, module=module_referentiel, volume_horaire=40)
    service = FormationService(FormationRepository(), FormationModuleRepository())
    f2 = service.creer(
        type_formation_id=formation.type_formation_id,
        intitule="Formation parallèle",
        vague="V2",
        date_debut=datetime.date(2025, 4, 1),
        date_fin=datetime.date(2025, 6, 30),
    )
    FormationModule.objects.create(formation=f2, module=module_referentiel, volume_horaire=20)

    data = {
        "form-TOTAL_FORMS": "2",
        "form-INITIAL_FORMS": "2",
        "form-MIN_NUM_FORMS": "0",
        "form-MAX_NUM_FORMS": "20",
    }
    for i, (fid, heures) in enumerate([(formation.pk, 40), (f2.pk, 20)]):
        data.update(
            {
                f"form-{i}-formation_id": fid,
                f"form-{i}-intitule": f"F{i}",
                f"form-{i}-nb_groupes": 4,
                f"form-{i}-capacite_groupe": 50,
                f"form-{i}-nb_modules": 5,
                f"form-{i}-heures_par_module": heures,
                f"form-{i}-nb_salles": 6,
                f"form-{i}-capacite_salle_moyenne": 60,
                f"form-{i}-tolerance_capacite_pct": 0,
                f"form-{i}-creneaux_par_jour": 2,
                f"form-{i}-duree_creneau_heures": 4,
                f"form-{i}-max_salles_simultanees_module": 5,
                f"form-{i}-jours_ouvres": 90,
            }
        )

    resp = logged_client.post(reverse("simulation:index"), data=data)
    assert resp.status_code == 200
    resultats = resp.context["resultats"]
    synthese = resp.context["synthese"]
    assert len(resultats) == 2
    assert synthese.nb_formations == 2
    assert resultats[0].resultat.inputs.heures_par_module == 40
    assert resultats[1].resultat.inputs.heures_par_module == 20


@pytest.mark.django_db
def test_formation_chiffres_json(logged_client, formation, module_referentiel):
    """L'endpoint JSON renvoie les chiffres d'une formation pour l'ajout dynamique."""
    from apps.formations.models import FormationModule

    FormationModule.objects.create(formation=formation, module=module_referentiel, volume_horaire=40)
    url = reverse("simulation:formation_chiffres", kwargs={"formation_id": formation.pk})
    resp = logged_client.get(url)

    assert resp.status_code == 200
    data = resp.json()
    assert data["formation_id"] == formation.pk
    assert data["intitule"] == formation.intitule
    assert data["heures_par_module"] == 40


@pytest.mark.django_db
def test_get_index_sans_bloc_par_defaut(logged_client, parametres):
    """À l'ouverture, aucun bloc : l'utilisateur ajoute via la liste ou la saisie manuelle."""
    resp = logged_client.get(reverse("simulation:index"))

    assert resp.status_code == 200
    assert len(resp.context["formset"].forms) == 0
    assert resp.context["form"] is None


@pytest.mark.django_db
def test_post_sans_formation_affiche_erreur(logged_client):
    """Soumission sans bloc formation → message d'erreur."""
    resp = logged_client.post(
        reverse("simulation:index"),
        data={
            "form-TOTAL_FORMS": "0",
            "form-INITIAL_FORMS": "0",
            "form-MIN_NUM_FORMS": "0",
            "form-MAX_NUM_FORMS": "20",
        },
    )
    assert resp.status_code == 200
    assert resp.context["resultats"] is None
