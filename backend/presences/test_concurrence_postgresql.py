"""Essais transactionnels QR sur PostgreSQL ISOLÉ uniquement.

Exécuter avec USE_SQLITE=0 et POSTGRES_* pointant vers un serveur de TEST :
Django crée sa base test_<POSTGRES_DB>. Jamais sur le serveur de production.
Sous SQLite ces scénarios sont ignorés explicitement, pas déclarés réussis.
"""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from unittest.mock import patch

from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from rest_framework.test import APIClient

from presences.models import AuditLog, Pointage
from parametres.models import Parametre
from presences.seances_edt_services import CLE_NOTIFIER_CLOTURE
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
        self.assertEqual(sorted(r[0] for r in reponses), [201, 400], reponses)
        self.assertEqual({r[1] for r in reponses}, {'ENTREE', None})
        self.assertEqual({r[2] for r in reponses}, {None, 'DUPLICATE_SCAN'})
        self.assertIsNone(Pointage.objects.get(
            seance_edt=self.affectation, participant=self.participants[0],
        ).timestamp_sortie)

    def test_revocation_entre_validation_et_enregistrement(self):
        """La validation initiale du QR ne suffit pas contre une révocation.

        Le scan atteint le service après résolution du jeton sur une autre
        connexion ; la transaction principale le révoque avant l'écriture.
        """
        from formations.models import QRToken
        from presences import seances_edt_services as service

        atteint_service, reprendre = Event(), Event()
        original = service.badger_scan

        def suspendre(*args, **kwargs):
            atteint_service.set()
            if not reprendre.wait(timeout=10):
                raise AssertionError('Timeout de synchronisation du scan QR')
            return original(*args, **kwargs)

        def scan():
            close_old_connections()
            try:
                client = APIClient()
                client.force_authenticate(self.auditeurs[0])
                return client.post('/api/scan/secure/', {
                    'token_qr': self.token, 'device_id': 'revocation-pendant-scan',
                    **self._dans_la_zone(),
                }, format='json')
            finally:
                connection.close()

        with patch.object(service, 'badger_scan', side_effect=suspendre):
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(scan)
                try:
                    self.assertTrue(atteint_service.wait(timeout=10))
                    QRToken.objects.filter(token=self.token).update(actif=False)
                finally:
                    reprendre.set()
                response = future.result(timeout=30)
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(response.data['code'], 'TOKEN_EXPIRED')
        self.assertEqual(response.data['code_normalise'], 'QR_REVOQUE')
        self.assertFalse(Pointage.objects.filter(seance_edt=self.affectation).exists())

    def test_expiration_entre_validation_et_enregistrement(self):
        from django.utils import timezone
        from datetime import timedelta
        from formations.models import QRToken
        from presences import seances_edt_services as service

        atteint_service, reprendre = Event(), Event()
        original = service.badger_scan

        def suspendre(*args, **kwargs):
            atteint_service.set()
            if not reprendre.wait(timeout=10):
                raise AssertionError('Timeout de synchronisation du scan QR')
            return original(*args, **kwargs)

        def scan():
            close_old_connections()
            try:
                client = APIClient()
                client.force_authenticate(self.auditeurs[0])
                return client.post('/api/scan/secure/', {
                    'token_qr': self.token, 'device_id': 'expiration-pendant-scan',
                    **self._dans_la_zone(),
                }, format='json')
            finally:
                connection.close()

        with patch.object(service, 'badger_scan', side_effect=suspendre):
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(scan)
                try:
                    self.assertTrue(atteint_service.wait(timeout=10))
                    QRToken.objects.filter(token=self.token).update(
                        expire_at=timezone.now() - timedelta(seconds=1))
                finally:
                    reprendre.set()
                response = future.result(timeout=30)
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(response.data['code'], 'TOKEN_EXPIRED')
        self.assertEqual(response.data['code_normalise'], 'QR_EXPIRE')
        self.assertFalse(Pointage.objects.filter(seance_edt=self.affectation).exists())

    def test_scans_simultanes_etudiants_distincts(self):
        reponses = self._scans_simultanes(self.auditeurs)
        self.assertEqual([r[0] for r in reponses], [201, 201, 201], reponses)
        lignes = Pointage.objects.filter(seance_edt=self.affectation)
        self.assertEqual(lignes.count(), 3)
        self.assertEqual(set(lignes.values_list('participant_id', flat=True)),
                         {participant.pk for participant in self.participants})

    def test_clotures_simultanees_sans_doublon_d_absence_ni_audit(self):
        from presences import seances_edt_services as service

        Parametre.objects.create(
            cle=CLE_NOTIFIER_CLOTURE, libelle='Notifier à la clôture (test)',
            categorie='presences', type='integer', valeur='0', valeur_defaut='1',
        )
        depart = Barrier(2)

        def cloturer():
            close_old_connections()
            try:
                depart.wait(timeout=10)
                from edts.models import AffectationCreneau
                affectation = AffectationCreneau.objects.get(pk=self.affectation.pk)
                return service.auto_clore(None, affectation, self.date_seance)
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            resultats = [future.result(timeout=30) for future in
                         [pool.submit(cloturer), pool.submit(cloturer)]]

        self.assertEqual(Pointage.objects.filter(
            seance_edt=self.affectation,
            statut=Pointage.Statut.ABSENT_NON_BADGE,
        ).count(), len(self.participants), resultats)
        self.assertEqual(AuditLog.objects.filter(
            action=AuditLog.Action.CLOSE_SESSION,
            cible_type='seance_edt', cible_numero=str(self.affectation.pk),
        ).count(), 1, resultats)
