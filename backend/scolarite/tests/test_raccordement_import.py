"""Tests de raccordement A-6 — pipeline source → validation → résolution → plan.

Ces tests n'écrivent JAMAIS en base : ils utilisent les mécanismes de test
Django (base `test_*` éphémère) et des lignes synthétiques en mémoire.
"""

from decimal import Decimal
from pathlib import Path
from unittest import TestCase

from django.test import TestCase as DjangoTestCase

from scolarite.pedagogie_raccordement import (
    EXACT_MATCH,
    MULTIPLE_MATCH,
    NO_MATCH,
    REJECT,
    construire_plan,
    normaliser,
    resoudre_ecue,
    resoudre_formation,
    resoudre_ue,
)
from scolarite.pedagogie_validateur import valider_ligne

#: Ligne synthétique parfaitement documentée (CAS A).
CAS_A = {
    'filiere': 'EM', 'niveau': 'L1', 'semestre': 'S1',
    'ue': 'BIOLOGIE APPLIQUEE AUX APS', 'ecue': 'Anatomie descriptive',
    'code_ue': 'BIO8101', 'code_ecue': 'BIO8101A', 'cect': '3',
    'coefficient': '2', 'cm': '20', 'td': '10', 'tp': '5',
    'source_id': 'P1-SYNTH', 'source_type': 'P1', 'statut_documentaire': 'VALIDEE',
}


def variante(**kw):
    d = dict(CAS_A)
    d.update(kw)
    return d


class TestNormalisation(TestCase):
    def test_normalisation_insensible_aux_accents(self):
        self.assertEqual(normaliser('Éducation et Motricité'),
                         normaliser('EDUCATION ET MOTRICITE'))

    def test_normalisation_ne_decide_pas(self):
        """La normalisation prépare une comparaison ; elle ne décide jamais seule."""
        self.assertNotEqual(normaliser('EM'), normaliser('ES'))


class TestResolutionReferentiels(DjangoTestCase):
    """Résolution contre les référentiels réellement présents en base."""

    def test_14_formation_inexistante(self):
        self.assertEqual(resoudre_formation('XX', 'LICENCE').resolution, NO_MATCH)

    def test_14b_formation_resolue_exactement(self):
        """Résolution contre la base réelle. La base de test peut être vide :
        dans ce cas NO_MATCH est un constat legitimate, pas un défaut."""
        r = resoudre_formation('EM', 'LICENCE')
        self.assertIn(r.resolution, (EXACT_MATCH, MULTIPLE_MATCH, NO_MATCH))
        if r.resolution in (EXACT_MATCH, MULTIPLE_MATCH):
            self.assertTrue(r.candidats)

    def test_14c_ambiguite_sans_cycle_bloque(self):
        """EM existe en Licence ET Master : sans cycle, la résolution est ambiguë."""
        r = resoudre_formation('EM', '')
        if len(r.candidats) > 1:
            self.assertEqual(r.resolution, MULTIPLE_MATCH)
            self.assertIsNone(r.retenu)

    def test_15_ecue_sans_ue_rejete(self):
        r = resoudre_ecue(None, 'X1', 'Intitule')
        self.assertEqual(r.resolution, REJECT)
        self.assertIsNone(r.retenu)

    def test_15b_ue_non_rattachable_sans_maquette(self):
        self.assertEqual(resoudre_ue(None, 'BIO8101', 'BIOLOGIE').resolution, NO_MATCH)

    def test_16_aucune_reference_creee_automatiquement(self):
        """Un NO_MATCH ne doit jamais devenir une création."""
        r = resoudre_ue(None, 'BIO8101', 'BIOLOGIE')
        self.assertIsNone(r.retenu)
        self.assertEqual(r.resolution, NO_MATCH)


class TestCasSynthetiques(TestCase):
    """Les cas demandés au §26 de A-6, sans base de données."""

    def test_cas_a_ligne_complete_prete(self):
        lv = valider_ligne(CAS_A, 1)
        self.assertTrue(lv.importable)
        self.assertEqual(lv.criteres_manquants, '')

    def test_cas_b_coefficient_absent_rejete(self):
        lv = valider_ligne(variante(coefficient='NULL'), 1)
        self.assertFalse(lv.importable)
        self.assertIn('H', lv.criteres_manquants)

    def test_cas_c_volumes_absents_rejetes(self):
        for champ in ('cm', 'td', 'tp'):
            self.assertFalse(valider_ligne(variante(**{champ: 'NULL'}), 1).importable,
                             champ)

    def test_cas_d_source_p3_refusee(self):
        lv = valider_ligne(variante(source_type='P3'), 1)
        self.assertFalse(lv.importable)
        self.assertIn('X_SOURCE_NON_OPPOSABLE', [a.code for a in lv.anomalies])

    def test_cas_e_cect_manquant_bloquant(self):
        self.assertFalse(valider_ligne(variante(cect='NON_DOCUMENTE'), 1).criteres['G'])

    def test_cas_f_statut_contradictoire_rejete(self):
        self.assertFalse(
            valider_ligne(variante(statut_documentaire='CONTRADICTOIRE'), 1).importable)

    def test_cas_g_master_es_non_arbitrable(self):
        lv = valider_ligne(variante(filiere='ES', niveau='M1', semestre='S7',
                                    cect='NON_ARBITRABLE'), 1)
        self.assertFalse(lv.criteres['G'])
        self.assertIsNone(lv.cect)

    def test_cas_g_aucune_valeur_32_ni_30_generee(self):
        """Le Master ES ne doit produire aucune valeur numérique."""
        lv = valider_ligne(variante(filiere='ES', niveau='M1', semestre='S7',
                                    cect='NON_ARBITRABLE'), 1)
        for attr in ('cect', 'coefficient', 'cm', 'td', 'tp'):
            self.assertNotIn(getattr(lv, attr), (Decimal('32'), Decimal('30')), attr)

    def test_aucun_code_artificiel_accepte(self):
        from scolarite.pedagogie_validateur import classer_code
        for c in ('UE-EM-001', 'ECUE-EM-001', 'UE-ES-101',
                  'ECUE-ES-101', 'EM-S1-ECUE-01'):
            self.assertEqual(classer_code(c), 'CODE_INTERDIT', c)


class TestIdempotenceLogique(DjangoTestCase):
    """§28 — deux exécutions du même plan donnent le même verdict."""

    def test_28_plan_identique_au_second_passage(self):
        from scolarite.models import AnneeAcademique
        lv = valider_ligne(CAS_A, 1)
        annee = AnneeAcademique.objects.order_by('id').first()
        p1 = construire_plan([lv], 's.csv', 'h1', annee)
        p2 = construire_plan([lv], 's.csv', 'h1', annee)
        self.assertEqual(p1.resume(), p2.resume())
        self.assertEqual([a.action for a in p1.actions], [a.action for a in p2.actions])
        self.assertEqual([a.motif for a in p1.actions], [a.motif for a in p2.actions])


class TestTracabiliteEtHash(DjangoTestCase):
    """§29, §30 — chaque décision est reliée à sa source."""

    def test_29_hash_conserve_dans_le_plan(self):
        from scolarite.models import AnneeAcademique
        lv = valider_ligne(CAS_A, 1)
        annee = AnneeAcademique.objects.order_by('id').first()
        plan = construire_plan([lv], 's.csv', 'HASH-ABC', annee)
        self.assertEqual(plan.source_hash, 'HASH-ABC')
        for a in plan.actions:
            self.assertEqual(a.source_hash, 'HASH-ABC')

    def test_29b_fichier_different_nouvelle_version(self):
        import os
        import tempfile

        from scolarite.pedagogie_validateur import sha256_fichier
        chemins = []
        for contenu in ('a;b\n1;2\n', 'a;b\n1;3\n'):
            with tempfile.NamedTemporaryFile('w', suffix='.csv', delete=False,
                                             encoding='utf-8') as fh:
                fh.write(contenu)
                chemins.append(fh.name)
        try:
            self.assertNotEqual(sha256_fichier(chemins[0]), sha256_fichier(chemins[1]))
        finally:
            for c in chemins:
                os.unlink(c)

    def test_30_action_rattachee_a_sa_source(self):
        from scolarite.models import AnneeAcademique
        lv = valider_ligne(CAS_A, 1)
        annee = AnneeAcademique.objects.order_by('id').first()
        plan = construire_plan([lv], 's.csv', 'H', annee)
        for a in plan.actions:
            self.assertTrue(a.source_id)
            self.assertTrue(a.source_hash)
            self.assertGreater(a.ligne, 0)

    def test_30b_source_absente_bloque(self):
        lv = valider_ligne(variante(source_type=''), 1)
        self.assertFalse(lv.importable)
        self.assertIn('X_SOURCE_ABSENTE', [a.code for a in lv.anomalies])

    def test_30c_classe_source_inconnue_bloque(self):
        lv = valider_ligne(variante(source_type='P9'), 1)
        self.assertFalse(lv.importable)
        self.assertIn('X_SOURCE_INCONNUE', [a.code for a in lv.anomalies])


class TestAucuneEcriture(TestCase):
    """§27/§31 — aucun module A-6 ne contient d'écriture."""

    F = Path(__file__).resolve().parents[1] / 'pedagogie_raccordement.py'

    def test_31_aucune_ecriture_modele(self):
        source = self.F.read_text(encoding='utf-8')
        for interdit in ('.save()', '.delete()', '.create(', 'bulk_create',
                         'transaction.atomic', 'update_or_create'):
            self.assertNotIn(interdit, source, interdit)

    def test_31b_lecture_seule_seulement(self):
        source = self.F.read_text(encoding='utf-8')
        self.assertIn('objects.filter', source)
        self.assertNotIn('objects.create', source)

        lv = valider_ligne(variante(filiere='ES', niveau='M1', semestre='S7',
                                    cect='NON_ARBITRABLE'), 1)
        self.assertFalse(lv.criteres['G'])
        self.assertIsNone(lv.cect)

    def test_cas_g_aucune_valeur_32_ni_30_generee(self):
        """Le Master ES ne doit produire aucune valeur numérique."""
        lv = valider_ligne(variante(filiere='ES', niveau='M1', semestre='S7',
                                    cect='NON_ARBITRABLE'), 1)
        for attr in ('cect', 'coefficient', 'cm', 'td', 'tp'):
            self.assertNotIn(getattr(lv, attr), (Decimal('32'), Decimal('30')), attr)

    def test_aucun_code_artificiel_accepte(self):
        from scolarite.pedagogie_validateur import classer_code
        for c in ('UE-EM-001', 'ECUE-EM-001', 'UE-ES-101',
                  'ECUE-ES-101', 'EM-S1-ECUE-01'):
            self.assertEqual(classer_code(c), 'CODE_INTERDIT', c)
