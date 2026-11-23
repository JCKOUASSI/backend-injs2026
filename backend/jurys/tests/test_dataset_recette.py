"""Tests A08 — jeu de données de recette reproductible.

Vérifie que la commande `creer_dataset_recette_jury` :
- crée le parcours complet Formation → … → Session de jury ;
- est IDEMPOTENTE (relancée sans dupliquer) ;
- est NON DESTRUCTIVE (elle ne touche pas aux données préexistantes) ;
- ne produit que des données FICTIVES (préfixe RECETTE).
"""
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from formations.models import NoteModule, Participant
from scolarite.models import Groupe, InscriptionAdministrative, Maquette
from formations.models import RefFormation

from jurys.models import DecisionJury, MembreJury, SessionJury

User = get_user_model()


class DatasetRecetteTest(TestCase):
    """Le jeu de recette doit permettre de valider le parcours de bout en bout."""

    def setUp(self):
        self.dfrc = User.objects.create_user(
            username='recette_admin', password='p', role='INJS_ADMIN',
        )

    def _executer(self, **kwargs):
        sortie = StringIO()
        call_command('creer_dataset_recette_jury', stdout=sortie, **kwargs)
        return sortie.getvalue()

    def test_parcours_complet_est_cree(self):
        self._executer(participants=6)
        # Pédagogie
        self.assertEqual(Groupe.objects.filter(nom__startswith='RECETTE').count(), 1)
        maquette = Maquette.objects.get(ref_formation__intitule__startswith='RECETTE')
        self.assertEqual(maquette.unites_enseignement.count(), 1)
        self.assertEqual(
            maquette.unites_enseignement.first().ecues.count(), 2,
        )
        # Participants + inscriptions + notes
        self.assertEqual(Participant.objects.filter(matricule__startswith='RECETTE').count(), 6)
        self.assertEqual(
            InscriptionAdministrative.objects.filter(
                ref_formation__intitule__startswith='RECETTE',
            ).count(), 6,
        )
        self.assertTrue(
            NoteModule.objects.filter(
                participant__matricule__startswith='RECETTE',
            ).exists(), 'le jeu doit contenir des notes saisies',
        )
        # Jury
        self.assertEqual(SessionJury.objects.count(), 1)
        session = SessionJury.objects.get()
        self.assertEqual(session.membres.count(), 1)
        self.assertEqual(session.membres.first().fonction, MembreJury.Fonction.PRESIDENT)

    def test_commande_est_idempotente(self):
        self._executer(participants=4)
        premiere = (
            Participant.objects.filter(matricule__startswith='RECETTE').count(),
            SessionJury.objects.count(),
            Maquette.objects.filter(ref_formation__intitule__startswith='RECETTE').count(),
        )
        # Relance : aucun doublon ne doit apparaître.
        self._executer(participants=4)
        self.assertEqual(
            Participant.objects.filter(matricule__startswith='RECETTE').count(),
            premiere[0],
        )
        self.assertEqual(SessionJury.objects.count(), premiere[1])
        self.assertEqual(
            Maquette.objects.filter(ref_formation__intitule__startswith='RECETTE').count(),
            premiere[2],
        )

    def test_commande_est_non_destructive(self):
        """Des données préexistantes hors RECETTE doivent rester intactes."""
        RefFormation.objects.create(intitule='Formation métier EXISTANTE')
        avant = RefFormation.objects.count()
        self._executer(participants=3)
        # La formation métier existe toujours, et la commande n'a rien effacé.
        self.assertTrue(
            RefFormation.objects.filter(intitule='Formation métier EXISTANTE').exists(),
        )
        self.assertGreater(RefFormation.objects.count(), avant)

    def test_donnees_strictement_fictives(self):
        """Tout ce que la commande crée est identifiable par le préfixe RECETTE."""
        self._executer(participants=3)
        for participant in Participant.objects.filter(matricule__startswith='RECETTE'):
            self.assertTrue(participant.matricule.startswith('RECETTE'))
            self.assertEqual(participant.nom, 'RECETTE')

    def test_etablit_calcule_les_propositions(self):
        """L'option --etablit enchaîne jusqu'aux propositions du moteur LMD."""
        from jurys.models import PropositionJury
        self._executer(participants=3, etablit=True)
        session = SessionJury.objects.get()
        self.assertTrue(
            PropositionJury.objects.filter(session=session).exists(),
            'le moteur LMD doit produire des propositions',
        )
        # Chaque proposition porte une empreinte SHA-256 (reproductibilité).
        proposition = PropositionJury.objects.filter(session=session).first()
        self.assertTrue(proposition.empreinte)
