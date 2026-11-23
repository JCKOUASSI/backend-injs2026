"""Non-régression de l'idempotence de la fixture `fx.admin()`.

`admin()` fixe un `username` par défaut (`admin5`), qui est la contrainte
d'unicité de la table utilisateur. La fixture doit donc être appelable
plusieurs fois sans lever d'`IntegrityError`.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase

from habilitations.tests import _u5_fixtures as fx

User = get_user_model()


class AdminIdempotenceTests(TestCase):
    def test_01_appel_unique(self):
        u = fx.admin()
        self.assertEqual(u.username, 'admin5')
        self.assertTrue(u.check_password('Mot#2026x'))
        self.assertTrue(u.is_staff)

    def test_02_deux_appels_meme_test_retournent_le_meme_objet(self):
        a = fx.admin()
        b = fx.admin()
        self.assertEqual(a.pk, b.pk)
        self.assertEqual(User.objects.filter(username='admin5').count(), 1)

    def test_03_plusieurs_appels_dans_le_meme_test(self):
        pks = {fx.admin().pk for _ in range(5)}
        self.assertEqual(len(pks), 1)

    def test_04_role_par_defaut_et_role_explicite(self):
        self.assertEqual(fx.admin().role, User.Role.ADMIN)
        autre = fx.admin('admin_autre', role=User.Role.SECRETARIAT)
        self.assertEqual(autre.role, User.Role.SECRETARIAT)

    def test_05_appels_depuis_plusieurs_tests_reutilisent_le_meme_nom(self):
        # Le rollback TestCase nettoie entre les tests : `admin5` est donc
        # recréé, jamais dupliqué.
        self.assertEqual(fx.admin().username, 'admin5')
        self.assertEqual(User.objects.filter(username='admin5').count(), 1)