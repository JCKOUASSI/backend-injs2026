"""Tests purs du garde-fou de cible du script de comptes démo.

Ces tests n'initialisent pas Django, n'ouvrent aucune base et n'exécutent pas
le script de création.
"""
import importlib.util
from pathlib import Path
import unittest


SCRIPT = Path(__file__).resolve().parents[3] / 'scripts' / 'creer_comptes_demo.py'
spec = importlib.util.spec_from_file_location('creer_comptes_demo_guard', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class DemoAccountsTargetGuardTests(unittest.TestCase):
    def setUp(self):
        self.base_dir = Path('/sandbox/backend')
        self.sqlite = {
            'default': {
                'ENGINE': 'django.db.backends.sqlite3',
                'NAME': str(self.base_dir / 'db_sandbox.sqlite3'),
            },
        }

    def env(self, **values):
        result = {'DEMO_ACCOUNTS_ALLOW': '1', 'USE_SQLITE': '1'}
        result.update(values)
        return result

    def test_accepte_la_sqlite_sandbox_explicitement_autorisee(self):
        cible = module.valider_cible_demo(self.sqlite, self.base_dir, self.env())
        self.assertEqual(cible, (self.base_dir / 'db_sandbox.sqlite3').resolve())

    def test_refuse_une_sqlite_hors_emplacement(self):
        config = {'default': {**self.sqlite['default'], 'NAME': '/tmp/autre.sqlite3'}}
        with self.assertRaisesRegex(RuntimeError, 'chemin SQLite'):
            module.valider_cible_demo(config, self.base_dir, self.env())

    def test_refuse_postgresql(self):
        config = {'default': {'ENGINE': 'django.db.backends.postgresql', 'NAME': 'demo'}}
        with self.assertRaisesRegex(RuntimeError, 'PostgreSQL'):
            module.valider_cible_demo(config, self.base_dir, self.env())

    def test_refuse_configuration_absente_ou_ambiguë(self):
        with self.assertRaisesRegex(RuntimeError, 'DEMO_ACCOUNTS_ALLOW'):
            module.valider_cible_demo(self.sqlite, self.base_dir, {})
        with self.assertRaisesRegex(RuntimeError, 'alias'):
            module.valider_cible_demo({'default': self.sqlite['default'], 'other': {}}, self.base_dir, self.env())

    def test_refuse_substitution_de_base_non_sqlite(self):
        with self.assertRaisesRegex(RuntimeError, 'USE_SQLITE'):
            module.valider_cible_demo(self.sqlite, self.base_dir, {'DEMO_ACCOUNTS_ALLOW': '1'})
