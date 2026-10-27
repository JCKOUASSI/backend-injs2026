from datetime import date, time, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from authentication.models import User
from formations.models import Formation, Module, SessionModule
from formations.session_edt_balance import (
    SessionEdtBalanceError,
    apply_session_edit_with_edt_balance,
)
from formations.volume_horaire import accumulate_sessions_volume


def _make_formation():
    return Formation.objects.create(formation='Cycle test EDT')


def _make_module(formation, *, intitule='Module EDT', duree_prevue_heures=30):
    return Module.objects.create(
        formation=formation,
        intitule=intitule,
        duree_prevue_heures=duree_prevue_heures,
    )


def _make_session(module, *, day_offset, debut, fin, numero=1):
    return SessionModule.objects.create(
        module=module,
        date_journee=date(2026, 1, 1) + timedelta(days=day_offset),
        numero=numero,
        heure_debut_prevue=debut,
        heure_fin_prevue=fin,
    )


class SessionEdtBalanceTest(TestCase):
    def setUp(self):
        self.formation = _make_formation()
        self.module = _make_module(self.formation, duree_prevue_heures=30)
        self.s1 = _make_session(
            self.module, day_offset=0, debut=time(8, 0), fin=time(18, 0), numero=1,
        )
        self.s2 = _make_session(
            self.module, day_offset=1, debut=time(8, 0), fin=time(18, 0), numero=1,
        )
        self.s3 = _make_session(
            self.module, day_offset=2, debut=time(8, 0), fin=time(18, 0), numero=1,
        )

    def _total_edt_minutes(self):
        sessions = SessionModule.objects.filter(module=self.module)
        return accumulate_sessions_volume(sessions)['prevu_min']

    def test_compensate_on_middle_session_increase(self):
        self.assertEqual(self._total_edt_minutes(), 30 * 60)

        self.s1.heure_fin_prevue = time(20, 0)
        result = apply_session_edit_with_edt_balance(
            self.s1, old_debut=time(8, 0), old_fin=time(18, 0),
        )

        self.s3.refresh_from_db()
        self.assertTrue(result['adjusted'])
        self.assertFalse(result['deleted_last'])
        self.assertEqual(self.s3.heure_fin_prevue, time(16, 0))
        self.assertEqual(self._total_edt_minutes(), 30 * 60)

    def test_compensate_on_middle_session_decrease(self):
        self.s1.heure_fin_prevue = time(16, 0)
        apply_session_edit_with_edt_balance(
            self.s1, old_debut=time(8, 0), old_fin=time(18, 0),
        )

        self.s3.refresh_from_db()
        self.assertEqual(self.s3.heure_fin_prevue, time(20, 0))
        self.assertEqual(self._total_edt_minutes(), 30 * 60)

    def test_delete_last_session_when_compensation_exceeds_duration(self):
        module = _make_module(
            self.formation, intitule='Module EDT compensation', duree_prevue_heures=30,
        )
        s1 = _make_session(
            module, day_offset=0, debut=time(8, 0), fin=time(20, 0), numero=1,
        )
        _make_session(
            module, day_offset=1, debut=time(8, 0), fin=time(23, 0), numero=1,
        )
        s3 = _make_session(
            module, day_offset=2, debut=time(8, 0), fin=time(11, 0), numero=1,
        )

        s1.heure_fin_prevue = time(23, 0)
        result = apply_session_edit_with_edt_balance(
            s1, old_debut=time(8, 0), old_fin=time(20, 0),
        )

        self.assertTrue(result['deleted_last'])
        self.assertFalse(SessionModule.objects.filter(pk=s3.pk).exists())

    def test_no_compensation_when_editing_last_session(self):
        self.s3.heure_fin_prevue = time(20, 0)
        result = apply_session_edit_with_edt_balance(
            self.s3, old_debut=time(8, 0), old_fin=time(18, 0),
        )

        self.assertIsNone(result)
        self.assertEqual(self._total_edt_minutes(), 32 * 60)

    def test_compensation_resolves_duree_from_sessions_edt(self):
        self.module.duree_prevue_heures = None
        self.module.save(update_fields=['duree_prevue_heures'])

        self.s1.heure_fin_prevue = time(20, 0)
        result = apply_session_edit_with_edt_balance(
            self.s1, old_debut=time(8, 0), old_fin=time(18, 0),
        )

        self.module.refresh_from_db()
        self.s3.refresh_from_db()
        self.assertTrue(result['adjusted'])
        self.assertEqual(float(self.module.duree_prevue_heures), 30)
        self.assertEqual(self.s3.heure_fin_prevue, time(16, 0))
        self.assertEqual(self._total_edt_minutes(), 30 * 60)

    def test_error_when_last_session_already_started(self):
        self.s3.demarree_le = timezone.now()
        self.s3.save(update_fields=['demarree_le'])

        self.s1.heure_fin_prevue = time(20, 0)
        with self.assertRaises(SessionEdtBalanceError):
            apply_session_edit_with_edt_balance(
                self.s1, old_debut=time(8, 0), old_fin=time(18, 0),
            )


class SessionUpdateApiEdtBalanceTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='sec_edt', password='pass', role='SECRETARIAT',
        )
        self.client.force_authenticate(self.user)
        self.formation = _make_formation()
        self.module = _make_module(self.formation, duree_prevue_heures=30)
        self.s1 = _make_session(
            self.module, day_offset=0, debut=time(8, 0), fin=time(18, 0), numero=1,
        )
        _make_session(
            self.module, day_offset=1, debut=time(8, 0), fin=time(18, 0), numero=1,
        )
        self.s3 = _make_session(
            self.module, day_offset=2, debut=time(8, 0), fin=time(18, 0), numero=1,
        )

    def test_api_update_triggers_auto_adjustment(self):
        url = reverse(
            'api-session-update',
            kwargs={'formation_pk': self.formation.pk, 'session_pk': self.s1.pk},
        )
        response = self.client.patch(url, {
            'heure_fin_prevue': '20:00',
        }, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertIn('auto_adjustment', response.data)
        self.s3.refresh_from_db()
        self.assertEqual(self.s3.heure_fin_prevue, time(16, 0))
