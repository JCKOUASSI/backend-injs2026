"""Tests du middleware d'auto-connexion du profil d'aperçu.

C'est ce middleware (`arena.preview_autologin`), et non celui de `config/`,
qui équipe le serveur du bac à sable (`arena.settings_sandbox`). Régression du
2026-10-28 : le bouton « Déconnexion » de l'admin semblait inopérant, car
chaque requête `/admin/` reconnectait aussitôt le compte de démonstration.

La suspension est un drapeau de PROCESSUS : dans l'iframe d'aperçu, les
cookies peuvent être bloqués et un marqueur de session ne survivrait pas.
"""

import sys
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings

# `arena` vit à la racine du dépôt, hors de BASE_DIR : on l'ajoute au chemin
# pour que ce test puisse importer le middleware réellement utilisé.
RACINE_DEPOT = Path(__file__).resolve().parents[3]
if str(RACINE_DEPOT) not in sys.path:
    sys.path.insert(0, str(RACINE_DEPOT))

from arena.preview_autologin import AutoLoginApercuMiddleware  # noqa: E402


def _middleware_avec_apercu():
    from django.conf import settings
    mw = list(settings.MIDDLEWARE)
    cible = 'arena.preview_autologin.AutoLoginApercuMiddleware'
    if cible not in mw:
        mw.insert(
            mw.index('django.contrib.auth.middleware.AuthenticationMiddleware') + 1,
            cible,
        )
    return mw


@override_settings(
    MIDDLEWARE=_middleware_avec_apercu(),
    DEBUG=True,
    PREVIEW_AUTOLOGIN_ENABLED=True,
    PREVIEW_AUTOLOGIN_USERNAME='admin',
)
class PreviewAutologinLogoutTests(TestCase):
    def setUp(self):
        AutoLoginApercuMiddleware._deconnecte = False
        self.addCleanup(setattr, AutoLoginApercuMiddleware, '_deconnecte', False)
        get_user_model().objects.create_superuser(
            username='admin', email='admin@example.org', password='x',
        )

    def test_premiere_visite_connecte_automatiquement(self):
        self.assertEqual(Client().get('/admin/').status_code, 200)

    def test_deconnexion_n_est_pas_annulee_par_la_reconnexion_automatique(self):
        client = Client()
        self.assertEqual(client.get('/admin/').status_code, 200)
        client.post('/admin/logout/')
        reponse = client.get('/admin/')
        self.assertEqual(reponse.status_code, 302)
        self.assertIn('/admin/login/', reponse.headers.get('Location', ''))

    def test_formulaire_de_connexion_accessible_apres_deconnexion(self):
        client = Client()
        client.get('/admin/')
        client.post('/admin/logout/')
        self.assertEqual(client.get('/admin/login/').status_code, 200)
