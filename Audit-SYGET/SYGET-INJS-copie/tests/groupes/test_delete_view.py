"""Tests de suppression d'un groupe."""

import datetime

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from apps.formations.models import Formation
from apps.groupes.models import ConfigGroupe, Groupe, GroupeAuditeur
from apps.referentiels.models import TypeFormation
from apps.seances.models import Seance


@pytest.fixture
def logged_client(db):
    User.objects.create_superuser("deluser", "del@example.com", "testpass123")
    client = Client()
    client.login(username="deluser", password="testpass123")
    return client


@pytest.fixture
def formation_groupe(db):
    type_form, _ = TypeFormation.objects.get_or_create(code="FAC", defaults={"libelle": "FAC"})
    formation = Formation.objects.create(
        type_formation=type_form,
        intitule="Formation delete",
        date_debut=datetime.date(2025, 1, 1),
        date_fin=datetime.date(2025, 6, 30),
    )
    groupe = Groupe.objects.create(formation=formation, nom="Groupe à supprimer", max_auditeurs=25)
    ConfigGroupe.objects.create(groupe=groupe)
    return formation, groupe


@pytest.mark.django_db
class TestGroupeDeleteView:
    def test_suppression_groupe(self, logged_client, formation_groupe, auditeur, module_referentiel):
        formation, groupe = formation_groupe
        GroupeAuditeur.objects.create(groupe=groupe, auditeur=auditeur)
        Seance.objects.create(
            groupe=groupe,
            module=module_referentiel,
            date=datetime.date(2025, 2, 1),
            heure_debut=datetime.time(8, 0),
            heure_fin=datetime.time(12, 0),
            duree_minutes=240,
        )
        url = reverse("groupes:groupe_delete", kwargs={"groupe_pk": groupe.pk})
        resp = logged_client.post(url)
        assert resp.status_code == 302
        assert resp.url == reverse("groupes:list", kwargs={"formation_pk": formation.pk})
        assert not Groupe.objects.filter(pk=groupe.pk).exists()
        assert not GroupeAuditeur.objects.filter(groupe_id=groupe.pk).exists()
        assert not Seance.objects.filter(groupe_id=groupe.pk).exists()

    def test_suppression_conserve_autres_groupes(self, logged_client, formation_groupe):
        formation, groupe = formation_groupe
        autre = Groupe.objects.create(formation=formation, nom="Autre", max_auditeurs=25)
        url = reverse("groupes:groupe_delete", kwargs={"groupe_pk": groupe.pk})
        resp = logged_client.post(url)
        assert resp.status_code == 302
        assert not Groupe.objects.filter(pk=groupe.pk).exists()
        assert Groupe.objects.filter(pk=autre.pk).exists()
