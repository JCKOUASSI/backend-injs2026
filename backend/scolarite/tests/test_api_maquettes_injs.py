"""API des maquettes : lecture des UE/ECUE et contrôle des permissions.

Ces tests couvrent le contrat réellement consommé par l'écran « UE / ECUE » du
frontend : ``GET /api/scolarite/maquettes/<id>/ues/``. Cette route n'acceptait
que POST et renvoyait 405 à l'interface ; elle est désormais lisible.
"""

from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from authentication.models import User
from scolarite.models import ECUE, Maquette, UE


class MaquettesApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('init_referentiels_lmd', '--annee', '2026-2027',
                     stdout=StringIO())
        call_command('import_referentiel_injs_lmd', stdout=StringIO())
        call_command('qualifier_referentiel_injs_l6', stdout=StringIO())
        call_command('configurer_referentiel_injs', stdout=StringIO())
        cls.maquette = Maquette.objects.filter(
            ref_formation__filiere_code='F01', niveau__code='L1',
        ).first()

    def setUp(self):
        self.admin = User.objects.create_user(
            username='api_admin', password='pass', role='INJS_ADMIN',
        )
        self.client = APIClient()

    # ── Lecture ────────────────────────────────────────────────────────────
    def test_liste_des_maquettes(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get('/api/scolarite/maquettes/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 20)

    def test_filtre_par_formation(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get(
            f'/api/scolarite/maquettes/?ref_formation_id={self.maquette.ref_formation_id}',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(all(
            m['ref_formation_id'] == self.maquette.ref_formation_id
            for m in response.json()
        ))

    def test_filtre_vide_ignore_et_filtre_invalide_refuse(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(
            self.client.get('/api/scolarite/maquettes/?ref_formation_id=').status_code,
            200,
        )
        self.assertEqual(
            self.client.get('/api/scolarite/maquettes/?ref_formation_id=abc').status_code,
            400,
        )

    def test_ue_de_la_maquette_lisibles(self):
        """Contrat de l'écran UE/ECUE : la route répond en lecture."""
        self.client.force_authenticate(self.admin)
        response = self.client.get(f'/api/scolarite/maquettes/{self.maquette.id}/ues/')
        self.assertEqual(response.status_code, 200)
        unites = response.json()
        self.assertEqual(len(unites), 18)  # L1 = S1 (9 UE) + S2 (9 UE)
        premiere = unites[0]
        self.assertIn('code', premiere)
        self.assertIn('famille', premiere)
        self.assertTrue(premiere['ecues'])

    def test_ue_filtrees_par_semestre(self):
        self.client.force_authenticate(self.admin)
        semestre = self.maquette.unites_enseignement.first().semestre
        response = self.client.get(
            f'/api/scolarite/maquettes/{self.maquette.id}/ues/?semestre_id={semestre.id}',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 9)

    def test_detail_maquette_expose_les_familles(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get(f'/api/scolarite/maquettes/{self.maquette.id}/')
        self.assertEqual(response.status_code, 200)
        families = {
            ue['famille'] for ue in response.json()['unites_enseignement']
        }
        self.assertNotIn(None, families)

    # ── Permissions ────────────────────────────────────────────────────────
    def test_anonyme_refuse(self):
        self.assertEqual(
            self.client.get(f'/api/scolarite/maquettes/{self.maquette.id}/ues/').status_code,
            401,
        )

    def test_role_non_habillite_refuse(self):
        """Un rôle canonique sans habilitation scolarité n'accède pas aux UE."""
        formateur = User.objects.create_user(
            username='formateur', password='pass', role='FORMATEUR',
        )
        self.client.force_authenticate(formateur)
        self.assertEqual(
            self.client.get(f'/api/scolarite/maquettes/{self.maquette.id}/ues/').status_code,
            403,
        )

    def test_direction_en_lecture_seule(self):
        direction = User.objects.create_user(
            username='direction', password='pass', role='DIRECTION',
        )
        self.client.force_authenticate(direction)
        self.assertEqual(
            self.client.get(f'/api/scolarite/maquettes/{self.maquette.id}/ues/').status_code,
            200,
        )
        # La direction ne peut pas créer d'UE.
        self.assertEqual(
            self.client.post(
                f'/api/scolarite/maquettes/{self.maquette.id}/ues/',
                {'semestre_id': 1, 'code': 'X'}, format='json',
            ).status_code,
            403,
        )

    # ── Cohérence avec la base ─────────────────────────────────────────────
    def test_aucune_ue_orpheline(self):
        self.assertEqual(UE.objects.filter(maquette__isnull=True).count(), 0)
        self.assertEqual(ECUE.objects.filter(ue__isnull=True).count(), 0)
