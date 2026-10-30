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
import os
from pathlib import Path
from unittest import mock, skipUnless

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

    def test_bootstrap_fournit_un_mot_de_passe_saisissable_a_l_admin_demo(self):
        """Le profil d'aperçu doit publier des identifiants réellement utilisables.

        La règle précédente (mot de passe aléatoire de 64 caractères) protégeait
        un secret que personne ne pouvait recopier : une fois la session perdue,
        l'admin était définitivement inaccessible. L'exigence n'est donc pas
        « aléatoire » mais « publié, saisissable et surchargeable » — la
        protection réelle du profil venant de `DEMO_ADMIN_AUTOLOGIN`, qui n'est
        branché que hors production.
        """
        contenu = _lire(BOOTSTRAP)
        self.assertIn('DJANGO_SUPERUSER_USERNAME=admin', contenu)
        self.assertIn('DJANGO_SUPERUSER_EMAIL=admin@arena.invalid', contenu)
        self.assertIn('DJANGO_SUPERUSER_PASSWORD="$SANDBOX_ADMIN_PASSWORD"', contenu)
        self.assertIn('PREVIEW_ADMIN_PASSWORD', contenu)
        # Le compte de démonstration n'est jamais branché en production.
        self.assertNotIn('DJANGO_SUPERUSER', _lire(REPO / 'backend' / 'config' / 'settings.py'))

    def test_hotes_de_l_apercu_toleres_sans_fichier_env(self):
        """L'aperçu doit démarrer sans `backend/.env`.

        `backend/.env` est ignoré par Git : il disparaît à chaque
        réinitialisation du bac à sable. Sans hôte d'aperçu déclaré dans
        l'overlay, Django répond `400 DisallowedHost` sur
        `<port>-<sandbox>.e2b.app` et la vignette reste blanche (panne
        reproduite lors de l'audit). Le profil d'aperçu — jamais chargé en
        production — doit donc tolérer cet hôte par lui-même.
        """
        for profil in (OVERLAY, BOOTSTRAP):
            contenu = _lire(profil)
            with self.subTest(profil=profil.name):
                self.assertIn('PREVIEW_HOST_SUFFIXE = ".e2b.app"', contenu)
                self.assertIn('ALLOWED_HOSTS = [*ALLOWED_HOSTS, PREVIEW_HOST_SUFFIXE]',
                              contenu)
                self.assertIn('https://*.e2b.app', contenu)

    def test_l_overlay_ne_fuit_pas_dans_la_configuration_de_production(self):
        """L'hôte d'aperçu reste confiné au profil d'aperçu.

        Les commentaires de `config/settings.py` peuvent mentionner l'hôte
        d'aperçu (documentation) ; ce qui est interdit, c'est une déclaration
        opérationnelle : constante dédiée, ou hôte ajouté à `ALLOWED_HOSTS`.
        """
        production = _lire(REPO / 'backend' / 'config' / 'settings.py')
        self.assertNotIn('PREVIEW_HOST_SUFFIXE', production)
        for ligne in production.splitlines():
            depouillee = ligne.split('#')[0]
            if 'ALLOWED_HOSTS' in depouillee or 'CSRF_TRUSTED_ORIGINS' in depouillee:
                with self.subTest(ligne=ligne.strip()):
                    self.assertNotIn('e2b', depouillee)

    def test_bootstrap_ecrit_env_par_defaut(self):
        """`bash arena/bootstrap.sh` doit suffire à rendre l'aperçu lançable.

        Le README documente l'appel sans option ; le fichier `.env` n'était
        pourtant écrit qu'avec `--write-env`, d'où un démarrage impossible
        (SECRET_KEY absent) sur un bac à sable neuf.
        """
        contenu = _lire(BOOTSTRAP)
        self.assertIn('if [[ ! -f "$ENV_FILE"', contenu)
        self.assertIn('--write-env', contenu)

    def test_racine_du_port_8000_ouvre_l_admin_pour_un_navigateur(self):
        """Ouvrir l'aperçu de l'API ne doit pas afficher un bloc JSON.

        La racine renvoyait le JSON de l'API : le tableau de bord semblait
        inaccessible. Un navigateur (Accept: text/html) doit être redirigé vers
        `/admin/` ; les clients d'API gardent la réponse JSON.
        """
        for profil in (OVERLAY, BOOTSTRAP):
            with self.subTest(profil=profil.name):
                self.assertIn(
                    'arena.preview_admin_redirect.AdminRedirectApercuMiddleware',
                    _lire(profil),
                )

    def test_redirection_racine_reservee_au_profil_d_apercu(self):
        production = _lire(REPO / 'backend' / 'config' / 'settings.py')
        self.assertNotIn('preview_admin_redirect', production)

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
        """Le bouton « Déconnexion » de l'admin d'aperçu doit ABOUTIR, pas afficher une erreur.

        Régression constatée : dans l'iframe d'aperçu les cookies sont filtrés,
        donc aucun jeton CSRF n'est disponible ; le middleware dispensait les
        routes admin **sauf** `/admin/logout/`. Résultat mesuré : un POST sans
        jeton renvoyait une page **403 « vérification CSRF échouée »** alors que
        la session, elle, était bel et bien détruite — l'utilisateur voyait une
        erreur pour une action réussie.

        Le test fige le contrat réel, sans jamais désactiver le contrôle :

        1. l'admin s'ouvre et authentifie le compte de démonstration (200) ;
        2. un POST de déconnexion **sans jeton** aboutit (302, pas de 403) et
           n'est **pas** suivi d'une reconnexion automatique ;
        3. le CSRF reste actif dans la configuration : l'exemption est portée
           par un middleware réservé au profil d'aperçu (`DEBUG` +
           `PREVIEW_AUTOLOGIN_ENABLED`), absent des réglages de production.
        """
        import sys

        if str(REPO) not in sys.path:
            sys.path.insert(0, str(REPO))
        from django.middleware.csrf import CsrfViewMiddleware

        from arena.preview_autologin import AutoLoginApercuMiddleware

        get_user_model().objects.create_superuser(
            'admin', 'admin@example.com', 'Temp#Pass123',
        )
        AutoLoginApercuMiddleware._deconnecte = False
        self.addCleanup(setattr, AutoLoginApercuMiddleware, '_deconnecte', False)
        client = Client(enforce_csrf_checks=True)

        page_admin = client.get('/admin/', HTTP_HOST='localhost')
        self.assertEqual(
            page_admin.status_code, 200,
            f"Redirection inattendue vers {page_admin.headers.get('Location')!r}.",
        )
        self.assertTrue(page_admin.wsgi_request.user.is_authenticated)
        self.assertEqual(page_admin.wsgi_request.user.username, 'admin')

        # 2) Le geste de l'utilisateur : cliquer « Déconnexion », sans jeton.
        deconnexion = client.post('/admin/logout/', {}, HTTP_HOST='localhost')
        self.assertNotEqual(
            deconnexion.status_code, 403,
            "Le bouton « Déconnexion » de l'aperçu ne doit pas afficher d'erreur CSRF : "
            'les cookies sont filtrés dans l’iframe, aucun jeton n’est disponible.',
        )
        self.assertEqual(deconnexion.status_code, 302)
        self.assertTrue(AutoLoginApercuMiddleware._deconnecte)

        # La reconnexion automatique ne reprend pas la main : la sortie tient.
        retour = client.get('/admin/', HTTP_HOST='localhost')
        self.assertEqual(retour.status_code, 302)
        self.assertIn('/admin/login/', retour.headers.get('Location', ''))
        AutoLoginApercuMiddleware._deconnecte = False

        # 3) Le contrôle n'est ni supprimé ni globalement désactivé.
        self.assertIn(
            'django.middleware.csrf.CsrfViewMiddleware', settings.MIDDLEWARE,
        )
        self.assertIsNotNone(CsrfViewMiddleware)
        production = _lire(REPO / 'backend' / 'config' / 'settings.py')
        self.assertNotIn('preview_autologin', production)



class MiddlewaresCompagnonsFonctionnelsTests(SimpleTestCase):
    """Les middlewares d'aperçu doivent être *appelables* et faire leur travail.

    Régression vécue : `AutoLoginApercuMiddleware` définissait `process_view`
    sans `__call__` → TypeError « object is not callable » et 500 sur toutes
    les pages du profil d'aperçu. Les tests ne vérifiaient que des chaînes.
    """

    CHEMINS = (
        'arena.partitioned_cookies.PartitionedCookieMiddleware',
        'arena.preview_autologin.AutoLoginApercuMiddleware',
    )

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        import sys
        cls._ajout_path = str(REPO) not in sys.path
        if cls._ajout_path:
            sys.path.insert(0, str(REPO))

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, '_ajout_path', False):
            import sys
            sys.path.remove(str(REPO))
        super().tearDownClass()

    def test_middlewares_appelables(self):
        from importlib import import_module

        for chemin in self.CHEMINS:
            with self.subTest(middleware=chemin):
                module, classe = chemin.rsplit('.', 1)
                cls = getattr(import_module(module), classe)
                instance = cls(lambda request: None)
                self.assertTrue(callable(instance))

    def test_cookie_partitionne_pose_partitioned(self):
        from importlib import import_module

        from django.http import HttpResponse

        cls = getattr(
            import_module('arena.partitioned_cookies'),
            'PartitionedCookieMiddleware',
        )

        def vue(request):
            response = HttpResponse('ok')
            response.set_cookie(
                'injs_csrftoken', 'x', secure=True, samesite='None',
            )
            return response

        response = cls(vue)(type('R', (), {})())
        entete = response.cookies['injs_csrftoken'].OutputString()
        self.assertIn('Partitioned', entete)

    def test_cookie_non_eligible_n_est_pas_partitionne(self):
        from importlib import import_module

        from django.http import HttpResponse

        cls = getattr(
            import_module('arena.partitioned_cookies'),
            'PartitionedCookieMiddleware',
        )

        def vue(request):
            response = HttpResponse('ok')
            # SameSite=Lax : « Partitioned » serait rejeté par le navigateur.
            response.set_cookie('injs_sessionid', 'x', samesite='Lax')
            return response

        response = cls(vue)(type('R', (), {})())
        self.assertNotIn('Partitioned', response.cookies['injs_sessionid'].OutputString())


class MiddlewaresApercuBranchesTests(SimpleTestCase):
    """Les middlewares d'aperçu doivent être BRANCHÉS, pas seulement présents.

    Les deux modules existaient dans ``config/`` sans figurer dans
    ``MIDDLEWARE`` : /admin/ répondait alors ``X-Frame-Options: DENY`` (iframe
    blanche) et la connexion échouait en 403 « vérification CSRF échouée »
    dès que le navigateur bloque les cookies tiers.
    """

    SETTINGS = REPO / 'backend' / 'config' / 'settings.py'

    def test_les_deux_middlewares_sont_references_sous_debug(self):
        contenu = _lire(self.SETTINGS)
        self.assertIn('config.dev_middleware.DevPreviewFrameMiddleware', contenu)
        self.assertIn('config.demo_admin_middleware.DemoAdminAutoLoginMiddleware', contenu)
        self.assertIn('if DEBUG:', contenu)

    def test_ordre_impose_par_le_cycle_de_vie_django(self):
        # Le middleware de cadre doit être plus EXTERNE que XFrameOptions
        # (traitement des réponses de l'intérieur vers l'extérieur) et celui
        # d'auto-connexion plus externe que CsrfViewMiddleware (process_view).
        contenu = _lire(self.SETTINGS)
        self.assertIn(
            "MIDDLEWARE.index('django.middleware.clickjacking.XFrameOptionsMiddleware')",
            contenu,
        )
        self.assertIn(
            "MIDDLEWARE.index('django.middleware.csrf.CsrfViewMiddleware')",
            contenu,
        )

    @skipUnless(getattr(settings, 'DEBUG', False), 'Ordre vérifié en mode DEBUG.')
    def test_ordre_effectif_dans_la_configuration_chargee(self):
        from django.conf import settings as conf
        cadre = conf.MIDDLEWARE.index('config.dev_middleware.DevPreviewFrameMiddleware')
        xframe = conf.MIDDLEWARE.index(
            'django.middleware.clickjacking.XFrameOptionsMiddleware',
        )
        demo = conf.MIDDLEWARE.index(
            'config.demo_admin_middleware.DemoAdminAutoLoginMiddleware',
        )
        csrf = conf.MIDDLEWARE.index('django.middleware.csrf.CsrfViewMiddleware')
        self.assertLess(cadre, xframe)
        self.assertLess(demo, csrf)


class AdminSansCookieEnApercuTests(TestCase):
    """L'admin reste utilisable quand le navigateur bloque les cookies tiers.

    Reproduit l'iframe d'aperçu : aucun cookie CSRF, aucun cookie de session.
    Sans le branchement des middlewares d'aperçu, la connexion renvoie 403.
    """

    MIDDLEWARE_DEMO = 'config.demo_admin_middleware.DemoAdminAutoLoginMiddleware'

    @override_settings(DEBUG=True)
    def test_admin_s_ouvre_sans_cookie_et_sans_jeton_csrf(self):
        if self.MIDDLEWARE_DEMO not in settings.MIDDLEWARE:
            self.skipTest(
                "Profil d'aperçu inactif : middlewares non branchés "
                "(DEBUG valait False au chargement de settings.py).",
            )
        # Le compte peut déjà exister : `authentication.apps` en crée un au
        # post_migrate lorsque DJANGO_SUPERUSER_* est défini (profil de démo).
        # Le test vérifie l'auto-connexion, pas la création du compte.
        admin, cree = get_user_model().objects.get_or_create(
            username='admin',
            defaults={'email': 'admin@example.com', 'is_staff': True, 'is_superuser': True},
        )
        if cree:
            admin.set_password('Temp#Pass123')
            admin.save(update_fields=['password'])
        with mock.patch.dict(os.environ, {'DEMO_ADMIN_AUTOLOGIN': '1'}):
            client = Client(enforce_csrf_checks=True)
            page = client.get('/admin/', HTTP_HOST='localhost')
            self.assertEqual(
                page.status_code, 200,
                f"Redirection inattendue vers {page.headers.get('Location')!r}.",
            )
            self.assertTrue(page.wsgi_request.user.is_authenticated)
            self.assertEqual(page.wsgi_request.user.username, 'admin')
            self.assertNotIn('X-Frame-Options', page.headers)
            self.assertIn('frame-ancestors', page.headers.get('Content-Security-Policy', ''))


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


class IdentifiantsDApercuTests(SimpleTestCase):
    """Les identifiants publiés pour l'aperçu doivent être utilisables.

    Défaut constaté : `bootstrap.sh` générait un mot de passe aléatoire de
    64 caractères, stocké uniquement dans `backend/.env`. Ce mot de passe
    n'était ni saisissable ni communiqué ; dès que la session d'aperçu était
    perdue (déconnexion, cookie filtré), plus personne ne pouvait entrer dans
    l'admin. Le profil utilise désormais un identifiant de démonstration
    documenté, surchargeable.
    """

    def test_le_profil_publie_un_identifiant_saisissable(self):
        contenu = _lire(BOOTSTRAP)
        self.assertIn('PREVIEW_ADMIN_PASSWORD', contenu)
        self.assertIn('SANDBOX_ADMIN_PASSWORD="${PREVIEW_ADMIN_PASSWORD:-', contenu)
        # Plus de génération d'un secret impossible à recopier.
        self.assertNotIn('secrets.token_urlsafe', contenu.split('SANDBOX_ADMIN_PASSWORD')[0])

    def test_le_mot_de_passe_est_applique_a_un_compte_existant(self):
        """Sans ce drapeau, régénérer `.env` ne changeait rien en base."""
        contenu = _lire(BOOTSTRAP)
        self.assertIn('DJANGO_SUPERUSER_RESET_PASSWORD=1', contenu)
