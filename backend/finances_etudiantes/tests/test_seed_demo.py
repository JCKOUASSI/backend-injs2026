"""Finances d'exemple (tâche 34) : jamais facturables, jamais encaissées."""
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from authentication.models import User
from finances_etudiantes.models import (
    Echeancier, Facture, LigneEcheancier, Paiement, Quittance,
    Remboursement, Tarification,
)
from finances_etudiantes.services import generer_echeancier_pour_etudiant
from formations.models import Participant, RefFormation
from scolarite.models import (
    AnneeAcademique, DossierEtudiant, InscriptionAdministrative, Niveau,
)


class SeedFinancesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='finance1', password='pass', role='FINANCE',
        )
        cls.annee = AnneeAcademique.objects.create(
            libelle='2026-2027', date_debut='2026-10-01',
            date_fin='2027-07-31', courante=True,
        )
        cls.formation = RefFormation.objects.create(intitule='LICENCE STAPS')
        cls.niveau = Niveau.objects.create(code='L1', libelle='Licence 1', ordre=1)
        participant = Participant.objects.create(
            matricule='INJS26-0001', nom='ETU', prenom='Finance',
        )
        cls.dossier = DossierEtudiant.objects.create(participant=participant)
        InscriptionAdministrative.objects.create(
            etudiant=cls.dossier, annee_academique=cls.annee,
            ref_formation=cls.formation, niveau=cls.niveau,
            statut=InscriptionAdministrative.Statut.VALIDEE,
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_aucun_acte_financier_reel(self):
        call_command('seed_finances_demo')
        # 1) Barème toujours inactif → le service officiel refuse de générer
        #    un échéancier facturable depuis les montants d'exemple.
        self.assertEqual(Tarification.objects.filter(actif=True).count(), 0)
        self.assertIsNone(
            generer_echeancier_pour_etudiant(self.dossier, self.annee),
        )
        # 2) Aucune ligne acquittée, aucun paiement confirmé, aucune quit‑
        #    tance, aucune facture émise.
        self.assertEqual(
            LigneEcheancier.objects.filter(statut='PAYE').count(), 0,
        )
        self.assertEqual(
            Paiement.objects.filter(
                statut__in=('CONFIRME', 'RAPPROCHE'),
            ).count(), 0,
        )
        self.assertEqual(Quittance.objects.count(), 0)
        self.assertEqual(
            Facture.objects.exclude(statut='BROUILLON').count(), 0,
        )
        self.assertEqual(
            Remboursement.objects.exclude(statut='INITIE').count(), 0,
        )
        self.assertEqual(Echeancier.objects.count(), 1)

        res = self.client.get('/api/finances-etudiantes/hub/stats/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['montant_encaisse_confirme'], 0.0)
        self.assertEqual(res.data['tarifications_actives'], 0)

        res = self.client.get('/api/finances-etudiantes/hub/echeanciers/')
        self.assertEqual(res.status_code, 200)
        ligne = res.data['results'][0]
        # 10 000 + 25 000 + 150 000 + 15 000 + 5 000 (barème indicatif)
        self.assertEqual(ligne['total'], 205000.0)
        self.assertEqual(ligne['reste'], ligne['total'])

    def test_idempotent_puis_purge(self):
        call_command('seed_finances_demo')
        call_command('seed_finances_demo')
        self.assertEqual(Echeancier.objects.count(), 1)
        self.assertEqual(Paiement.objects.count(), 1)
        call_command('seed_finances_demo', '--purger')
        self.assertEqual(Tarification.objects.count(), 0)
        self.assertEqual(Paiement.objects.count(), 0)
        self.assertEqual(Facture.objects.count(), 0)
