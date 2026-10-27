"""Tests P00-08 — snapshots de contrat d'API.

Le test principal (``compare_api_contract``) garantit que le schéma courant
n'a ni route ni clé supprimée/renommée par rapport au snapshot figé dans
``docs/api/contract.snapshot.json``. Les ajouts sont autorisés.
"""

import json
import os

from django.test import SimpleTestCase

from config.api_contract import (
    build_contract,
    diff_contract,
    snapshot_path,
)


def _mini_contrat():
    """Contrat jouet couvrant paramètres, corps de requête et codes réponses."""
    return {
        'routes': {
            'GET /api/test/': {
                'parameters': ['search'],
                'request_keys': None,
                'responses': {
                    '200': {'count': None, 'results': {'[]': {'id': None, 'nom': None}}},
                },
            },
            'POST /api/test/': {
                'parameters': [],
                'request_keys': {'nom': None},
                'responses': {'201': {'id': None}},
            },
        }
    }


class ApiContractMoteurTests(SimpleTestCase):
    def test_contrats_identiques_aucune_rupture(self):
        contrat = _mini_contrat()
        self.assertEqual(diff_contract(contrat, contrat), [])

    def test_ajout_de_route_et_de_cle_autorise(self):
        snapshot = _mini_contrat()
        courant = _mini_contrat()
        courant['routes']['GET /api/nouveau/'] = {
            'parameters': [], 'request_keys': None, 'responses': {'200': {'x': None}},
        }
        courant['routes']['GET /api/test/']['responses']['200']['nouvelle_cle'] = None
        self.assertEqual(diff_contract(courant, snapshot), [])

    def test_route_supprimee_detectee(self):
        courant = _mini_contrat()
        del courant['routes']['POST /api/test/']
        ruptures = diff_contract(courant, _mini_contrat())
        self.assertTrue(any('POST /api/test/' in r and 'Route' in r for r in ruptures))

    def test_cle_de_reponse_supprimee_detectee(self):
        courant = _mini_contrat()
        del courant['routes']['GET /api/test/']['responses']['200']['results']
        ruptures = diff_contract(courant, _mini_contrat())
        self.assertTrue(any('results' in r for r in ruptures))

    def test_cle_d_element_de_tableau_supprimee_detectee(self):
        snapshot = _mini_contrat()
        courant = _mini_contrat()
        del courant['routes']['GET /api/test/']['responses']['200']['results']['[]']['nom']
        ruptures = diff_contract(courant, snapshot)
        self.assertTrue(any('nom' in r for r in ruptures))

    def test_parametre_supprime_detecte(self):
        courant = _mini_contrat()
        courant['routes']['GET /api/test/']['parameters'] = []
        ruptures = diff_contract(courant, _mini_contrat())
        self.assertTrue(any('paramètre' in r and 'search' in r for r in ruptures))

    def test_cle_de_requete_supprimee_detectee(self):
        courant = _mini_contrat()
        courant['routes']['POST /api/test/']['request_keys'] = {}
        ruptures = diff_contract(courant, _mini_contrat())
        self.assertTrue(any('requête' in r and 'nom' in r for r in ruptures))

    def test_code_de_reponse_supprime_detecte(self):
        courant = _mini_contrat()
        courant['routes']['POST /api/test/']['responses'] = {'400': None}
        ruptures = diff_contract(courant, _mini_contrat())
        self.assertTrue(any('201' in r for r in ruptures))


class CompareApiContractSnapshotTests(SimpleTestCase):
    """compare_api_contract — le snapshot déposé fait foi de non-régression."""

    def test_le_snapshot_existe(self):
        self.assertTrue(
            os.path.exists(snapshot_path()),
            'docs/api/contract.snapshot.json absent : lancez export_api_contract.',
        )

    def test_api_courante_conforme_au_snapshot(self):
        with open(snapshot_path(), encoding='utf-8') as fh:
            snapshot = json.load(fh)
        courant = build_contract()
        ruptures = diff_contract(courant, snapshot)
        self.assertEqual(
            ruptures, [],
            'Ruptures du contrat d’API :\n  '
            + '\n  '.join(ruptures)
            + '\nRenouvelez avec update_api_contract --justification "…" si volontaire.',
        )

    def test_les_routes_p00_06_et_p00_08_sont_contractualisees(self):
        contrat = build_contract()
        self.assertIn('GET /api/auth/capabilities/', contrat['routes'])
        self.assertIn('GET /api/parametres/flags/', contrat['routes'])
        caps = contrat['routes']['GET /api/auth/capabilities/']['responses']['200']
        self.assertIn('capacites', caps)
        self.assertIn('perimetres', caps)
        self.assertIn('niveau', caps)
        flags = contrat['routes']['GET /api/parametres/flags/']['responses']['200']
        self.assertIn('flags', flags)
