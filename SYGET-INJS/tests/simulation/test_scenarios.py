"""Tests persistance scénarios simulation."""

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse


@pytest.fixture
def logged_client(db):
    User.objects.create_superuser("simuser", "sim@example.com", "testpass123")
    client = Client()
    client.login(username="simuser", password="testpass123")
    return client


@pytest.mark.django_db
def test_save_and_load_scenario(logged_client):
    from apps.simulation.models import ScenarioSimulation

    data = {
        "form-TOTAL_FORMS": "1",
        "form-INITIAL_FORMS": "0",
        "form-MIN_NUM_FORMS": "0",
        "form-MAX_NUM_FORMS": "1000",
        "form-0-intitule": "Test scénario",
        "form-0-nb_groupes": "2",
        "form-0-capacite_groupe": "25",
        "form-0-nb_modules": "3",
        "form-0-heures_par_module": "20",
        "form-0-nb_salles": "2",
        "form-0-capacite_salle_moyenne": "25",
        "form-0-tolerance_capacite_pct": "0",
        "form-0-creneaux_par_jour": "2",
        "form-0-duree_creneau_heures": "4",
        "form-0-max_salles_simultanees_module": "1",
        "form-0-jours_semaine": ["0", "1", "2", "3", "4"],
        "scenario_libelle": "Mon scénario test",
        "action": "save_scenario",
    }
    resp = logged_client.post(reverse("simulation:scenario_save"), data=data)
    assert resp.status_code == 302
    scenario = ScenarioSimulation.objects.get(libelle="Mon scénario test")
    assert len(scenario.payload) == 1
    assert scenario.payload[0]["nb_groupes"] == 2

    resp = logged_client.get(reverse("simulation:index") + f"?scenario={scenario.pk}")
    assert resp.status_code == 200
    assert "Mon scénario test".encode() in resp.content or b"charg" in resp.content.lower()
