"""C2.3 — Tests D2 / D3 / D15 (règles validées pour le lot).

D2  SI statut_participation IN (ABSENT, ABSENT_JUSTIFIE, ABSENT_INJUSTIFIE)
    ALORS composante = NON NOTÉE (aucune imputation) ; ECUE non calculable
    via D6 ; moyenne = None ; jamais 0. La distinction justifié / non
    justifié est DISCIPLINAIRE : aucune différence académique.

D3  Le rattrapage est une session distincte (type_session=RATTRAPAGE,
    session_origine obligatoire), historique append-only : la note
    initiale n'est jamais écrasée. Substitution non déclarée ⇒ aucune note
    n'est retenue automatiquement.

D15 Éligibilité SI ET SEULEMENT SI : session NORMALE, résultat calculé,
    résultat < seuil LMD déclaré (D1), aucune donnée manquante.
    SINON non éligible.
"""
from decimal import Decimal

from django.test import TestCase

from evaluations.models import (
    Evaluation,
    EvaluationComponent,
    EvaluationGrade,
    EvaluationParticipant,
    SessionEvaluation,
    TypeEvaluation,
)
from evaluations.services import calcul as moteur
from evaluations.tests import factories as f
from scolarite.models import RegleValidationLMD


class BaseC23(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.encadrant = f.creer_compte('ENCADRANT', 'encadrant-c23')
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
            type_evaluation=cls.type_eval, libelle='Épreuve C2.3',
        )
        cls.examen = EvaluationComponent.objects.create(
            evaluation=cls.evaluation, code='EXAMEN', libelle='Examen',
            poids=Decimal('60.00'), bareme=Decimal('20.00'), ordre=1,
        )
        cls.cc = EvaluationComponent.objects.create(
            evaluation=cls.evaluation, code='CC', libelle='CC',
            poids=Decimal('40.00'), bareme=Decimal('20.00'), ordre=2,
        )
        cls.participant = EvaluationParticipant.objects.create(
            evaluation=cls.evaluation,
            inscription_pedagogique=cls.ctx['inscription_pedagogique'],
        )
        RegleValidationLMD.objects.create(
            ref_formation=cls.ctx['ref_formation'], niveau=cls.ctx['niveau'],
            seuil_admission=Decimal('10.00'), actif=True,
        )

    def saisir(self, composant, valeur):
        return EvaluationGrade.objects.create(
            evaluation_participant=self.participant, component=composant,
            valeur=valeur, bareme=composant.bareme,
        )

    def absence(self, statut):
        self.participant.statut_participation = statut
        self.participant.save()
        return statut

    def rattrapage(self):
        """Session + évaluation de rattrapage rattachées à la normale."""
        session = SessionEvaluation.objects.create(
            annee_academique=self.ctx['annee'],
            ref_formation=self.ctx['ref_formation'], niveau=self.ctx['niveau'],
            semestre=self.ctx['semestre'], maquette=self.ctx['maquette'],
            type_session=SessionEvaluation.TypeSession.RATTRAPAGE,
            session_origine=self.session, libelle='Rattrapage',
        )
        evaluation = Evaluation.objects.create(
            session=session, ecue=self.ctx['ecue'],
            affectation_pedagogique=self.ctx['affectation'],
            type_evaluation=self.type_eval, libelle='Épreuve rattrapage',
        )
        EvaluationComponent.objects.create(
            evaluation=evaluation, code='EXAMEN', libelle='EXAMEN',
            poids=Decimal('100.00'), bareme=Decimal('20.00'), ordre=1,
        )
        participant = EvaluationParticipant.objects.create(
            evaluation=evaluation,
            inscription_pedagogique=self.ctx['inscription_pedagogique'],
        )
        return session, evaluation, participant

    def noter_rattrapage(self, participant, evaluation, valeur):
        return EvaluationGrade.objects.create(
            evaluation_participant=participant,
            component=evaluation.components.get(code='EXAMEN'),
            valeur=Decimal(valeur), bareme=Decimal('20.00'),
        )


class TestD2AbsenceAcademique(BaseC23):
    """SI absence académique ALORS composante non notée, jamais 0."""

    def test_absence_justificie_ne_produit_jamais_de_zero(self):
        self.saisir(self.examen, Decimal('15.00'))
        self.saisir(self.cc, Decimal('10.00'))
        self.absence('ABSENT_JUSTIFIE')
        preparation = moteur.preparer(self.participant)
        self.assertIsNone(preparation['moyenne'])
        self.assertEqual(preparation['regle_absence'], 'COMPOSANTE_NON_NOTEE')

    def test_absence_non_justifiee_traitee_de_maniere_identique(self):
        self.saisir(self.examen, Decimal('15.00'))
        self.saisir(self.cc, Decimal('10.00'))
        self.absence('ABSENT_INJUSTIFIE')
        injustifiee = moteur.preparer(self.participant)
        self.absence('ABSENT_JUSTIFIE')
        justifiee = moteur.preparer(self.participant)
        self.assertIsNone(injustifiee['moyenne'])
        self.assertEqual(injustifiee['moyenne'], justifiee['moyenne'])

    def test_absence_ecarte_la_note_deja_saisie(self):
        """Composante non notée : la note présente n'est pas retenue."""
        self.saisir(self.examen, Decimal('15.00'))
        self.saisir(self.cc, Decimal('10.00'))
        self.absence('ABSENT')
        preparation = moteur.preparer(self.participant)
        self.assertTrue(all(l['valeur'] is None for l in preparation['composants']))

    def test_absent_simple_bloque_egalement(self):
        self.saisir(self.examen, Decimal('15.00'))
        self.saisir(self.cc, Decimal('10.00'))
        self.absence('ABSENT')
        self.assertIsNone(moteur.preparer(self.participant)['moyenne'])

    def test_absence_nest_pas_une_note_zero(self):
        """0 reste une note : l'absence n'en produit pas."""
        self.saisir(self.examen, Decimal('0.00'))
        self.saisir(self.cc, Decimal('0.00'))
        self.absence('ABSENT')
        self.assertIsNone(moteur.preparer(self.participant)['moyenne'])

    def test_note_zero_reelle_reste_zero(self):
        self.saisir(self.examen, Decimal('0.00'))
        self.saisir(self.cc, Decimal('0.00'))
        self.assertEqual(moteur.preparer(self.participant)['moyenne'], 0.0)

    def test_d2_compatible_avec_d6(self):
        """Composante obligatoire non notée (D6) ≠ 0."""
        self.saisir(self.examen, Decimal('15.00'))
        self.absence('ABSENT')
        preparation = moteur.preparer(self.participant)
        self.assertIn(
            'COMPOSANT_MANQUANT',
            [d['code'] for d in preparation['diagnostics']],
        )
        self.assertIsNone(preparation['moyenne'])

    def test_dispense_ne_produit_pas_de_zero_artificiel(self):
        self.saisir(self.examen, Decimal('15.00'))
        self.saisir(self.cc, Decimal('10.00'))
        self.absence('DISPENSE')
        self.assertIsNone(moteur.preparer(self.participant)['moyenne'])


class TestD3Rattrapage(BaseC23):
    """Rattrapage = session distincte, historique append-only."""

    def test_session_rattrapage_reference_son_origine(self):
        session, _, _ = self.rattrapage()
        self.assertEqual(session.type_session, 'RATTRAPAGE')
        self.assertEqual(session.session_origine_id, self.session.pk)

    def test_note_initiale_conservee_et_note_rattrapage_calculee(self):
        self.saisir(self.examen, Decimal('05.00'))
        origine = moteur.preparer(self.participant)
        _, evaluation, participant_rt = self.rattrapage()
        self.noter_rattrapage(participant_rt, evaluation, '16.00')
        self.assertEqual(moteur.preparer(participant_rt)['moyenne'], 16.0)
        # La note d'origine n'est ni écrasée ni supprimée.
        relu = moteur.preparer(self.participant)
        self.assertEqual(relu['composants'][0]['valeur'], 5.0)
        self.assertEqual(EvaluationGrade.objects.count(), 2)
        self.assertEqual(origine['empreinte'], relu['empreinte'])
class TestD15Eligibilite(BaseC23):
    """Éligibilité calculée, jamais posée par défaut, jamais décidée par jury."""

    def eligibilite(self, preparation=None):
        preparation = preparation or moteur.preparer(self.participant)
        return moteur.eligibilite_rattrapage(self.participant, preparation)

    def test_non_eligible_si_moyenne_absente(self):
        self.saisir(self.examen, Decimal('05.00'))
        self.absence('ABSENT')
        self.assertFalse(self.eligibilite()['eligible'])

    def test_non_eligible_si_donnee_manquante(self):
        self.saisir(self.examen, Decimal('05.00'))  # CC non notée
        verdict = self.eligibilite()
        self.assertFalse(verdict['eligible'])
        self.assertIn('DONNEE_MANQUANTE', verdict['motifs'])

    def test_eligible_sous_le_seuil_lmd(self):
        self.saisir(self.examen, Decimal('05.00'))
        self.saisir(self.cc, Decimal('05.00'))
        verdict = self.eligibilite()
        self.assertTrue(verdict['eligible'])
        self.assertEqual(verdict['motifs'], [])

    def test_non_eligible_au_dessus_du_seuil(self):
        self.saisir(self.examen, Decimal('15.00'))
        self.saisir(self.cc, Decimal('15.00'))
        verdict = self.eligibilite()
        self.assertFalse(verdict['eligible'])
        self.assertIn('MOYENNE_SUP_OU_EQUALE_AU_SEUIL', verdict['motifs'])

    def test_seuil_provient_de_la_regle_lmd(self):
        self.saisir(self.examen, Decimal('05.00'))
        self.saisir(self.cc, Decimal('05.00'))
        self.assertEqual(self.eligibilite()['seuil'], 10.0)

    def test_champ_par_defaut_reste_false(self):
        self.participant.refresh_from_db()
        self.assertFalse(self.participant.eligible_rattrapage)

    def test_calcul_n_alimente_pas_le_champ(self):
        """L'éligibilité est calculée, jamais persistée automatiquement."""
        self.saisir(self.examen, Decimal('05.00'))
        self.saisir(self.cc, Decimal('05.00'))
        self.eligibilite()
        self.participant.refresh_from_db()
        self.assertFalse(self.participant.eligible_rattrapage)

    def test_session_non_normale_non_eligible(self):
        self.saisir(self.examen, Decimal('05.00'))
        self.saisir(self.cc, Decimal('05.00'))
        # Une session non normale (RECTIFICATION) : l'éligibilité se juge
        # sur la session d'origine normale.
        self.session.type_session = SessionEvaluation.TypeSession.RECTIFICATION
        self.session.save()
        verdict = self.eligibilite()
        self.assertFalse(verdict['eligible'])
        self.assertIn('SESSION_NON_NORMALE', verdict['motifs'])


class TestNonRegressionC2(BaseC23):
    """D1 / D5 / D6 / D10 doivent rester strictement inchangés."""

    def test_d1_seuil_depuis_la_regle_lmd(self):
        self.saisir(self.examen, Decimal('15.00'))
        self.saisir(self.cc, Decimal('10.00'))
        preparation = moteur.preparer(self.participant)
        self.assertEqual(preparation['regle_lmd']['seuil_admission'], 10.0)

    def test_d5_normalisation_par_somme_des_poids(self):
        self.saisir(self.examen, Decimal('15.00'))
        self.saisir(self.cc, Decimal('10.00'))
        self.assertEqual(moteur.preparer(self.participant)['moyenne'], 13.0)

    def test_d6_composant_manquant_nejamais_zero(self):
        self.saisir(self.examen, Decimal('15.00'))
        self.assertIsNone(moteur.preparer(self.participant)['moyenne'])

    def test_d10_aucune_decision_de_jury(self):
        self.saisir(self.examen, Decimal('15.00'))
        self.saisir(self.cc, Decimal('10.00'))
        preparation = moteur.preparer(self.participant)
        for cle in ('acquise', 'admis', 'decision', 'jury', 'compense'):
            self.assertNotIn(cle, preparation)
        verdict = moteur.eligibilite_rattrapage(self.participant, preparation)
        for cle in ('acquise', 'admis', 'decision', 'jury'):
            self.assertNotIn(cle, verdict)

    def test_aucune_substitution_automatique(self):
        """Substitution non déclarée ⇒ aucune note n'est retenue."""
        self.saisir(self.examen, Decimal('05.00'))
        origine = moteur.preparer(self.participant)
        _, evaluation, participant_rt = self.rattrapage()
        self.noter_rattrapage(participant_rt, evaluation, '16.00')
        combine = moteur.comparer_rattrapage(
            origine, moteur.preparer(participant_rt),
        )
        self.assertIsNone(combine['note_retenue'])
        self.assertEqual(combine['regle_substitution'], 'NON_DECLAREE')

    def test_rattrapage_independant_du_badgeage(self):
        """Aucune dépendance au système de présence/badgeage."""
        session, _, _ = self.rattrapage()
        self.assertFalse(hasattr(session, 'badgeage'))
        self.assertEqual(session.session_origine.type_session, 'NORMALE')

    def test_session_rattrapage_calculee_indepamment(self):
        _, evaluation, participant_rt = self.rattrapage()
        self.noter_rattrapage(participant_rt, evaluation, '16.00')
        preparation = moteur.preparer(participant_rt)
        self.assertEqual(preparation['moyenne'], 16.0)
        self.assertEqual(preparation['regle_lmd']['seuil_admission'], 10.0)
class TestAbsenceEtZero(BaseC23):
    """D2 / D6 : absence ≠ 0, et un 0 réel reste un 0."""

    def test_zero_explicite_conserve(self):
        self.saisir(self.examen, Decimal('0.00'))
        self.saisir(self.cc, Decimal('0.00'))
        self.assertEqual(moteur.preparer(self.participant)['moyenne'], 0.0)

    def test_absence_et_zero_ne_produisent_pas_le_meme_calcul(self):
        self.saisir(self.examen, Decimal('0.00'))
        self.saisir(self.cc, Decimal('0.00'))
        zero = moteur.preparer(self.participant)
        self.absence('ABSENT')
        absent = moteur.preparer(self.participant)
        self.assertEqual(zero['moyenne'], 0.0)
        self.assertIsNone(absent['moyenne'])

    def test_composante_non_notee_nest_pas_comptabilisee_zero(self):
        self.saisir(self.cc, Decimal('10.00'))
        preparation = moteur.preparer(self.participant)
        self.assertIsNone(preparation['moyenne'])
        self.assertIn(
            'COMPOSANT_MANQUANT',
            [d['code'] for d in preparation['diagnostics']],
        )


class TestSeuilEtJuridiction(BaseC23):
    def test_cas_exactement_au_seuil(self):
        """Uniquement les bornes de la règle existante, rien d'autre."""
        self.saisir(self.examen, Decimal('10.00'))
        self.saisir(self.cc, Decimal('10.00'))
        preparation = moteur.preparer(self.participant)
        self.assertEqual(preparation['moyenne'], 10.0)
        self.assertEqual(preparation['regle_lmd']['seuil_admission'], 10.0)

    def test_arbitrage_arrondi_deja_implemente(self):
        from evaluations.services.calcul import ARRONDI, FORMULE_VERSION

        self.assertEqual(str(ARRONDI), '0.01')
        self.assertTrue(FORMULE_VERSION.startswith('LMD.'))

    def test_jury_absent_du_moteur_de_calcul(self):
        self.saisir(self.examen, Decimal('15.00'))
        self.saisir(self.cc, Decimal('10.00'))
        preparation = moteur.preparer(self.participant)
        for cle in ('jury', 'decision', 'deliberation', 'acquise'):
            self.assertNotIn(cle, preparation)
class TestRegleSubstitutionDeclarative(BaseC23):
    """D3 : la règle est lue dans RegleCalcul (famille RATTRAPAGE),
    jamais codée en dur. Sans déclaration : aucune substitution."""

    def declarer(self, valeur, **kw):
        from evaluations.models import RegleCalcul, RegleCalculVersion

        regle, _ = RegleCalcul.objects.get_or_create(
            code='RATTRAPAGE',
            defaults={'libelle': 'Rattrapage', 'categorie': 'C'},
        )
        return RegleCalculVersion.objects.create(
            regle=regle, version=1, date_effet='2026-10-01',
            parametres={'substitution': valeur}, **kw,
        )

    def pair(self, initiale, rattrapage):
        """Note les DEUX composantes du calcul initial pour disposer
        d'une moyenne initiale exploitable (sinon D6 : composante
        manquante → moyenne None)."""
        self.saisir(self.examen, Decimal(initiale))
        self.saisir(self.cc, Decimal(initiale))
        origine = moteur.preparer(self.participant)
        _, evaluation, participant_rt = self.rattrapage()
        self.noter_rattrapage(participant_rt, evaluation, rattrapage)
        return origine, moteur.preparer(participant_rt)

    def test_aucune_declaration_aucune_substitution(self):
        origine, rt = self.pair('05.00', '16.00')
        combine = moteur.comparer_rattrapage(origine, rt)
        self.assertEqual(combine['regle_substitution'], 'NON_DECLAREE')
        self.assertIsNone(combine['note_retenue'])

    def test_remplacement_systematique(self):
        origine, rt = self.pair('05.00', '16.00')
        combine = moteur.comparer_rattrapage(
            origine, rt, self.declarer('REMPLACEMENT_SYSTEMATIQUE'),
        )
        self.assertEqual(combine['note_retenue'], 16.0)

    def test_remplacement_systematique_si_inferieure(self):
        origine, rt = self.pair('16.00', '05.00')
        combine = moteur.comparer_rattrapage(
            origine, rt, self.declarer('REMPLACEMENT_SYSTEMATIQUE'),
        )
        self.assertEqual(combine['note_retenue'], 5.0)

    def test_meilleure_note(self):
        origine, rt = self.pair('05.00', '16.00')
        combine = moteur.comparer_rattrapage(
            origine, rt, self.declarer('MEILLEURE_NOTE'),
        )
        self.assertEqual(combine['note_retenue'], 16.0)

    def test_meilleure_note_garde_la_plus_forte_note_initiale(self):
        origine, rt = self.pair('18.00', '04.00')
        combine = moteur.comparer_rattrapage(
            origine, rt, self.declarer('MEILLEURE_NOTE'),
        )
        self.assertEqual(combine['note_retenue'], 18.0)

    def test_conservation_separee(self):
        origine, rt = self.pair('05.00', '16.00')
        combine = moteur.comparer_rattrapage(
            origine, rt, self.declarer('CONSERVATION_SEPAREE'),
        )
        self.assertIsNone(combine['note_retenue'])
        self.assertEqual(combine['note_initiale'], 5.0)
        self.assertEqual(combine['note_rattrapage'], 16.0)

    def test_valeur_non_autorisee_refusee(self):
        origine, rt = self.pair('05.00', '16.00')
        combine = moteur.comparer_rattrapage(
            origine, rt, self.declarer('MOYENNE_DES_DEUX'),
        )
        self.assertEqual(combine['regle_substitution'], 'NON_DECLAREE')
        self.assertIsNone(combine['note_retenue'])

    def test_regle_inactive_ignoree(self):
        """Une famille RATTRAPAGE désactivée ne s'applique pas."""
        origine, rt = self.pair('05.00', '16.00')
        version = self.declarer('REMPLACEMENT_SYSTEMATIQUE')
        version.regle.actif = False
        version.regle.save()
        combine = moteur.comparer_rattrapage(origine, rt, version)
        self.assertEqual(combine['regle_substitution'], 'NON_DECLAREE')

    def test_les_deux_notes_restent_tracees(self):
        origine, rt = self.pair('05.00', '16.00')
        combine = moteur.comparer_rattrapage(
            origine, rt, self.declarer('REMPLACEMENT_SYSTEMATIQUE'),
        )
        self.assertEqual(combine['note_initiale'], 5.0)
        self.assertEqual(combine['note_rattrapage'], 16.0)
        self.assertIsNotNone(combine['empreinte_initiale'])
        self.assertIsNotNone(combine['empreinte_rattrapage'])
        # 3 notes historiques : 2 initiales + 1 rattrapage, aucune détruite.
        self.assertEqual(EvaluationGrade.objects.count(), 3)

    def test_aucune_moyenne_implicite_des_deux(self):
        origine, rt = self.pair('05.00', '16.00')
        combine = moteur.comparer_rattrapage(
            origine, rt, self.declarer('REMPLACEMENT_SYSTEMATIQUE'),
        )
        self.assertNotEqual(combine['note_retenue'], 10.5)


#__REFONTE_2__
