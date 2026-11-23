"""Tests des générateurs SVG pour l'accueil admin."""

import re

from django.template.loader import render_to_string
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


class AdminChartsRenderingTests(SimpleTestCase):
    """Les gabarits SVG doivent produire des nombres au format SVG (point décimal).

    Régression constatée le 2026-10-28 : Django localise les flottants en
    français, donc `x="46,0"` était émis. Une virgule est invalide en SVG :
    l'attribut est ignoré par le navigateur et retombe à 0, ce qui empilait
    tous les libellés de l'histogramme au bord gauche et cassait le camembert.
    """

    ATTRIBUTS_NUMERIQUES = ('x', 'y', 'cx', 'cy', 'r', 'rx', 'width', 'height', 'font-size')

    def _controler(self, html):
        nombre = re.compile(r'^-?\d+(\.\d+)?$')
        invalides = []
        for attribut in self.ATTRIBUTS_NUMERIQUES:
            motif = r'(?<![\w-])' + attribut + r'="([^"]*)"'
            for valeur in re.findall(motif, html):
                if attribut in ('width', 'height') and valeur.endswith('%'):
                    continue
                if not nombre.match(valeur):
                    invalides.append((attribut, valeur))
        return invalides

    def test_histogramme_attributs_valides(self):
        chart = build_histogram([
            {'label': 'avr. 2026', 'value': 4},
            {'label': 'mai 2026', 'value': 2},
            {'label': 'juin 2026', 'value': 0},
        ])
        html = render_to_string('admin/includes/chart_histogram.html', {'chart': chart})
        self.assertEqual(self._controler(html), [])

    def test_camembert_attributs_valides(self):
        chart = build_donut([
            {'label': 'Présent', 'value': 7, 'color': '#123456'},
            {'label': 'Absent', 'value': 3, 'color': '#654321'},
        ])
        html = render_to_string('admin/includes/chart_donut.html', {'chart': chart})
        self.assertEqual(self._controler(html), [])

    def test_libelles_histogramme_ne_se_chevauchent_pas(self):
        """La ligne la plus longue doit tenir dans l'espace entre deux barres."""
        chart = build_histogram([
            {'label': f'{m} 2026', 'value': 1}
            for m in ('janv.', 'févr.', 'mars', 'avr.', 'mai', 'juin')
        ])
        largeur_car = chart['label_font'] * 0.56
        for barre in chart['bars']:
            for ligne in barre['label_lines']:
                largeur = len(ligne) * largeur_car
                self.assertLessEqual(largeur, barre['bar_w'] + 12, ligne)
                # Le libellé centré ne doit pas sortir du cadre à gauche.
                self.assertGreaterEqual(barre['text_x'] - largeur / 2, 0, ligne)

    def test_libelles_sur_deux_lignes(self):
        """« sept. 2026 » doit être réparti sur deux lignes : mois puis année."""
        chart = build_histogram([{'label': 'sept. 2026', 'value': 3}])
        self.assertEqual(chart['bars'][0]['label_lines'], ['sept.', '2026'])
        # Libellé d'un seul mot : une seule ligne, pas de découpe artificielle.
        chart2 = build_histogram([{'label': 'Total', 'value': 3}])
        self.assertEqual(chart2['bars'][0]['label_lines'], ['Total'])
        self.assertIn('label_line_gap', chart2)
