"""Écran « Réinscriptions & transferts » — pagination et panorama des flux.

La liste historique plafonnait à 500 lignes sans total réel (1 867 flux en
2026-2027 affichés « 500 éléments ») : ces tests couvrent la pagination
opt-in (total exact, pages disjointes et stables), la compatibilité de
l'ancien contrat (liste simple sans paramètres) et l'endpoint stats.
"""
from django.test import TestCase
from rest_framework.test import APIClient

from authentication.models import User
from formations.models import Participant, RefFormation
from scolarite.models import (
    AnneeAcademique, DossierEtudiant, InscriptionAdministrative, Niveau,
)

IA = InscriptionAdministrative


class ReinscriptionsBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.annee = AnneeAcademique.objects.create(
            libelle='2026-2027', date_debut='2026-10-01', date_fin='2027-07-31',
            courante=True,
        )
        cls.formation = RefFormation.objects.create(intitule='LICENCE STAPS')
        cls.niveau = Niveau.objects.create(code='L2', libelle='Licence 2', ordre=2)
        cls.user = User.objects.create_user(
            username='sec_reins', password='pass', role='SECRETARIAT',
        )
        # 1 première inscription (exclue des flux) + 3 flux de types distincts.
        types = [IA.Type.PREMIERE, IA.Type.REINSCRIPTION, IA.Type.REDOUBLEMENT, IA.Type.TRANSFERT]
        for rang, type_inscription in enumerate(types):
            participant = Participant.objects.create(
                matricule=f'INJS25-03{rang:02d}', nom=f'NOM{rang}', prenom='Test',
            )
            dossier = DossierEtudiant.objects.create(participant=participant)
            IA.objects.create(
                etudiant=dossier, annee_academique=cls.annee,
                ref_formation=cls.formation, niveau=cls.niveau,
                type_inscription=type_inscription, statut=IA.Statut.VALIDEE,
            )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)


class ReinscriptionsListeTests(ReinscriptionsBase):
    def test_sans_parametres_contrat_historique_exclut_les_premieres(self):
        res = self.client.get('/api/scolarite/reinscriptions/')
        self.assertEqual(res.status_code, 200)
        self.assertIsInstance(res.data, list)
        self.assertEqual(len(res.data), 3)
        self.assertEqual(
            {d['type_inscription'] for d in res.data},
            {'REINSCRIPTION', 'REDOUBLEMENT', 'TRANSFERT'},
        )

    def test_pagination_totaux_exacts_et_pages_disjointes(self):
        page1 = self.client.get('/api/scolarite/reinscriptions/', {'page': 1, 'page_size': 2})
        self.assertEqual(page1.status_code, 200)
        self.assertEqual(page1.data['count'], 3)
        self.assertEqual(page1.data['total_pages'], 2)
        page2 = self.client.get('/api/scolarite/reinscriptions/', {'page': 2, 'page_size': 2})
        ids1 = {d['id'] for d in page1.data['results']}
        ids2 = {d['id'] for d in page2.data['results']}
        self.assertEqual(len(ids2), 1)
        self.assertFalse(ids1 & ids2)

    def test_parametres_de_pagination_invalides_refuses(self):
        res = self.client.get('/api/scolarite/reinscriptions/', {'page': 'abc'})
        self.assertEqual(res.status_code, 400)
        res = self.client.get('/api/scolarite/reinscriptions/', {'page_size': 500})
        self.assertEqual(res.status_code, 400)

    def test_filtre_par_type(self):
        res = self.client.get(
            '/api/scolarite/reinscriptions/',
            {'type_inscription': 'TRANSFERT', 'page': 1},
        )
        self.assertEqual(res.data['count'], 1)
        self.assertEqual(res.data['results'][0]['type_inscription'], 'TRANSFERT')


class ReinscriptionsStatsTests(ReinscriptionsBase):
    def test_panorama_par_type_et_taux_de_continuite(self):
        res = self.client.get('/api/scolarite/reinscriptions/stats/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['annee_academique'], '2026-2027')
        self.assertEqual(res.data['total_inscriptions'], 4)
        self.assertEqual(res.data['total_flux'], 3)
        self.assertEqual(res.data['par_type']['REINSCRIPTION'], 1)
        self.assertEqual(res.data['par_type']['PREMIERE'], 1)
        self.assertEqual(res.data['par_niveau'], {'L2': 3})
        # 3 flux validés sur 4 inscriptions validées.
        self.assertEqual(res.data['taux_continuite'], 75.0)

    def test_annee_inconnue_refusee(self):
        res = self.client.get(
            '/api/scolarite/reinscriptions/stats/', {'annee_academique_id': 999999},
        )
        self.assertEqual(res.status_code, 400)
