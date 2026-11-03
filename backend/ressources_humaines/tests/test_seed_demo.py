"""Personnel d'exemple (tâche 34) : seed, vues globales et panorama."""
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from authentication.models import User
from ressources_humaines.models import (
    Agent, AffectationRH, DocumentRH, Fonction, Service,
)


class SeedPersonnelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='dir_rh', password='pass', role='DIRECTION',
        )
        Service.objects.create(nom='Service des examens et concours', code='SRV-EXAM')
        Service.objects.create(nom='Service de la trésorerie', code='SRV-TRE')

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_seed_et_vues_globales(self):
        call_command('seed_personnel_demo')
        self.assertEqual(Agent.objects.count(), 24)
        self.assertEqual(Fonction.objects.count(), 4)
        self.assertEqual(AffectationRH.objects.count(), 22)
        self.assertEqual(DocumentRH.objects.count(), 20)
        # Aucun compte de connexion n'est créé pour les agents d'exemple.
        self.assertEqual(Agent.objects.filter(user__isnull=False).count(), 0)

        res = self.client.get('/api/rh/stats/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['agents_actifs'], 22)

        res = self.client.get('/api/rh/affectations/', {'actives': '1'})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.data['results']), 22)

        res = self.client.get('/api/rh/disponibilites/', {'type_indispo': 'CONGE'})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data['results'])

    def test_idempotent_puis_purge(self):
        call_command('seed_personnel_demo')
        call_command('seed_personnel_demo')
        self.assertEqual(Agent.objects.count(), 24)
        call_command('seed_personnel_demo', '--purger')
        self.assertEqual(Agent.objects.count(), 0)
        self.assertEqual(AffectationRH.objects.count(), 0)
