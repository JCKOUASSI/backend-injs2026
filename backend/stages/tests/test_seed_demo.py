"""Stages d'exemple (tâche 34) : seed idempotent et panorama."""
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from authentication.models import User
from formations.models import Participant, RefFormation
from scolarite.models import (
    AnneeAcademique, DossierEtudiant, InscriptionAdministrative, Niveau,
)
from stages.models import ConventionStage, EvaluationStage, OrganismeAccueil


class SeedStagesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='admin_stages', password='pass', role='ADMIN',
        )
        cls.annee = AnneeAcademique.objects.create(
            libelle='2026-2027', date_debut='2026-10-01', date_fin='2027-07-31',
            courante=True,
        )
        cls.formation = RefFormation.objects.create(intitule='LICENCE STAPS')
        cls.niveau = Niveau.objects.create(code='L3', libelle='Licence 3', ordre=3)
        for rang in range(3):
            participant = Participant.objects.create(
                matricule=f'INJS24-09{rang}', nom=f'STAGIAIRE{rang}', prenom='Test',
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

    def test_seed_cree_organismes_et_conventions(self):
        call_command('seed_stages_demo')
        self.assertEqual(OrganismeAccueil.objects.count(), 20)
        self.assertEqual(ConventionStage.objects.count(), 3)
        self.assertTrue(
            ConventionStage.objects.filter(
                commentaires__startswith='[Exemple]',
            ).exists(),
        )
        res = self.client.get('/api/stages/stats/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['conventions'], 3)
        self.assertEqual(res.data['organismes'], 20)
        self.assertEqual(res.data['etudiants_en_stage'], 3)

    def test_seed_idempotent_puis_purge(self):
        call_command('seed_stages_demo')
        call_command('seed_stages_demo')
        self.assertEqual(ConventionStage.objects.count(), 3)
        self.assertEqual(OrganismeAccueil.objects.count(), 20)
        call_command('seed_stages_demo', '--purger')
        self.assertEqual(ConventionStage.objects.count(), 0)
        self.assertEqual(EvaluationStage.objects.count(), 0)
        self.assertEqual(OrganismeAccueil.objects.count(), 0)
