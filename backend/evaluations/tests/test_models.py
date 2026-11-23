"""C1 — Invariants structurels du socle « Évaluations académiques ».

Ces tests ne valident **aucune** règle métier : ils vérifient les
garanties structurelles du contrat B.1 (unicité, PROTECT, domaines de
valeurs, immuabilité, invariants d'absence).
"""
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from evaluations.models import (
    Evaluation,
    EvaluationComponent,
    EvaluationGrade,
    EvaluationGradeHistory,
    EvaluationParticipant,
    RegleCalcul,
    RegleCalculVersion,
    SessionEvaluation,
    TypeEvaluation,
)
from evaluations.tests import factories as f


class SocleTestCase(TestCase):
    """Base : périmètre LMD complet et prêt."""

    @classmethod
    def setUpTestData(cls):
        cls.ctx = f.base_lmd_complete()
        cls.type_eval = TypeEvaluation.objects.create(
            code='EXAMEN', libelle='Examen écrit', categorie='Examen',
        )


class TestSessionEvaluation(SocleTestCase):
    def test_creation_nominale_et_statut_initial(self):
        session = SessionEvaluation.objects.create(
            annee_academique=self.ctx['annee'],
            ref_formation=self.ctx['ref_formation'],
            niveau=self.ctx['niveau'],
            semestre=self.ctx['semestre'],
            maquette=self.ctx['maquette'],
            libelle='Session normale 2026-2027',
        )
        self.assertEqual(session.statut, 'BROUILLON')
        self.assertFalse(session.verrouillee)

    def test_unicite_du_perimetre_meme_avec_parcours_null(self):
        """La contrainte Coalesce empêche deux sessions de même périmètre."""
        SessionEvaluation.objects.create(
            annee_academique=self.ctx['annee'], ref_formation=self.ctx['ref_formation'],
            niveau=self.ctx['niveau'], semestre=self.ctx['semestre'],
            maquette=self.ctx['maquette'], parcours=None,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                SessionEvaluation.objects.create(
                    annee_academique=self.ctx['annee'],
                    ref_formation=self.ctx['ref_formation'],
                    niveau=self.ctx['niveau'], semestre=self.ctx['semestre'],
                    maquette=self.ctx['maquette'], parcours=None,
                )

    def test_rattrapage_exige_une_session_origine(self):
        with self.assertRaises(ValidationError):
            SessionEvaluation.objects.create(
                annee_academique=self.ctx['annee'],
                ref_formation=self.ctx['ref_formation'],
                niveau=self.ctx['niveau'], semestre=self.ctx['semestre'],
                maquette=self.ctx['maquette'],
                type_session=SessionEvaluation.TypeSession.RATTRAPAGE,
            )

    def test_dates_incoherentes_refusees(self):
        with self.assertRaises(ValidationError):
            SessionEvaluation.objects.create(
                annee_academique=self.ctx['annee'],
                ref_formation=self.ctx['ref_formation'],
                niveau=self.ctx['niveau'], semestre=self.ctx['semestre'],
                maquette=self.ctx['maquette'],
                date_debut=date(2027, 6, 1), date_fin=date(2027, 1, 1),
            )

    def test_maquette_d_une_autre_annee_refusee(self):
        autre_annee = f.creer_annee('2025-2026', courante=False)
        autre_niveau = f.creer_niveau('L2')
        autre_maquette = f.creer_maquette(autre_annee, self.ctx['ref_formation'], autre_niveau)
        f.activer_maquette(autre_maquette)
        with self.assertRaises(ValidationError):
            SessionEvaluation.objects.create(
                annee_academique=self.ctx['annee'],
                ref_formation=self.ctx['ref_formation'],
                niveau=self.ctx['niveau'], semestre=self.ctx['semestre'],
                maquette=autre_maquette,
            )


class TestEvaluation(SocleTestCase):
    def setUp(self):
        self.session = SessionEvaluation.objects.create(
            annee_academique=self.ctx['annee'], ref_formation=self.ctx['ref_formation'],
            niveau=self.ctx['niveau'], semestre=self.ctx['semestre'],
            maquette=self.ctx['maquette'],
        )

    def _evaluation(self, **kwargs):
        defauts = {
            'session': self.session, 'ecue': self.ctx['ecue'],
            'affectation_pedagogique': self.ctx['affectation'],
            'type_evaluation': self.type_eval, 'libelle': 'Examen final S1',
        }
        defauts.update(kwargs)
        return Evaluation.objects.create(**defauts)

    def test_creation_nominale_avec_ecue_et_affectation_explicites(self):
        evaluation = self._evaluation()
        self.assertEqual(evaluation.ecue_id, self.ctx['ecue'].pk)
        self.assertEqual(
            evaluation.affectation_pedagogique_id, self.ctx['affectation'].pk,
        )

    def test_affectation_d_un_autre_ecue_refusee(self):
        autre_maquette = f.creer_maquette(
            self.ctx['annee'], self.ctx['ref_formation'], self.ctx['niveau'], version=2,
        )
        autre_ue = f.creer_ue(autre_maquette, self.ctx['semestre'], code='UE-Y', credits=3)
        autre_ecue = f.creer_ecue(autre_ue, code='ECUE-Y-1', credits=3)
        f.activer_maquette(autre_maquette)
        autre_affectation = f.creer_affectation(
            self.ctx['annee'], self.ctx['ref_formation'], self.ctx['niveau'],
            self.ctx['semestre'], autre_ecue, self.ctx['formateur'],
        )
        with self.assertRaises(ValidationError):
            self._evaluation(affectation_pedagogique=autre_affectation)

    def test_poids_hors_domaine_refuse(self):
        for poids in (Decimal('0'), Decimal('100.01'), Decimal('-1')):
            with self.assertRaises(ValidationError):
                self._evaluation(libelle=f'Exam {poids}', poids=poids)

    def test_bareme_non_positif_refuse(self):
        with self.assertRaises(ValidationError):
            self._evaluation(libelle='Exam bareme 0', bareme=Decimal('0'))

    def test_unicite_session_ecue_type_libelle(self):
        self._evaluation()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._evaluation()


class TestEvaluationComponent(SocleTestCase):
    def setUp(self):
        self.session = SessionEvaluation.objects.create(
            annee_academique=self.ctx['annee'], ref_formation=self.ctx['ref_formation'],
            niveau=self.ctx['niveau'], semestre=self.ctx['semestre'],
            maquette=self.ctx['maquette'],
        )
        self.evaluation = Evaluation.objects.create(
            session=self.session, ecue=self.ctx['ecue'],
            affectation_pedagogique=self.ctx['affectation'],
            type_evaluation=self.type_eval, libelle='CC + Examen',
        )

    def test_creation_nominale(self):
        composant = EvaluationComponent.objects.create(
            evaluation=self.evaluation, code='CC', libelle='Contrôle continu',
            poids=Decimal('40.00'), bareme=Decimal('20.00'), ordre=1,
        )
        self.assertEqual(composant.evaluation_id, self.evaluation.pk)

    def test_code_unique_par_evaluation(self):
        EvaluationComponent.objects.create(
            evaluation=self.evaluation, code='CC', libelle='CC',
            poids=Decimal('40.00'),
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                EvaluationComponent.objects.create(
                    evaluation=self.evaluation, code='CC', libelle='CC bis',
                    poids=Decimal('60.00'),
                )

    def test_poids_et_bareme_controles(self):
        with self.assertRaises(ValidationError):
            EvaluationComponent.objects.create(
                evaluation=self.evaluation, code='BAD', libelle='x',
                poids=Decimal('0'), bareme=Decimal('20'),
            )
        with self.assertRaises(ValidationError):
            EvaluationComponent.objects.create(
                evaluation=self.evaluation, code='BAD2', libelle='x',
                poids=Decimal('10'), bareme=Decimal('0'),
            )


class TestEvaluationParticipant(SocleTestCase):
    def setUp(self):
        self.session = SessionEvaluation.objects.create(
            annee_academique=self.ctx['annee'], ref_formation=self.ctx['ref_formation'],
            niveau=self.ctx['niveau'], semestre=self.ctx['semestre'],
            maquette=self.ctx['maquette'],
        )
        self.evaluation = Evaluation.objects.create(
            session=self.session, ecue=self.ctx['ecue'],
            affectation_pedagogique=self.ctx['affectation'],
            type_evaluation=self.type_eval, libelle='Examen final',
        )

    def test_participant_rattache_a_l_inscription_pedagogique(self):
        participant = EvaluationParticipant.objects.create(
            evaluation=self.evaluation,
            inscription_pedagogique=self.ctx['inscription_pedagogique'],
        )
        self.assertEqual(
            participant.inscription_pedagogique_id,
            self.ctx['inscription_pedagogique'].pk,
        )

    def test_doublon_participant_refuse(self):
        EvaluationParticipant.objects.create(
            evaluation=self.evaluation,
            inscription_pedagogique=self.ctx['inscription_pedagogique'],
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                EvaluationParticipant.objects.create(
                    evaluation=self.evaluation,
                    inscription_pedagogique=self.ctx['inscription_pedagogique'],
                )

    def test_exclusion_sans_motif_refusee(self):
        with self.assertRaises(ValidationError):
            EvaluationParticipant.objects.create(
                evaluation=self.evaluation,
                inscription_pedagogique=self.ctx['inscription_pedagogique'],
                statut_participation='EXCLU', motif='',
            )


class TestEvaluationGrade(SocleTestCase):
    def setUp(self):
        self.session = SessionEvaluation.objects.create(
            annee_academique=self.ctx['annee'], ref_formation=self.ctx['ref_formation'],
            niveau=self.ctx['niveau'], semestre=self.ctx['semestre'],
            maquette=self.ctx['maquette'],
        )
        self.evaluation = Evaluation.objects.create(
            session=self.session, ecue=self.ctx['ecue'],
            affectation_pedagogique=self.ctx['affectation'],
            type_evaluation=self.type_eval, libelle='Examen final',
        )
        self.composant = EvaluationComponent.objects.create(
            evaluation=self.evaluation, code='EXAMEN', libelle='Examen',
            poids=Decimal('100.00'), bareme=Decimal('20.00'),
        )
        self.participant = EvaluationParticipant.objects.create(
            evaluation=self.evaluation,
            inscription_pedagogique=self.ctx['inscription_pedagogique'],
        )
        self.auteur = f.creer_compte('ADMIN', 'admin-historique')

    def _note(self, valeur, **kwargs):
        defauts = {
            'evaluation_participant': self.participant,
            'component': self.composant, 'valeur': valeur,
            'bareme': self.composant.bareme,
        }
        defauts.update(kwargs)
        return EvaluationGrade.objects.create(**defauts)

    def test_note_valide_avec_historique(self):
        grade = self._note(Decimal('14.50'))
        self.assertEqual(grade.statut, 'BROUILLON')
        ligne = EvaluationGradeHistory.objects.create(
            grade=grade, action='SAISIE', nouvelle_valeur=Decimal('14.50'),
            auteur=self.auteur,
        )
        self.assertIsNone(ligne.ancienne_valeur)

    def test_note_hors_bareme_refusee(self):
        with self.assertRaises(ValidationError):
            self._note(Decimal('21.00'))

    def test_note_negative_refusee(self):
        with self.assertRaises(ValidationError):
            self._note(Decimal('-1.00'))

    def test_note_nulle_autorisee(self):
        """0 reste une VALEUR ; seule l'absence exclut un candidat."""
        grade = self._note(Decimal('0.00'))
        self.assertEqual(grade.valeur, Decimal('0.00'))

    def test_verrouillee_exige_le_statut_validee(self):
        with self.assertRaises(ValidationError):
            self._note(Decimal('12.00'), verrouillee=True, statut='BROUILLON')

    def test_unicite_composant_participant(self):
        self._note(Decimal('10.00'))
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._note(Decimal('11.00'))


class TestReglesVersionnees(SocleTestCase):
    def test_aucune_regle_n_est_creee_par_defaut(self):
        """Aucun seuil ni pondération n'est inventé (DECISION-1)."""
        self.assertEqual(RegleCalcul.objects.count(), 0)
        self.assertEqual(RegleCalculVersion.objects.count(), 0)

    def test_version_verrouillee_est_immuable(self):
        regle = RegleCalcul.objects.create(
            code='VALIDATION_UE', libelle='Validation UE', categorie='C',
            source='PARAMETRABLE',
        )
        version = RegleCalculVersion.objects.create(
            regle=regle, version=1, date_effet=date(2026, 10, 1),
            parametres={'seuil': 'PARAMETRABLE'},
        )
        version.parametres = {'seuil': 'PARAMETRABLE_V2'}
        version.verrouillee = True
        version.save()
        with self.assertRaises(ValidationError):
            version.parametres = {'seuil': '12'}
            version.save()

    def test_dates_incoherentes_refusees(self):
        regle = RegleCalcul.objects.create(code='ARRONDI', libelle='Arrondi')
        with self.assertRaises(ValidationError):
            RegleCalculVersion.objects.create(
                regle=regle, version=1, date_effet=date(2027, 1, 1),
                date_fin=date(2026, 1, 1),
            )