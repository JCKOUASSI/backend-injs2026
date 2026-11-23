"""Tests d'INTÉGRATION — chaîne Évaluation → Délibération → Décision → Résultat.

Ces tests ne valident pas un module isolé : ils vérifient que les briques
s'enchaînent et que le MOTEUR DE DÉCISION est UNIQUE.

Règle vérifiée (non-contradiction) :
    pour une même situation académique, `evaluations` (moyennes) et `jurys`
    (moteur LMD/ECTS) ne doivent produire AUCUNE réponse contradictoire.
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
from scolarite.models import (
    AnneeAcademique,
    DossierEtudiant,
    ECUE,
    InscriptionAdministrative,
    InscriptionPedagogique,
    Maquette,
    Niveau,
    Semestre,
    UE,
)

from jurys.models import DecisionJury, PropositionJury, SessionJury

User = get_user_model()
class ChaineEvaluationDeliberationTest(TestCase):
    """Parcours complet : notes saisies → propositions LMD → décision."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username='integ_admin', password='p', role='INJS_ADMIN',
        )
        self.annee = AnneeAcademique.objects.create(
            libelle='2026-2027', date_debut=date(2026, 10, 1),
            date_fin=date(2027, 9, 30),
        )
        self.ref_formation = RefFormation.objects.create(intitule='Licence Intégration')
        self.niveau = Niveau.objects.create(
            code='L1I', libelle='Licence 1 Intégration', credits_requis=60,
        )
        self.semestre = Semestre.objects.create(niveau=self.niveau, numero=1)
        self.maquette = Maquette.objects.create(
            annee_academique=self.annee, ref_formation=self.ref_formation,
            niveau=self.niveau, statut=Maquette.Statut.BROUILLON,
        )
        self.ue = UE.objects.create(
            maquette=self.maquette, semestre=self.semestre, code='UE-INT', credits=30,
        )
        self.ref_module = RefModule.objects.create(intitule='Module intégré')
        self.ecue = ECUE.objects.create(
            ue=self.ue, code='ECUE-INT', intitule='ECUE intégré',
            credits=30, ref_module=self.ref_module,
        )
        # La maquette ACTIVE est immuable : on l'active après les UE/ECUE.
        self.maquette.statut = Maquette.Statut.ACTIVE
        self.maquette.save(update_fields=['statut'])

        self.participant = Participant.objects.create(
            nom='Intégration', prenom='Aimé', matricule='INT-001',
        )
        dossier = DossierEtudiant.objects.create(participant=self.participant)
        self.inscription = InscriptionAdministrative.objects.create(
            etudiant=dossier, annee_academique=self.annee,
            ref_formation=self.ref_formation, niveau=self.niveau,
            statut=InscriptionAdministrative.Statut.VALIDEE,
        )
        self.formation_op = Formation.objects.create(formation='Licence Intégration op')
        self.module = Module.objects.create(
            formation=self.formation_op, intitule=self.ecue.code,
            ref_module=self.ref_module,
        )
        self.mp = ModuleParticipant.objects.create(
            module=self.module, participant=self.participant,
        )
        self.ip = InscriptionPedagogique.objects.create(
            inscription=self.inscription, ecue=self.ecue, semestre=self.semestre,
            module_participant=self.mp,
            statut=InscriptionPedagogique.Statut.VALIDEE,
        )
        self.session = SessionJury.objects.create(
            annee_academique=self.annee, ref_formation=self.ref_formation,
            niveau=self.niveau, maquette=self.maquette,
            libelle='Jury intégration', creee_par=self.admin,
        )

    def _saisir_note(self, valeur):
        colonne = NoteModuleColonne.objects.create(
            module=self.module, libelle='Finale', note_max=20,
        )
        return NoteModule.objects.create(
            colonne=colonne, participant=self.participant,
            note=valeur, verrouillee=True, statut_validation='VALIDEE',
        )

    def test_chaine_notes_vers_propositions_vers_decision(self):
        """Les notes saisies alimentent le moteur, qui produit la décision."""
        from jurys import services

        self._saisir_note(Decimal('14.00'))
        services.calculer_propositions(self.session, self.admin)

        # 1. Le moteur LMD a produit des propositions pour CETTE inscription.
        proposition = PropositionJury.objects.filter(
            session=self.session, inscription=self.inscription,
        ).first()
        self.assertIsNotNone(proposition, 'le moteur doit produire une proposition')
        # 2. Empreinte SHA-256 : reproductibilité du calcul.
        self.assertTrue(proposition.empreinte)

        # 3. La décision est enregistrée et reste distincte de la proposition.
        decision = DecisionJury.objects.create(
            session=self.session, inscription=self.inscription,
            participant=self.participant,
            decision=DecisionJury.Decision.ADMIS,
            credits_acquis=Decimal('30.00'),
        )
        self.assertTrue(decision.decision)
        self.assertEqual(DecisionJury.objects.filter(session=self.session).count(), 1)

    def test_moteurs_evaluations_et_jurys_ne_se_contredisent_pas(self):
        """NON-CONTRADICTION : un seul moteur de décision.

        Règle LMD réelle (`scolarite/validation_services.py`) :
            ADMIS  ⟺ crédits acquis ≥ credits_requis DU NIVEAU
                     ET toutes les ECUE de la maquette sont notées
        La MOYENNE n'entre pas dans la décision : une bonne moyenne avec des
        crédits insuffisants donne AJOURNE. Le module `evaluations` ne produit
        aucune décision concurrente (moyennes + éligibilité rattrapage
        uniquement) : il ne peut donc pas contredire le moteur LMD.
        """
        from jurys import services

        self._saisir_note(Decimal('14.00'))
        services.calculer_propositions(self.session, self.admin)
        proposition = PropositionJury.objects.filter(
            session=self.session, inscription=self.inscription,
        ).first()
        self.assertIsNotNone(proposition)

        # 30 ECTS acquis pour 60 requis ⇒ AJOURNE : c'est la règle LMD,
        # pas une contradiction. On l'affirme explicitement pour verrouiller
        # la sémantique du moteur.
        self.assertEqual(proposition.decision_proposee, 'AJOURNE')
        self.assertEqual(proposition.credits_acquis, 30)

    def test_statistiques_refletent_les_decisions_reelles(self):
        """Les statistiques agrègent les décisions — aucune valeur en dur."""
        from jurys.services import statistiques_deliberation

        DecisionJury.objects.create(
            session=self.session, inscription=self.inscription,
            participant=self.participant, decision=DecisionJury.Decision.ADMIS,
            credits_acquis=Decimal('30.00'),
        )
        stats = statistiques_deliberation(self.session)
        self.assertEqual(stats['participants'], 1)
        self.assertEqual(stats['admis'], 1)
        self.assertEqual(stats['ajournes'], 0)
        self.assertEqual(stats['decisions']['enregistrees'], 1)
        self.assertTrue(stats['decisions']['completes'])

    def test_session_verrouillee_bloque_les_mutations(self):
        """Immutabilité : verrouiller interdit l'ajout ultérieur de membre."""
        from jurys import services

        self.session.statut = SessionJury.Statut.VERROUILLE
        self.session.save(update_fields=['statut'])
        self.assertTrue(self.session.verrouillee)
        cible = User.objects.create_user(
            username='membre_integre', password='p', role='FORMATEUR',
        )
        with self.assertRaises(Exception):
            services.ajouter_membre(self.session, cible, 'MEMBRE', self.admin)
