"""Tests Bilan FAC — périmètre grades / groupes."""
from django.test import TestCase

from formations.models import Formation, Module, Secretariat
from statistiques.bilans import (
    compute_bilan_fac,
    list_bilan_fac_perimetre,
)


class BilanFacPerimetreTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sec = Secretariat.objects.create(nom='Sec FAC')
        cls.formation = Formation.objects.create(formation='FAB test')
        Module.objects.create(
            formation=cls.formation, intitule='M1', grade='A4', groupe='G1',
            secretariat=cls.sec,
        )
        Module.objects.create(
            formation=cls.formation, intitule='M2', grade='A4', groupe='G2',
            secretariat=cls.sec,
        )
        Module.objects.create(
            formation=cls.formation, intitule='M3', grade='B', groupe='G3',
            secretariat=cls.sec,
        )

    def test_list_perimetre_returns_grades_and_groupes(self):
        data = list_bilan_fac_perimetre(self.formation.id)
        self.assertEqual(data['grades'], ['A4', 'B'])
        self.assertEqual(len(data['groupes']), 3)
        self.assertEqual(data['groupes'][0]['id'], 'A4|G1')

    def test_compute_filtered_by_grade(self):
        data = compute_bilan_fac(
            self.formation.id, grades_filter=['A4'],
        )
        grades = [l['grade'] for l in data['point_global']['lignes']]
        self.assertEqual(grades, ['A4'])

    def test_compute_filtered_by_groupe(self):
        data = compute_bilan_fac(
            self.formation.id, groupes_filter=['A4|G1'],
        )
        self.assertEqual(len(data['point_global']['lignes']), 1)
        vh_groupes = [g['groupe'] for entry in data['vh_par_grade'] for g in entry['groupes']]
        self.assertEqual(vh_groupes, ['G1'])
