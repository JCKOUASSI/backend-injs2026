"""Tests des générateurs SVG pour l'accueil admin."""

from django.test import SimpleTestCase

from config.admin_charts import build_donut, build_histogram, build_stacked_bars


class AdminChartsTests(SimpleTestCase):
    def test_build_histogram_empty(self):
        self.assertIsNone(build_histogram([]))

    def test_build_histogram_bars(self):
        chart = build_histogram([
            {'label': 'jan. 2026', 'value': 10},
            {'label': 'fév. 2026', 'value': 5},
        ])
        self.assertEqual(len(chart['bars']), 2)
        self.assertGreater(chart['bars'][0]['bar_h'], chart['bars'][1]['bar_h'])
        self.assertEqual(chart['bars'][0]['text_x'], chart['bars'][0]['x'] + chart['bars'][0]['bar_w'] / 2)

    def test_build_donut_empty(self):
        self.assertIsNone(build_donut([]))
        self.assertIsNone(build_donut([{'label': 'A', 'value': 0, 'color': '#000'}]))

    def test_build_donut_slices(self):
        chart = build_donut([
            {'label': 'Présent', 'value': 75, 'color': '#0e58ab'},
            {'label': 'Absent', 'value': 25, 'color': '#ea9d0c'},
        ])
        self.assertEqual(chart['total'], 100)
        self.assertEqual(len(chart['slices']), 2)
        self.assertEqual(chart['slices'][0]['pct'], 75)
        self.assertTrue(chart['slices'][0]['path'].startswith('M'))

    def test_build_donut_single_full_slice(self):
        chart = build_donut([
            {'label': 'Badgé, liaison inactive', 'value': 2, 'color': '#ea9d0c'},
        ])
        self.assertEqual(chart['total'], 2)
        self.assertEqual(len(chart['slices']), 1)
        self.assertEqual(chart['slices'][0]['pct'], 100)
        self.assertEqual(chart['slices'][0]['path'].count('A'), 2)

    def test_build_stacked_bars(self):
        rows = build_stacked_bars([
            {'label': 'jan.', 'presents': 80, 'absents': 20},
            {'label': 'fév.', 'presents': 0, 'absents': 0},
        ])
        self.assertEqual(rows[0]['first_pct'], 80.0)
        self.assertEqual(rows[0]['second_pct'], 20.0)
        self.assertEqual(rows[1]['first_pct'], 0.0)
