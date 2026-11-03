"""Diplômation d'exemple (tâche 34) : jamais validé, jamais authentique."""
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from authentication.models import User
from formations.models import Participant, RefFormation
from graduation.models import Diplome, ModeleDocument, RegistreDiplomes
from scolarite.models import (
    AnneeAcademique, DossierEtudiant, InscriptionAdministrative, Niveau,
)


class SeedDiplomationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='dir_grad', password='pass', role='DIRECTION',
        )
        cls.secr = User.objects.create_user(
            username='secr_grad', password='pass', role='SECRETARIAT',
        )
        cls.annee = AnneeAcademique.objects.create(
            libelle='2026-2027', date_debut='2026-10-01',
            date_fin='2027-07-31', courante=True,
        )
        cls.formation = RefFormation.objects.create(intitule='MASTER STAPS')
        cls.niveau = Niveau.objects.create(code='M2', libelle='Master 2', ordre=5)
        for rang in range(2):
            participant = Participant.objects.create(
                matricule=f'INJS21-00{rang}', nom=f'FINDE{rang}', prenom='Cycle',
            )
            dossier = DossierEtudiant.objects.create(participant=participant)
            InscriptionAdministrative.objects.create(
                etudiant=dossier, annee_academique=cls.annee,
                ref_formation=cls.formation, niveau=cls.niveau,
                statut=InscriptionAdministrative.Statut.VALIDEE,
            )

    def test_diplomes_exemple_jamais_valides_portail_public(self):
        call_command('seed_diplomation_demo')
        self.assertEqual(Diplome.objects.count(), 2)
        self.assertEqual(
            Diplome.objects.filter(statut=Diplome.Statut.VALIDATED).count(), 0,
        )
        self.assertEqual(ModeleDocument.objects.count(), 4)
        registre = RegistreDiplomes.objects.get(annee_academique=self.annee)
        self.assertFalse(registre.cloture)
        self.assertEqual(registre.diplomes.count(), 2)

        # Le portail public NE PEUT PAS authentifier un diplôme d'exemple.
        public = APIClient()
        diplome = Diplome.objects.first()
        res = public.get(f'/api/graduation/verifier/{diplome.numero_unique}/')
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.data['valide'])

        client = APIClient()
        client.force_authenticate(self.secr)
        res = client.get('/api/graduation/stats/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['diplomes'], 2)
        res = client.get('/api/graduation/eligibles/')
        self.assertEqual(len(res.data['results']), 2)
        self.assertTrue(
            all(r['etat'] == 'Diplôme préparé' for r in res.data['results']),
        )

    def test_idempotent_puis_purge(self):
        call_command('seed_diplomation_demo')
        call_command('seed_diplomation_demo')
        self.assertEqual(Diplome.objects.count(), 2)
        call_command('seed_diplomation_demo', '--purger')
        self.assertEqual(Diplome.objects.count(), 0)
        self.assertEqual(ModeleDocument.objects.count(), 0)
