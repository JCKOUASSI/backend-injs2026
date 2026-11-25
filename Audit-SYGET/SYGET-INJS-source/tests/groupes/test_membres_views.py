"""Tests de la gestion manuelle des membres de groupe."""

import datetime

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from apps.formations.models import Formation, FormationModule, Inscription
from apps.groupes.models import Groupe, GroupeAuditeur
from apps.referentiels.models import TypeFormation


@pytest.fixture
def logged_client(db):
    User.objects.create_superuser("memuser", "mem@example.com", "testpass123")
    client = Client()
    client.login(username="memuser", password="testpass123")
    return client


@pytest.fixture
def formation_groupe(db, module_referentiel):
    type_form, _ = TypeFormation.objects.get_or_create(code="FAC", defaults={"libelle": "FAC"})
    formation = Formation.objects.create(
        type_formation=type_form,
        intitule="Formation membres",
        date_debut=datetime.date(2025, 1, 1),
        date_fin=datetime.date(2025, 6, 30),
    )
    fm = FormationModule.objects.create(
        formation=formation,
        module=module_referentiel,
        volume_horaire=12,
        site_nom=f"SITE-{formation.pk}",
    )
    groupe = Groupe.objects.create(formation=formation, nom="Groupe test", max_auditeurs=25)
    return formation, fm, groupe


@pytest.mark.django_db
class TestMembresManuels:
    def test_page_gestion_membres_accessible(self, logged_client, formation_groupe, auditeur):
        formation, fm, groupe = formation_groupe
        Inscription.objects.create(formation=formation, formation_module=fm, auditeur=auditeur)
        url = reverse("groupes:membre_add", kwargs={"groupe_pk": groupe.pk})
        resp = logged_client.get(url)
        assert resp.status_code == 200
        html = resp.content.decode()
        assert "Gestion des membres" in html
        assert "Affecter la sélection" in html
        assert auditeur.nom in html

    def test_affectation_manuelle(self, logged_client, formation_groupe, auditeur):
        formation, fm, groupe = formation_groupe
        Inscription.objects.create(formation=formation, formation_module=fm, auditeur=auditeur)
        url = reverse("groupes:membre_add", kwargs={"groupe_pk": groupe.pk})
        resp = logged_client.post(
            url,
            {"auditeur_ids": [auditeur.pk], "from_page": "membres"},
        )
        assert resp.status_code == 302
        assert GroupeAuditeur.objects.filter(groupe=groupe, auditeur=auditeur).exists()

    def test_auditeur_deja_dans_autre_groupe_propose_pour_deplacement(
        self, logged_client, formation_groupe, auditeur, auditeur2
    ):
        formation, fm, groupe = formation_groupe
        g2 = Groupe.objects.create(formation=formation, nom="Autre groupe", max_auditeurs=25)
        for aud in (auditeur, auditeur2):
            Inscription.objects.create(formation=formation, formation_module=fm, auditeur=aud)
        GroupeAuditeur.objects.create(groupe=g2, auditeur=auditeur)

        url = reverse("groupes:membre_add", kwargs={"groupe_pk": groupe.pk})
        resp = logged_client.get(url)
        html = resp.content.decode()
        assert f'value="{auditeur2.pk}"' in html
        assert f'value="{auditeur.pk}"' in html
        assert "Autre groupe" in html

    def test_deplacement_depuis_autre_groupe(self, logged_client, formation_groupe, auditeur):
        formation, fm, groupe = formation_groupe
        g2 = Groupe.objects.create(formation=formation, nom="Autre groupe", max_auditeurs=25)
        Inscription.objects.create(formation=formation, formation_module=fm, auditeur=auditeur)
        GroupeAuditeur.objects.create(groupe=g2, auditeur=auditeur)

        url = reverse("groupes:membre_add", kwargs={"groupe_pk": groupe.pk})
        resp = logged_client.post(
            url,
            {"auditeur_ids": [auditeur.pk], "from_page": "membres"},
        )
        assert resp.status_code == 302
        assert GroupeAuditeur.objects.filter(groupe=groupe, auditeur=auditeur).exists()
        assert not GroupeAuditeur.objects.filter(groupe=g2, auditeur=auditeur).exists()

    def test_retrait_manuel(self, logged_client, formation_groupe, auditeur):
        formation, fm, groupe = formation_groupe
        Inscription.objects.create(formation=formation, formation_module=fm, auditeur=auditeur)
        GroupeAuditeur.objects.create(groupe=groupe, auditeur=auditeur)
        url = reverse("groupes:membre_delete", kwargs={"groupe_pk": groupe.pk, "auditeur_pk": auditeur.pk})
        resp = logged_client.post(url, {"redirect_to": "membres"})
        assert resp.status_code == 302
        assert not GroupeAuditeur.objects.filter(groupe=groupe, auditeur=auditeur).exists()
