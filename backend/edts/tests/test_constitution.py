"""Constitution intelligente des groupes — tests.

Vérifie : plan dérivé du dimensionnement (noms en continuation de
l'existant, capacité = capacité cible), création effective, idempotence
(un second appel ne crée rien), simulation sans écriture, unicité des
noms entre parcours d'une même formation/niveau, et garde API
(planification requise, année requise).
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from edts.moteur.constitution import constituer_groupes, plan_constitution
from edts.moteur.dimensionnement import dimensionner
from edts.tests.test_dimensionnement import DimensionnementBase
from scolarite.models import Groupe, Parcours


class ConstitutionTests(DimensionnementBase):
    def test_plan_prolonge_la_numerotation_existante(self):
        self.inscrire(130)  # 3 groupes nécessaires à 60, 1 existe (L1-G1)
        plan = plan_constitution(self.annee.pk, capacite_cible=60)

        self.assertEqual(plan['total_a_creer'], 2)
        bloc = plan['creations'][0]
        self.assertEqual(
            [g['nom'] for g in bloc['groupes_a_creer']], ['L1-G2', 'L1-G3'])
        self.assertTrue(all(g['capacite_max'] == 60
                            for g in bloc['groupes_a_creer']))
        # Plan = lecture seule.
        self.assertEqual(Groupe.objects.count(), 1)

    def test_creation_puis_idempotence(self):
        self.inscrire(130)
        bilan = constituer_groupes(self.annee.pk, capacite_cible=60)
        self.assertEqual(bilan['total_crees'], 2)
        self.assertEqual(Groupe.objects.count(), 3)

        rapport = dimensionner(self.annee.pk, capacite_cible=60)
        self.assertEqual(rapport['totaux']['deficit_groupes'], 0)

        bilan2 = constituer_groupes(self.annee.pk, capacite_cible=60)
        self.assertEqual(bilan2['total_crees'], 0)
        self.assertEqual(Groupe.objects.count(), 3)

    def test_simulation_ne_cree_rien(self):
        self.inscrire(130)
        bilan = constituer_groupes(self.annee.pk, simulation=True)
        self.assertTrue(bilan['simulation'])
        self.assertEqual(bilan['plan']['total_a_creer'], 2)
        self.assertEqual(Groupe.objects.count(), 1)

    def test_noms_uniques_entre_parcours(self):
        """Deux parcours de la même formation/niveau : aucun nom répété."""
        parcours2 = Parcours.objects.create(
            code='P9', intitule='Parcours bis', ref_formation=self.formation,
        )
        self.inscrire(130)  # parcours principal : déficit 2
        # 70 inscrits sur le second parcours, aucun groupe : déficit 2.
        from formations.models import Participant
        from scolarite.models import DossierEtudiant, InscriptionAdministrative

        participants = [
            Participant(matricule=f'BIS-{i:04d}', nom='Nom', prenom='Prenom')
            for i in range(70)
        ]
        Participant.objects.bulk_create(participants)
        dossiers = [DossierEtudiant(participant=p) for p in participants]
        DossierEtudiant.objects.bulk_create(dossiers)
        InscriptionAdministrative.objects.bulk_create([
            InscriptionAdministrative(
                etudiant=d, annee_academique=self.annee,
                ref_formation=self.formation, niveau=self.f.niveau,
                parcours=parcours2,
                statut=InscriptionAdministrative.Statut.VALIDEE,
            )
            for d in dossiers
        ])

        bilan = constituer_groupes(self.annee.pk, capacite_cible=60)
        noms = [g['nom'] for g in bilan['groupes_crees']]
        self.assertEqual(len(noms), len(set(noms)))
        self.assertEqual(
            Groupe.objects.filter(annee_academique=self.annee).count(), 5)


class ConstitutionApiTests(DimensionnementBase):
    def setUp(self):
        super().setUp()
        self.inscrire(130)
        self.client = APIClient()
        User = get_user_model()
        self.planificateur = User.objects.create_user(
            username='planif-const', password='x')
        self.planificateur.role = 'SECRETARIAT'
        self.planificateur.save()
        self.lecteur = User.objects.create_user(
            username='lecteur-const', password='x')
        self.lecteur.role = 'AUDITEUR'
        self.lecteur.save()

    def test_simulation_puis_creation_via_api(self):
        self.client.force_authenticate(user=self.planificateur)
        reponse = self.client.post(
            '/api/edts/lmd/dimensionnement/constituer/',
            {'annee_academique_id': self.annee.pk, 'simulation': True},
            format='json',
        )
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.data['plan']['total_a_creer'], 2)
        self.assertEqual(Groupe.objects.count(), 1)

        reponse = self.client.post(
            '/api/edts/lmd/dimensionnement/constituer/',
            {'annee_academique_id': self.annee.pk},
            format='json',
        )
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.data['total_crees'], 2)
        self.assertEqual(Groupe.objects.count(), 3)

    def test_annee_requise(self):
        self.client.force_authenticate(user=self.planificateur)
        reponse = self.client.post(
            '/api/edts/lmd/dimensionnement/constituer/', {}, format='json')
        self.assertEqual(reponse.status_code, 400)
        self.assertEqual(reponse.data['motif_echec'], 'ANNEE_ACADEMIQUE_REQUISE')

    def test_lecteur_seul_refuse(self):
        self.client.force_authenticate(user=self.lecteur)
        reponse = self.client.post(
            '/api/edts/lmd/dimensionnement/constituer/',
            {'annee_academique_id': self.annee.pk},
            format='json',
        )
        self.assertEqual(reponse.status_code, 403)
        self.assertEqual(Groupe.objects.count(), 1)

