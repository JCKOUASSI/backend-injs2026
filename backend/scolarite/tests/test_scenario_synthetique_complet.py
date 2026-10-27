"""Tests de finalisation A-FINAL — scénario synthétique complet + négatifs.

Objectif : prouver que le moteur sait reconnaître une donnée IMPORTABLE
(chemin nominal) ET bloquer les 16 écarts critiques, le tout sans aucune
écriture en base.
"""

from decimal import Decimal
from unittest import TestCase

from django.test import TestCase as DjangoTestCase

from scolarite.pedagogie_raccordement import (
    REJECT,
    resoudre_ecue,
    resoudre_ue,
)
from scolarite.pedagogie_validateur import classer_code, valider_ligne

#: Scénario nominal complet : Formation, L1, S1, UE, ECUE, codes, CECT,
#: coefficient, CM, TD, TP, source P1, statut VALIDEE.
COMPLET = {
    'filiere': 'EM', 'niveau': 'L1', 'semestre': 'S1',
    'ue': 'BIOLOGIE APPLIQUEE AUX APS', 'ecue': 'Anatomie descriptive',
    'code_ue': 'BIO8101', 'code_ecue': 'BIO8101A', 'cect': '3',
    'coefficient': '2', 'cm': '20', 'td': '10', 'tp': '5',
    'source_id': 'P1-SYNTH', 'source_type': 'P1', 'statut_documentaire': 'VALIDEE',
}


def v(**kw):
    d = dict(COMPLET)
    d.update(kw)
    return d


class TestScenarioComplet(TestCase):
    """§24 — le moteur doit conclure IMPORTABLE = TRUE, sans écrire."""

    def test_24_scenario_complet_importable(self):
        lv = valider_ligne(COMPLET, 1)
        self.assertTrue(lv.importable, lv.criteres_manquants)
        self.assertEqual(lv.criteres_manquants, '')

    def test_24b_les_11_criteres_passent(self):
        lv = valider_ligne(COMPLET, 1)
        for critere in 'ABCDEFGHIJK':
            self.assertTrue(lv.criteres[critere], critere)

    def test_24c_valeurs_conservees_telles_quelles(self):
        lv = valider_ligne(COMPLET, 1)
        self.assertEqual(lv.cect, Decimal('3'))
        self.assertEqual(lv.coefficient, Decimal('2'))
        self.assertEqual(lv.cm, Decimal('20'))
        self.assertEqual(lv.td, Decimal('10'))
        self.assertEqual(lv.tp, Decimal('5'))

    def test_24d_aucune_valeur_par_defaut(self):
        """Aucun champ ne doit être comblé : la ligne porte déjà tout."""
        lv = valider_ligne(COMPLET, 1)
        for attr in ('cect', 'coefficient', 'cm', 'td', 'tp'):
            self.assertIsNotNone(getattr(lv, attr), attr)


class TestNegatifsCritiques(TestCase):
    """§25 — les 16 écarts doivent tous être bloqués."""

    def test_n01_ue_sans_code(self):
        lv = valider_ligne(v(code_ue='NON_DOCUMENTE'), 1)
        self.assertFalse(lv.importable)
        self.assertIn('X_CODE_UE_ABSENT', [a.code for a in lv.anomalies])

    def test_n02_ecue_sans_code(self):
        lv = valider_ligne(v(code_ecue='NON_DOCUMENTE'), 1)
        self.assertFalse(lv.importable)
        self.assertIn('X_CODE_ECUE_ABSENT', [a.code for a in lv.anomalies])

    def test_n03_coefficient_absent(self):
        self.assertFalse(valider_ligne(v(coefficient='NULL'), 1).criteres['H'])

    def test_n04_cm_absent(self):
        self.assertFalse(valider_ligne(v(cm='NULL'), 1).criteres['I'])

    def test_n05_td_absent(self):
        self.assertFalse(valider_ligne(v(td='NULL'), 1).criteres['J'])

    def test_n06_tp_absent(self):
        self.assertFalse(valider_ligne(v(tp='NULL'), 1).criteres['K'])

    def test_n07_cect_incorrect(self):
        """CECT non numérique : sentinelle d'absence, jamais 0."""
        lv = valider_ligne(v(cect='NON_DOCUMENTE'), 1)
        self.assertFalse(lv.criteres['G'])
        self.assertIsNone(lv.cect)

    def test_n07b_cect_negatif(self):
        self.assertFalse(valider_ligne(v(cect='-3'), 1).criteres['G'])

    def test_n08_source_p3(self):
        lv = valider_ligne(v(source_type='P3'), 1)
        self.assertFalse(lv.importable)
        self.assertIn('X_SOURCE_NON_OPPOSABLE', [a.code for a in lv.anomalies])

    def test_n09_source_contradictoire(self):
        lv = valider_ligne(v(statut_documentaire='CONTRADICTOIRE'), 1)
        self.assertFalse(lv.importable)
        self.assertIn('X_STATUT_NON_IMPORTABLE', [a.code for a in lv.anomalies])

    def test_n10_code_artificiel(self):
        for c in ('UE-EM-001', 'ECUE-EM-001', 'UE-ES-101',
                  'ECUE-ES-101', 'EM-S1-ECUE-01'):
            self.assertEqual(classer_code(c), 'CODE_INTERDIT', c)
            lv = valider_ligne(v(code_ue=c), 1)
            self.assertFalse(lv.importable, c)

    def test_n11_doublon_code_ue(self):
        from scolarite.pedagogie_validateur import controler_doublons
        l1 = valider_ligne(v(code_ecue='A'), 1)
        l2 = valider_ligne(v(code_ecue='A'), 2)
        self.assertTrue([a for a in controler_doublons([l1, l2])
                         if a.code == 'X_DOUBLON_UE'])

    def test_n12_master_es_non_arbitre(self):
        lv = valider_ligne(v(filiere='ES', niveau='M1', semestre='S7',
                             cect='NON_ARBITRABLE'), 1)
        self.assertFalse(lv.importable)
        self.assertIsNone(lv.cect)
        self.assertNotIn(lv.cect, (Decimal('32'), Decimal('30')))

    def test_n13_filiere_inconnue(self):
        self.assertFalse(valider_ligne(v(filiere='XX'), 1).criteres['A'])

    def test_n14_niveau_inconnu(self):
        self.assertFalse(valider_ligne(v(niveau='L9'), 1).criteres['B'])

    def test_n15_semestre_inconnu(self):
        self.assertFalse(valider_ligne(v(semestre='S11'), 1).criteres['C'])

    def test_n16_relation_ue_ecue_absente(self):
        self.assertFalse(valider_ligne(v(ue='NULL', ecue='NULL'), 1).criteres['F'])


class TestRattachementSecurise(TestCase):
    """§17 — pas de fallback heuristique."""

    def test_ecue_sans_ue_rejete(self):
        r = resoudre_ecue(None, 'X', 'Intitule')
        self.assertEqual(r.resolution, REJECT)

    def test_ue_sans_maquette_non_rattachee(self):
        r = resoudre_ue(None, 'BIO8101', 'BIOLOGIE')
        self.assertIsNone(r.retenu)
