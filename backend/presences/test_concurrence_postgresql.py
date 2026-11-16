"""Essais transactionnels QR sur PostgreSQL ISOLÉ uniquement.

Exécuter avec USE_SQLITE=0 et POSTGRES_* pointant vers un serveur de TEST :
Django crée sa base test_<POSTGRES_DB>. Jamais sur le serveur de production.
Sous SQLite ces scénarios sont ignorés explicitement, pas déclarés réussis.
"""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from rest_framework.test import APIClient

from presences.models import Pointage
from .test_seances_edt_mobile import MobileSeanceEdtMixin


class ConcurrenceScanPostgres(MobileSeanceEdtMixin, TransactionTestCase):
    def setUp(self):
        if connection.vendor != 'postgresql':
            self.skipTest('PostgreSQL de test indispensable (SQLite ne prouve pas les courses)')
        # TransactionTestCase ne gère pas setUpTestData ; chaque test crée ses
        # données dans la base de test isolée et autorise des commits inter-threads.
        self.setUpTestData()
        super().setUp()

    def _scans_simultanes(self, users):
        depart = Barrier(len(users))
        def scan(user):
            close_old_connections()
            try:
                client = APIClient()
                client.force_authenticate(user)
                depart.wait(timeout=10)
                response = client.post('/api/scan/secure/', {
                    'token_qr': self.token, 'device_id': f'concurrence-{user.pk}',
                    **self._dans_la_zone(),
                }, format='json')
                return response.status_code, response.data.get('action'), response.data.get('code')
            finally:
                connection.close()
        with ThreadPoolExecutor(max_workers=len(users)) as pool:
            futures = [pool.submit(scan, user) for user in users]
            return [future.result(timeout=30) for future in futures]

    def test_deux_scans_meme_etudiant_une_seule_ligne(self):
        user = self.auditeurs[0]
        reponses = self._scans_simultanes([user, user])
        self.assertEqual(Pointage.objects.filter(
            seance_edt=self.affectation, participant=self.participants[0],
        ).count(), 1, reponses)
        self.assertEqual(sorted(r[0] for r in reponses), [200, 201], reponses)
        # Contrat ACTUEL : le second scan ferme la présence. Il faut arbitrer
        # une fenêtre anti-double-tap avant de qualifier l'assiduité de fiable.
        self.assertEqual({r[1] for r in reponses}, {'ENTREE', 'SORTIE'})

    def test_scans_simultanes_etudiants_distincts(self):
        reponses = self._scans_simultanes(self.auditeurs)
        self.assertEqual([r[0] for r in reponses], [201, 201, 201], reponses)
        lignes = Pointage.objects.filter(seance_edt=self.affectation)
        self.assertEqual(lignes.count(), 3)
        self.assertEqual(set(lignes.values_list('participant_id', flat=True)),
                         {participant.pk for participant in self.participants})
