"""Tests du tableau de bord admin."""

from django.test import TestCase
from django.utils import timezone

from authentication.models import User
from config.admin_dashboard import (
    _build_auditeurs_mobile_donut,
    auditeurs_mobile_breakdown,
    auditeurs_mobile_counts,
)
from formations.models import Formation, Module, Participant, SessionModule
from presences.models import DeviceBinding, Pointage


def _make_session():
    formation = Formation.objects.create(formation='Formation test')
    module = Module.objects.create(formation=formation, intitule='Module test', statut='PLANIFIEE')
    return SessionModule.objects.create(
        module=module,
        date_journee=timezone.localdate(),
        numero=1,
    )


class AdminDashboardMobileStatsTests(TestCase):
    def _make_auditeur(self, matricule, nom='Test', prenom='User'):
        participant = Participant.objects.create(
            matricule=matricule,
            nom=nom,
            prenom=prenom,
        )
        user = User.objects.create_user(
            username=f'user-{matricule.lower()}',
            password='pass',
            matricule=matricule,
            role=User.Role.AUDITEUR,
        )
        participant.refresh_from_db()
        return participant, user

    def test_auditeurs_mobile_counts_empty(self):
        self.assertEqual(auditeurs_mobile_counts(), (0, 0))

    def test_auditeurs_mobile_counts_connecte_sans_badge(self):
        participant, user = self._make_auditeur('AUD001')
        DeviceBinding.objects.create(user=user, device_id='device-001', is_active=True)

        self.assertEqual(auditeurs_mobile_counts(), (0, 1))
        self.assertEqual(participant.pk, Participant.objects.filter(
            user__device_bindings__is_active=True,
        ).distinct().get().pk)

    def test_auditeurs_mobile_counts_badge_sans_liaison_active(self):
        participant, _user = self._make_auditeur('AUD002', nom='Badge', prenom='Seul')
        session = _make_session()
        Pointage.objects.create(
            session=session,
            participant=participant,
            date_journee=timezone.localdate(),
            device_id='device-002',
            timestamp_entree=timezone.now(),
        )

        self.assertEqual(auditeurs_mobile_counts(), (1, 0))

    def test_auditeurs_mobile_counts_badge_et_connecte(self):
        participant, user = self._make_auditeur('AUD003', nom='Complet', prenom='Mobile')
        DeviceBinding.objects.create(user=user, device_id='device-003', is_active=True)
        session = _make_session()
        Pointage.objects.create(
            session=session,
            participant=participant,
            date_journee=timezone.localdate(),
            device_id='device-003',
            timestamp_entree=timezone.now(),
        )

        self.assertEqual(auditeurs_mobile_counts(), (1, 1))

    def test_auditeurs_mobile_counts_ignore_inactive_binding(self):
        _participant, user = self._make_auditeur('AUD004', nom='Inactif', prenom='Device')
        DeviceBinding.objects.create(user=user, device_id='device-004', is_active=False)

        self.assertEqual(auditeurs_mobile_counts(), (0, 0))

    def test_auditeurs_mobile_breakdown_mixed(self):
        p1, u1 = self._make_auditeur('AUD010', nom='Badged', prenom='One')
        p2, u2 = self._make_auditeur('AUD011', nom='Linked', prenom='Only')
        DeviceBinding.objects.create(user=u1, device_id='device-010', is_active=True)
        DeviceBinding.objects.create(user=u2, device_id='device-011', is_active=True)
        session = _make_session()
        Pointage.objects.create(
            session=session,
            participant=p1,
            date_journee=timezone.localdate(),
            device_id='device-010',
            timestamp_entree=timezone.now(),
        )

        self.assertEqual(auditeurs_mobile_breakdown(), {
            'badgeurs': 1,
            'connectes': 2,
            'badge_et_connecte': 1,
            'connecte_sans_badge': 1,
            'badge_sans_liaison': 0,
        })

    def test_auditeurs_mobile_donut_slices(self):
        participant, user = self._make_auditeur('AUD012', nom='Donut', prenom='Test')
        DeviceBinding.objects.create(user=user, device_id='device-012', is_active=True)
        session = _make_session()
        Pointage.objects.create(
            session=session,
            participant=participant,
            date_journee=timezone.localdate(),
            device_id='device-012',
            timestamp_entree=timezone.now(),
        )

        chart = _build_auditeurs_mobile_donut()
        self.assertEqual(chart['total'], 1)
        self.assertEqual(len(chart['slices']), 1)
        self.assertEqual(chart['slices'][0]['value'], 1)

    def test_auditeurs_mobile_donut_empty(self):
        self.assertIsNone(_build_auditeurs_mobile_donut())
