"""
Tests des vues (HTTP) — auditeurs.
"""

import pytest
from django.test import Client
from django.urls import reverse


@pytest.fixture
def logged_client(db):
    """Client Django authentifié avec un super-utilisateur."""
    from django.contrib.auth.models import User

    User.objects.create_superuser("testuser2", "t2@example.com", "testpass123")
    client = Client()
    client.login(username="testuser2", password="testpass123")
    return client


@pytest.mark.django_db
class TestAuditeursViews:
    """Tests d'intégration pour les vues auditeurs."""

    def test_liste_accessible(self, logged_client):
        """La liste des auditeurs est accessible."""
        resp = logged_client.get(reverse("auditeurs:list"))
        assert resp.status_code == 200

    def test_recherche_filtre_resultats(self, logged_client, auditeur):
        """La recherche filtre correctement les auditeurs."""
        resp = logged_client.get(reverse("auditeurs:list") + "?q=MARTIN")
        assert resp.status_code == 200
        assert b"MARTIN" in resp.content

    def test_recherche_sans_resultat(self, logged_client, auditeur):
        """Une recherche sans résultat n'affiche rien."""
        resp = logged_client.get(reverse("auditeurs:list") + "?q=XXXXXX")
        assert resp.status_code == 200
        assert b"MARTIN" not in resp.content

    def test_detail_auditeur(self, logged_client, auditeur):
        """La page détail d'un auditeur est accessible."""
        resp = logged_client.get(reverse("auditeurs:detail", kwargs={"pk": auditeur.pk}))
        assert resp.status_code == 200
        assert auditeur.nom.encode() in resp.content

    def test_detail_auditeur_inexistant(self, logged_client):
        """Un auditeur inexistant retourne 404."""
        resp = logged_client.get(reverse("auditeurs:detail", kwargs={"pk": 99999}))
        assert resp.status_code == 404
