"""Tests du middleware de démonstration (reconnexion automatique de l'admin).

Régression constatée le 2026-10-28 : le bouton « Déconnexion » de l'admin
semblait inopérant. La session était pourtant bien détruite, mais le
middleware de démonstration reconnectait aussitôt le superutilisateur sur la
requête suivante (/admin/ répondait 200 au lieu de rediriger vers la
connexion). Une déconnexion explicite doit désormais être respectée.
"""

import os

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings

from config.demo_admin_middleware import DemoAdminAutoLoginMiddleware

def _middleware_avec_autologin():
    from django.conf import settings
    mw = list(settings.MIDDLEWARE)
    cible = 'config.demo_admin_middleware.DemoAdminAutoLoginMiddleware'
    if cible not in mw:
        index = mw.index('django.middleware.csrf.CsrfViewMiddleware')
        mw.insert(index, cible)
    return mw


# DEBUG=True : le middleware de démonstration ne s'active QUE dans ce mode
# (double garde-fou). En production il est totalement inerte, ce que
# `test_middleware_inerte_hors_debug` vérifie explicitement.
@override_settings(MIDDLEWARE=_middleware_avec_autologin(), DEBUG=True)
class DemoAdminLogoutTests(TestCase):
    def setUp(self):
        self._env = os.environ.get('DEMO_ADMIN_AUTOLOGIN')
        os.environ['DEMO_ADMIN_AUTOLOGIN'] = '1'
        self.addCleanup(self._restaurer_env)
        self.user = get_user_model().objects.create_superuser(
            username='demo_admin_test', email='demo@example.org', password='x',
        )

    def _restaurer_env(self):
        if self._env is None:
            os.environ.pop('DEMO_ADMIN_AUTOLOGIN', None)
        else:
            os.environ['DEMO_ADMIN_AUTOLOGIN'] = self._env
        # Le drapeau de suspension est un état de processus : on le remet à
        # zéro pour que les tests soient indépendants les uns des autres.
        DemoAdminAutoLoginMiddleware._suspendu = False

    def test_premiere_visite_connecte_automatiquement(self):
        """La démo reste utilisable : sans session, /admin/ s'ouvre."""
        self.assertEqual(Client().get('/admin/').status_code, 200)

    def test_deconnexion_est_respectee(self):
        """Après déconnexion, /admin/ doit rediriger vers la connexion."""
        client = Client()
        self.assertEqual(client.get('/admin/').status_code, 200)
        client.post('/admin/logout/')
        reponse = client.get('/admin/')
        self.assertEqual(reponse.status_code, 302)
        self.assertIn('/admin/login/', reponse.headers.get('Location', ''))

    def test_page_de_connexion_accessible_apres_deconnexion(self):
        """Le formulaire doit s'afficher au lieu de renvoyer au tableau de bord."""
        client = Client()
        client.get('/admin/')
        client.post('/admin/logout/')
        self.assertEqual(client.get('/admin/login/').status_code, 200)


    def test_deconnexion_suspend_la_reconnexion_meme_sans_cookie(self):
        """Sans aucun cookie conservé, la déconnexion doit rester effective.

        C'est le cas réel de l'iframe d'aperçu : les cookies peuvent être
        bloqués, donc le marqueur de session ne survit pas. La suspension au
        niveau du processus garantit que « Déconnexion » reste effective.
        """
        DemoAdminAutoLoginMiddleware._suspendu = True  # simule la déconnexion
        reponse = Client().get('/admin/')             # client neuf, sans cookie
        self.assertEqual(reponse.status_code, 302)
        self.assertIn('/admin/login/', reponse.headers.get('Location', ''))


@override_settings(MIDDLEWARE=_middleware_avec_autologin(), DEBUG=False)
class DemoAdminInerteHorsDebugTests(TestCase):
    """Garde-fou : sans DEBUG, la reconnexion automatique ne doit pas exister."""

    def setUp(self):
        self._env = os.environ.get('DEMO_ADMIN_AUTOLOGIN')
        os.environ['DEMO_ADMIN_AUTOLOGIN'] = '1'
        self.addCleanup(self._restaurer_env)

    def _restaurer_env(self):
        if self._env is None:
            os.environ.pop('DEMO_ADMIN_AUTOLOGIN', None)
        else:
            os.environ['DEMO_ADMIN_AUTOLOGIN'] = self._env
        DemoAdminAutoLoginMiddleware._suspendu = False

    def test_aucune_reconnexion_automatique_hors_debug(self):
        reponse = Client().get('/admin/')
        self.assertEqual(reponse.status_code, 302)
        self.assertIn('/admin/login/', reponse.headers.get('Location', ''))
