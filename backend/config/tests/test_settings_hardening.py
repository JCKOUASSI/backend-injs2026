"""Non-regression B4 : convention canonique DJANGO_* et alias de compatibilite.

Cause racine corrigee : le .env de production ecrivait DJANGO_DEBUG=0 alors
que settings.py lisait DEBUG, et le defaut True exposait alors la page de
debug Django sur le domaine public. Ces tests verrouillent la resolution
des variables et le garde-fou SECRET_KEY.
"""
import importlib
import os
import sys
from unittest import mock

from django.test import SimpleTestCase

# Marqueur de test uniquement : ce nest pas une cle reelle et cette valeur
# ne doit jamais etre reprise dans un .env de production.
_MARQUEUR = 'b4-marqueur-test-pas-une-cle'

_VARIABLES = (
    'DEBUG', 'DJANGO_DEBUG',
    'SECRET_KEY', 'DJANGO_SECRET_KEY',
    'ALLOWED_HOSTS', 'DJANGO_ALLOWED_HOSTS',
    'CSRF_TRUSTED_ORIGINS', 'DJANGO_CSRF_TRUSTED_ORIGINS',
)


def _purger():
    # Purge tous les modules config* : config, config.settings, config.apps...
    for nom in [m for m in list(sys.modules) if m == 'config' or m.startswith('config.')]:
        sys.modules.pop(nom, None)

class ChargementConfigurationMixin:
    """Recharge config.settings sous un environnement maitrise puis le restaure."""

    def charger(self, env, attendre_erreur=False, avec_cle=True):
        """Retourne le module config.settings recharge, ou None si RuntimeError.

        Deux precautions rendent la recharge deterministic :

        * ``mock.patch.dict`` enveloppe toute l'operation : les variables
          retirees pour le test sont REMISEES dans leur etat d'origine a la
          sortie. Sans cela, la purge etait definitive et polluait le
          processus pour tous les tests suivants de la suite.
        * ``load_dotenv`` est neutralise : ``settings`` appelle
          ``load_dotenv(BASE_DIR/'.env')`` a l'import (lignes 5-8), ce qui
          reinjectait DJANGO_DEBUG / DJANGO_SECRET_KEY / DJANGO_ALLOWED_HOSTS
          depuis le .env reel de la machine. Les tests qui verifient le
          comportement « variable canonique absente » (alias, defaut sur,
          garde-fou sans cle) observaient alors la valeur du .env au lieu de
          l'absence de variable. Le contrat de production n'est pas modifie :
          seul son rechargement par le .env est ecarte pendant le test.
        """
        env = dict(env)
        with mock.patch.dict(os.environ, {}, clear=False):
            # Purge AVANT l'injection : les variables du test doivent
            # etre posees apres le nettoyage, jamais avant.
            for cle in _VARIABLES:
                os.environ.pop(cle, None)
            if avec_cle:
                env.setdefault('SECRET_KEY', _MARQUEUR)
            os.environ.update(env)
            with mock.patch('dotenv.load_dotenv', return_value=False):
                _purger()
                try:
                    return importlib.import_module('config.settings')
                except RuntimeError:
                    if attendre_erreur:
                        return None
                    raise
                finally:
                    _purger()


class ResolutionDebugTests(ChargementConfigurationMixin, SimpleTestCase):
    """DJANGO_DEBUG canonique, DEBUG en alias, defat sur (False)."""

    def test_canonique_zero_desactive_debug(self):
        self.assertIs(self.charger({'DJANGO_DEBUG': '0'}).DEBUG, False)

    def test_canonique_false_desactive_debug(self):
        self.assertIs(self.charger({'DJANGO_DEBUG': 'false'}).DEBUG, False)

    def test_canonique_un_active_debug(self):
        self.assertIs(self.charger({'DJANGO_DEBUG': '1'}).DEBUG, True)

    def test_canonique_true_active_debug(self):
        self.assertIs(self.charger({'DJANGO_DEBUG': 'true'}).DEBUG, True)

    def test_canonique_prime_sur_alias(self):
        self.assertIs(self.charger({'DJANGO_DEBUG': '0', 'DEBUG': '1'}).DEBUG, False)
        self.assertIs(self.charger({'DJANGO_DEBUG': '1', 'DEBUG': '0'}).DEBUG, True)

    def test_alias_utilise_si_canonique_absente(self):
        self.assertIs(self.charger({'DEBUG': '1'}).DEBUG, True)

    def test_defaut_sur_quand_aucune_variable(self):
        self.assertIs(self.charger({}).DEBUG, False)


class ResolutionSecretKeyTests(ChargementConfigurationMixin, SimpleTestCase):
    """DJANGO_SECRET_KEY canonique, SECRET_KEY en alias, valeur vide = absente."""

    def test_canonique_prioritaire(self):
        s = self.charger({'DJANGO_SECRET_KEY': 'canonique', 'SECRET_KEY': 'alias'})
        self.assertEqual(s.SECRET_KEY, 'canonique')

    def test_alias_si_canonique_absente(self):
        s = self.charger({'SECRET_KEY': 'alias-seul'})
        self.assertEqual(s.SECRET_KEY, 'alias-seul')

    def test_canonique_vide_retombe_sur_alias(self):
        s = self.charger({'DJANGO_SECRET_KEY': '', 'SECRET_KEY': 'alias-seul'})
        self.assertEqual(s.SECRET_KEY, 'alias-seul')

    def test_canonique_blancs_retombe_sur_alias(self):
        s = self.charger({'DJANGO_SECRET_KEY': '   ', 'SECRET_KEY': 'alias-seul'})
        self.assertEqual(s.SECRET_KEY, 'alias-seul')

    def test_garde_fou_refuse_demarrage_hors_debug(self):
        # Risque B4 : hors DEBUG, une cle absente doit empecher le demarrage.
        self.assertIsNone(self.charger({'DJANGO_DEBUG': '0'}, attendre_erreur=True, avec_cle=False))

    def test_garde_fou_refuse_demarrage_avec_defaut_sur(self):
        self.assertIsNone(self.charger({}, attendre_erreur=True, avec_cle=False))

    def test_dev_sans_cle_conserve_le_repli_historique(self):
        s = self.charger({'DJANGO_DEBUG': '1'}, attendre_erreur=True, avec_cle=False)
        self.assertEqual(s.SECRET_KEY,
                         'django-insecure-dev-only-do-not-use-in-production')


class ResolutionHotesTests(ChargementConfigurationMixin, SimpleTestCase):
    """Conventions canonique et alias pour ALLOWED_HOSTS et CSRF."""

    def test_allowed_hosts_canonique(self):
        s = self.charger({'DJANGO_ALLOWED_HOSTS': 'a.example,b.example'})
        self.assertEqual(s.ALLOWED_HOSTS, ['a.example', 'b.example'])

    def test_allowed_hosts_alias(self):
        s = self.charger({'ALLOWED_HOSTS': 'c.example'})
        self.assertEqual(s.ALLOWED_HOSTS, ['c.example'])

    def test_allowed_hosts_canonique_prioritaire(self):
        s = self.charger({'DJANGO_ALLOWED_HOSTS': 'a.example',
                         'ALLOWED_HOSTS': 'c.example'})
        self.assertEqual(s.ALLOWED_HOSTS, ['a.example'])

    def test_csrf_canonique(self):
        s = self.charger({'DJANGO_CSRF_TRUSTED_ORIGINS': 'https://a.example'})
        self.assertEqual(s.CSRF_TRUSTED_ORIGINS, ['https://a.example'])

    def test_csrf_alias_conserve(self):
        s = self.charger({'CSRF_TRUSTED_ORIGINS': 'https://c.example'})
        self.assertEqual(s.CSRF_TRUSTED_ORIGINS, ['https://c.example'])
