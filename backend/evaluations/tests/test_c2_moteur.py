"""C2 — Tests du moteur de préparation (TDD).

Ces tests ne valident AUCUNE règle académique : ils vérifient des
INVARIANTS TECHNIQUES uniquement.

Invariants couverts :
    * empreinte SHA-256 déterministe et canonique (indépendante de
      l'ordre des composants, stable sur les Decimal) ;
    * instantané de règle immuable (copie des paramètres) ;
    * 0 reste une VALEUR, l'absence reste ABSENCE (jamais convertie) ;
    * un composant obligatoire manquant produit un DIAGNOSTIC, jamais
      une valeur ;
    * sans règle déclarée, le moteur ne calcule aucune moyenne ;
    * le périmètre ENCADRANT s'applique aussi à la préparation.
"""
from decimal import Decimal

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from evaluations.models import (
    Evaluation,
    EvaluationAttendance,
    EvaluationComponent,
    EvaluationGrade,
    EvaluationParticipant,
    RegleCalcul,
    RegleCalculVersion,
    SessionEvaluation,
    TypeEvaluation,
)
from evaluations.services import calcul as moteur
from evaluations.services.diagnostics import BLOQUANTS, DECISIONS
from evaluations.services.empreinte import empreinte, json_canonique
from evaluations.tests import factories as f

BASE = '/api/evaluations-academiques'


class TestEmpreinte(TestCase):
    """Contrats de l'empreinte : brique d'audit de C2."""

    def test_json_canonique_est_stable_et_trie(self):
        self.assertEqual(
            json_canonique({'b': 1, 'a': 2}), json_canonique({'a': 2, 'b': 1}),
        )

    def test_decimal_serialise_en_chaine(self):
        self.assertEqual(json_canonique({'v': Decimal('12.50')}), '{"v":"12.50"}')

    def test_empreinte_deterministe(self):
        charge = {'composants': [{'code': 'EXAMEN', 'valeur': Decimal('14.5')}]}
        self.assertEqual(empreinte(charge), empreinte(dict(charge)))

    def test_empreinte_change_si_une_valeur_change(self):
        base = {'composants': [{'code': 'EXAMEN', 'valeur': Decimal('14.5')}]}
        autre = {'composants': [{'code': 'EXAMEN', 'valeur': Decimal('14.6')}]}
        self.assertNotEqual(empreinte(base), empreinte(autre))

    def test_empreinte_est_un_sha256_hexadecimal(self):
        valeur = empreinte({'a': 1})
        self.assertEqual(len(valeur), 64)
        int(valeur, 16)  # lève si non hexadécimal


class TestDiagnostics(TestCase):
    def test_chaque_blocage_reference_une_decision_metier(self):
        for code, info in BLOQUANTS.items():
            self.assertIn(info['decision'], DECISIONS)

    def test_les_sept_decisions_sont_couvertes(self):
        couvertes = {info['decision'] for info in BLOQUANTS.values()}
        for decision in ('D1', 'D2', 'D3', 'D5', 'D6', 'D10', 'D15'):
            self.assertIn(decision, couvertes)


class BaseScenarioC2(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = f.creer_compte('ADMIN', 'admin-c2')
        cls.encadrant = f.creer_compte('ENCADRANT', 'encadrant-c2')
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
            type_evaluation=cls.type_eval, libelle='Épreuve C2',
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

    def _saisir(self, composant, valeur, statut='BROUILLON'):
        return EvaluationGrade.objects.create(
            evaluation_participant=self.participant, component=composant,
            valeur=valeur, bareme=composant.bareme, statut=statut,
        )


class TestPreparation(BaseScenarioC2):
    def test_preparation_sans_regle_ne_calcule_aucune_moyenne(self):
        """Aucune règle déclarée -> AUCUNE moyenne inventée."""
        self._saisir(self.examen, Decimal('15.00'))
        self._saisir(self.cc, Decimal('10.00'))
        preparation = moteur.preparer(self.participant)
        self.assertIsNone(preparation['moyenne'])
        self.assertFalse(preparation['calculable'])
        self.assertTrue(preparation['diagnostics'])

    def test_quote_par_composant_sans_choix_de_regle(self):
        """Le quotient valeur/barème est arithmétique, pas une règle."""
        self._saisir(self.examen, Decimal('10.00'))
        self._saisir(self.cc, Decimal('5.00'))
        par_code = {c['code']: c for c in moteur.preparer(self.participant)['composants']}
        self.assertEqual(par_code['EXAMEN']['quotient'], 0.5)
        self.assertEqual(par_code['CC']['quotient'], 0.25)

    def test_zero_est_une_valeur_et_non_une_absence(self):
        self._saisir(self.examen, Decimal('0.00'))
        self._saisir(self.cc, Decimal('0.00'))
        preparation = moteur.preparer(self.participant)
        self.assertFalse(preparation['imputation_absence'])
        par_code = {c['code']: c for c in preparation['composants']}
        self.assertEqual(par_code['EXAMEN']['valeur'], 0.0)
        self.assertFalse(par_code['EXAMEN']['absent'])

    def test_absence_n_est_jamais_convertie_en_valeur(self):
        """C2.3 / D2 : l'absence rend la composante NON NOTÉE (jamais 0)."""
        self._saisir(self.examen, Decimal('15.00'))
        self.participant.statut_participation = 'ABSENT_INJUSTIFIE'
        self.participant.save()
        preparation = moteur.preparer(self.participant)
        self.assertIsNone(preparation['moyenne'])
        self.assertEqual(preparation['regle_absence'], 'COMPOSANTE_NON_NOTEE')
        self.assertTrue(preparation['composante_non_notee'])
        self.assertTrue(all(l['valeur'] is None for l in preparation['composants']))
        codes = [d['code'] for d in preparation['diagnostics']]
        self.assertIn('COMPOSANT_MANQUANT', codes)

    def test_composant_obligatoire_manquant_produit_un_diagnostic(self):
        self._saisir(self.examen, Decimal('15.00'))
        preparation = moteur.preparer(self.participant)
        codes = [d['code'] for d in preparation['diagnostics']]
        decisions = [d['decision'] for d in preparation['diagnostics']]
        self.assertIn('COMPOSANT_MANQUANT', codes)
        self.assertIn('D6', decisions)

    def test_emargement_absent_est_signale_sans_conversion(self):
        """D2 : le badgeage est INFORMATIF et ne pilote pas le calcul
        académique (règle fondée sur le seul statut académique)."""
        from evaluations.models import Epreuve

        epreuve = Epreuve.objects.create(
            evaluation=self.evaluation, date='2027-01-10',
            heure_debut='08:00:00', heure_fin='10:00:00',
        )
        EvaluationAttendance.objects.create(
            evaluation_participant=self.participant, epreuve=epreuve, statut='ABSENT',
        )
        self._saisir(self.cc, Decimal('10.00'))
        self._saisir(self.examen, Decimal('15.00'))
        preparation = moteur.preparer(self.participant)
        self.assertFalse(preparation['imputation_absence'])
        self.assertFalse(preparation['composante_non_notee'])
        codes = [d['code'] for d in preparation['diagnostics']]
        # Le badgeage ne produit AUCUN diagnostic d'absence académique.
        self.assertNotIn('COMPOSANT_MANQUANT', codes)
        self.assertNotIn('ABSENCE_NON_TRAITEE', codes)
        # Les notes réellement saisies restent intactes.
        valeurs = sorted(l['valeur'] for l in preparation['composants'])
        self.assertEqual(valeurs, [10.0, 15.0])

    def test_composants_ordonnes_de_maniere_canonique(self):
        self._saisir(self.cc, Decimal('5.00'))
        self._saisir(self.examen, Decimal('15.00'))
        preparation = moteur.preparer(self.participant)
        self.assertEqual(
            [c['code'] for c in preparation['composants']], ['EXAMEN', 'CC'],
        )

    def test_empreinte_stable_entre_deux_preparations_identiques(self):
        self._saisir(self.examen, Decimal('15.00'))
        self._saisir(self.cc, Decimal('10.00'))
        self.assertEqual(
            moteur.preparer(self.participant)['empreinte'],
            moteur.preparer(self.participant)['empreinte'],
        )

    def test_instantane_de_regle_est_une_copie(self):
        regle = RegleCalcul.objects.create(
            code='PONDERATION_ECUE', libelle='Pondération ECUE', categorie='C',
            source='PARAMETRABLE',
        )
        version = RegleCalculVersion.objects.create(
            regle=regle, version=1, date_effet='2026-10-01',
            parametres={'normalisation': 'bareme'},
        )
        self._saisir(self.examen, Decimal('15.00'))
        self._saisir(self.cc, Decimal('10.00'))
        preparation = moteur.preparer(self.participant, regle_version=version)
        self.assertEqual(preparation['regle_snapshot']['code'], 'PONDERATION_ECUE')
        version.parametres = {'normalisation': 'AUTRE'}
        version.save()
        self.assertEqual(
            preparation['regle_snapshot']['parametres'], {'normalisation': 'bareme'},
        )

    def test_aucune_ecriture_en_base(self):
        from evaluations.models import ECUEResult

        self._saisir(self.examen, Decimal('15.00'))
        moteur.preparer(self.participant)
        self.assertEqual(ECUEResult.objects.count(), 0)


class TestPreparationApi(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = f.creer_compte('ADMIN', 'admin-api-c2')
        cls.encadrant = f.creer_compte('ENCADRANT', 'encadrant-api-c2')
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
            type_evaluation=cls.type_eval, libelle='Épreuve API C2',
        )
        cls.composant = EvaluationComponent.objects.create(
            evaluation=cls.evaluation, code='EXAMEN', libelle='Examen',
            poids=Decimal('100.00'), bareme=Decimal('20.00'),
        )
        cls.participant = EvaluationParticipant.objects.create(
            evaluation=cls.evaluation,
            inscription_pedagogique=cls.ctx['inscription_pedagogique'],
        )

    def api(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def _url(self):
        return (
            f'{BASE}/evaluations/{self.evaluation.pk}/participants/'
            f'{self.participant.pk}/preparation/'
        )

    def test_preparation_lisible_par_la_scolarite(self):
        reponse = self.api(self.admin).get(self._url())
        self.assertEqual(reponse.status_code, status.HTTP_200_OK, reponse.content)
        donnees = reponse.json()
        self.assertIn('empreinte', donnees)
        self.assertIn('diagnostics', donnees)
        self.assertIsNone(donnees['moyenne'])

    def test_preparation_refusee_hors_perimetre(self):
        tiers = f.creer_compte('ENCADRANT', 'encadrant-tiers')
        f.base_lmd_complete(formateur_user=tiers, suffixe='B')
        reponse = self.api(tiers).get(self._url())
        self.assertEqual(reponse.status_code, status.HTTP_404_NOT_FOUND)

    def test_preparation_refusee_a_un_auditeur(self):
        auditeur = f.creer_compte('AUDITEUR', 'auditeur-c2')
        reponse = self.api(auditeur).get(self._url())
        self.assertEqual(reponse.status_code, status.HTTP_403_FORBIDDEN)