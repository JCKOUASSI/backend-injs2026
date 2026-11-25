"""Tests du flux de connexion, du tableau de bord (/accueil/) et du middleware d'aperçu iframe."""

from __future__ import annotations

import re

import pytest
from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.test import Client, override_settings
from django.urls import reverse

from config.settings import MIDDLEWARE as BASE_MIDDLEWARE


@pytest.mark.django_db
class TestLoginAndDashboard:
    """Vérifie la connexion et l'accès au dashboard (/accueil/) selon les rôles."""

    def test_root_redirige_vers_login_si_anonyme(self, client: Client):
        resp = client.get(reverse("root"))
        assert resp.status_code == 302
        assert resp["Location"] == reverse("login")

    def test_login_vers_dashboard_superuser(self, client: Client):
        User.objects.create_superuser("admin_test", "admin@test.ci", "pass1234")
        resp = client.post(reverse("login"), {"username": "admin_test", "password": "pass1234"})
        assert resp.status_code == 302
        assert resp["Location"] == reverse("home")

        dash = client.get(reverse("home"))
        assert dash.status_code == 200
        content = dash.content.decode("utf-8")
        assert "Bonjour, admin_test" in content

    def test_dashboard_masque_boutons_ecriture_pour_direction(self, client: Client):
        call_command("seed_roles")
        user = User.objects.create_user("dir_user", "dir@test.ci", "pass1234")
        user.groups.add(Group.objects.get(name="DIRECTION_EDT"))
        client.force_login(user)

        dash = client.get(reverse("home"))
        assert dash.status_code == 200
        content = dash.content.decode("utf-8")
        assert "Bonjour, dir_user" in content
        assert reverse("formations:create") not in content


@pytest.mark.django_db
class TestIframePreviewMiddleware:
    """Vérifie la connexion et l'ouverture du dashboard en iframe sans cookies tiers."""

    def test_cookieless_login_et_ouverture_dashboard(self):
        with override_settings(
            MIDDLEWARE=["config.preview_middleware.PartitionedIframeCookiesMiddleware", *BASE_MIDDLEWARE],
            SESSION_COOKIE_SAMESITE="None",
            SESSION_COOKIE_SECURE=True,
            CSRF_COOKIE_SAMESITE="None",
            CSRF_COOKIE_SECURE=True,
        ):
            User.objects.create_superuser("iframe_admin", "iframe@test.ci", "secret123")
            client = Client(enforce_csrf_checks=True)

            # 1. Chargement initial de /login/
            login_get = client.get(reverse("login"))
            assert login_get.status_code == 200
            html = login_get.content.decode("utf-8")
            csrf_token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', html).group(1)
            pcsrf_token = re.search(r'name="_pcsrf" value="([^"]+)"', html).group(1)
            assert login_get.cookies["csrftoken"]["partitioned"] is True

            # Simule un navigateur en iframe qui bloque tous les cookies tiers
            client.cookies.clear()

            # 2. Soumission POST /login/ sans aucun cookie (via _pcsrf)
            login_post = client.post(
                reverse("login"),
                {
                    "username": "iframe_admin",
                    "password": "secret123",
                    "csrfmiddlewaretoken": csrf_token,
                    "_pcsrf": pcsrf_token,
                },
            )
            assert login_post.status_code == 302
            location = login_post["Location"]
            assert location.startswith("/accueil/?_pauth=")

            # 3. Ouverture du dashboard sans aucun cookie (via _pauth dans l'URL)
            client.cookies.clear()
            dash_resp = client.get(location)
            assert dash_resp.status_code == 200
            assert "Bonjour, iframe_admin" in dash_resp.content.decode("utf-8")
