from datetime import datetime, time, timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from ..models import Formation, Module, SessionModule, QRToken
from ..session_views import (
    _auto_manage_sessions,
    reactiver_session_et_qr,
    reactiver_sessions_en_lot,
)


class SessionReactivationTest(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.local_now = timezone.localtime(self.now)
        self.today = self.local_now.date()
        self.formation = Formation.objects.create(formation='Formation réactivation')
        self.module = Module.objects.create(
            formation=self.formation,
            intitule='Module test',
            statut='TERMINEE',
        )
        past_fin = (
            self.local_now - timedelta(hours=2)
        ).time().replace(second=0, microsecond=0)
        self.session = SessionModule.objects.create(
            module=self.module,
            date_journee=self.today,
            numero=1,
            heure_fin_prevue=past_fin,
            demarree_le=self.now - timedelta(hours=4),
            terminee_le=self.now - timedelta(hours=1),
        )
        self.qr = QRToken.objects.create(
            session=self.session,
            expire_at=self.now + timedelta(hours=1),
            actif=False,
        )

    def test_reactivation_survives_auto_manage(self):
        # Fixer l'horloge évite un faux échec entre 23:59 et minuit, quand la
        # borne métier de 23:59 ne peut plus être strictement future.
        fixed_now = timezone.make_aware(
            datetime.combine(self.today, time(12, 0)),
            timezone.get_current_timezone(),
        )
        self.session.heure_fin_prevue = time(11, 0)
        self.session.save(update_fields=['heure_fin_prevue'])

        with patch('formations.session_views.timezone.now', return_value=fixed_now):
            reactiver_session_et_qr(self.session)
            self.session.refresh_from_db()
            self.qr.refresh_from_db()

            self.assertIsNone(self.session.terminee_le)
            self.assertTrue(self.qr.actif)
            self.assertGreater(self.session.heure_fin_prevue, fixed_now.time())

            _auto_manage_sessions(self.formation)
            self.session.refresh_from_db()
            self.qr.refresh_from_db()

            self.assertIsNone(self.session.terminee_le)
            self.assertTrue(self.qr.actif)

    def test_reactivation_bumps_past_date_to_today(self):
        yesterday = self.today - timedelta(days=1)
        self.session.date_journee = yesterday
        self.session.heure_fin_prevue = time(12, 0)
        self.session.save(update_fields=['date_journee', 'heure_fin_prevue'])

        reactiver_session_et_qr(self.session)
        self.session.refresh_from_db()

        self.assertEqual(self.session.date_journee, self.today)
        self.assertIsNone(self.session.terminee_le)

        _auto_manage_sessions(self.formation)
        self.session.refresh_from_db()
        self.assertIsNone(self.session.terminee_le)

    def test_one_by_one_reactivation_does_not_close_other_modules(self):
        module_b = Module.objects.create(
            formation=self.formation,
            intitule='Autre module',
            statut='EN_COURS',
            groupe='GROUPE 99',
        )
        session_a = self.session
        session_b = SessionModule.objects.create(
            module=module_b,
            date_journee=self.today,
            numero=1,
            heure_fin_prevue=(self.local_now + timedelta(hours=2)).time().replace(
                second=0, microsecond=0
            ),
            demarree_le=self.now - timedelta(hours=2),
            terminee_le=self.now - timedelta(hours=1),
        )

        reactiver_session_et_qr(session_a)
        reactiver_session_et_qr(session_b)
        session_a.refresh_from_db()
        session_b.refresh_from_db()

        self.assertIsNone(session_a.terminee_le)
        self.assertIsNone(session_b.terminee_le)

    def test_bulk_reactivation_keeps_all_sessions_open(self):
        past_fin = (self.local_now - timedelta(hours=1)).time().replace(
            second=0, microsecond=0
        )
        sessions = [self.session]
        for numero in (2, 3):
            s = SessionModule.objects.create(
                module=self.module,
                date_journee=self.today,
                numero=numero,
                heure_fin_prevue=past_fin,
                demarree_le=self.now - timedelta(hours=4),
                terminee_le=self.now - timedelta(hours=1),
            )
            QRToken.objects.create(
                session=s,
                expire_at=self.now + timedelta(hours=1),
                actif=False,
            )
            sessions.append(s)

        reactiver_sessions_en_lot(sessions)
        for s in sessions:
            s.refresh_from_db()
            self.assertIsNone(
                s.terminee_le,
                msg=f'La séance {s.numero} ne devrait pas être re-fermée par le lot',
            )
