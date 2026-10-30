"""Tests de régression du logo de l'en-tête de l'admin Django.

Contexte métier : le monogramme officiel INJS Abidjan (bleu #283A87) était
posé sur une plaque bleu nuit (#001a33) dans l'en-tête de l'admin : bleu sur
bleu, quasi illisible. Le logo officiel n'est pas retouché ; on utilise une
variante monochrome blanche du MÊME tracé géométrique (mêmes 6 tracés, même
viewBox), et la plaque a été agrandie.

Ces tests protègent trois choses :
1. la variante blanche reste géométriquement identique au logo officiel
   (aucune déformation, aucun filtre) ;
2. l'en-tête utilise bien la variante blanche sur la plaque sombre ;
3. l'ancien PNG base64 (bleu sur bleu) ne revient pas dans le gabarit.
"""

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


IMG_DIR = Path(settings.BASE_DIR) / 'static' / 'img'
OFFICIEL = IMG_DIR / 'logo-injs.svg'
BLANC = IMG_DIR / 'logo-injs-blanc.svg'
BASE_HTML = Path(settings.BASE_DIR) / 'templates' / 'admin' / 'base.html'


def _tracés(fichier):
    return re.findall(r'd="([^"]+)"', fichier.read_text(encoding='utf-8'))


def _viewbox(fichier):
    return re.search(r'viewBox="([^"]+)"', fichier.read_text(encoding='utf-8')).group(1)


class VarianteBlancheTests(SimpleTestCase):
    def test_variante_blanche_existe(self):
        self.assertTrue(BLANC.is_file(), f'variante blanche absente : {BLANC}')

    def test_geometrie_identique_au_logo_officiel(self):
        """Même nombre de tracés, mêmes tracés, même viewBox : logo non déformé."""
        self.assertEqual(
            len(_tracés(BLANC)), len(_tracés(OFFICIEL)),
            'la variante blanche ne doit pas ajouter ni retirer de tracé',
        )
        self.assertEqual(_tracés(BLANC), _tracés(OFFICIEL))
        self.assertEqual(_viewbox(BLANC), _viewbox(OFFICIEL))

    def test_toutes_les_couleurs_passent_en_blanc(self):
        """Le logo officiel utilise plusieurs nuances de bleu : aucune ne doit subsister."""
        couleurs = set(re.findall(r'fill="([^"]+)"', BLANC.read_text(encoding='utf-8')))
        self.assertEqual(couleurs, {'#FFFFFF'})

    def test_transformations_identiques_au_logo_officiel(self):
        """Le logo officiel place ses tracés par ``transform="translate(...)"``.

        On n'interdit donc pas les transformations : on vérifie qu'elles sont
        exactement celles du fichier officiel (aucun déplacement introduit).
        """
        motif = r'transform="([^"]+)"'
        officiel = re.findall(motif, OFFICIEL.read_text(encoding='utf-8'))
        variante = re.findall(motif, BLANC.read_text(encoding='utf-8'))
        self.assertTrue(officiel, 'le logo officiel devrait contenir des transformations')
        self.assertEqual(variante, officiel)

    def test_aucun_filtre_ni_degradé(self):
        contenu = BLANC.read_text(encoding='utf-8')
        for interdit in ('<filter', 'feColorMatrix', '<linearGradient', 'opacity='):
            self.assertNotIn(interdit, contenu, f'{interdit} interdit : le tracé doit rester net')

    def test_le_mot_abidjan_reste_blanc(self):
        """Le libellé ABIDJAN fait partie du logo officiel : il doit passer en blanc."""
        contenu = BLANC.read_text(encoding='utf-8')
        self.assertIn('>ABIDJAN</text>', contenu)
        bloc_text = re.search(r'<text\b(.*?)>ABIDJAN</text>', contenu, re.S).group(1)
        self.assertIn('fill="#FFFFFF"', bloc_text)


class EnteteAdminTests(SimpleTestCase):
    def setUp(self):
        self.html = BASE_HTML.read_text(encoding='utf-8')

    def test_en_tete_utilise_la_variante_blanche(self):
        self.assertIn("img/logo-injs-blanc.svg", self.html)

    def test_en_tete_n_inline_plus_le_png_base64(self):
        """Le PNG base64 bleu (illisible sur la plaque sombre) a été retiré."""
        self.assertNotIn('data:image/png;base64', self.html)

    def test_plaque_sombre_et_logo_agrandis(self):
        """Plaque 52 px (avant 40) et icône 44 px (avant 32)."""
        self.assertIn('width: 52px !important;', self.html)
        self.assertIn('background: #001a33 !important;', self.html)
        bloc = re.search(r'\.injs-brand-icon\s*\{(.*?)\}', self.html, re.S).group(1)
        self.assertIn('width: 44px !important;', bloc)

    def test_libelle_accessible_conserve(self):
        """Le texte alternatif nomme l'établissement : lecteur d'écran servi."""
        self.assertIn('alt="INJS Abidjan"', self.html)
