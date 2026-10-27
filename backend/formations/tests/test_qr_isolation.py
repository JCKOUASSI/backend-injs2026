"""Tests QR codes : isolation par groupe/séance et durée d'expiration.

Couvre les corrections de deux bugs :
- Le QR d'un groupe pouvait apparaître chez un autre (endpoint image
  formation sans filtre de séance).
- L'expiration ignorait le réglage QR_TOKEN_LIFETIME_HOURS (24h codé en dur).
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from formations.models import Formation, Module, QRToken, SessionModule
from formations.session_views import close_open_sessions_for_module

User = get_user_model()


def make_qr(session, hours=24, actif=True):
    return QRToken.objects.create(
        session=session,
        expire_at=timezone.now() + timedelta(hours=hours),
        actif=actif,
    )


class QRImageIsolationTests(TestCase):
    """Endpoint image « niveau formation » : /api/formations/<pk>/qr-image/."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='admin_qr', password='x', role='INJS_ADMIN',
        )
        self.client.force_authenticate(self.user)

        self.formation = Formation.objects.create(formation='Cycle multi-groupes')
        self.module_g1 = Module.objects.create(
            formation=self.formation, intitule='Module', groupe='GROUPE 1',
        )
        self.module_g2 = Module.objects.create(
            formation=self.formation, intitule='Module', groupe='GROUPE 2',
        )
        self.session_g1 = SessionModule.objects.create(
            module=self.module_g1, numero=1, intitule='Séance G1',
        )
        self.session_g2 = SessionModule.objects.create(
            module=self.module_g2, numero=1, intitule='Séance G2',
        )

    def test_ambiguous_when_multiple_groups_active(self):
        """Deux groupes avec QR actif → refus (409) au lieu d'un QR au hasard."""
        make_qr(self.session_g1)
        make_qr(self.session_g2)

        res = self.client.get(f'/api/formations/{self.formation.pk}/qr-image/')

        self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(res.data.get('code'), 'QR_AMBIGUOUS')

    def test_session_id_scopes_to_correct_group(self):
        """Avec session_id, on récupère bien le QR de la séance demandée."""
        make_qr(self.session_g1)
        make_qr(self.session_g2)

        res = self.client.get(
            f'/api/formations/{self.formation.pk}/qr-image/',
            {'session_id': self.session_g2.pk},
        )

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res['Content-Type'], 'image/png')

    def test_single_group_still_works(self):
        """Formation mono-groupe : l'image formation reste disponible."""
        make_qr(self.session_g1)

        res = self.client.get(f'/api/formations/{self.formation.pk}/qr-image/')

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res['Content-Type'], 'image/png')

    def test_module_mismatch_rejected(self):
        """session d'un groupe + module_id d'un autre → 403 QR_MODULE_MISMATCH."""
        make_qr(self.session_g1)

        res = self.client.get(
            f'/api/formations/{self.formation.pk}/qr-image/',
            {'session_id': self.session_g1.pk, 'module_id': self.module_g2.pk},
        )

        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(res.data.get('code'), 'QR_MODULE_MISMATCH')


class QRGenerationScopeTests(TestCase):
    """Génération API : scope par séance + durée d'expiration configurable."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='admin_gen', password='x', role='INJS_ADMIN',
        )
        self.client.force_authenticate(self.user)

        self.formation = Formation.objects.create(formation='Cycle gen')
        self.module_g1 = Module.objects.create(
            formation=self.formation, intitule='Module', groupe='GROUPE 1',
        )
        self.module_g2 = Module.objects.create(
            formation=self.formation, intitule='Module', groupe='GROUPE 2',
        )
        self.session_g1 = SessionModule.objects.create(
            module=self.module_g1, numero=1, intitule='Séance G1',
        )
        self.session_g2 = SessionModule.objects.create(
            module=self.module_g2, numero=1, intitule='Séance G2',
        )

    @override_settings(QR_TOKEN_LIFETIME_HOURS=5)
    def test_expiration_uses_setting(self):
        """expire_at doit suivre QR_TOKEN_LIFETIME_HOURS, pas un 24h codé en dur."""
        before = timezone.now()
        res = self.client.post(
            f'/api/formations/{self.formation.pk}/sessions/{self.session_g1.pk}/generate-qr/'
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        token = QRToken.objects.get(token=res.data['token'])
        expected = before + timedelta(hours=5)
        # Tolérance large pour l'écart d'exécution.
        self.assertLess(abs((token.expire_at - expected).total_seconds()), 120)

    def test_generation_only_deactivates_same_session(self):
        """Régénérer le QR d'un groupe ne doit pas invalider celui d'un autre."""
        make_qr(self.session_g2)

        res = self.client.post(
            f'/api/formations/{self.formation.pk}/sessions/{self.session_g1.pk}/generate-qr/'
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        # Le QR du groupe 2 reste actif.
        self.assertTrue(
            QRToken.objects.filter(session=self.session_g2, actif=True).exists()
        )


class CloseOpenSessionsForModuleTests(TestCase):
    """Helper de fermeture : ne ferme que les séances du module ciblé."""

    def setUp(self):
        self.formation = Formation.objects.create(formation='Cycle close')
        self.module_g1 = Module.objects.create(
            formation=self.formation, intitule='Module', groupe='GROUPE 1',
        )
        self.module_g2 = Module.objects.create(
            formation=self.formation, intitule='Module', groupe='GROUPE 2',
        )
        now = timezone.now()
        # Deux séances ouvertes dans le module G1, une dans le module G2.
        self.s1a = SessionModule.objects.create(
            module=self.module_g1, numero=1, demarree_le=now,
        )
        self.s1b = SessionModule.objects.create(
            module=self.module_g1, numero=2, demarree_le=now,
        )
        self.s2 = SessionModule.objects.create(
            module=self.module_g2, numero=1, demarree_le=now,
        )

    def test_closes_only_target_module(self):
        """Les séances des autres modules/groupes ne sont pas fermées."""
        closed = close_open_sessions_for_module(self.module_g1)

        self.assertEqual(closed, 2)
        self.s2.refresh_from_db()
        self.assertIsNone(self.s2.terminee_le)

    def test_exclude_pks_preserves_current_session(self):
        """La séance qu'on démarre (exclue) reste ouverte."""
        closed = close_open_sessions_for_module(
            self.module_g1, exclude_pks=[self.s1b.pk],
        )

        self.assertEqual(closed, 1)
        self.s1a.refresh_from_db()
        self.s1b.refresh_from_db()
        self.assertIsNotNone(self.s1a.terminee_le)
        self.assertIsNone(self.s1b.terminee_le)

    def test_accepts_module_id(self):
        """Le helper accepte aussi module_id."""
        closed = close_open_sessions_for_module(module_id=self.module_g2.pk)

        self.assertEqual(closed, 1)
        self.s1a.refresh_from_db()
        self.assertIsNone(self.s1a.terminee_le)
