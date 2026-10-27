from django.core.management import call_command
from django.test import TestCase

from formations.models import Formation, Module, RefFormation, SessionModule


class CleanupTestFormationsCommandTest(TestCase):
    def setUp(self):
        self.formation = Formation.objects.create(formation='Test DEONTO')
        Module.objects.create(
            formation=self.formation,
            intitule='DEONTOLOGIE',
            grade='G',
            groupe='GROUPE 18',
        )
        SessionModule.objects.create(
            module=Module.objects.get(formation=self.formation),
            date_journee='2026-06-15',
            numero=1,
        )
        RefFormation.objects.create(intitule='Test DEONTO', actif=True)
        Formation.objects.create(formation='FORMATION METIER REELLE')

    def test_dry_run_does_not_delete(self):
        call_command('cleanup_test_formations', '--dry-run')
        self.assertEqual(Formation.objects.filter(formation='Test DEONTO').count(), 1)
        self.assertTrue(RefFormation.objects.filter(intitule='Test DEONTO').exists())

    def test_cleanup_removes_test_data_only(self):
        call_command('cleanup_test_formations')
        self.assertFalse(Formation.objects.filter(formation='Test DEONTO').exists())
        self.assertFalse(RefFormation.objects.filter(intitule='Test DEONTO').exists())
        self.assertTrue(Formation.objects.filter(formation='FORMATION METIER REELLE').exists())

    def test_custom_label(self):
        Formation.objects.create(formation='XYZ cleanup cible')
        call_command('cleanup_test_formations', '--label=XYZ cleanup cible')
        self.assertFalse(Formation.objects.filter(formation='XYZ cleanup cible').exists())
