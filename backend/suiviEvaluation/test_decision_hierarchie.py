"""Garde-fou — hiérarchie des décisions INJS-LMD (résolution de l'audit A04).

CONTEXTE DE L'AUDIT A04
-----------------------
Deux moteurs coexistaient et pouvaient produire des verdicts opposés sur une
même situation :

    suiviEvaluation.calculer_decision   →  ADMIS   (notes + présence)
    scolarite.validation_services       →  AJOURNE (crédits ECTS / LMD)

RÉSOLUTION ADOPTÉE (non destructive, aucune donnée supprimée)
-------------------------------------------------------------
1. `jurys.DecisionJury` (moteur LMD/ECTS) est **l'unique autorité académique**.
2. `suiviEvaluation.DecisionPedagogique` devient un **verdict opérationnel** :
   il est conservé, mais explicitement étiqueté comme non-officiel partout où
   il est exposé (API, fiche 360°, exports).
3. `EXCLUSION` redevient une décision officielle à part entière : elle est
   produite par le moteur LMD dès qu'une UE tombe sous le seuil éliminatoire
   déjà paramétré (`RegleValidationLMD.seuil_elim`) et n'est JAMAIS convertie
   en AJOURNE.

Ces tests verrouillent cette hiérarchie : toute régression qui remettrait un
verdict opérationnel en position d'autorité, ou qui rabattrait EXCLUSION sur
AJOURNE, fera échouer la suite.
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from formations.models import (
    Formation,
    Module,
    ModuleParticipant,
    NoteModule,
    NoteModuleColonne,
    Participant,
    RefFormation,
    RefModule,
)
from jurys.models import DecisionJury, SessionJury
from scolarite.models import (
    AnneeAcademique,
    DossierEtudiant,
    ECUE,
    InscriptionAdministrative,
    InscriptionPedagogique,
    Maquette,
    Niveau,
    RegleValidationLMD,
    Semestre,
    UE,
)

User = get_user_model()


class HierarchieDecisionTest(TestCase):
    """Vérifie qu'une seule autorité décisionnelle subsiste."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            username='hierarchie_admin', password='p', role='INJS_ADMIN',
        )
        cls.participant = Participant.objects.create(
            nom='Hierarchie', prenom='Cas', matricule='HIER-001',
        )

        # ── Chaîne LMD (autorité officielle) ──────────────────────────
        cls.annee = AnneeAcademique.objects.create(
            libelle='2026-2027', date_debut=date(2026, 10, 1),
            date_fin=date(2027, 9, 30),
        )
        cls.ref_formation = RefFormation.objects.create(intitule='Cycle Hiérarchie')
        cls.niveau = Niveau.objects.create(
            code='HIER', libelle='Niveau Hiérarchie', credits_requis=60,
        )
        cls.semestre = Semestre.objects.create(niveau=cls.niveau, numero=1)
        cls.maquette = Maquette.objects.create(
            annee_academique=cls.annee, ref_formation=cls.ref_formation,
            niveau=cls.niveau, statut=Maquette.Statut.BROUILLON,
        )
        cls.ue = UE.objects.create(
            maquette=cls.maquette, semestre=cls.semestre, code='UE-HIER', credits=30,
        )
        cls.ref_module = RefModule.objects.create(intitule='Module Hiérarchie')
        cls.ecue = ECUE.objects.create(
            ue=cls.ue, code='ECUE-HIER', intitule='ECUE Hiérarchie',
            credits=30, ref_module=cls.ref_module,
        )
        cls.maquette.statut = Maquette.Statut.ACTIVE
        cls.maquette.save(update_fields=['statut'])

        cls.dossier = DossierEtudiant.objects.create(participant=cls.participant)
        cls.inscription = InscriptionAdministrative.objects.create(
            etudiant=cls.dossier, annee_academique=cls.annee,
            ref_formation=cls.ref_formation, niveau=cls.niveau,
            statut=InscriptionAdministrative.Statut.VALIDEE,
        )

        # ── Chaîne opérationnelle (verdict, jamais autorité) ──────────
        cls.formation = Formation.objects.create(
            formation='Formation Hiérarchie',
        )
        cls.module = Module.objects.create(
            formation=cls.formation, intitule='Module Hiérarchie',
            ref_module=cls.ref_module, duree_prevue_heures=Decimal('100'),
        )
        cls.mp = ModuleParticipant.objects.create(
            module=cls.module, participant=cls.participant,
        )
        cls.ip = InscriptionPedagogique.objects.create(
            inscription=cls.inscription, ecue=cls.ecue, semestre=cls.semestre,
            module_participant=cls.mp,
            statut=InscriptionPedagogique.Statut.VALIDEE,
        )
        cls.colonne = NoteModuleColonne.objects.create(
            module=cls.module, libelle='Finale', note_max=20,
        )

        cls.session = SessionJury.objects.create(
            annee_academique=cls.annee, ref_formation=cls.ref_formation,
            niveau=cls.niveau, maquette=cls.maquette,
            libelle='Jury hiérarchie', creee_par=cls.admin,
        )

        # Règle LMD officielle : seuil éliminatoire à 8/20 (paramétrage
        # EXISTANT du référentiel, aucune règle inventée pour ce correctif).
        RegleValidationLMD.objects.create(
            ref_formation=cls.ref_formation, niveau=cls.niveau,
            seuil_admission=Decimal('10.00'),
            compensation=RegleValidationLMD.Compensation.SEMESTRE,
            seuil_elim=Decimal('8.00'),
            credits_semestre=30,
        )

    def _poser_note(self, valeur):
        self.note, _ = NoteModule.objects.update_or_create(
            colonne=self.colonne, participant=self.participant,
            defaults={
                'note': Decimal(valeur), 'verrouillee': True,
                'statut_validation': 'VALIDEE',
            },
        )
        return self.note

    def _proposition_lmd(self):
        from jurys import services
        from jurys.models import PropositionJury

        services.calculer_propositions(self.session, self.admin)
        return (
            PropositionJury.objects
            .filter(session=self.session, inscription=self.inscription)
            .order_by('-id')
            .first()
        )

    # ────────────────────────────────────────────────────────────────
    # 1. EXCLUSION : décision officielle, jamais rabattue sur AJOURNE
    # ────────────────────────────────────────────────────────────────
    def test_exclusion_quand_moyenne_ue_sous_le_seuil_eliminatoire(self):
        """Moyenne 5/20 < seuil_elim 8 ⇒ EXCLUSION (et non AJOURNE)."""
        self._poser_note('5.00')
        proposition = self._proposition_lmd()

        self.assertIsNotNone(proposition)
        self.assertEqual(proposition.decision_proposee, 'EXCLUSION')
        self.assertNotEqual(
            proposition.decision_proposee, 'AJOURNE',
            "l'exclusion ne doit jamais être convertie en ajournement",
        )
        self.assertIn(
            'EXCLUSION', DecisionJury.Decision.values,
            'EXCLUSION doit rester une décision officielle du jury',
        )

    def test_ajourne_conserve_quand_les_credits_sont_insuffisants(self):
        """Moyenne correcte (14/20) mais 30 ECTS sur 60 ⇒ AJOURNE."""
        self._poser_note('14.00')
        proposition = self._proposition_lmd()

        self.assertIsNotNone(proposition)
        self.assertEqual(proposition.decision_proposee, 'AJOURNE')
        self.assertEqual(proposition.credits_acquis, 30)

    # ────────────────────────────────────────────────────────────────
    # 2. Le verdict opérationnel n'est pas une autorité
    # ────────────────────────────────────────────────────────────────
    def test_verdict_operationnel_etiquete_comme_non_officiel(self):
        """`DecisionPedagogique` est exposé mais étiqueté non-officiel."""
        from suiviEvaluation.academic_views import _serialize_decision
        from suiviEvaluation.services import calculer_decision

        presence_map = {(self.module.pk, self.participant.pk): 6000.0}
        verdict = calculer_decision(
            self.participant, self.formation, presence_map=presence_map,
        )
        payload = _serialize_decision(verdict)

        self.assertIs(payload['est_decision_officielle'], False)
        self.assertEqual(payload['autorite'], 'operationnelle')
        self.assertEqual(payload['source'], 'suiviEvaluation.DecisionPedagogique')
        # Aucune décision de jury n'existe encore : rien à afficher comme
        # autorité officielle — et surtout pas le verdict lui-même.
        self.assertIsNone(payload['decision_officielle'])

    # ────────────────────────────────────────────────────────────────
    # 3. La décision officielle est l'autorité affichée
    # ────────────────────────────────────────────────────────────────
    def test_decision_officielle_exposee_a_cote_du_verdict(self):
        from jurys.services import decision_officielle_pour
        from suiviEvaluation.academic_views import _serialize_decision
        from suiviEvaluation.services import calculer_decision

        DecisionJury.objects.create(
            session=self.session, inscription=self.inscription,
            participant=self.participant, decision=DecisionJury.Decision.ADMIS,
            credits_acquis=60, moyenne_generale=Decimal('14.00'),
        )

        officielle = decision_officielle_pour(self.participant)
        self.assertIsNotNone(officielle)
        self.assertEqual(officielle.decision, DecisionJury.Decision.ADMIS)

        presence_map = {(self.module.pk, self.participant.pk): 6000.0}
        verdict = calculer_decision(
            self.participant, self.formation, presence_map=presence_map,
        )
        payload = _serialize_decision(verdict)

        self.assertIsNotNone(payload['decision_officielle'])
        self.assertEqual(payload['decision_officielle']['decision'], 'ADMIS')
        self.assertEqual(payload['decision_officielle']['autorite'], 'officielle')
        self.assertEqual(
            payload['decision_officielle']['source'], 'jurys.DecisionJury',
        )

    def test_decision_officielle_la_plus_recente_est_retenue(self):
        from jurys.services import decision_officielle_pour

        DecisionJury.objects.create(
            session=self.session, inscription=self.inscription,
            participant=self.participant, decision=DecisionJury.Decision.AJOURNE,
            credits_acquis=30,
        )
        seconde = SessionJury.objects.create(
            annee_academique=self.annee, ref_formation=self.ref_formation,
            niveau=self.niveau, maquette=self.maquette,
            libelle='Jury hiérarchie (session 2)', creee_par=self.admin,
        )
        DecisionJury.objects.create(
            session=seconde, inscription=self.inscription,
            participant=self.participant, decision=DecisionJury.Decision.EXCLUSION,
            credits_acquis=0,
        )

        officielle = decision_officielle_pour(self.participant)
        self.assertEqual(officielle.decision, DecisionJury.Decision.EXCLUSION)
        # Le filtrage par session reste possible.
        self.assertEqual(
            decision_officielle_pour(self.participant, session=self.session).decision,
            DecisionJury.Decision.AJOURNE,
        )

    # ────────────────────────────────────────────────────────────────
    # 4. Statistiques : les exclusions ne sont plus des « autres »
    # ────────────────────────────────────────────────────────────────
    def test_statistiques_deliberation_isole_les_exclusions(self):
        from jurys.services import statistiques_deliberation

        DecisionJury.objects.create(
            session=self.session, inscription=self.inscription,
            participant=self.participant, decision=DecisionJury.Decision.EXCLUSION,
            credits_acquis=0,
        )
        stats = statistiques_deliberation(self.session)

        self.assertEqual(stats['exclus'], 1)
        self.assertEqual(stats['admis'], 0)
        self.assertEqual(stats['ajournes'], 0)
        self.assertEqual(stats['autres_decisions'], 0)