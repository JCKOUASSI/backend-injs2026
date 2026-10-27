"""Tests du LOT 2 (unité U6 CURP) — sécurité effective de la connexion.

Couvre :
* le verrouillage de compte à la connexion (seuil/délai issus de
  ``PolitiqueSecurite``, machine à états A5, journalisation,
  déverrouillage auto à échéance et par un administrateur) ;
* l'étape MFA TOTP (jeton court, code valide/invalide/expiré, flux
  armement/confirmation, désactivation contrôlée, obligation pour les
  rôles sensibles) ;
* l'alimentation de ``User.last_login`` / ``derniere_connexion`` à chaque
  connexion réussie (correction de l'écart E11 d'U0) ;
* la règle des drapeaux : fermé = comportement strictement d'avant (no-op).

Aucun drapeau n'est ouvert dans la base de test sans que le test ne
l'ouvre explicitement (les migrations les livrent éteints).
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework_simplejwt.tokens import AccessToken

from habilitations.models import (
    AttributionRole,
    CompteUtilisateur,
    JournalHabilitation,
    RoleMetier,
)
from habilitations.services import totp
from parametres.flags import invalidate_flags_cache
from parametres.models import Parametre

User = get_user_model()

MOT_DE_PASSE = 'Test!2026curp'


def _flag(cle, valeur=True):
    """Ouvre/ferme un drapeau dans la base de test (cache invalidé)."""
    Parametre.objects.update_or_create(
        cle=cle,
        defaults={
            'libelle': cle,
            'description': 'test LOT 2',
            'categorie': 'flags',
            'ordre': 900,
            'type': 'bool',
            'valeur': 'true' if valeur else 'false',
            'valeur_defaut': 'false',
            'choices_json': '',
            'regex_validation': '',
            'modifiable': True,
            'modifiable_par_roles': '["ADMIN"]',
            'lecturable_par_roles': '["ADMIN"]',
            'actif': True,
        },
    )
    invalidate_flags_cache()


class SocleLot2(TestCase):
    """Compte CURP de base + administrateur (super-user)."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser(
            'lot2_admin', 'lot2.admin@injs.ci', 'Admin!2026curp')
        cls.user = User.objects.create_user(
            username='lot2_util', password=MOT_DE_PASSE,
            role=User.Role.SECRETARIAT,
        )
        cls.compte = CompteUtilisateur.objects.create(user=cls.user)

    def setUp(self):
        # Le cache (LocMem) n'est pas remis à zéro entre les tests
        # (base de test en savepoints) : compteurs de throttlage login
        # et drapeaux y survivraient — vidé intégralement.
        from django.core.cache import cache
        cache.clear()
        invalidate_flags_cache()

    def _login(self, password=MOT_DE_PASSE, username='lot2_util', **extra):
        donnees = {'username': username, 'password': password}
        donnees.update(extra)
        return self.client.post(
            '/api/auth/login/', donnees, content_type='application/json')

    def _echecs(self, n, password='Mauvais!123x'):
        derniere = None
        for _ in range(n):
            derniere = self._login(password=password)
            self.assertEqual(derniere.status_code, 401)
        return derniere

    def _compte_fraisch(self):
        return CompteUtilisateur.objects.get(pk=self.compte.pk)

    def _user_fraisch(self):
        return User.objects.get(pk=self.user.pk)

    def _armer_compte(self):
        """Arme directement le MFA du compte de base (secret + actif)."""
        self.compte.mfa_secret = totp.generer_secret()
        self.compte.mfa_actif = True
        self.compte.save(update_fields=['mfa_secret', 'mfa_actif'])
        return self._compte_fraisch().mfa_secret


class VerrouillageConnexionTests(SocleLot2):
    """Seuil/délai de PolitiqueSecurite, machine A5, journal, déverrouillage."""

    def test_01_drapeau_fermec_comportement_avant(self):
        # Drapeau fermé : aucune écriture d'échec, aucun verrouillage.
        self._echecs(10)
        compte = self._compte_fraisch()
        self.assertEqual(compte.echecs_consecutifs, 0)
        self.assertEqual(compte.statut, CompteUtilisateur.Statut.ACTIF)
        self.assertFalse(
            JournalHabilitation.objects.filter(
                type_evenement=JournalHabilitation.TypeEvenement
                .COMPTE_VERROUILLE).exists())

    def test_02_verrouillage_au_seuil_de_la_politique(self):
        _flag('flag.curp_verrouillage_connexion')
        self._echecs(4)
        self.assertEqual(self._compte_fraisch().statut,
                         CompteUtilisateur.Statut.ACTIF)
        self.assertEqual(self._compte_fraisch().echecs_consecutifs, 4)
        self._echecs(1)  # le 5e échec atteint le seuil par défaut
        compte = self._compte_fraisch()
        self.assertEqual(compte.statut, CompteUtilisateur.Statut.VERROUILLE)
        self.assertIsNotNone(compte.date_verrouillage)
        self.assertFalse(self._user_fraisch().is_active)
        self.assertTrue(
            JournalHabilitation.objects.filter(
                type_evenement=JournalHabilitation.TypeEvenement
                .COMPTE_VERROUILLE).exists())

    def test_03_refus_pendant_le_verrouillage(self):
        _flag('flag.curp_verrouillage_connexion')
        self._echecs(5)
        # Même avec le BON mot de passe : refus 403 explicite (pas de fuite).
        reponse = self._login()
        self.assertEqual(reponse.status_code, 403)
        self.assertEqual(reponse.json()['code'], 'COMPTE_VERROUILLE')
        self.assertEqual(self._compte_fraisch().statut,
                         CompteUtilisateur.Statut.VERROUILLE)
        self.assertTrue(
            JournalHabilitation.objects.filter(
                type_evenement=JournalHabilitation.TypeEvenement
                .CONNEXION_REFUSEE_VERROUILLEE).exists())

    def test_04_deverrouillage_auto_a_l_echeance(self):
        _flag('flag.curp_verrouillage_connexion')
        self._echecs(5)
        # Le délai (15 min par défaut) est écoulé.
        compte = self._compte_fraisch()
        compte.date_verrouillage = timezone.now() - timedelta(minutes=16)
        compte.save(update_fields=['date_verrouillage'])
        reponse = self._login()
        self.assertEqual(reponse.status_code, 200)
        self.assertIn('access', reponse.json())
        compte = self._compte_fraisch()
        self.assertEqual(compte.statut, CompteUtilisateur.Statut.ACTIF)
        self.assertEqual(compte.echecs_consecutifs, 0)
        self.assertTrue(
            JournalHabilitation.objects.filter(
                type_evenement=JournalHabilitation.TypeEvenement
                .COMPTE_DEVERROUILLE).exists())

    def test_05_deverrouillage_par_un_administrateur(self):
        _flag('flag.curp_verrouillage_connexion')
        _flag('flag.curp_ui_admin')
        self._echecs(5)
        self.client.force_login(self.admin)
        reponse = self.client.post(
            f'/api/habilitations/comptes/{self.compte.pk}/statut/',
            data={'transition': 'deverrouiller', 'motif': 'Maintenance.'},
            content_type='application/json',
        )
        self.assertEqual(reponse.status_code, 200, reponse.content)
        self.client.logout()
        self.assertEqual(self._login().status_code, 200)

    def test_06_echecs_remises_a_zero_apres_un_succes(self):
        _flag('flag.curp_verrouillage_connexion')
        self._echecs(3)
        self.assertEqual(self._login().status_code, 200)
        self.assertEqual(self._compte_fraisch().echecs_consecutifs, 0)
        self._echecs(3)  # 3 + 3 au total, mais le compteur a été remis à zéro
        self.assertEqual(self._compte_fraisch().statut,
                         CompteUtilisateur.Statut.ACTIF)
        self.assertEqual(self._compte_fraisch().echecs_consecutifs, 3)

    def test_07_last_login_alimente_a_chaque_connexion(self):
        # Sans aucun drapeau (correction de l'écart E11, sans condition).
        avant = timezone.now()
        reponse = self._login()
        self.assertEqual(reponse.status_code, 200)
        user = self._user_fraisch()
        self.assertIsNotNone(user.last_login)
        self.assertGreaterEqual(user.last_login, avant - timedelta(seconds=5))
        self.assertIsNotNone(self._compte_fraisch().derniere_connexion)


class MfaTotpTests(SocleLot2):
    """Étape MFA : jeton court, codes, flux armement/confirmation/désactivation."""

    def test_08_drapeau_fermec_mfa_ignoree(self):
        secret = self._armer_compte()
        self.assertTrue(totp.verifier_code(secret, totp.code_actuel(secret)))
        reponse = self._login()
        # Drapeau curp_mfa_active fermé : connexion directe, pas d'étape.
        self.assertEqual(reponse.status_code, 200)

    def test_09_etape_mfa_puis_completion(self):
        _flag('flag.curp_mfa_active')
        secret = self._armer_compte()
        reponse = self._login()
        self.assertEqual(reponse.status_code, 403)
        corps = reponse.json()
        self.assertEqual(corps['code'], 'MFA_REQUIRED')
        self.assertTrue(corps['mfa_token'])
        self.assertTrue(
            JournalHabilitation.objects.filter(
                type_evenement=JournalHabilitation.TypeEvenement
                .MFA_ETAPSE_DEMANDEE).exists())
        # Code erroné : 400, pas de jeton.
        mauvaise = '000000' if totp.code_actuel(secret) != '000000' else '000001'
        refus = self.client.post(
            '/api/auth/mfa/verify/',
            data={'mfa_token': corps['mfa_token'], 'code': mauvaise},
            content_type='application/json',
        )
        self.assertEqual(refus.status_code, 400)
        self.assertEqual(refus.json()['code'], 'MFA_CODE_INVALIDE')
        # Code valide : connexion complète (tokens + cookie + horodatage).
        avant = timezone.now()
        reussie = self.client.post(
            '/api/auth/mfa/verify/',
            data={'mfa_token': corps['mfa_token'],
                  'code': totp.code_actuel(secret)},
            content_type='application/json',
        )
        self.assertEqual(reussie.status_code, 200)
        self.assertIn('access', reussie.json())
        self.assertIn('refresh_token', self.client.cookies)
        user = self._user_fraisch()
        self.assertGreaterEqual(user.last_login, avant - timedelta(seconds=5))
        self.assertEqual(self._compte_fraisch().echecs_consecutifs, 0)

    def test_10_jeton_expire_ou_hors_etape_rejete(self):
        _flag('flag.curp_mfa_active')
        secret = self._armer_compte()
        # Jeton d'étape expiré (horodatage dans le passé).
        expire = AccessToken()
        expire['mfa_etape'] = True
        expire['username'] = 'lot2_util'
        expire['exp'] = int(
            (timezone.now() - timedelta(minutes=1)).timestamp())
        reponse = self.client.post(
            '/api/auth/mfa/verify/',
            data={'mfa_token': str(expire), 'code': totp.code_actuel(secret)},
            content_type='application/json',
        )
        self.assertEqual(reponse.status_code, 400)
        self.assertEqual(reponse.json()['code'], 'MFA_JETON_INVALIDE')
        # Un jeton d'accès ordinaire (sans claim mfa_etape) ne suffit pas.
        ordinaire = AccessToken.for_user(self.user)
        reponse = self.client.post(
            '/api/auth/mfa/verify/',
            data={'mfa_token': str(ordinaire),
                  'code': totp.code_actuel(secret)},
            content_type='application/json',
        )
        self.assertEqual(reponse.status_code, 400)

    def test_11_flux_armement_confirmation(self):
        self.client.force_login(self.user)
        reponse = self.client.post('/api/auth/mfa/setup/', data={},
                                   content_type='application/json')
        self.assertEqual(reponse.status_code, 200, reponse.content)
        corps = reponse.json()
        secret = corps['secret']
        self.assertIn(secret, corps['otpauth_url'])
        self.assertEqual(self._compte_fraisch().mfa_actif, False)
        # Confirmation avec code erroné puis valide.
        mauvaise = '000000' if totp.code_actuel(secret) != '000000' else '000001'
        refus = self.client.post('/api/auth/mfa/confirm/',
                                 data={'code': mauvaise},
                                 content_type='application/json')
        self.assertEqual(refus.status_code, 400)
        reussie = self.client.post(
            '/api/auth/mfa/confirm/',
            data={'code': totp.code_actuel(secret)},
            content_type='application/json',
        )
        self.assertEqual(reussie.status_code, 200)
        self.assertTrue(self._compte_fraisch().mfa_actif)
        self.assertTrue(
            JournalHabilitation.objects.filter(
                type_evenement=JournalHabilitation.TypeEvenement
                .MFA_ACTIVE).exists())

    def test_12_desactivation_par_soit_meme_exige_un_code(self):
        self._armer_compte()
        secret = self._compte_fraisch().mfa_secret
        self.client.force_login(self.user)
        refus = self.client.post('/api/auth/mfa/disable/', data={},
                                 content_type='application/json')
        self.assertEqual(refus.status_code, 400)
        reussie = self.client.post(
            '/api/auth/mfa/disable/',
            data={'code': totp.code_actuel(secret)},
            content_type='application/json',
        )
        self.assertEqual(reussie.status_code, 200)
        compte = self._compte_fraisch()
        self.assertFalse(compte.mfa_actif)
        self.assertEqual(compte.mfa_secret, '')
        self.assertTrue(
            JournalHabilitation.objects.filter(
                type_evenement=JournalHabilitation.TypeEvenement
                .MFA_DESACTIVE).exists())

    def test_13_un_admin_gere_le_mfa_d_un_tiers(self):
        self._armer_compte()
        # Un compte sans mutate_users ne gère pas les tiers.
        tiers = User.objects.create_user(
            username='lot2_tiers', password=MOT_DE_PASSE,
            role=User.Role.ARCHIVE,
        )
        self.client.force_login(tiers)
        refus = self.client.post(
            '/api/auth/mfa/setup/',
            data={'compte_id': self.user.pk},
            content_type='application/json',
        )
        self.assertEqual(refus.status_code, 403)
        # L'administrateur peut armer le MFA du compte cible.
        self.client.force_login(self.admin)
        reponse = self.client.post(
            '/api/auth/mfa/setup/',
            data={'compte_id': self.user.pk},
            content_type='application/json',
        )
        self.assertEqual(reponse.status_code, 200, reponse.content)
        self.assertEqual(
            reponse.json()['secret'], self._compte_fraisch().mfa_secret)
        # Un compte sans profil CURP est signalé (404, pas 500).
        sans_profil = User.objects.create_user(
            username='lot2_sans', password=MOT_DE_PASSE,
            role=User.Role.ARCHIVE,
        )
        refus = self.client.post(
            '/api/auth/mfa/setup/',
            data={'compte_id': sans_profil.pk},
            content_type='application/json',
        )
        self.assertEqual(refus.status_code, 404)


class MfaObligatoireSensiblesTests(SocleLot2):
    """MFA obligatoire pour les comptes portant un rôle sensible actif."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.role_sensible = RoleMetier.objects.create(
            code='TEST_ROLE_SENSIBLE', libelle='Rôle sensible de test',
            domaine='TECHNIQUE', sensible=True,
        )

    def _rattacher_role_sensible(self):
        AttributionRole.objects.create(
            compte=self.compte, role=self.role_sensible,
            niveau_effectif='N2', motif='Test LOT 2',
            statut=AttributionRole.Statut.ACTIVE,
        )

    def test_14_connexion_refusee_sans_mfa(self):
        self._rattacher_role_sensible()
        _flag('flag.curp_mfa_active')
        _flag('flag.curp_mfa_obligatoire_sensibles')
        reponse = self._login()
        self.assertEqual(reponse.status_code, 403)
        self.assertEqual(reponse.json()['code'], 'MFA_OBLIGATOIRE')
        # Et l'étape MFA devient possible une fois le MFA armé.
        secret = self._armer_compte()
        reponse = self._login()
        self.assertEqual(reponse.json()['code'], 'MFA_REQUIRED')
        reussie = self.client.post(
            '/api/auth/mfa/verify/',
            data={'mfa_token': reponse.json()['mfa_token'],
                  'code': totp.code_actuel(secret)},
            content_type='application/json',
        )
        self.assertEqual(reussie.status_code, 200)

    def test_15_desactivation_bloquee_pendant_l_obligation(self):
        self._rattacher_role_sensible()
        self._armer_compte()
        _flag('flag.curp_mfa_obligatoire_sensibles')
        self.client.force_login(self.admin)
        refus = self.client.post(
            '/api/auth/mfa/disable/',
            data={'compte_id': self.user.pk},
            content_type='application/json',
        )
        self.assertEqual(refus.status_code, 409)
        self.assertTrue(self._compte_fraisch().mfa_actif)
        # Drapeau fermé : la désadministration redevient possible.
        _flag('flag.curp_mfa_obligatoire_sensibles', valeur=False)
        reussie = self.client.post(
            '/api/auth/mfa/disable/',
            data={'compte_id': self.user.pk},
            content_type='application/json',
        )
        self.assertEqual(reussie.status_code, 200)

    def test_16_sans_drapeau_obligatoire_pas_d_empechement(self):
        self._rattacher_role_sensible()
        _flag('flag.curp_mfa_active')
        # Drapeau d'obligation fermé : un compte sensible sans MFA se
        # connecte normalement (le MFA reste optionnel).
        reponse = self._login()
        self.assertEqual(reponse.status_code, 200)
