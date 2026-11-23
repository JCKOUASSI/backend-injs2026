"""Protection BASE de l'immuabilité, spécifique PostgreSQL (prod / CI).

Les déclencheurs ``BEFORE UPDATE/DELETE`` sont posés par la migration
``0002_triggers_immuabilite``. Ce fichier ne s'exécute que sur PostgreSQL ;
sur SQLite (développement), l'immuabilité est garantie et testée au niveau
ORM dans ``test_journal``.

``TransactionTestCase`` est requis : une exception levée par un déclencheur
annulerait la transaction englobante d'un ``TestCase`` classique.
"""
import unittest

from django.db import connection
from django.test import TransactionTestCase

from habilitations.services.journalisation import journaliser


@unittest.skipUnless(
    connection.vendor == 'postgresql',
    "Les déclencheurs d'immuabilité base ne sont posés que sur PostgreSQL.",
)
class DeclencheursImmuabiliteTests(TransactionTestCase):
    def setUp(self):
        journaliser('CONNEXION', motif='test trigger')

    def test_update_brut_en_sql_est_bloque_par_la_base(self):
        with connection.cursor() as curseur, self.assertRaises(Exception):
            curseur.execute(
                "UPDATE habilitations_journalhabilitation "
                "SET motif = 'altéré' WHERE numero = 1"
            )

    def test_delete_brut_en_sql_est_bloque_par_la_base(self):
        with connection.cursor() as curseur, self.assertRaises(Exception):
            curseur.execute(
                "DELETE FROM habilitations_journalhabilitation WHERE numero = 1"
            )
