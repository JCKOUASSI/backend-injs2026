from django.test import TestCase

from .finance_tolerance import evaluate_volume_tolerance, tolerance_threshold_minutes
from .models import FinanceSettings


class FinanceToleranceTest(TestCase):

    def setUp(self):
        self.settings = FinanceSettings.get_solo()
        self.settings.tolerance_active = True
        self.settings.tolerance_minutes = 30
        self.settings.tolerance_pct = 10
        self.settings.save()

    def test_ok_when_realized_meets_planned(self):
        result = evaluate_volume_tolerance(240, 240, settings=self.settings)
        self.assertEqual(result['statut'], 'ok')

    def test_alerte_within_tolerance_minutes(self):
        result = evaluate_volume_tolerance(240, 220, settings=self.settings)
        self.assertEqual(result['statut'], 'alerte')
        self.assertEqual(result['ecart_minutes'], 20.0)

    def test_anomalie_beyond_tolerance(self):
        result = evaluate_volume_tolerance(240, 180, settings=self.settings)
        self.assertEqual(result['statut'], 'anomalie')

    def test_inactive_tolerance_reports_ecart_only(self):
        self.settings.tolerance_active = False
        self.settings.save()
        result = evaluate_volume_tolerance(240, 200, settings=self.settings)
        self.assertEqual(result['statut'], 'ecart')
        self.assertFalse(result['tolerance_active'])

    def test_threshold_uses_max_of_minutes_and_pct(self):
        threshold = tolerance_threshold_minutes(600, self.settings)
        self.assertEqual(threshold, 60.0)
