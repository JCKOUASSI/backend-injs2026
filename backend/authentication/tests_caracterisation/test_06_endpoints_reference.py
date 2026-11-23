"""U0-CURP — caractérisation des endpoints de RÉFÉRENCE en lecture seule.

Trois routes servent la vérité au front :
* ``GET /api/auth/me/``           — profil de la session ;
* ``GET /api/auth/roles/``        — hiérarchie, libellés et périmètres de gestion ;
* ``GET /api/auth/capabilities/`` — projection complète des capacités d'affichage.

Toutes trois exigent une session authentifiée (401 sinon) et doivent
rester strictement en lecture. U2 étendra la projection, sans jamais créer
de route ``/api/auth/capacites/`` concurrente.
"""
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from authentication.role_groups import ensure_role_groups

User = get_user_model()

MOT_DE_PASSE = 'Route#2026x'


class EndpointsReferenceTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_role_groups()
        cls.secretaire = User.objects.create_user(
            username='curp-route-sec', password=MOT_DE_PASSE, role='SECRETARIAT',
        )
        cls.formateur = User.objects.create_user(
            username='curp-route-form', password=MOT_DE_PASSE, role='FORMATEUR',
        )

    def _jeton(self, username, device_id=None):
        donnees = {'username': username, 'password': MOT_DE_PASSE}
        if device_id:
            donnees['device_id'] = device_id
        reponse = self.client.post('/api/auth/login/', donnees, format='json')
        self.assertEqual(reponse.status_code, 200, reponse.content)
        return reponse.json()['access']

    def _authentifier(self, jeton):
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {jeton}')

    def test_me_renvoie_le_profil_et_le_role(self):
        self._authentifier(self._jeton('curp-route-sec'))
        reponse = self.client.get('/api/auth/me/')
        self.assertEqual(reponse.status_code, status.HTTP_200_OK)
        corps = reponse.json()
        self.assertEqual(corps['username'], 'curp-route-sec')
        self.assertEqual(corps['role'], 'SECRETARIAT')
        self.assertEqual(corps['roles'], ['SECRETARIAT'])

    def test_roles_renvoie_la_hierarchie_complete(self):
        self._authentifier(self._jeton('curp-route-sec'))
        reponse = self.client.get('/api/auth/roles/')
        self.assertEqual(reponse.status_code, status.HTTP_200_OK)
        self.assertEqual(len(reponse.json()['hierarchy']), 12)
        self.assertEqual(reponse.json()['hierarchy'][0], 'ADMIN')
        self.assertIn('SECRETARIAT', reponse.json()['labels'])

    def test_capabilities_renvoie_la_projection_versionnee(self):
        self._authentifier(self._jeton('curp-route-sec'))
        reponse = self.client.get('/api/auth/capabilities/')
        self.assertEqual(reponse.status_code, status.HTTP_200_OK)
        corps = reponse.json()
        self.assertEqual(corps['version'], 1)
        self.assertEqual(corps['role'], 'SECRETARIAT')
        self.assertIn('capacites', corps)
        self.assertIn('perimetres', corps)

    def test_capabilities_secretariat_peut_lister_les_participants(self):
        self._authentifier(self._jeton('curp-route-sec'))
        corps = self.client.get('/api/auth/capabilities/').json()
        self.assertIn('lister', corps['capacites']['participants'])

    def test_capabilities_mobile_apres_connexion_appareil(self):
        jeton = self._jeton('curp-route-form', device_id='appareil-curp-route')
        self._authentifier(jeton)
        for route in ('/api/auth/me/', '/api/auth/roles/', '/api/auth/capabilities/'):
            with self.subTest(route=route):
                reponse = self.client.get(route)
                self.assertEqual(reponse.status_code, status.HTTP_200_OK)
        corps = self.client.get('/api/auth/capabilities/').json()
        self.assertEqual(corps['role'], 'FORMATEUR')

    def test_endpoints_reference_exigent_un_jeton(self):
        for route in ('/api/auth/me/', '/api/auth/roles/', '/api/auth/capabilities/'):
            with self.subTest(route=route):
                reponse = self.client.get(route)
                self.assertEqual(reponse.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_capacites_finance_n_inclut_pas_la_creation_de_participants(self):
        finance = User.objects.create_user(
            username='curp-route-fin', password=MOT_DE_PASSE, role='FINANCE',
        )
        self.client.force_authenticate(finance)
        corps = self.client.get('/api/auth/capabilities/').json()
        self.assertEqual(corps['role'], 'FINANCE')
        self.assertEqual(corps['capacites']['participants'], [])
