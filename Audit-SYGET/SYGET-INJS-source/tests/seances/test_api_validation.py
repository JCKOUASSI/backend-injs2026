"""Tests validation API PATCH séances."""

import datetime
import json

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse


@pytest.fixture
def api_client(db):
    User.objects.create_superuser("apiuser", "api@example.com", "testpass123")
    client = Client()
    client.login(username="apiuser", password="testpass123")
    return client


@pytest.mark.django_db
def test_api_seance_patch_rejette_champ_inconnu(api_client, type_formation):
    from apps.formations.models import Formation
    from apps.groupes.models import Groupe
    from apps.referentiels.models import Module, Specialite
    from apps.seances.models import Seance

    spec = Specialite.objects.create(code="API-UNK", libelle="Unk")
    mod = Module.objects.create(titre="M unk", specialite=spec, actif=True)
    formation = Formation.objects.create(
        type_formation=type_formation,
        intitule="F unk",
        date_debut=datetime.date(2026, 1, 1),
        date_fin=datetime.date(2026, 12, 31),
    )
    groupe = Groupe.objects.create(formation=formation, nom="G", max_auditeurs=20)
    seance = Seance.objects.create(
        groupe=groupe,
        module=mod,
        date=datetime.date(2026, 2, 1),
        heure_debut=datetime.time(8, 0),
        heure_fin=datetime.time(12, 0),
        duree_minutes=240,
    )
    url = reverse("api_seance_detail", kwargs={"pk": seance.pk})
    response = api_client.patch(
        url,
        data=json.dumps({"foo": "bar"}),
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "non autorisé" in json.loads(response.content)["detail"]


@pytest.mark.django_db
def test_api_seance_patch_rejette_jour_ferie(api_client, type_formation):
    from apps.formations.models import Formation
    from apps.groupes.models import Groupe
    from apps.parametrage.models import JourFerie
    from apps.referentiels.models import Module, Specialite
    from apps.seances.models import Seance

    JourFerie.objects.create(date=datetime.date(2026, 5, 1), libelle="Fête", actif=True)
    spec = Specialite.objects.create(code="API-FER", libelle="Férié")
    mod = Module.objects.create(titre="M férié", specialite=spec, actif=True)
    formation = Formation.objects.create(
        type_formation=type_formation,
        intitule="F férié",
        date_debut=datetime.date(2026, 1, 1),
        date_fin=datetime.date(2026, 12, 31),
    )
    groupe = Groupe.objects.create(formation=formation, nom="G", max_auditeurs=20)
    seance = Seance.objects.create(
        groupe=groupe,
        module=mod,
        date=datetime.date(2026, 2, 1),
        heure_debut=datetime.time(8, 0),
        heure_fin=datetime.time(12, 0),
        duree_minutes=240,
    )
    url = reverse("api_seance_detail", kwargs={"pk": seance.pk})
    response = api_client.patch(
        url,
        data=json.dumps({"date": "2026-05-01"}),
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "férié" in json.loads(response.content)["detail"].lower()
