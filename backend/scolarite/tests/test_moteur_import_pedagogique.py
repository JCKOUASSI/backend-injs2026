"""Tests du moteur d'import pédagogique INJS-LMD (A-5.4).

Aucun de ces tests n'accède à une base de données réelle : ils valident la
logique de contrôle seule. Le test critique est `test_staging_a53_refuse` :
le moteur doit REJETER le staging actuel — c'est un test de sécurité métier,
pas un échec.
"""

from decimal import Decimal
from pathlib import Path
from unittest import TestCase

from scolarite.pedagogie_validateur import (
    CODES_INTERDITS,
    ECTS_SEMESTRE,
    classer_code,
    controler_ECTS,
    controler_doublons,
    est_absent,
    nombre,
    normaliser_ligne,
    valider_ligne,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]

#: Ligne de référence parfaitement documentée (critères A→K tous PASS).
VALIDE = {
    'filiere': 'EM', 'niveau': 'L1', 'semestre': 'S1',
    'ue': 'BIOLOGIE APPLIQUEE AUX APS', 'ecue': 'Anatomie descriptive',
    'code_ue': 'BIO8101', 'code_ecue': 'BIO8101A', 'cect': '3',
    'coefficient': '2', 'cm': '20', 'td': '10', 'tp': '5',
    'source_id': 'P1-S16', 'source_type': 'P1', 'statut_documentaire': 'COMPLETE',
}


def variante(**kwargs):
    d = dict(VALIDE)
    d.update(kwargs)
    return d


class TestAbsenceEtConversion(TestCase):
    """Une absence ne doit JAMAIS devenir une valeur."""

    def test_sentinelles_reconnues(self):
        for v in ('NULL', '', 'NON_DOCUMENTE', 'NON_ARBITRABLE', None, 'n/a', '-'):
            self.assertTrue(est_absent(v), v)

    def test_absence_ne_devient_pas_zero(self):
        self.assertIsNone(nombre('NULL'))
        self.assertIsNone(nombre('NON_DOCUMENTE'))
        self.assertIsNone(nombre(''))
        self.assertIsNone(nombre(None))

    def test_nombres_reels_convertis(self):
        self.assertEqual(nombre('30'), Decimal('30'))
        self.assertEqual(nombre('2,5'), Decimal('2.5'))
        self.assertIsNone(nombre('abc'))


class TestAliasColonnes(TestCase):
    def test_alias_staging(self):
        d = normaliser_ligne({'intitule_ue': 'X', 'intitule_ecue': 'Y',
                              'statut': 'PARTIELLE', 'volume_cm': '10'})
        self.assertEqual(d['ue'], 'X')
        self.assertEqual(d['ecue'], 'Y')
        self.assertEqual(d['statut_documentaire'], 'PARTIELLE')
        self.assertEqual(d['cm'], '10')

    def test_colonne_inconnue_ignoree(self):
        d = normaliser_ligne({'ue': 'X', 'colonne_bidon': 'Y'})
        self.assertNotIn('colonne_bidon', d)


class TestGrilleAK(TestCase):
    def test_ligne_complete_est_importable(self):
        lv = valider_ligne(VALIDE, 1)
        self.assertTrue(lv.importable, lv.criteres_manquants)
        self.assertEqual(lv.statut_import, 'PRETE_A_VALIDER')

    def test_1_filiere_inconnue(self):
        lv = valider_ligne(variante(filiere='XX'), 1)
        self.assertFalse(lv.criteres['A'])
        self.assertFalse(lv.importable)

    def test_2_niveau_inconnu(self):
        self.assertFalse(valider_ligne(variante(niveau='L9'), 1).criteres['B'])

    def test_3_semestre_inconnu(self):
        self.assertFalse(valider_ligne(variante(semestre='S11'), 1).criteres['C'])

    def test_3b_semestre_incoherent_avec_niveau(self):
        self.assertFalse(valider_ligne(variante(niveau='L1', semestre='S7'), 1).criteres['C'])

    def test_4_ue_absente(self):
        self.assertFalse(valider_ligne(variante(ue='NULL'), 1).criteres['D'])

    def test_5_ecue_absent(self):
        self.assertFalse(valider_ligne(variante(ecue='NULL'), 1).criteres['E'])

    def test_6_relation_absente(self):
        self.assertFalse(valider_ligne(variante(ue='NULL', ecue='NULL'), 1).criteres['F'])

    def test_7_cect_absent(self):
        self.assertFalse(valider_ligne(variante(cect='NON_DOCUMENTE'), 1).criteres['G'])

    def test_9_coefficient_absent(self):
        self.assertFalse(valider_ligne(variante(coefficient='NULL'), 1).criteres['H'])

    def test_9b_coefficient_non_positif(self):
        self.assertFalse(valider_ligne(variante(coefficient='0'), 1).criteres['H'])

    def test_10_cm_absent(self):
        self.assertFalse(valider_ligne(variante(cm='NULL'), 1).criteres['I'])

    def test_11_td_absent(self):
        self.assertFalse(valider_ligne(variante(td='NULL'), 1).criteres['J'])

    def test_12_tp_absent(self):
        self.assertFalse(valider_ligne(variante(tp='NULL'), 1).criteres['K'])

    def test_13_source_p3_refusee(self):
        lv = valider_ligne(variante(source_type='P3'), 1)
        self.assertFalse(lv.importable)
        self.assertIn('X_SOURCE_NON_OPPOSABLE', [a.code for a in lv.anomalies])

    def test_13b_source_p4_refusee(self):
        self.assertFalse(valider_ligne(variante(source_type='P4'), 1).importable)

    def test_13c_source_p2_acceptee(self):
        self.assertTrue(valider_ligne(variante(source_type='P2'), 1).importable)

    def test_14_statut_contradictoire_bloquant(self):
        lv = valider_ligne(variante(statut_documentaire='CONTRADICTOIRE'), 1)
        self.assertFalse(lv.importable)

    def test_14b_statut_partiel_bloquant(self):
        self.assertFalse(valider_ligne(variante(statut_documentaire='PARTIELLE'), 1).importable)

    def test_14c_aucun_statut_nest_autrement_importable(self):
        """Le statut ne peut jamais Fabricquer l'importabilite."""
        for st in ('ABSENTE', 'PARTIELLE', 'CONTRADICTOIRE', 'A_VERIFIER', 'REJETEE'):
            self.assertFalse(valider_ligne(variante(statut_documentaire=st), 1).importable, st)

    def test_15_master_es_non_arbitre(self):
        lv = valider_ligne(variante(filiere='ES', niveau='M1', semestre='S7',
                                    cect='NON_ARBITRABLE'), 1)
        self.assertFalse(lv.criteres['G'])
        self.assertEqual(lv.statut_documentaire, 'COMPLETE')
        self.assertFalse(lv.importable)



class TestCodes(TestCase):
    def test_6_code_artificiel_interdit(self):
        for interdit in ('UE-EM-001', 'ECUE-EM-001', 'UE-ES-101',
                         'ECUE-ES-101', 'EM-S1-ECUE-01'):
            self.assertEqual(classer_code(interdit), 'CODE_INTERDIT', interdit)
            self.assertIn(interdit, CODES_INTERDITS)

    def test_code_artificiel_bloque_la_ligne(self):
        lv = valider_ligne(variante(code_ue='UE-EM-001'), 1)
        self.assertFalse(lv.importable)
        self.assertTrue(any('INTERDIT' in a.code for a in lv.anomalies))

    def test_code_ue_absent_signale(self):
        self.assertFalse(valider_ligne(variante(code_ue='NULL'), 1).importable)

    def test_code_ecue_absent_bloquant(self):
        lv = valider_ligne(variante(code_ecue='NON_DOCUMENTE'), 1)
        self.assertFalse(lv.importable)
        self.assertTrue(any('CODE_ECUE' in a.code for a in lv.anomalies))

    def test_aucun_code_genere_automatiquement(self):
        lv = valider_ligne(variante(code_ue='NULL', code_ecue='NULL'), 1)
        self.assertTrue(est_absent(lv.code_ue))
        self.assertTrue(est_absent(lv.code_ecue))

    def test_code_officiel_reconnu(self):
        self.assertEqual(classer_code('BIO8101', officiel=True), 'CODE_OFFICIEL')


class TestECTS(TestCase):
    def _lignes(self, cects, filiere='EM', semestre='S1', niveau='L1'):
        return [valider_ligne(variante(filiere=filiere, niveau=niveau, semestre=semestre,
                                       cect=str(c), code_ue=f'X{i:03d}1',
                                       code_ecue=f'X{i:03d}1A'), i + 1)
                for i, c in enumerate(cects)]

    def test_8_cect_total_correct(self):
        anomalies = controler_ECTS(self._lignes([5, 5, 5, 5, 5, 5]))
        self.assertEqual([a for a in anomalies if a.code == 'G_ECTS_SEMESTRE'], [])

    def test_8b_cect_total_faux_bloquant(self):
        anomalies = controler_ECTS(self._lignes([5, 5, 5, 5, 5, 4]))
        self.assertTrue([a for a in anomalies if a.code == 'G_ECTS_SEMESTRE'])
        self.assertTrue(all(a.niveau == 'ERREUR_BLOQUANTE' for a in anomalies))

    def test_8c_cect_non_corrige_automatiquement(self):
        lignes = self._lignes([5, 5, 5, 5, 5, 4])
        avant = [lv.cect for lv in lignes]
        controler_ECTS(lignes)
        self.assertEqual([lv.cect for lv in lignes], avant)

    def test_9_niveau_non_controle_si_semestre_manquant(self):
        anomalies = controler_ECTS(self._lignes([30]))
        self.assertEqual([a for a in anomalies if a.code == 'G_ECTS_NIVEAU'], [])

    def test_9b_niveau_controle_complet(self):
        l1 = self._lignes([15, 15], semestre='S1')
        l2 = self._lignes([15, 15], semestre='S2')
        anomalies = controler_ECTS(l1 + l2)
        self.assertEqual([a for a in anomalies if a.code == 'G_ECTS_NIVEAU'], [])

    def test_9c_niveau_non_equilibre_bloquant(self):
        l1 = self._lignes([20, 20], semestre='S1')
        l2 = self._lignes([20, 20], semestre='S2')
        anomalies = controler_ECTS(l1 + l2)
        self.assertTrue([a for a in anomalies if a.code == 'G_ECTS_NIVEAU'])

    def test_10_cect_licence_non_controlee_si_incomplet(self):
        lignes = []
        for s in ('S1', 'S2', 'S3', 'S4', 'S5'):
            lignes += self._lignes([30], semestre=s)
        anomalies = controler_ECTS(lignes)
        self.assertEqual([a for a in anomalies if a.code == 'G_ECTS_LICENCE'], [])


class TestDoublonsEtIdempotence(TestCase):
    def test_16_doublon_ue_detecte(self):
        l1 = valider_ligne(variante(code_ue='BIO8101', code_ecue='A1'), 1)
        l2 = valider_ligne(variante(code_ue='BIO8101', code_ecue='A2'), 2)
        anomalies = controler_doublons([l1, l2])
        self.assertTrue([a for a in anomalies if a.code == 'X_DOUBLON_UE'])

    def test_17_doublon_ecue_detecte(self):
        l1 = valider_ligne(variante(code_ue='BIO8101', code_ecue='A1'), 1)
        l2 = valider_ligne(variante(code_ue='BIO8101', code_ecue='A1'), 2)
        anomalies = controler_doublons([l1, l2])
        self.assertTrue([a for a in anomalies if a.code == 'X_DOUBLON_ECUE'])

    def test_18_idempotence_cle_fonctionnelle(self):
        """Rejouer le meme referentiel ne cree aucun doublon interne."""
        lignes = [valider_ligne(VALIDE, 1)]
        self.assertEqual(controler_doublons(lignes), [])

    def test_aucune_suppression_de_doublon(self):
        l1 = valider_ligne(variante(code_ue='B1', code_ecue='E1'), 1)
        l2 = valider_ligne(variante(code_ue='B1', code_ecue='E1'), 2)
        controler_doublons([l1, l2])
        self.assertEqual(len([l1, l2]), 2)


class TestSecuriteStagingA53(TestCase):
    """TEST CRITIQUE A-5.4 — le staging actuel doit etre REFUSE."""

    STAGING = (
        REPOSITORY_ROOT / 'workspace' / '26092026' / 'a53-express'
        / 'referentiel-pedagogique-staging.csv'
    )

    def test_27_staging_a53_entierement_refuse(self):
        if not self.STAGING.exists():
            self.skipTest('staging A-5.3 absent')
        from scolarite.pedagogie_validateur import valider_fichier
        r = valider_fichier(self.STAGING)
        self.assertEqual(len(r['lignes']), 80)
        self.assertEqual(sum(1 for lv in r['lignes'] if lv.importable), 0)

    def test_27b_aucune_cellule_importable(self):
        if not self.STAGING.exists():
            self.skipTest('staging A-5.3 absent')
        from scolarite.pedagogie_validateur import valider_fichier
        r = valider_fichier(self.STAGING)
        for lv in r['lignes']:
            self.assertFalse(
                lv.importable,
                f'ligne {lv.index} importable alors que le staging doit etre refuse')


class TestPasDEcritureBase(TestCase):
    """Aucun acces base de donnees dans le validateur ni dans la commande."""

    V = Path(__file__).resolve().parents[1] / 'pedagogie_validateur.py'
    C = (
        Path(__file__).resolve().parents[1] / 'management' / 'commands'
        / 'import_referentiel_pedagogique.py'
    )

    def test_28_validateur_sans_acces_db(self):
        source = self.V.read_text(encoding='utf-8')
        for interdit in ('from django.db', 'import django', '.save()', '.objects'):
            self.assertNotIn(interdit, source, interdit)

    def test_29_commande_refuse_apply(self):
        source = self.C.read_text(encoding='utf-8')
        self.assertIn("--apply n'est PAS implemente", source)
        # Aucune ECRITURE : .save() / .delete() / .create() / transaction
        for interdit in ('.save()', '.delete()', '.create(', 'bulk_create',
                         'transaction.atomic', 'update_or_create'):
            self.assertNotIn(interdit, source, interdit)
        # Les lectures (`objects.first()`, `objects.filter`) sont autorisées :
        # la simulation doit résoudre les référentiels existants.
