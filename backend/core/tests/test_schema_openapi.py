"""Non-régression sur le schéma OpenAPI.

Avant correctif, `manage.py spectacular` émettait 1 032 avertissements
« operationId … has collisions » : la classe standard supprime les paramètres
de chemin avant de construire l'identifiant, donc `/formations/{id}/formateurs/`
et `/formations/formateurs/{id}/` recevaient le même `operationId`. Les
clients générés perdaient alors une des deux opérations.

Ce test échoue si un doublon réapparaît.
"""

from django.test import TestCase
from drf_spectacular.generators import SchemaGenerator

METHODES = ('get', 'post', 'put', 'patch', 'delete')


class SchemaOpenAPITests(TestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        generateur = SchemaGenerator()
        cls.schema = generateur.get_schema(request=None, public=True)

    def _operations(self):
        for chemin, methodes in self.schema['paths'].items():
            for methode, operation in methodes.items():
                if methode in METHODES:
                    yield chemin, methode, operation

    def test_les_operation_id_sont_uniques(self):
        identifiants = [operation['operationId']
                        for _, _, operation in self._operations()]
        self.assertGreater(len(identifiants), 500, 'Schéma suspicieusement vide.')
        doublons = sorted({
            identifiant for identifiant in identifiants
            if identifiants.count(identifiant) > 1
        })
        self.assertEqual(
            doublons, [],
            'operationId dupliqués dans le schéma OpenAPI : '
            f'{doublons[:5]} — un client généré perdrait ces opérations.',
        )

    def test_les_parametres_de_chemin_distinguent_les_routes(self):
        """`…/{id}/formateurs/` et `…/formateurs/{id}/` restent distincts."""
        identifiants = {operation['operationId'] for _, _, operation in self._operations()}
        self.assertTrue(
            any('by_id' in identifiant for identifiant in identifiants),
            'Les paramètres de chemin ne sont plus repris dans les operationId.',
        )
