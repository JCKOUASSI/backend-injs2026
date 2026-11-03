"""Les documents livrés ne doivent pas se contredire.

Constat. Le document de conception GET-INJS existait en deux exemplaires : à la
racine du dépôt et sous `docs/getinjs/`. Les deux avaient divergé — 1 180 lignes
d'un côté, 713 de l'autre. Un lecteur qui ouvre la copie `docs/` lit donc un
état périmé du projet, avec des compteurs de tests faux et des sections
manquantes : c'est pire qu'une absence de documentation, parce que le document
a l'air à jour.

Que faut-il faire de deux copies ? Les fusionner en supprimant l'une serait une
perte : la copie `docs/` est celle que sert le site de documentation. On garde
donc les deux, la racine faisant foi, et **un test empêche la dérive** : il
échoue dès que les deux fichiers diffèrent, en disant exactement quoi exécuter.

Ce test ne vérifie pas le CONTENU (un document se relit, il ne s'auto-évalue
pas) : il vérifie qu'il n'existe qu'une seule version du contenu.
"""

from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

RACINE = Path(settings.BASE_DIR).parent
DOCUMENT = 'Conception-GET-INJS.txt'


class DocumentConceptionTests(SimpleTestCase):

    def setUp(self):
        self.source = RACINE / DOCUMENT
        self.copie = RACINE / 'docs' / 'getinjs' / DOCUMENT

    def test_le_document_existe_a_la_racine(self):
        self.assertTrue(self.source.is_file(), f'{self.source} est absent')

    def test_la_copie_pour_le_site_existe(self):
        self.assertTrue(
            self.copie.is_file(),
            'La copie servie par docs/ est absente : le site de documentation '
            'n’aurait plus de document de conception.',
        )

    def test_les_deux_copies_sont_identiques(self):
        contenu_source = self.source.read_text(encoding='utf-8')
        contenu_copie = self.copie.read_text(encoding='utf-8')
        self.assertEqual(
            contenu_source, contenu_copie,
            'Les deux exemplaires du document de conception ont divergé. '
            f'La racine fait foi : exécuter `cp {DOCUMENT} docs/getinjs/` '
            'depuis la racine du dépôt, puis relire le diff avant de committer.',
        )

    def test_la_copie_n_est_pas_vide(self):
        """Une copie tronquée passerait le test d'égalité si les deux étaient vides."""
        self.assertGreater(len(self.source.read_text(encoding='utf-8')), 5000)
