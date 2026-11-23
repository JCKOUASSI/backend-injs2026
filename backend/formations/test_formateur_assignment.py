"""Règles d'assignation formateur : conflit même jour et liste avec module_id."""
from datetime import date, time

from django.test import TestCase
from rest_framework.test import APIClient

from authentication.models import User
from .formateur_assignment import check_formateur_groupe_jour_conflict
from .models import (
    Formation,
    Formateur,
    Module,
    ModuleFormateur,
    Secretariat,
    SessionModule,
)


class FormateurSameDayConflictTest(TestCase):
    def setUp(self):
        self.secretariat = Secretariat.objects.create(nom='FAB')
        self.formation = Formation.objects.create(formation='Cycle test')
        self.formateur = Formateur.objects.create(
            numerobadge='F001',
            nom='Dupont',
            prenom='Jean',
        )
        self.formateur.secretariats.add(self.secretariat)

        self.module_a = Module.objects.create(
            formation=self.formation,
            intitule='Module A',
            statut='PLANIFIEE',
            secretariat=self.secretariat,
            groupe='GROUPE 1',
        )
        self.module_b = Module.objects.create(
            formation=self.formation,
            intitule='Module B',
            statut='PLANIFIEE',
            secretariat=self.secretariat,
            groupe='GROUPE 1',
        )
        self.conflict_day = date(2026, 3, 10)

        SessionModule.objects.create(
            module=self.module_a,
            numero=1,
            date_journee=self.conflict_day,
            heure_debut_prevue=time(8, 0),
            heure_fin_prevue=time(10, 0),
        )
        SessionModule.objects.create(
            module=self.module_b,
            numero=1,
            date_journee=self.conflict_day,
            heure_debut_prevue=time(14, 0),
            heure_fin_prevue=time(16, 0),
        )

        ModuleFormateur.objects.create(module=self.module_a, formateur=self.formateur)

    def test_allows_assignment_when_same_group_without_time_overlap(self):
        conflict = check_formateur_groupe_jour_conflict(self.formateur, self.module_b)
        self.assertIsNone(conflict)

    def test_allows_assignment_when_no_common_day(self):
        other_day = date(2026, 3, 11)
        SessionModule.objects.filter(module=self.module_b).update(date_journee=other_day)
        conflict = check_formateur_groupe_jour_conflict(self.formateur, self.module_b)
        self.assertIsNone(conflict)


class FormateurListModuleConflictTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.secretariat = Secretariat.objects.create(nom='FAB')
        self.sec_user = User.objects.create_user(
            username='chef_fab',
            password='test',
            role='CHEF_SECRETARIAT',
            secretariat=self.secretariat,
        )
        self.formation = Formation.objects.create(formation='Cycle test')
        self.module_a = Module.objects.create(
            formation=self.formation,
            intitule='Module A',
            statut='PLANIFIEE',
            secretariat=self.secretariat,
        )
        self.module_b = Module.objects.create(
            formation=self.formation,
            intitule='Module B',
            statut='PLANIFIEE',
            secretariat=self.secretariat,
        )
        self.conflict_day = date(2026, 4, 1)
        SessionModule.objects.create(
            module=self.module_a,
            numero=1,
            date_journee=self.conflict_day,
            heure_debut_prevue=time(9, 0),
            heure_fin_prevue=time(11, 0),
        )
        SessionModule.objects.create(
            module=self.module_b,
            numero=1,
            date_journee=self.conflict_day,
            heure_debut_prevue=time(13, 0),
            heure_fin_prevue=time(15, 0),
        )

        self.formateur_libre = Formateur.objects.create(
            numerobadge='F010',
            nom='Libre',
            prenom='Paul',
        )
        self.formateur_libre.secretariats.add(self.secretariat)

        self.formateur_occupe = Formateur.objects.create(
            numerobadge='F011',
            nom='Occupe',
            prenom='Marie',
        )
        self.formateur_occupe.secretariats.add(self.secretariat)
        ModuleFormateur.objects.create(module=self.module_a, formateur=self.formateur_occupe)

    def test_list_marks_occupied_formateur_without_hiding(self):
        self.client.force_authenticate(user=self.sec_user)
        res = self.client.get(
            f'/api/formations/formateurs/list/?module_id={self.module_b.pk}'
        )
        self.assertEqual(res.status_code, 200)
        by_id = {row['id']: row for row in res.data['results']}

        self.assertIn(self.formateur_occupe.pk, by_id)
        self.assertFalse(by_id[self.formateur_occupe.pk]['assignable'])
        self.assertIn('même jour', by_id[self.formateur_occupe.pk]['conflit_assignation'])

        self.assertIn(self.formateur_libre.pk, by_id)
        self.assertTrue(by_id[self.formateur_libre.pk]['assignable'])
        self.assertIsNone(by_id[self.formateur_libre.pk]['conflit_assignation'])

    def test_add_formateur_rejected_when_same_day(self):
        self.client.force_authenticate(user=self.sec_user)
        res = self.client.post(
            f'/api/formations/{self.formation.pk}/modules/{self.module_b.pk}/formateurs/add/',
            {'formateur_id': self.formateur_occupe.pk},
            format='json',
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn('même jour', res.data['detail'])
