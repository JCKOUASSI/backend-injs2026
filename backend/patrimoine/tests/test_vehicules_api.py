"""Tests API de l'endpoint véhicules (patrimoine) — régression vehicules_api.

Couvre le correctif fonctionnel : le POST réussi doit retourner
201 + le véhicule sérialisé (le retour était absent, la vue retournait None).
"""
from django.db import transaction
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from authentication.models import User
from patrimoine.models import Vehicule

URL_VEHICULES = '/api/patrimoine/vehicules/'
URL_MOUVEMENTS = '/api/patrimoine/mouvements/'


class VehiculesApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.gestionnaire = User.objects.create_user(
            username='gestionnaire_pat', password='pass', role='ADMIN')
        cls.lecteur = User.objects.create_user(
            username='lecteur_pat', password='pass', role='ENCADRANT')

    def setUp(self):
        self.client = APIClient()

    # ── GET ──────────────────────────────────────────────────────────
    def test_get_liste_vide_authentifie(self):
        self.client.force_authenticate(user=self.lecteur)
        res = self.client.get(URL_VEHICULES)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data, {'results': []})

    def test_get_liste_format_reel(self):
        Vehicule.objects.create(
            immatriculation='AB-123-CD', marque='Toyota', modele='Hilux',
            kilometrage=45000)
        self.client.force_authenticate(user=self.lecteur)
        res = self.client.get(URL_VEHICULES)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data['results']), 1)
        self.assertEqual(res.data['results'][0], {
            'id': res.data['results'][0]['id'],
            'immatriculation': 'AB-123-CD',
            'marque': 'Toyota',
            'modele': 'Hilux',
            'annee_mise_en_circulation': None,
            'kilometrage': 45000,
            'prochaine_revision': None,
        })

    def test_get_anonyme_refuse(self):
        res = self.client.get(URL_VEHICULES)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    # ── POST valide ──────────────────────────────────────────────────
    def test_post_valide_retourne_201_et_vehicule_serialise(self):
        """Régression : le POST réussi retournait None (500) avant correctif."""
        self.client.force_authenticate(user=self.gestionnaire)
        res = self.client.post(URL_VEHICULES, {
            'immatriculation': 'CI-2026-01', 'marque': 'Renault',
            'modele': 'Kangoo', 'kilometrage': 1200,
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        vehicule = Vehicule.objects.get(immatriculation='CI-2026-01')
        self.assertEqual(res.data, {
            'id': vehicule.id,
            'immatriculation': 'CI-2026-01',
            'marque': 'Renault',
            'modele': 'Kangoo',
            'annee_mise_en_circulation': None,
            'kilometrage': 1200,
            'prochaine_revision': None,
        })

    def test_post_minimal_champs_par_defaut(self):
        self.client.force_authenticate(user=self.gestionnaire)
        res = self.client.post(
            URL_VEHICULES, {'immatriculation': 'CI-2026-02'}, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data['marque'], '')
        self.assertEqual(res.data['modele'], '')
        self.assertEqual(res.data['kilometrage'], 0)

    # ── POST invalide / erreurs métier ───────────────────────────────
    def test_post_sans_immatriculation_400(self):
        self.client.force_authenticate(user=self.gestionnaire)
        res = self.client.post(URL_VEHICULES, {'marque': 'Toyota'}, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res.data, {'error': "L'immatriculation est obligatoire."})
        self.assertEqual(Vehicule.objects.count(), 0)

    def test_post_immatriculation_dupliquee_400(self):
        Vehicule.objects.create(immatriculation='AB-123-CD')
        self.client.force_authenticate(user=self.gestionnaire)
        # savepoint : l'IntegrityError doit rester contenue (transaction PG)
        with transaction.atomic():
            res = self.client.post(
                URL_VEHICULES, {'immatriculation': 'AB-123-CD'}, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', res.data)
        self.assertEqual(Vehicule.objects.filter(immatriculation='AB-123-CD').count(), 1)

    # ── Permissions ──────────────────────────────────────────────────
    def test_post_lecture_seule_403(self):
        self.client.force_authenticate(user=self.lecteur)
        res = self.client.post(
            URL_VEHICULES, {'immatriculation': 'CI-403'}, format='json')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Vehicule.objects.count(), 0)

    def test_post_anonyme_401(self):
        res = self.client.post(
            URL_VEHICULES, {'immatriculation': 'CI-401'}, format='json')
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(Vehicule.objects.count(), 0)

    # ── Non-régression des endpoints voisins ─────────────────────────
    def test_mouvements_get_non_regression(self):
        """La suppression du code mort ne change pas mouvements_api."""
        self.client.force_authenticate(user=self.lecteur)
        res = self.client.get(URL_MOUVEMENTS)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data, {'results': []})

    def test_creation_vehicule_puis_liste(self):
        self.client.force_authenticate(user=self.gestionnaire)
        res = self.client.post(
            URL_VEHICULES, {'immatriculation': 'CI-2026-03'}, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        res = self.client.get(URL_VEHICULES)
        self.assertEqual(
            [v['immatriculation'] for v in res.data['results']], ['CI-2026-03'])
