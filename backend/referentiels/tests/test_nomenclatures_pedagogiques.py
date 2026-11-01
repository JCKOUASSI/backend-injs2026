"""Nomenclatures pédagogiques importées (évaluations, jurys, espaces sportifs).

Les quatre référentiels pédagogiques du tableau de bord — types
d'enseignement, d'espace sportif, d'évaluation et de décision — doivent
être complètement renseignés : chaque valeur porte code, libellé,
description, source documentaire et fiabilité explicite (aucune valeur
« à renseigner »), et l'import reste idempotent.
"""
import json
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase

from referentiels.models import (
    RefGradeEnseignant,
    RefTypeDecision,
    RefTypeEnseignement,
    RefTypeEspaceSportif,
    RefTypeEvaluation,
)

DONNEES = Path(__file__).resolve().parents[1] / 'data'


def _charger(nom):
    return json.loads((DONNEES / nom).read_text(encoding='utf-8'))


class ImportNomenclaturesPedagogiquesTests(TestCase):
    """L'import canonique remplit les quatre référentiels, toutes zones."""

    @classmethod
    def setUpTestData(cls):
        cls.sortie = StringIO()
        call_command(
            'importer_referentiels_injs',
            '--sans-lieux', '--sans-cycles',
            stdout=cls.sortie,
        )

    def _assert_complet(self, modele, codes_attendus):
        lignes = list(modele.objects.all())
        self.assertEqual(
            {l.code for l in lignes}, set(codes_attendus),
            f'{modele.__name__} : codes importés divergents du jeu de données.',
        )
        for ligne in lignes:
            with self.subTest(modele=modele.__name__, code=ligne.code):
                self.assertTrue(ligne.libelle.strip())
                self.assertTrue(
                    ligne.description.strip(),
                    'description obligatoire (toutes les zones de la fiche).',
                )
                self.assertTrue(ligne.source_document.strip())
                self.assertNotEqual(ligne.fiabilite, 'A_RENSEIGNER')
                self.assertTrue(ligne.actif)
                self.assertFalse(ligne.archive)

    def test_types_enseignement_complets_avec_champs_metier(self):
        attendu = {i['code'] for i in _charger('institutions.json')['types_enseignement']}
        self._assert_complet(RefTypeEnseignement, attendu)
        self.assertEqual(attendu, {'CM', 'TD', 'TP', 'STAGE'})
        for ligne in RefTypeEnseignement.objects.all():
            self.assertEqual(ligne.abrege, ligne.code)
            self.assertEqual(ligne.est_stage, ligne.code == 'STAGE')
            self.assertEqual(ligne.fiabilite, 'OFFICIEL')

    def test_types_evaluation_nomenclature_du_cadrage(self):
        bloc = _charger('nomenclatures_pedagogiques.json')['types_evaluation']
        attendu = {i['code'] for i in bloc['valeurs']}
        self._assert_complet(RefTypeEvaluation, attendu)
        # Les modalités annoncées par la carte et le moteur de notes.
        self.assertTrue({'CC', 'EXAMEN_TERMINAL', 'RATTRAPAGE'} <= attendu)
        for ligne in RefTypeEvaluation.objects.all():
            self.assertEqual(ligne.fiabilite, 'CADRAGE')
            self.assertEqual(ligne.source_document, bloc['source_document'])

    def test_types_decision_alignes_sur_le_module_jurys(self):
        from jurys.models import DecisionJury

        officielles = {choix.value for choix in DecisionJury.Decision}
        self._assert_complet(RefTypeDecision, officielles)
        for ligne in RefTypeDecision.objects.all():
            self.assertEqual(ligne.fiabilite, 'OFFICIEL')

    def test_types_espace_sportif_categories_de_l_inventaire(self):
        bloc = _charger('nomenclatures_pedagogiques.json')['types_espace_sportif']
        attendu = {i['code'] for i in bloc['valeurs']}
        self._assert_complet(RefTypeEspaceSportif, attendu)
        # Les exemples de la carte et le code partagé avec les types de lieu.
        self.assertTrue({'GYMNASE', 'PISCINE', 'TERRAIN', 'DOJO'} <= attendu)
        # L'arbitrage documenté : pas de types génériques de salles ici.
        self.assertFalse(attendu & {'AMPHI', 'SALLE_TD', 'SALLE_INFO', 'SALLE_REUNION'})
        for ligne in RefTypeEspaceSportif.objects.all():
            self.assertEqual(ligne.fiabilite, 'MODELISE')

    def test_grades_enseignant_deux_familles_sans_confusion_de_plan(self):
        bloc = _charger('nomenclatures_pedagogiques.json')['grades_enseignant']
        attendu = {i['code'] for i in bloc['valeurs']}
        self._assert_complet(RefGradeEnseignant, attendu)
        familles = {i['famille'] for i in bloc['valeurs']}
        self.assertEqual(
            familles,
            {'Grades universitaires (CAMES)', 'Corps de la fonction publique'},
        )
        cames = [i for i in bloc['valeurs'] if i['famille'].endswith('(CAMES)')]
        self.assertEqual(len(cames), 12)
        self.assertEqual(len(bloc['valeurs']) - len(cames), 16)
        # Échelle CAMES complète, de l'assistant au professeur titulaire.
        self.assertTrue({
            'ASSISTANT', 'MAITRE_ASSISTANT', 'MAITRE_CONFERENCES',
            'PROFESSEUR_TITULAIRE',
        } <= attendu)
        # Grades de sortie des concours INJS (B3, A3, A4).
        self.assertTrue({'MAITRE_EPS', 'PC_EPS', 'PL_EPS'} <= attendu)
        # Le PDF distingue les plans : ni rôle applicatif, ni statut
        # d'exercice, ni corps administratif dans les grades.
        self.assertFalse(attendu & {
            'ADMIN', 'DIRECTION', 'FORMATEUR', 'SUPERVISEUR', 'AUDITEUR',
            'VACATAIRE', 'CONTRACTUEL', 'STAGIAIRE', 'TITULAIRE',
            'CADRE_ADMINISTRATIF',
        })
        for ligne in RefGradeEnseignant.objects.all():
            self.assertEqual(ligne.fiabilite, 'OFFICIEL')

    def test_deuxieme_execution_ne_cree_rien(self):
        avant = {
            m.__name__: m.objects.count()
            for m in (
                RefTypeEnseignement, RefTypeEvaluation,
                RefTypeDecision, RefTypeEspaceSportif, RefGradeEnseignant,
            )
        }
        call_command(
            'importer_referentiels_injs',
            '--sans-lieux', '--sans-cycles',
            stdout=StringIO(),
        )
        for m in (
            RefTypeEnseignement, RefTypeEvaluation,
            RefTypeDecision, RefTypeEspaceSportif, RefGradeEnseignant,
        ):
            self.assertEqual(m.objects.count(), avant[m.__name__])


class DryRunNomenclaturesTests(TestCase):
    def test_dry_run_ne_persiste_rien(self):
        call_command(
            'importer_referentiels_injs',
            '--dry-run', '--sans-lieux', '--sans-cycles',
            stdout=StringIO(),
        )
        self.assertEqual(RefTypeEvaluation.objects.count(), 0)
        self.assertEqual(RefTypeDecision.objects.count(), 0)
        self.assertEqual(RefTypeEspaceSportif.objects.count(), 0)
        self.assertEqual(RefGradeEnseignant.objects.count(), 0)
