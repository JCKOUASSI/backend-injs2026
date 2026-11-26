"""
Tests de non-régression du RBAC applicatif.
Vérifie que la matrice de permissions définie par `seed_roles` est respectée
sur l'ensemble des apps (formations, auditeurs, groupes, référentiels,
paramétrage) :

- DIRECTION_EDT : lecture seule partout, refus 403 sur toutes les actions
  d'écriture (création, suppression, paramétrage…).
- GESTIONNAIRE_EDT : lecture/écriture sur le métier, refus 403 sur les
  actions d'écriture du paramétrage.
- Utilisateur authentifié hors groupe : refus 403 sur tout.
"""

from __future__ import annotations

from typing import Optional
import pytest
from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.test import Client
from django.urls import reverse


@pytest.fixture
def seed(db):
    """Seed des rôles applicatifs."""
    call_command("seed_roles")


def _login_with_group(group_name: Optional[str]) -> Client:
    """Crée un utilisateur dans le groupe demandé (ou non) et retourne un client connecté."""
    suffix = (group_name or "none").lower().replace("_", "")
    user = User.objects.create_user(f"user_{suffix}", f"{suffix}@test.local", "testpass123")
    if group_name:
        user.groups.add(Group.objects.get(name=group_name))
    client = Client()
    client.login(username=user.username, password="testpass123")
    return client


@pytest.mark.django_db
class TestRBACDirection:
    """DIRECTION_EDT : lecture autorisée, écriture refusée."""

    def test_lecture_listes_metier_ok(self, seed):
        client = _login_with_group("DIRECTION_EDT")
        urls = [
            reverse("formations:list"),
            reverse("auditeurs:list"),
            reverse("formations:formateurs_list"),
            reverse("referentiels:module_list"),
            reverse("parametrage:index"),
            reverse("simulation:index"),
        ]
        for url in urls:
            resp = client.get(url)
            assert resp.status_code == 200, f"Lecture refusée sur {url} : {resp.status_code}"

    def test_ecriture_metier_refusee(self, seed):
        client = _login_with_group("DIRECTION_EDT")
        urls_post = [
            reverse("formations:create"),
            reverse("auditeurs:create"),
            reverse("auditeurs:import"),
            reverse("parametrage:grade_create"),
            reverse("parametrage:site_create"),
            reverse("parametrage:parametres_update"),
            reverse("referentiels:module_create"),
        ]
        for url in urls_post:
            resp = client.post(url, {})
            assert resp.status_code == 403, f"POST {url} aurait dû être refusé (reçu {resp.status_code})"


@pytest.mark.django_db
class TestRBACGestionnaire:
    """GESTIONNAIRE_EDT : écriture métier OK, écriture paramétrage refusée."""

    def test_lecture_metier_ok(self, seed):
        client = _login_with_group("GESTIONNAIRE_EDT")
        urls = [
            reverse("formations:list"),
            reverse("auditeurs:list"),
            reverse("parametrage:index"),
        ]
        for url in urls:
            resp = client.get(url)
            assert resp.status_code == 200

    def test_ecriture_metier_acceptee(self, seed):
        client = _login_with_group("GESTIONNAIRE_EDT")
        resp = client.get(reverse("auditeurs:create"))
        assert resp.status_code == 200, "GET formulaire de création auditeur doit être autorisé"

    def test_ecriture_parametrage_refusee(self, seed):
        client = _login_with_group("GESTIONNAIRE_EDT")
        urls_post = [
            reverse("parametrage:grade_create"),
            reverse("parametrage:site_create"),
            reverse("parametrage:parametres_update"),
            reverse("parametrage:jour_ferie_create"),
        ]
        for url in urls_post:
            resp = client.post(url, {})
            assert resp.status_code == 403, f"POST {url} aurait dû être refusé pour le gestionnaire"


@pytest.mark.django_db
class TestRBACGroupesSeances:
    """Vérifie que les POST sensibles groupes/planning sont protégés."""

    def test_direction_ne_peut_pas_regenerer_groupes(self, seed, formation):
        client = _login_with_group("DIRECTION_EDT")
        url = reverse("groupes:auto_generate", kwargs={"formation_pk": formation.pk})
        resp = client.post(url, {})
        assert resp.status_code == 403

    def test_direction_ne_peut_pas_regenerer_planning(self, seed, formation):
        client = _login_with_group("DIRECTION_EDT")
        url = reverse("groupes:regenerer_planning", kwargs={"formation_pk": formation.pk})
        resp = client.post(url, {})
        assert resp.status_code == 403


@pytest.mark.django_db
class TestRBACUserSansGroupe:
    """Utilisateur authentifié sans groupe applicatif : tout est refusé (403)."""

    def test_lectures_refusees(self, seed):
        client = _login_with_group(None)
        urls = [
            reverse("formations:list"),
            reverse("auditeurs:list"),
            reverse("parametrage:index"),
            reverse("simulation:index"),
        ]
        for url in urls:
            resp = client.get(url)
            assert resp.status_code == 403, f"Utilisateur sans rôle aurait dû recevoir 403 sur {url}"


@pytest.mark.django_db
class TestRBACAnonyme:
    """Utilisateur anonyme : redirection vers la page de login (302)."""

    def test_redirection_login(self, seed):
        client = Client()
        resp = client.get(reverse("formations:list"))
        assert resp.status_code == 302
        assert "/login/" in resp.url
