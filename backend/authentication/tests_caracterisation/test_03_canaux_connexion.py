"""U0-CURP — caractérisation des CANAUX DE CONNEXION (web vs application mobile).

Comportement actuel de ``POST /api/auth/login/`` (``authentication/views.py``) :
* les 10 rôles web se connectent SANS ``device_id`` ;
* FORMATEUR et AUDITEUR sont refusés sur le web (HTTP 403, message
  « réservé à l'application mobile ») et acceptés avec ``device_id`` ;
* un appareil est verrouillé sur le premier compte mobile qui l'utilise
  (``presences.DeviceBinding``), tout autre compte reçoit 403 DEVICE_LOCKED ;
* le jeton de rafraîchissement est déposé dans un cookie HttpOnly dont le
  chemin est restreint à ``/api/auth/`` (et reste aussi dans le corps pour la
  rétrocompatibilité de l'application mobile) ;
* l'endpoint est limité à 20 tentatives par minute et par IP (réglage
  ``login`` du limiteur DRF).
"""
from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework import status
from rest_framework.test import APITestCase

from authentication.role_groups import ALLOWED_WEB_ROLES, MOBILE_ONLY_ROLES, ensure_role_groups

User = get_user_model()

MOT_DE_PASSE = 'Canal#2026x'
URL_CONNEXION = '/api/auth/login/'


def _creer(username, role, **champs):
    return User.objects.create_user(
        username=username, password=MOT_DE_PASSE, role=role, **champs
    )


class _IsolationLimiteurTestCase(APITestCase):
    """Isole chaque test du limiteur de connexion (cache partagé du process).

    Le compteur 20/min par IP vit dans le cache global ; sans purge, les
    tests de connexion héritent des tentatives d'autres applications et,
    inversement, le test de rafale polluerait les tests suivants.
    """

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()


class ConnexionWebParRoleTests(_IsolationLimiteurTestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_role_groups()


def _test_login_web(role):
    def test(self):
        _creer(f'car-web-{role.lower()}', role)
        reponse = self.client.post(
            URL_CONNEXION,
            {'username': f'car-web-{role.lower()}', 'password': MOT_DE_PASSE},
            format='json',
        )
        self.assertEqual(reponse.status_code, status.HTTP_200_OK)
        self.assertIn('access', reponse.json())
        self.assertEqual(reponse.json().get('user', {}).get('role'), role)
    test.__doc__ = f"Le rôle {role} est autorisé sur le canal web sans appareil."
    return test


for _role in sorted(ALLOWED_WEB_ROLES):
    setattr(
        ConnexionWebParRoleTests,
        f'test_login_web_autorise_pour_{_role.lower()}',
        _test_login_web(_role),
    )


class ConnexionMobileTests(_IsolationLimiteurTestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_role_groups()

    def test_login_web_refuse_pour_formateur(self):
        _creer('car-form-web', 'FORMATEUR')
        reponse = self.client.post(
            URL_CONNEXION,
            {'username': 'car-form-web', 'password': MOT_DE_PASSE},
            format='json',
        )
        self.assertEqual(reponse.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('mobile', reponse.json()['detail'].lower())

    def test_login_web_refuse_pour_auditeur(self):
        _creer('car-aud-web', 'AUDITEUR')
        reponse = self.client.post(
            URL_CONNEXION,
            {'username': 'car-aud-web', 'password': MOT_DE_PASSE},
            format='json',
        )
        self.assertEqual(reponse.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('mobile', reponse.json()['detail'].lower())

    def test_login_mobile_autorise_pour_formateur(self):
        _creer('car-form-mobile', 'FORMATEUR')
        reponse = self.client.post(
            URL_CONNEXION,
            {'username': 'car-form-mobile', 'password': MOT_DE_PASSE,
             'device_id': 'appareil-form-001'},
            format='json',
        )
        self.assertEqual(reponse.status_code, status.HTTP_200_OK, reponse.content)
        self.assertIn('access', reponse.json())

    def test_login_mobile_autorise_pour_auditeur(self):
        _creer('car-aud-mobile', 'AUDITEUR')
        reponse = self.client.post(
            URL_CONNEXION,
            {'username': 'car-aud-mobile', 'password': MOT_DE_PASSE,
             'device_id': 'appareil-aud-001'},
            format='json',
        )
        self.assertEqual(reponse.status_code, status.HTTP_200_OK, reponse.content)
        self.assertIn('access', reponse.json())

    def test_appareil_deja_lie_refuse_pour_un_autre_compte(self):
        _creer('car-form-lock', 'FORMATEUR')
        _creer('car-aud-lock', 'AUDITEUR')
        premier = self.client.post(
            URL_CONNEXION,
            {'username': 'car-form-lock', 'password': MOT_DE_PASSE,
             'device_id': 'appareil-partage'},
            format='json',
        )
        self.assertEqual(premier.status_code, 200)
        second = self.client.post(
            URL_CONNEXION,
            {'username': 'car-aud-lock', 'password': MOT_DE_PASSE,
             'device_id': 'appareil-partage'},
            format='json',
        )
        self.assertEqual(second.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(second.json().get('code'), 'DEVICE_LOCKED')

    def test_reutilisation_du_meme_appareil_par_son_titulaire_autorisee(self):
        _creer('car-form-rebind', 'FORMATEUR')
        for _ in range(2):
            reponse = self.client.post(
                URL_CONNEXION,
                {'username': 'car-form-rebind', 'password': MOT_DE_PASSE,
                 'device_id': 'appareil-fidele'},
                format='json',
            )
            self.assertEqual(reponse.status_code, 200)

    def test_role_web_avec_device_ne_cree_pas_de_verrou_appareil(self):
        from presences.models import DeviceBinding
        _creer('car-sec-device', 'SECRETARIAT')
        reponse = self.client.post(
            URL_CONNEXION,
            {'username': 'car-sec-device', 'password': MOT_DE_PASSE,
             'device_id': 'navigateur-web'},
            format='json',
        )
        self.assertEqual(reponse.status_code, 200)
        self.assertFalse(DeviceBinding.objects.filter(device_id='navigateur-web').exists())


class DurecissementConnexionTests(_IsolationLimiteurTestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_role_groups()
        _creer('car-dure', 'SECRETARIAT')

    def setUp(self):
        super().setUp()  # purge du limiteur (voir _IsolationLimiteurTestCase)

    def test_mauvais_mot_de_passe_refuse_en_401(self):
        reponse = self.client.post(
            URL_CONNEXION,
            {'username': 'car-dure', 'password': 'mot-de-passe-faux'},
            format='json',
        )
        self.assertEqual(reponse.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_compte_inactif_refuse_a_la_connexion(self):
        utilisateur = User.objects.get(username='car-dure')
        utilisateur.is_active = False
        utilisateur.save(update_fields=['is_active'])
        reponse = self.client.post(
            URL_CONNEXION,
            {'username': 'car-dure', 'password': MOT_DE_PASSE},
            format='json',
        )
        # Le backend Django renvoie None pour un compte inactif : l'API
        # répond par le même message que des identifiants invalides (401).
        self.assertEqual(reponse.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_champ_mot_de_passe_obligatoire_refuse_en_400(self):
        reponse = self.client.post(
            URL_CONNEXION, {'username': 'car-dure'}, format='json',
        )
        self.assertEqual(reponse.status_code, status.HTTP_400_BAD_REQUEST)

    def test_drapeau_changement_mot_de_passe_expose_a_la_connexion(self):
        _creer('car-must-change', 'SECRETARIAT', must_change_password=True)
        reponse = self.client.post(
            URL_CONNEXION,
            {'username': 'car-must-change', 'password': MOT_DE_PASSE},
            format='json',
        )
        self.assertEqual(reponse.status_code, 200)
        self.assertTrue(reponse.json()['must_change_password'])

    def test_drapeau_changement_mot_de_passe_faux_par_defaut(self):
        reponse = self.client.post(
            URL_CONNEXION,
            {'username': 'car-dure', 'password': MOT_DE_PASSE},
            format='json',
        )
        self.assertEqual(reponse.status_code, 200)
        self.assertFalse(reponse.json()['must_change_password'])

    def test_limiteur_bloque_au_dela_de_20_tentatives_par_minute(self):
        codes = []
        for _ in range(22):
            reponse = self.client.post(
                URL_CONNEXION,
                {'username': 'car-dure', 'password': 'force-brute'},
                format='json',
            )
            codes.append(reponse.status_code)
        self.assertEqual(codes[:20].count(429), 0)
        self.assertEqual(codes[20], status.HTTP_429_TOO_MANY_REQUESTS)

    def test_limiteur_ne_sapplique_pas_au_refresh_ni_aux_autres_routes(self):
        # Le limiteur de connexion est spécifique à la vue login : une
        # rafale sur une autre route ne doit pas produire de 429.
        for _ in range(25):
            reponse = self.client.get('/api/auth/me/')
            # 401 (anonyme) et non 429 : la route n'est pas limitée comme login.
            self.assertEqual(reponse.status_code, status.HTTP_401_UNAUTHORIZED)


class TraceDerniereConnexionTests(_IsolationLimiteurTestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_role_groups()

    def test_connexion_jwt_met_a_jour_last_login(self):
        # ÉCART E11 CORRIGÉ (LOT 2 / unité U6) : la vue login alimente
        # désormais ``User.last_login`` (et
        # ``CompteUtilisateur.derniere_connexion``) à chaque connexion
        # réussie, web comme mobile — les comptes dormants sont à nouveau
        # détectables à partir de la trace de connexion elle-même.
        compte = _creer('car-trace', 'SECRETARIAT')
        self.assertIsNone(compte.last_login)
        reponse = self.client.post(
            URL_CONNEXION,
            {'username': 'car-trace', 'password': MOT_DE_PASSE},
            format='json',
        )
        self.assertEqual(reponse.status_code, 200)
        compte.refresh_from_db()
        self.assertIsNotNone(compte.last_login)


class CookieRafraichissementTests(_IsolationLimiteurTestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_role_groups()

    def test_cookie_refresh_httponly_et_chemin_restreint_pour_role_web(self):
        _creer('car-cookie', 'SECRETARIAT')
        reponse = self.client.post(
            URL_CONNEXION,
            {'username': 'car-cookie', 'password': MOT_DE_PASSE},
            format='json',
        )
        self.assertEqual(reponse.status_code, 200)
        cookie = reponse.cookies['refresh_token']
        self.assertTrue(cookie['httponly'])
        self.assertEqual(cookie['path'], '/api/auth/')
        # Le corps contient encore le refresh (rétrocompatibilité mobile).
        self.assertIn('refresh', reponse.json())
