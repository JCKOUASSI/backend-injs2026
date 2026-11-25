"""Tests API JSON read-only."""

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
def test_api_formations_list(api_client, type_formation):
    from apps.formations.models import Formation

    Formation.objects.create(
        type_formation=type_formation,
        intitule="Formation API",
        date_debut=datetime.date(2026, 1, 1),
        date_fin=datetime.date(2026, 12, 31),
    )
    url = reverse("api_formations_list")
    response = api_client.get(url)
    assert response.status_code == 200
    data = json.loads(response.content)
    assert any(f["intitule"] == "Formation API" for f in data["formations"])


@pytest.mark.django_db
def test_api_formation_seances(api_client, type_formation):
    from apps.formations.models import Formation
    from apps.groupes.models import Groupe
    from apps.referentiels.models import Module, Specialite
    from apps.seances.models import Seance

    spec = Specialite.objects.create(code="API-X", libelle="API X")
    mod = Module.objects.create(titre="M API", specialite=spec, actif=True)
    formation = Formation.objects.create(
        type_formation=type_formation,
        intitule="F API",
        date_debut=datetime.date(2026, 1, 1),
        date_fin=datetime.date(2026, 12, 31),
    )
    groupe = Groupe.objects.create(formation=formation, nom="G", max_auditeurs=20)
    Seance.objects.create(
        groupe=groupe,
        module=mod,
        date=datetime.date(2026, 2, 1),
        heure_debut=datetime.time(8, 0),
        heure_fin=datetime.time(12, 0),
        duree_minutes=240,
        salle_nom="S1",
    )
    url = reverse("api_formation_seances", kwargs={"pk": formation.pk})
    response = api_client.get(url)
    assert response.status_code == 200
    data = json.loads(response.content)
    assert data["formation_id"] == formation.pk
    assert len(data["seances"]) == 1
    assert data["seances"][0]["module_titre"] == "M API"


@pytest.mark.django_db
def test_api_seance_patch(api_client, type_formation, admin_user):
    from apps.formations.models import Formation
    from apps.groupes.models import Groupe
    from apps.referentiels.models import Module, Specialite
    from apps.seances.models import Seance

    spec = Specialite.objects.create(code="PATCH", libelle="Patch")
    mod = Module.objects.create(titre="M patch", specialite=spec, actif=True)
    formation = Formation.objects.create(
        type_formation=type_formation,
        intitule="F patch",
        date_debut=datetime.date(2026, 1, 1),
        date_fin=datetime.date(2026, 12, 31),
        responsable=admin_user,
    )
    groupe = Groupe.objects.create(formation=formation, nom="G", max_auditeurs=20)
    seance = Seance.objects.create(
        groupe=groupe,
        module=mod,
        date=datetime.date(2026, 2, 1),
        heure_debut=datetime.time(8, 0),
        heure_fin=datetime.time(12, 0),
        duree_minutes=240,
        salle_nom="S1",
    )
    url = reverse("api_seance_detail", kwargs={"pk": seance.pk})
    response = api_client.patch(
        url,
        data=json.dumps({"site_nom": "Site PATCH", "heure_fin": "13:00"}),
        content_type="application/json",
    )
    assert response.status_code == 200
    data = json.loads(response.content)
    assert data["site_nom"] == "Site PATCH"
    assert data["heure_fin"] == "13:00"
    seance.refresh_from_db()
    assert seance.site_nom == "Site PATCH"
