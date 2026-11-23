"""Périmètre formateurs : pool global pour le secrétariat, règles d'assignation inchangées."""
from django.test import TestCase
from rest_framework.test import APIClient

from authentication.models import User
from .models import Formation, Module, Formateur, Secretariat, ModuleFormateur


class FormateurScopeTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.secretariat = Secretariat.objects.create(nom='FAB')
        self.other_secretariat = Secretariat.objects.create(nom='FAC')
        self.sec_user = User.objects.create_user(
            username='sec_fab',
            password='test',
            role='SECRETARIAT',
            secretariat=self.secretariat,
        )
        self.formation = Formation.objects.create(formation='Cycle test')
        self.module = Module.objects.create(
            formation=self.formation,
            intitule='Module FAB',
            statut='PLANIFIEE',
            secretariat=self.secretariat,
        )
        self.formateur_via_module = Formateur.objects.create(
            numerobadge='F007',
            nom='ViaModule',
            prenom='Test',
        )
        ModuleFormateur.objects.create(
            module=self.module,
            formateur=self.formateur_via_module,
        )
        self.formateur_other = Formateur.objects.create(
            numerobadge='F999',
            nom='Autre',
            prenom='Sec',
        )
        self.formateur_other.secretariats.add(self.other_secretariat)

    def test_secretariat_can_patch_formateur_assigned_to_module(self):
        self.client.force_authenticate(user=self.sec_user)
        res = self.client.patch(
            f'/api/formations/formateurs/{self.formateur_via_module.pk}/',
            {'telephone': '0102030405'},
            format='json',
        )
        self.assertEqual(res.status_code, 200, res.data)
        self.formateur_via_module.refresh_from_db()
        self.assertEqual(self.formateur_via_module.telephone, '0102030405')

    def test_formateur_list_includes_all_formateurs_for_secretariat(self):
        self.client.force_authenticate(user=self.sec_user)
        res = self.client.get('/api/formations/formateurs/list/')
        self.assertEqual(res.status_code, 200)
        ids = {row['id'] for row in res.data['results']}
        self.assertIn(self.formateur_via_module.pk, ids)
        self.assertIn(self.formateur_other.pk, ids)
