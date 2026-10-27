from datetime import timedelta, time as dt_time

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import Formation, Module, SessionModule
from .finance_encadrants import finance_encadrants_report

User = get_user_model()


class FinanceEncadrantsTest(TestCase):

    def setUp(self):
        self.encadrant = User.objects.create_user(
            username='enc1',
            password='test',
            role='ENCADRANT',
            first_name='Ali',
            last_name='Koné',
        )
        self.finance_user = User.objects.create_user(
            username='fin1', password='test', role='FINANCE',
        )
        self.formation = Formation.objects.create(formation='Cycle A4')
        self.module = Module.objects.create(
            formation=self.formation,
            intitule='Déontologie',
            statut='PLANIFIEE',
            grade='A4',
            groupe='GROUPE 4',
            duree_prevue_heures=4,
            superviseur=self.encadrant,
        )
        now = timezone.now()
        SessionModule.objects.create(
            module=self.module,
            date_journee=timezone.localdate(),
            numero=1,
            demarree_le=now - timedelta(hours=2),
            terminee_le=now,
            heure_debut_prevue=dt_time(8, 0),
            heure_fin_prevue=dt_time(10, 0),
        )

    def test_report_includes_encadrant_groupe_volumes(self):
        data = finance_encadrants_report()
        self.assertEqual(len(data['encadrants']), 1)
        block = data['encadrants'][0]
        self.assertEqual(block['encadrant_label'], 'Ali Koné')
        self.assertEqual(len(block['lignes']), 1)
        ligne = block['lignes'][0]
        self.assertEqual(ligne['groupe'], 'GROUPE 4')
        self.assertEqual(ligne['planned_minutes'], 240.0)  # fiche 4h (pas de RefModule)
        self.assertEqual(ligne['realized_minutes'], 120.0)
        self.assertEqual(data['totaux']['lignes_count'], 1)

    def test_api_encadrants_json(self):
        client = APIClient()
        client.force_authenticate(user=self.finance_user)
        res = client.get('/api/formations/finance/encadrants/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['totaux']['encadrants_count'], 1)
        self.assertEqual(res.json()['encadrants'][0]['lignes'][0]['groupe'], 'GROUPE 4')
