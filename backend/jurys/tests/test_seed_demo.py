"""Jurys d'exemple (tâche 34) : seed, hub staff et garde-fous."""
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from authentication.models import User
from formations.models import Participant, RefFormation
from jurys.models import DecisionJury, PropositionJury, SessionJury
from scolarite.models import (
    AnneeAcademique, DossierEtudiant, InscriptionAdministrative, Maquette,
    Niveau, Semestre,
)


class SeedJurysTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.users = [
            User.objects.create_user(
                username=f'membre{i}', password='pass', role='DIRECTION',
            ) for i in range(3)
        ]
        cls.user = User.objects.create_user(
            username='secr_jury', password='pass', role='SECRETARIAT',
        )
        cls.annee = AnneeAcademique.objects.create(
            libelle='2026-2027', date_debut='2026-10-01',
            date_fin='2027-07-31', courante=True,
        )
        cls.formation = RefFormation.objects.create(intitule='LICENCE STAPS')
        cls.niveau = Niveau.objects.create(code='L3', libelle='Licence 3', ordre=3)
        Semestre.objects.create(niveau=cls.niveau, numero=5, libelle='Semestre 5')
        Maquette.objects.create(
            ref_formation=cls.formation, annee_academique=cls.annee,
            niveau=cls.niveau, statut=Maquette.Statut.ACTIVE,
        )
        participant = Participant.objects.create(
            matricule='INJS24-0100', nom='ETU', prenom='Test',
        )
        dossier = DossierEtudiant.objects.create(participant=participant)
        InscriptionAdministrative.objects.create(
            etudiant=dossier, annee_academique=cls.annee,
            ref_formation=cls.formation, niveau=cls.niveau,
            statut=InscriptionAdministrative.Statut.VALIDEE,
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_seed_cree_session_membres_sans_propositions(self):
        call_command('seed_jurys_demo')
        self.assertEqual(
            SessionJury.objects.filter(libelle__startswith='[Exemple]').count(), 1,
        )
        # Aucune proposition du moteur ECTS ne doit être fabriquée.
        self.assertEqual(PropositionJury.objects.count(), 0)
        decisions = DecisionJury.objects.all()
        for decision in decisions:
            self.assertTrue(decision.decision_manuelle)
            self.assertIn('[Exemple]', decision.justification)
            self.assertNotEqual(decision.decision, 'EXCLUSION')

        res = self.client.get('/api/juries/hub/stats/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['sessions'], 1)
        self.assertEqual(res.data['membres'], 3)

        res = self.client.get('/api/juries/hub/sessions/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['results'][0]['formation'], 'LICENCE STAPS')

    def test_idempotent_puis_purge(self):
        call_command('seed_jurys_demo')
        call_command('seed_jurys_demo')
        self.assertEqual(SessionJury.objects.count(), 1)
        call_command('seed_jurys_demo', '--purger')
        self.assertEqual(SessionJury.objects.count(), 0)
        self.assertEqual(DecisionJury.objects.count(), 0)
        # Les inscriptions ne sont jamais touchées.
        self.assertEqual(InscriptionAdministrative.objects.count(), 1)
