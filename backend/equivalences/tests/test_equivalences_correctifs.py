"""Correctifs du module Équivalences et dispenses + seed d'exemple.

1. Le sérialiseur de liste n'exposait pas les intitulés (`ref_formation`,
   `niveau`, nom de l'étudiant) que l'écran affiche : colonne Formation
   vide en réel.
2. La garde « dossier complet » vers AVIS_PEDAGOGIQUE s'appliquait APRÈS
   la transition : le 400 partait mais le statut avait déjà changé.
3. `services.appliquer` sans UE/ECUE cible dispensait TOUTES les
   inscriptions pédagogiques de l'étudiant.
4. La commande `seed_equivalences_demo` couvre types et statuts sur les
   cohortes réelles, de façon idempotente et purgeable.
"""
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from authentication.models import User
from formations.models import Participant, RefFormation
from scolarite.models import (
    ECUE, AnneeAcademique, DossierEtudiant, EvenementScolarite,
    InscriptionAdministrative, InscriptionPedagogique, Maquette, Niveau,
    Semestre, UE,
)

from equivalences import services, workflow
from equivalences.models import DemandeEquivalenceDispense
from equivalences.tests.test_equivalences import EquivalenceBase, make_user

S = DemandeEquivalenceDispense.Statut
D = DemandeEquivalenceDispense.Decision


class SerialiseurEtGardesTests(EquivalenceBase):
    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(make_user('sec_corr', role='SECRETARIAT'))

    def test_liste_expose_les_intitules_affiches_par_ecran(self):
        res = self.client.get('/api/equivalences/demandes/')
        self.assertEqual(res.status_code, 200)
        ligne = next(d for d in res.data if d['id'] == self.demande.pk)
        self.assertEqual(ligne['ref_formation'], 'LICENCE STAPS')
        self.assertEqual(ligne['niveau'], 'L1')
        self.assertIn('Fatou', ligne['etudiant_nom'])
        self.assertEqual(ligne['ue_code'], 'UE11')
        self.assertEqual(ligne['ecue_code'], 'ECUE111')
        self.assertEqual(ligne['etablissement_origine'], 'Université de Cocody')
        self.assertEqual(ligne['nb_pieces'], 1)
        self.assertFalse(ligne['dossier_complet'])  # pièce obligatoire manquante

    def test_garde_pieces_ne_change_plus_le_statut_en_cas_de_refus(self):
        workflow.appliquer_transition(self.demande, S.SOUMISE)
        workflow.appliquer_transition(self.demande, S.EN_INSTRUCTION)
        res = self.client.post(
            f'/api/equivalences/demandes/{self.demande.pk}/transition/',
            {'statut': 'AVIS_PEDAGOGIQUE'}, format='json',
        )
        self.assertEqual(res.status_code, 400)
        self.demande.refresh_from_db()
        self.assertEqual(self.demande.statut, S.EN_INSTRUCTION)


class ApplicationSansCibleTests(EquivalenceBase):
    def test_sans_cible_aucune_ip_dispensee(self):
        globale = DemandeEquivalenceDispense.objects.create(
            type_demande='EQUIVALENCE', etudiant=self.dossier,
            annee_academique=self.annee, ref_formation=self.formation,
            niveau=self.niveau,
        )
        for statut in (S.SOUMISE, S.EN_INSTRUCTION, S.AVIS_PEDAGOGIQUE, S.DECISION):
            workflow.appliquer_transition(globale, statut)
        globale.decision = D.FAVORABLE
        globale.credits_reconnus = 30
        globale.save(update_fields=['decision', 'credits_reconnus'])
        workflow.appliquer_transition(globale, S.VALIDEE)

        services.appliquer(globale)
        self.ip.refresh_from_db()
        self.assertNotEqual(
            self.ip.statut, InscriptionPedagogique.Statut.DISPENSEE,
            'Une reconnaissance globale ne doit dispenser aucune IP.',
        )
        self.assertTrue(EvenementScolarite.objects.filter(
            etudiant=self.dossier,
            type_evenement=EvenementScolarite.Type.EQUIVALENCE_DISPENSE,
        ).exists())


class SeedEquivalencesDemoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            username='admin_eq', password='pass', role='ADMIN', is_superuser=True,
        )
        cls.annee = AnneeAcademique.objects.create(
            libelle='2026-2027', date_debut='2026-10-01', date_fin='2027-07-31',
            courante=True,
        )
        cls.formation = RefFormation.objects.create(intitule='LICENCE STAPS')
        cls.niveau = Niveau.objects.create(code='L1', libelle='Licence 1', ordre=1)
        s1 = Semestre.objects.create(niveau=cls.niveau, numero=1, libelle='S1')
        # BROUILLON d'abord (UE/ECUE verrouillées sur maquette ACTIVE), puis ACTIVE.
        maquette = Maquette.objects.create(
            annee_academique=cls.annee, ref_formation=cls.formation, niveau=cls.niveau,
        )
        ue = UE.objects.create(
            maquette=maquette, semestre=s1, code='UE11',
            intitule='Sciences du mouvement', credits=6,
        )
        ECUE.objects.create(ue=ue, code='ECUE111', intitule='Anatomie', credits=6)
        maquette.statut = Maquette.Statut.ACTIVE
        maquette.save(update_fields=['statut'])
        for rang in range(3):
            participant = Participant.objects.create(
                matricule=f'INJS26-02{rang:02d}', nom=f'NOM{rang}', prenom='Test',
            )
            dossier = DossierEtudiant.objects.create(participant=participant)
            InscriptionAdministrative.objects.create(
                etudiant=dossier, annee_academique=cls.annee,
                ref_formation=cls.formation, niveau=cls.niveau,
                statut=InscriptionAdministrative.Statut.VALIDEE,
            )

    def test_seed_couvre_les_deux_types_et_est_idempotent(self):
        call_command('seed_equivalences_demo', utilisateur='admin_eq', stdout=None)
        demandes = DemandeEquivalenceDispense.objects.all()
        self.assertEqual(demandes.count(), 2)  # 1 cohorte × 2 types
        self.assertEqual(
            set(demandes.values_list('type_demande', flat=True)),
            {'EQUIVALENCE', 'DISPENSE'},
        )
        for demande in demandes:
            self.assertTrue(demande.motif.startswith('[Exemple]'))
            self.assertIsNotNone(demande.ue_id)
        dispense = demandes.get(type_demande='DISPENSE')
        self.assertIsNotNone(dispense.ecue_id)

        call_command('seed_equivalences_demo', utilisateur='admin_eq', stdout=None)
        self.assertEqual(DemandeEquivalenceDispense.objects.count(), 2)

    def test_volume_complete_jusqua_la_cible_sans_depasser(self):
        """--volume N : complète jusqu'à N demandes [Exemple], idempotent."""
        call_command('seed_equivalences_demo', utilisateur='admin_eq', volume=6, stdout=None)
        self.assertEqual(DemandeEquivalenceDispense.objects.count(), 6)
        call_command('seed_equivalences_demo', utilisateur='admin_eq', volume=6, stdout=None)
        self.assertEqual(DemandeEquivalenceDispense.objects.count(), 6)
        # Les demandes de volume sont repérables et purgeables.
        self.assertTrue(DemandeEquivalenceDispense.objects.filter(
            motif__contains='Demande de volume',
        ).exists())

    def test_purge_retire_les_exemples_non_appliquees(self):
        call_command('seed_equivalences_demo', utilisateur='admin_eq', stdout=None)
        # Cohorte 0 → cibles BROUILLON et SOUMISE : toutes purgeables.
        call_command('seed_equivalences_demo', purger=True, stdout=None)
        self.assertEqual(DemandeEquivalenceDispense.objects.count(), 0)
