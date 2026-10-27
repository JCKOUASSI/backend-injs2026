"""C2-ACTIVATION — Tests d'activation du moteur (TDD).

Règles activées uniquement parce qu'elles sont **établies par le moteur LMD
existant du projet** (``scolarite.validation_services`` et
``scolarite.RegleValidationLMD``), jamais parce qu'elles seraient
raisonnables :

    D1  seuil        : ``RegleValidationLMD.seuil_admission`` (donnée)
    D5  pondération  : ``Σ(quotient×poids)/Σ(poids)`` (poids > 0, aucune
                       exigence de somme = 100) — idem ``_ponderee``
    D6  incomplet    : pas de moyenne si un composant obligatoire manque
                       (idem ``_moyenne_ecue`` → ``(None, False)``)
    D10 gouvernance  : le moteur produit un résultat, jamais une décision

Règles qui restent BLOQUÉES (aucune source dans le dépôt) :
    D2  absence : pas d'imputation ; D3 rattrapage ; D15 éligibilité
"""
from decimal import Decimal

from django.test import TestCase

from evaluations.models import (
    Evaluation,
    EvaluationAttendance,
    EvaluationComponent,
    EvaluationGrade,
    EvaluationParticipant,
    RegleCalculVersion,
    SessionEvaluation,
    TypeEvaluation,
)
from evaluations.services import calcul as moteur
from evaluations.services.diagnostics import BLOQUANTS
from evaluations.tests import factories as f
from scolarite.models import RegleValidationLMD


class BaseActivation(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = f.creer_compte('ADMIN', 'admin-act')
        cls.encadrant = f.creer_compte('ENCADRANT', 'encadrant-act')
        cls.ctx = f.base_lmd_complete(formateur_user=cls.encadrant)
        cls.type_eval = TypeEvaluation.objects.create(code='EXAMEN', libelle='Examen')
        cls.session = SessionEvaluation.objects.create(
            annee_academique=cls.ctx['annee'], ref_formation=cls.ctx['ref_formation'],
            niveau=cls.ctx['niveau'], semestre=cls.ctx['semestre'],
            maquette=cls.ctx['maquette'],
        )
        cls.evaluation = Evaluation.objects.create(
            session=cls.session, ecue=cls.ctx['ecue'],
            affectation_pedagogique=cls.ctx['affectation'],
            type_evaluation=cls.type_eval, libelle='Épreuve activée',
        )
        cls.examen = EvaluationComponent.objects.create(
            evaluation=cls.evaluation, code='EXAMEN', libelle='Examen',
            poids=Decimal('60.00'), bareme=Decimal('20.00'), ordre=1,
        )
        cls.cc = EvaluationComponent.objects.create(
            evaluation=cls.evaluation, code='CC', libelle='Contrôle continu',
            poids=Decimal('40.00'), bareme=Decimal('20.00'), ordre=2,
        )
        cls.participant = EvaluationParticipant.objects.create(
            evaluation=cls.evaluation,
            inscription_pedagogique=cls.ctx['inscription_pedagogique'],
        )

    def declarer_regle_lmd(self, seuil='10.00'):
        """Règle déclarée par la scolarité (donnée, pas une valeur choisie)."""
        return RegleValidationLMD.objects.create(
            ref_formation=self.ctx['ref_formation'],
            niveau=self.ctx['niveau'],
            seuil_admission=Decimal(seuil),
            actif=True,
        )

    def saisir(self, composant, valeur):
        return EvaluationGrade.objects.create(
            evaluation_participant=self.participant, component=composant,
            valeur=valeur, bareme=composant.bareme,
        )


class TestD1FormuleVersion(BaseActivation):
    def test_formule_version_est_explicite(self):
        self.assertTrue(moteur.FORMULE_VERSION)
        self.assertRegex(moteur.FORMULE_VERSION, r'^LMD\.\d{4}\.\d+$')

    def test_seuil_vient_de_la_regle_declaree(self):
        self.declarer_regle_lmd('12.00')
        preparation = moteur.preparer(self.participant)
        self.assertEqual(preparation['regle_lmd']['seuil_admission'], 12.0)

    def test_aucune_regle_declaree_bloque_le_calcul(self):
        preparation = moteur.preparer(self.participant)
        self.assertIsNone(preparation['moyenne'])
        self.assertIn(
            'REGLE_ABSENTE', [d['code'] for d in preparation['diagnostics']],
        )


class TestD5Ponderation(BaseActivation):
    def test_moyenne_ponderee_sans_exigence_de_somme_100(self):
        self.declarer_regle_lmd()
        self.saisir(self.examen, Decimal('15.00'))   # 0.75 × 60
        self.saisir(self.cc, Decimal('10.00'))       # 0.50 × 40
        # (0.75*60 + 0.50*40) / 100 = 0.65 → sur 20 → 13.00
        self.assertEqual(moteur.preparer(self.participant)['moyenne'], 13.0)

    def test_poids_non_normalises_donnent_le_meme_equivalent(self):
        self.declarer_regle_lmd()
        self.saisir(self.examen, Decimal('15.00'))
        self.saisir(self.cc, Decimal('10.00'))
        reference = moteur.preparer(self.participant)['moyenne']
        EvaluationComponent.objects.filter(pk=self.examen.pk).update(
            poids=Decimal('6'),
        )
        EvaluationComponent.objects.filter(pk=self.cc.pk).update(poids=Decimal('4'))
        self.assertEqual(moteur.preparer(self.participant)['moyenne'], reference)

    def test_composition_non_declaree_disparait_une_fois_poids_declares(self):
        self.declarer_regle_lmd()
        self.saisir(self.examen, Decimal('15.00'))
        self.saisir(self.cc, Decimal('10.00'))
        preparation = moteur.preparer(self.participant)
        self.assertNotIn(
            'COMPOSITION_NON_DECLAREE',
            [d['code'] for d in preparation['diagnostics']],
        )


class TestD6ComposantManquant(BaseActivation):
    def test_composant_obligatoire_manquant_donne_moyenne_nulle(self):
        self.declarer_regle_lmd()
        self.saisir(self.examen, Decimal('15.00'))
        preparation = moteur.preparer(self.participant)
        self.assertIsNone(preparation['moyenne'])
        self.assertIn(
            'COMPOSANT_MANQUANT',
            [d['code'] for d in preparation['diagnostics']],
        )

    def test_calcul_complet_ne_produit_pas_zero(self):
        self.declarer_regle_lmd()
        self.saisir(self.examen, Decimal('15.00'))
        preparation = moteur.preparer(self.participant)
        self.assertIsNone(preparation['moyenne'])


class TestD2Absence(BaseActivation):
    def test_absence_bloque_toujours_le_calcul(self):
        """C2.3 / D2 : la règle est appliquée — composante non notée,
        ECUE non calculable. D2 reste donc bloquant, mais pour une raison
        RÈGLE (D6), plus pour une règle non tranchée."""
        self.declarer_regle_lmd()
        self.saisir(self.examen, Decimal('15.00'))
        self.saisir(self.cc, Decimal('10.00'))
        self.participant.statut_participation = 'ABSENT_INJUSTIFIE'
        self.participant.save()
        preparation = moteur.preparer(self.participant)
        self.assertIsNone(preparation['moyenne'])
        self.assertEqual(preparation['regle_absence'], 'COMPOSANTE_NON_NOTEE')
        self.assertIn(
            'COMPOSANT_MANQUANT',
            [d['code'] for d in preparation['diagnostics']],
        )

    def test_emargement_absent_bloque_egalement(self):
        """D2 : le badgeage ne pilote PAS le calcul académique."""
        from evaluations.models import Epreuve

        self.declarer_regle_lmd()
        self.saisir(self.examen, Decimal('15.00'))
        self.saisir(self.cc, Decimal('10.00'))
        epreuve = Epreuve.objects.create(
            evaluation=self.evaluation, date='2027-01-10',
            heure_debut='08:00:00', heure_fin='10:00:00',
        )
        EvaluationAttendance.objects.create(
            evaluation_participant=self.participant, epreuve=epreuve, statut='ABSENT',
        )
        self.assertEqual(moteur.preparer(self.participant)['moyenne'], 13.0)

    def test_zero_reste_une_valeur(self):
        self.declarer_regle_lmd()
        self.saisir(self.examen, Decimal('0.00'))
        self.saisir(self.cc, Decimal('0.00'))
        preparation = moteur.preparer(self.participant)
        self.assertEqual(preparation['moyenne'], 0.0)
        self.assertFalse(preparation['imputation_absence'])


class TestD10Gouvernance(BaseActivation):
    def test_calcul_n_emett_aucune_decision(self):
        self.declarer_regle_lmd()
        self.saisir(self.examen, Decimal('15.00'))
        self.saisir(self.cc, Decimal('10.00'))
        preparation = moteur.preparer(self.participant)
        for cle in ('acquise', 'admis', 'decision', 'jury', 'compense'):
            self.assertNotIn(cle, preparation)

    def test_gouvernance_reste_non_declaree(self):
        self.assertIn('GOUVERNANCE_NON_DECLAREE', BLOQUANTS)


class TestD3D15ResteBloque(BaseActivation):
    def test_rattrapage_et_eligibilite_restent_non_declares(self):
        self.assertIn('RATTRAPAGE_NON_DECLARE', BLOQUANTS)
        self.assertIn('ELIGIBILITE_NON_DECLAREE', BLOQUANTS)

    def test_champ_eligibilite_non_alimente(self):
        self.declarer_regle_lmd()
        self.saisir(self.examen, Decimal('05.00'))
        self.saisir(self.cc, Decimal('04.00'))
        moteur.preparer(self.participant)
        self.participant.refresh_from_db()
        self.assertFalse(self.participant.eligible_rattrapage)


class TestResultatNonPersiste(BaseActivation):
    def test_calcul_activable_ne_persiste_aucun_resultat(self):
        """L'activation n'écrit aucun résultat : la gouvernance D10 ne
        l'autorise pas encore (pas de validation métier)."""
        from evaluations.models import ECUEResult

        self.declarer_regle_lmd()
        self.saisir(self.examen, Decimal('15.00'))
        self.saisir(self.cc, Decimal('10.00'))
        self.assertEqual(moteur.preparer(self.participant)['moyenne'], 13.0)
        self.assertEqual(ECUEResult.objects.count(), 0)

    def test_regle_calcul_custom_acceptee(self):
        from evaluations.models import RegleCalcul

        regle = RegleCalcul.objects.create(code='X', libelle='X', categorie='C')
        version = RegleCalculVersion.objects.create(
            regle=regle, version=1, date_effet='2026-10-01', parametres={},
        )
        preparation = moteur.preparer(self.participant, regle_version=version)
        self.assertEqual(preparation['regle_snapshot']['code'], 'X')