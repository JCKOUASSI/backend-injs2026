"""L'administration ne dépend d'aucune ressource réseau externe.

Constat (capture d'écran réelle du 31/10/2026). L'admin chargeait Inter et la
police d'icônes « Material Symbols » depuis ``fonts.googleapis.com``. Dans un
environnement sans accès à ce domaine — le cas de la passerelle d'aperçu, et
d'un poste INJS derrière un proxy filtrant — le navigateur affichait le nom
littéral des icônes à la place des pictogrammes : « chevron_right » en clair
dans la barre latérale, « open_in_new », « filter_list »… La typographie
retombait sur une police système. L'écran restait « fonctionnel » mais illisible.

Correctif. Les deux fichiers sont désormais **versionnés** dans
``backend/static/admin/fonts/`` avec leurs licences (OFL pour Inter, Apache 2.0
pour Material Symbols) et déclarés en ``@font-face`` dans ``custom_admin.css``.

Ce que ce test protège :

1. aucune référence à un domaine de polices externe ne revient dans les
   gabarits ou les feuilles de style de l'admin ;
2. les fichiers de police déclarés existent réellement et sont servis ;
3. la liste des icônes du sous-ensemble correspond exactement aux icônes
   utilisées par les gabarits et la configuration — sinon une icône ajoutée
   sans régénérer le sous-ensemble s'afficherait en toutes lettres, et
   personne ne le verrait avant une capture d'écran.
"""

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

BACKEND = Path(settings.BASE_DIR)
STATIC = BACKEND / 'static' / 'admin'
TEMPLATES = BACKEND / 'templates' / 'admin'
FONTS = STATIC / 'fonts'

#: Domaines de polices distants — bannis de l'admin.
DOMAINES_BANNIS = ('fonts.googleapis.com', 'fonts.gstatic.com', 'use.typekit.net')

#: Nom de police d'icônes tel qu'il apparaît dans le CSS.
FAMILLE_ICONES = 'Material Symbols Outlined'
FAMILLE_TEXTE = 'Inter'


def _fichiers_textes(dossier, suffixes):
    return sorted(
        chemin for chemin in dossier.rglob('*')
        if chemin.is_file() and chemin.suffix in suffixes
    )


class RessourcesLocalesAdminTests(SimpleTestCase):

    def test_aucune_police_distante_dans_les_gabarits(self):
        fautifs = []
        for chemin in _fichiers_textes(TEMPLATES, {'.html'}):
            contenu = chemin.read_text(encoding='utf-8')
            for domaine in DOMAINES_BANNIS:
                if domaine in contenu:
                    fautifs.append(f'{chemin.relative_to(BACKEND)} → {domaine}')
        self.assertEqual(
            fautifs, [],
            'L’admin doit rester utilisable sans réseau : remplacer ces liens '
            'par les fichiers de static/admin/fonts/ '
            f'({", ".join(fautifs)}).',
        )

    def test_aucun_import_de_police_distante_dans_le_css(self):
        fautifs = []
        for chemin in _fichiers_textes(STATIC, {'.css'}):
            contenu = chemin.read_text(encoding='utf-8')
            for domaine in DOMAINES_BANNIS:
                # Le commentaire d'explication cite le domaine : seul un
                # `@import` ou une `url(...)` comptent comme dépendance.
                for motif in (rf'@import[^;]*{re.escape(domaine)}',
                              rf'url\([^)]*{re.escape(domaine)}'):
                    if re.search(motif, contenu):
                        fautifs.append(f'{chemin.relative_to(BACKEND)} → {domaine}')
        self.assertEqual(fautifs, [], f'Polices distantes encore chargées : {fautifs}')

    def test_les_fichiers_de_police_existent(self):
        attendus = {
            'inter-latin-wght.woff2',
            'material-symbols-outlined-subset.woff2',
            'LICENSE-inter.txt',
            'LICENSE-material-symbols.txt',
            'README.txt',
        }
        presents = {chemin.name for chemin in FONTS.iterdir() if chemin.is_file()}
        self.assertEqual(attendus - presents, set(), 'Fichiers de police manquants')
        for nom in ('inter-latin-wght.woff2', 'material-symbols-outlined-subset.woff2'):
            # Un fichier tronqué ou vide passerait un simple test d'existence.
            self.assertGreater((FONTS / nom).stat().st_size, 10_000, nom)
            self.assertEqual((FONTS / nom).read_bytes()[:4], b'wOF2', f'{nom} n’est pas un woff2')

    def test_le_css_declare_les_deux_familles_en_local(self):
        css = (STATIC / 'custom_admin.css').read_text(encoding='utf-8')
        self.assertRegex(css, rf"@font-face\s*\{{[^}}]*font-family:\s*'{FAMILLE_TEXTE}'",
                         'Inter doit être déclarée en @font-face local')
        self.assertRegex(css, rf"@font-face\s*\{{[^}}]*font-family:\s*'{FAMILLE_ICONES}'",
                         'La police d’icônes doit être déclarée en @font-face local')
        self.assertIn("url('fonts/inter-latin-wght.woff2')", css)
        self.assertIn("url('fonts/material-symbols-outlined-subset.woff2')", css)

    def test_toutes_les_icones_utilisees_sont_dans_le_sous_ensemble(self):
        """Une icône hors sous-ensemble s'afficherait en toutes lettres."""
        liste = FONTS / 'README.txt'
        declarees = set()
        dans_liste = False
        for ligne in liste.read_text(encoding='utf-8').splitlines():
            if ligne.startswith('Glyphes conservés'):
                dans_liste = True
                continue
            if dans_liste and ligne.strip().startswith('- '):
                declarees.add(ligne.strip()[2:].strip())
        self.assertGreater(len(declarees), 20, 'Liste des glyphes illisible dans README.txt')

        utilisees = set()
        motif_gabarit = re.compile(
            r'material-symbols-outlined[^>]*>\s*([a-z0-9_]+)\s*<')
        for chemin in _fichiers_textes(TEMPLATES, {'.html'}):
            utilisees |= set(motif_gabarit.findall(chemin.read_text(encoding='utf-8')))
        for chemin in sorted(BACKEND.glob('config/admin_*.py')):
            contenu = chemin.read_text(encoding='utf-8')
            utilisees |= set(re.findall(r"'icon'\s*:\s*'([a-z0-9_]+)'", contenu))

        self.assertTrue(utilisees, 'Aucune icône détectée : le motif de recherche a-t-il changé ?')
        manquantes = sorted(utilisees - declarees)
        self.assertEqual(
            manquantes, [],
            'Icônes utilisées mais absentes du sous-ensemble de police : '
            f'{manquantes}. Régénérer le sous-ensemble (recette dans '
            'static/admin/fonts/README.txt) ou choisir une icône existante.',
        )
