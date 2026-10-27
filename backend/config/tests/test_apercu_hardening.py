"""Garde-fous de l'aperçu Arena (iframe cross-site) et des ports figés.

Le durcissement cookies/CSRF indispensable à l'admin Django servie en iframe
https a été perdu plusieurs fois lors de réinitialisations du sandbox, ce qui
reproduisait le « 403 — vérification CSRF échouée ». Ce test fige les
exigences à deux endroits :

* ``arena/settings_sandbox.py`` — overlay effectif versionné ;
* ``arena/bootstrap.sh`` — son générateur, exécuté après chaque reset.

Il fige aussi les ports canoniques (front 3000 avec ``strictPort``, API 8000)
pour empêcher tout retour accidentel vers un autre port (ex. 5173).
"""
from pathlib import Path
from unittest import skipUnless

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, SimpleTestCase, TestCase, override_settings

REPO = settings.BASE_DIR.parent
OVERLAY = REPO / 'arena' / 'settings_sandbox.py'
BOOTSTRAP = REPO / 'arena' / 'bootstrap.sh'
VITE_CONFIG = REPO / 'frontend' / 'vite.config.js'


def _lire(chemin):
    return chemin.read_text(encoding='utf-8')


class OverlayCsrfHardeningTests(SimpleTestCase):
    """L'overlay ET son générateur doivent contenir le durcissement complet."""

    EXIGENCES = (
        'CSRF_COOKIE_NAME = "injs_csrftoken"',
        'SESSION_COOKIE_NAME = "injs_sessionid"',
        'SESSION_COOKIE_SAMESITE = "None"',
        'CSRF_COOKIE_SAMESITE = "None"',
        'SESSION_COOKIE_SECURE = True',
        'CSRF_COOKIE_SECURE = True',
        'SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")',
        # CHIPS : l'attribut Partitioned est posé par un middleware compagnon
        # car Django 5.1 ne connaît pas SESSION_COOKIE_PARTITIONED (5.2).
        'arena.partitioned_cookies.PartitionedCookieMiddleware',
        # La passerelle Arena filtre les cookies : l'admin en vignette est
        # auto-connectée au compte démo par un middleware d'aperçu uniquement.
        'arena.preview_autologin.AutoLoginApercuMiddleware',
        'PREVIEW_AUTOLOGIN_USERNAME = "admin"',
    )

    def test_overlay_effectif_durci(self):
        contenu = _lire(OVERLAY)
        for exigence in self.EXIGENCES:
            with self.subTest(exigence=exigence):
                self.assertIn(exigence, contenu)

    def test_generateur_bootstrap_durci(self):
        # Le bootstrap régénère l'overlay après chaque réinitialisation : il doit
        # contenir le même durcissement, sinon le correctif disparaît au reset.
        contenu = _lire(BOOTSTRAP)
        for exigence in self.EXIGENCES:
            with self.subTest(exigence=exigence):
                self.assertIn(exigence, contenu)

    def test_middlewares_compagnons_versionnes_et_overlay_seul(self):
        # Les middlewares d'aperçu (cookies partitionnés, auto-connexion démo)
        # doivent exister dans le dépôt (recopiés par bootstrap) et n'être
        # référencés NI par la configuration de production NI par un réglage
        # autre que l'overlay d'aperçu.
        for module in ('partitioned_cookies.py', 'preview_autologin.py'):
            with self.subTest(module=module):
                self.assertTrue((REPO / 'arena' / module).is_file())
        production = _lire(REPO / 'backend' / 'config' / 'settings.py')
        self.assertNotIn('preview_autologin', production)
        self.assertNotIn('PREVIEW_AUTOLOGIN_USERNAME', production)

    def test_auto_login_suit_le_middleware_d_authentification(self):
        # AutoLogin lit request.user : il doit s'exécuter après que Django l'a
        # installé, dans le profil actif comme dans son générateur bootstrap.
        insertion = (
            'MIDDLEWARE.index("django.contrib.auth.middleware.AuthenticationMiddleware") + 1'
        )
        for profil in (OVERLAY, BOOTSTRAP):
            with self.subTest(profil=profil.name):
                self.assertIn(insertion, _lire(profil))

    def test_bootstrap_fournit_un_mot_de_passe_aleatoire_a_l_admin_demo(self):
        contenu = _lire(BOOTSTRAP)
        self.assertIn('DJANGO_SUPERUSER_USERNAME=admin', contenu)
        self.assertIn('DJANGO_SUPERUSER_EMAIL=admin@arena.invalid', contenu)
        self.assertIn('DJANGO_SUPERUSER_PASSWORD="$SANDBOX_ADMIN_PASSWORD"', contenu)
        self.assertIn('secrets.token_urlsafe(48)', contenu)

    def test_noms_de_cookies_dedies(self):
        # Un nom dédié neutralise définitivement tout vieux cookie csrftoken /
        # sessionid hérité du navigateur (cause du « incorrect length »).
        contenu = _lire(OVERLAY)
        self.assertIn('injs_csrftoken', contenu)
        self.assertNotIn('CSRF_COOKIE_NAME = "csrftoken"', contenu)


@skipUnless(
    getattr(settings, 'PREVIEW_AUTOLOGIN_ENABLED', False),
    'Test intégré actif uniquement avec le profil de preview Arena.',
)
class PreviewAutoLoginTests(TestCase):
    """Le compte de démonstration est utilisable dans l'admin embarqué."""

    @override_settings(DEBUG=True)
    def test_admin_est_connecte_et_post_ne_bloque_pas_sur_csrf(self):
        get_user_model().objects.create_superuser(
            'admin', 'admin@example.com', 'Temp#Pass123',
        )
        client = Client(enforce_csrf_checks=True)

        page_admin = client.get('/admin/', HTTP_HOST='localhost')
        self.assertEqual(
            page_admin.status_code, 200,
            f"Redirection inattendue vers {page_admin.headers.get('Location')!r}.",
        )
        self.assertTrue(page_admin.wsgi_request.user.is_authenticated)
        self.assertEqual(page_admin.wsgi_request.user.username, 'admin')

        deconnexion = client.post('/admin/logout/', {}, HTTP_HOST='localhost')
        self.assertNotEqual(deconnexion.status_code, 403)


class PortsCanoniquesTests(SimpleTestCase):
    def test_vite_fige_le_port_3000_avec_strictport(self):
        contenu = _lire(VITE_CONFIG)
        self.assertIn('port: 3000', contenu)
        self.assertIn('strictPort: true', contenu)
        # Plus jamais de port de contournement codé en dur.
        self.assertNotIn('5173', contenu)

    def test_vite_force_https_derriere_proxy_e2b(self):
        # Le proxy de l'aperçu Arena relaie parfois X-Forwarded-Proto: http alors
        # que la navigation est en HTTPS : Django émet alors des cookies Secure
        # que le navigateur refuse en iframe (« CSRF cookie not set »). Le proxy
        # Vite doit forcer https dès que l'hôte public est un hôte *.e2b.app.
        contenu = _lire(VITE_CONFIG)
        self.assertIn('.e2b.app', contenu)
        self.assertIn("'https'", contenu)
        # Le proto ne doit plus dépendre aveuglément du seul en-tête reçu :
        self.assertNotIn("const proto = protoRecu || 'http'", contenu)

    def test_lanceurs_avec_ports_figes(self):
        api = _lire(REPO / 'arena' / 'lancer-api.sh')
        front = _lire(REPO / 'arena' / 'lancer-front.sh')
        self.assertIn('PORT=8000', api)
        self.assertIn('runserver 0.0.0.0:$PORT', api)
        self.assertIn('PORT=3000', front)
