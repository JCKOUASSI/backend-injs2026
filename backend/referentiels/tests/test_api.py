"""Tests d'intégration de l'API référentiels (lot L0/L7)."""
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from authentication.models import User
from referentiels.models import RefModePaiement, RefTypeEvaluation, ReferentielJournal

LIST_URL = '/api/referentiels/types-evaluation/'


def make_user(username, role='ADMIN'):
    return User.objects.create_user(username=username, password='pass', role=role)


class ReferentielsAPIAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ref = RefTypeEvaluation.objects.create(code='ECRIT', libelle='Épreuve écrite')

    def setUp(self):
        self.client = APIClient()
        self.detail_url = f'{LIST_URL}{self.ref.pk}/'

    def test_anonyme_refuse(self):
        res = self.client.get(LIST_URL)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authentifie_peut_consulter(self):
        self.client.force_authenticate(make_user('aud_ref', role='AUDITEUR'))
        res = self.client.get(LIST_URL)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data['results']), 1)

    def test_auditeur_ne_peut_pas_creer(self):
        self.client.force_authenticate(make_user('aud_ref2', role='AUDITEUR'))
        res = self.client.post(LIST_URL, {'code': 'ORAL', 'libelle': 'Oral'})
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_peut_creer_et_journal_cree(self):
        admin = make_user('admin_ref', role='ADMIN')
        self.client.force_authenticate(admin)
        res = self.client.post(LIST_URL, {'code': 'ORAL', 'libelle': 'Oral'})
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        self.assertTrue(
            ReferentielJournal.objects.filter(
                action='CREATION', object_id=res.data['id'], utilisateur=admin,
            ).exists()
        )

    def test_code_invalide_rejete(self):
        self.client.force_authenticate(make_user('admin_ref2', role='ADMIN'))
        res = self.client.post(LIST_URL, {'code': 'code minuscul!', 'libelle': 'X'})
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_regle4_doublon_libelle_casse_rejete(self):
        self.client.force_authenticate(make_user('admin_ref3', role='ADMIN'))
        res = self.client.post(LIST_URL, {'code': 'ECRIT2', 'libelle': 'épreuve ÉCRITE'})
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_regle4_doublon_libelle_casse_rejete_au_patch(self):
        # ADR-006 — la même forme normalisée (casse/accent) est refusée en
        # modification, pour le même modèle, portable sur SQLite.
        self.client.force_authenticate(make_user('admin_ref3b', role='ADMIN'))
        res = self.client.post(LIST_URL, {'code': 'ORAL', 'libelle': 'Oral'})
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        res = self.client.patch(
            self.detail_url, {'libelle': 'oral  '},
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        # Une forme normalisée différente passe.
        res = self.client.patch(
            self.detail_url, {'libelle': 'Épreuve écrite avec barème'},
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        # Se renommer sans changer la forme normalisée : accepté (pk exclu).
        res = self.client.patch(
            self.detail_url, {'libelle': '  ÉPREUVE écrite '},
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_regle2_delete_interdit(self):
        self.client.force_authenticate(make_user('admin_ref4', role='ADMIN'))
        res = self.client.delete(self.detail_url)
        self.assertEqual(res.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertTrue(RefTypeEvaluation.objects.filter(pk=self.ref.pk).exists())

    def test_code_immuable_au_patch(self):
        self.client.force_authenticate(make_user('admin_ref5', role='ADMIN'))
        res = self.client.patch(self.detail_url, {'code': 'PIRATE'})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.ref.refresh_from_db()
        self.assertEqual(self.ref.code, 'ECRIT')

    def test_archivage_via_action_et_masquage(self):
        self.client.force_authenticate(make_user('admin_ref6', role='ADMIN'))
        res = self.client.post(f'{self.detail_url}archiver/', {'motif': 'n plus utilisée'})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.ref.refresh_from_db()
        self.assertTrue(self.ref.archive)
        # Règle 5 : masquée par défaut, visible avec ?archives=1
        res = self.client.get(LIST_URL)
        self.assertEqual(len(res.data['results']), 0)
        res = self.client.get(f'{LIST_URL}?archives=1')
        self.assertEqual(len(res.data['results']), 1)

    def test_reactivation(self):
        self.ref.archiver()
        self.client.force_authenticate(make_user('admin_ref7', role='ADMIN'))
        res = self.client.post(f'{self.detail_url}reactiver/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.ref.refresh_from_db()
        self.assertFalse(self.ref.archive)

    def test_endpoints_tous_referentiels(self):
        self.client.force_authenticate(make_user('admin_ref8', role='ADMIN'))
        RefModePaiement.objects.create(code='VIREMENT', libelle='Virement bancaire')
        for slug in [
            'types-evaluation', 'types-document', 'grades-enseignant', 'types-frais',
            'modes-paiement', 'types-decision', 'types-notification', 'types-espace-sportif',
        ]:
            res = self.client.get(f'/api/referentiels/{slug}/')
            self.assertEqual(res.status_code, status.HTTP_200_OK, slug)

    def test_journal_endpoint(self):
        admin = make_user('admin_ref9', role='ADMIN')
        self.client.force_authenticate(admin)
        self.client.post(LIST_URL, {'code': 'PRATIQUE', 'libelle': 'Épreuve pratique'})
        res = self.client.get('/api/referentiels/journal/', {'app': 'referentiels', 'model': 'reftypeevaluation'})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(any(j['action'] == 'CREATION' for j in res.data['results']))
