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
