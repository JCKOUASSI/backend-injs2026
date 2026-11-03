"""Le compte de démonstration ne doit pas contaminer la suite de tests.

Constat d'audit : `backend/.env` (écrit par `arena/bootstrap.sh`) déclare
`DJANGO_SUPERUSER_*`. Le signal `post_migrate` créait alors un administrateur
supplémentaire dans la base de test, ce qui faisait échouer des tests comptant
les comptes — « AssertionError: 3 != 2 » dans
`habilitations.tests.test_console_u4`. La suite doit donner le même résultat
avec ou sans fichier d'environnement de démonstration.
"""

import os
from unittest import mock

from django.test import TestCase

from authentication.apps import create_superuser_from_env, _suite_de_tests_en_cours


class IsolationCompteDemoTests(TestCase):

    def test_la_suite_est_reconnue_comme_telle(self):
        # `manage.py test` : l'application doit se savoir en test.
        self.assertTrue(_suite_de_tests_en_cours())

    def test_aucun_compte_demo_n_est_cree_pendant_les_tests(self):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        avant = User.objects.count()
        with mock.patch.dict(os.environ, {
            'DJANGO_SUPERUSER_USERNAME': 'demo-audit',
            'DJANGO_SUPERUSER_EMAIL': 'demo@arena.invalid',
            'DJANGO_SUPERUSER_PASSWORD': 'mot-de-passe-de-demo',
        }):
            create_superuser_from_env()

        self.assertFalse(
            User.objects.filter(username='demo-audit').exists(),
            "Le compte de démonstration a été créé dans la base de test.",
        )
        self.assertEqual(User.objects.count(), avant)


class RemiseANiveauMotDePasseDemoTests(TestCase):
    """Le mot de passe publié dans `.env` doit correspondre au compte réel.

    Défaut constaté : `DJANGO_SUPERUSER_PASSWORD` n'était appliqué qu'à la
    CRÉATION du compte. Un `.env` régénéré (ou un mot de passe changé)
    annonçait donc des identifiants qui échouaient à la connexion — l'admin
    d'aperçu devenait inaccessible sans aucun moyen d'y revenir.
    """

    IDENTIFIANTS = {
        'DJANGO_SUPERUSER_USERNAME': 'admin-demo',
        'DJANGO_SUPERUSER_EMAIL': 'admin-demo@arena.invalid',
        'DJANGO_SUPERUSER_PASSWORD': 'nouveau-mot-de-passe',
    }

    def setUp(self):
        from django.contrib.auth import get_user_model

        self.User = get_user_model()
        self.compte = self.User.objects.create_superuser(
            username='admin-demo', email='admin-demo@arena.invalid',
            password='ancien-mot-de-passe',
        )
        # `create_superuser_from_env` ne fait rien pendant la suite de tests :
        # on neutralise uniquement cette garde, pas les autres.
        patche = mock.patch(
            'authentication.apps._suite_de_tests_en_cours', return_value=False,
        )
        patche.start()
        self.addCleanup(patche.stop)

    def test_mot_de_passe_non_remplace_sans_demande_explicite(self):
        with mock.patch.dict(os.environ, self.IDENTIFIANTS, clear=False):
            os.environ.pop('DJANGO_SUPERUSER_RESET_PASSWORD', None)
            create_superuser_from_env()

        self.compte.refresh_from_db()
        self.assertTrue(self.compte.check_password('ancien-mot-de-passe'))
        self.assertFalse(self.compte.check_password('nouveau-mot-de-passe'))

    def test_mot_de_passe_remis_a_niveau_sur_demande(self):
        with mock.patch.dict(os.environ, {
            **self.IDENTIFIANTS, 'DJANGO_SUPERUSER_RESET_PASSWORD': '1',
        }, clear=False):
            create_superuser_from_env()

        self.compte.refresh_from_db()
        self.assertTrue(
            self.compte.check_password('nouveau-mot-de-passe'),
            "Le mot de passe annoncé par `.env` doit être celui du compte.",
        )
        self.assertFalse(self.compte.check_password('ancien-mot-de-passe'))

    def test_compte_reactive_au_passage(self):
        """Un compte désactivé redevient utilisable : sinon l'aperçu est bloqué."""
        self.User.objects.filter(pk=self.compte.pk).update(is_active=False)
        with mock.patch.dict(os.environ, {
            **self.IDENTIFIANTS, 'DJANGO_SUPERUSER_RESET_PASSWORD': '1',
        }, clear=False):
            create_superuser_from_env()

        self.compte.refresh_from_db()
        self.assertTrue(self.compte.is_active)
