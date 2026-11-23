from django.test import TestCase

from .models import Formation, Module, Formateur, ModuleFormateur, RefFormation, SessionModule
from .api_views import (
    _finance_report_rows,
    _finance_kpis_from_rows,
    _finance_dashboard_modules_breakdown,
    _finance_total_montant_prevu_from_breakdown,
)


def _make_formation(titre='Cycle test'):
    return Formation.objects.create(formation=titre)


def _make_formateur():
    return Formateur.objects.create(numerobadge='F300', nom='Dupont', prenom='Marie')


class FinanceTarifsParFormationTest(TestCase):

    def setUp(self):
        self.formation = _make_formation('Cycle A')
        RefFormation.objects.create(intitule='Cycle A', prix_heure_realisee=7500, actif=True)
        self.module = Module.objects.create(
            formation=self.formation,
            intitule='Module A',
            statut='PLANIFIEE',
            grade='A4',
            groupe='G1',
            duree_prevue_heures=2,
        )
        self.formateur = _make_formateur()
        ModuleFormateur.objects.create(module=self.module, formateur=self.formateur)
        SessionModule.objects.create(
            module=self.module,
            date_journee='2026-01-15',
            numero=1,
            heure_debut_prevue='08:00',
            heure_fin_prevue='10:00',
        )

    def test_montant_uses_formation_tariff_not_global(self):
        rows = _finance_report_rows([self.formateur], include_sessions=True)
        mod = rows[0]['modules'][0]
        self.assertEqual(mod['prix_heure_realisee'], 7500.0)
        sess = rows[0]['sessions'][0]
        self.assertEqual(sess['prix_heure_realisee'], 7500.0)
        self.assertTrue(rows[0]['tarifs_variables'])

    def test_missing_formation_tariff_yields_zero(self):
        RefFormation.objects.filter(intitule='Cycle A').delete()
        rows = _finance_report_rows([self.formateur], include_sessions=True)
        mod = rows[0]['modules'][0]
        self.assertEqual(mod['prix_heure_realisee'], 0.0)
        self.assertEqual(mod['montant_realise'], 0.0)

    def test_kpis_always_per_formation_mode(self):
        rows = _finance_report_rows([self.formateur], include_sessions=False)
        kpis = _finance_kpis_from_rows(rows)
        self.assertTrue(kpis['tarifs_variables'])
        self.assertIn(7500.0, kpis['tarifs_appliques'])

    def test_montant_prevu_from_planned_volume(self):
        rows = _finance_report_rows([self.formateur], include_sessions=False)
        breakdown = _finance_dashboard_modules_breakdown(rows, date_debut=None, date_fin=None)
        self.assertEqual(len(breakdown), 1)
        mod = breakdown[0]
        self.assertEqual(mod['total_duree_minutes'], 120.0)
        self.assertEqual(mod['montant_prevu'], 15000.0)  # 2 h × 7500 FCFA/h
        self.assertEqual(_finance_total_montant_prevu_from_breakdown(breakdown), 15000.0)
