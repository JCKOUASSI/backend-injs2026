"""Administration d'exemple (tâche 34) : seed idempotent et panorama."""
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from administrations.models import (
    Courrier, Departement, Direction, Mission, ReunionCommission,
)
from authentication.models import User
from ressources_humaines.models import Service


class SeedAdministrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='admin_adm', password='pass', role='ADMIN',
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_seed_complet_et_panorama(self):
        call_command('seed_administration_demo')
        self.assertEqual(Direction.objects.count(), 5)
        self.assertEqual(Departement.objects.count(), 10)
        self.assertEqual(Service.objects.count(), 14)
        self.assertEqual(Courrier.objects.count(), 40)
        self.assertEqual(ReunionCommission.objects.count(), 16)
        # Aucun titulaire de poste inventé, aucun budget inventé.
        self.assertEqual(
            Direction.objects.filter(responsable__isnull=False).count(), 0,
        )
        self.assertEqual(Mission.objects.exclude(budget=0).count(), 0)
        res = self.client.get('/api/administrations/stats/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['courriers'], 40)
        self.assertEqual(res.data['courriers_par_sens']['ENTRANT'], 20)

    def test_idempotent_puis_purge(self):
        call_command('seed_administration_demo')
        call_command('seed_administration_demo')
        self.assertEqual(Courrier.objects.count(), 40)
        call_command('seed_administration_demo', '--purger')
        self.assertEqual(Courrier.objects.count(), 0)
        self.assertEqual(Direction.objects.count(), 0)
        self.assertEqual(Service.objects.count(), 0)
