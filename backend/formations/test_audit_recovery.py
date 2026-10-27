"""Tests appariement stable post-migration 0076."""

from datetime import date, datetime, timezone as dt_timezone

from django.test import TestCase
from django.utils import timezone

from formations.audit_recovery import (
    _parse_explicit_mapping,
    apply_session_recovery,
    match_deleted_modules_to_survivors,
)
from formations.models import Formation, Module, SessionModule

# IDs fictifs élevés : évite toute collision avec des modules réels de la base de dev
# si le setUp est exécuté hors runner de tests (shell, debug).
_ID_BASE = 900_000
_DELETED_IDS = (_ID_BASE + 321, _ID_BASE + 312, _ID_BASE + 330, _ID_BASE + 357)
_SURVIVOR_IDS = (_ID_BASE + 327, _ID_BASE + 336, _ID_BASE + 363, _ID_BASE + 372, _ID_BASE + 392)


class AuditRecoveryMatchingTest(TestCase):
    """Scénario DEONTOLOGIE : 4 doublons supprimés, survivants proches en id."""

    def setUp(self):
        self.formation = Formation.objects.create(formation='TEST_AUDIT_RECOVERY')
        self.d15 = date(2026, 6, 15)
        self.d16 = date(2026, 6, 16)
        self.d17 = date(2026, 6, 17)

        def mod(pk, groupe):
            return Module.objects.create(
                pk=pk,
                formation=self.formation,
                intitule='DEONTOLOGIE',
                grade='G',
                groupe=groupe,
                vague='V1',
            )

        self.surv_327 = mod(_SURVIVOR_IDS[0], 'GROUPE 18')
        self.surv_336 = mod(_SURVIVOR_IDS[1], 'GROUPE 17')
        self.surv_363 = mod(_SURVIVOR_IDS[2], 'GROUPE 20')
        self.surv_372 = mod(_SURVIVOR_IDS[3], 'GROUPE 19')
        # Bruit : id proche mais mauvais EDT
        self.surv_392 = mod(_SURVIVOR_IDS[4], 'GROUPE 25')

        for mod in (self.surv_327, self.surv_336, self.surv_363, self.surv_372):
            for day in (self.d15, self.d16, self.d17):
                SessionModule.objects.create(module=mod, date_journee=day, numero=2)

        # #0b578e a déjà les horaires (survivant du doublon #312)
        stop_312 = timezone.make_aware(datetime(2026, 6, 15, 17, 25, 54))
        start_312 = timezone.make_aware(datetime(2026, 6, 15, 13, 5, 32))
        s372 = SessionModule.objects.get(module=self.surv_372, date_journee=self.d15, numero=2)
        s372.demarree_le = start_312
        s372.terminee_le = stop_312
        s372.save()

        def audit_events(stop15, stop16=None, stop17=None):
            start = timezone.make_aware(datetime(2026, 6, 15, 13, 5, 32))
            events = {
                1: {
                    'date_journee': self.d15,
                    'numero': 2,
                    'start': start,
                    'stop': stop15,
                },
                2: {
                    'date_journee': self.d16,
                    'numero': 2,
                    'start': timezone.make_aware(datetime(2026, 6, 16, 13, 6, 0)),
                    'stop': stop16 or timezone.make_aware(datetime(2026, 6, 16, 18, 0, 0)),
                },
            }
            if stop17:
                events[3] = {
                    'date_journee': self.d17,
                    'numero': 2,
                    'start': timezone.make_aware(datetime(2026, 6, 17, 13, 3, 0)),
                    'stop': stop17,
                }
            return events

        self.deleted = {
            _DELETED_IDS[0]: audit_events(timezone.make_aware(datetime(2026, 6, 15, 17, 23, 38))),
            _DELETED_IDS[1]: audit_events(timezone.make_aware(datetime(2026, 6, 15, 17, 25, 54))),
            _DELETED_IDS[2]: audit_events(timezone.make_aware(datetime(2026, 6, 15, 17, 31, 8))),
            _DELETED_IDS[3]: audit_events(timezone.make_aware(datetime(2026, 6, 15, 17, 35, 18))),
        }
        self.meta = {
            mid: {'formation_id': self.formation.id, 'intitule': 'DEONTOLOGIE'}
            for mid in self.deleted
        }

    def test_auto_match_dedup_0076(self):
        mapping = match_deleted_modules_to_survivors(self.deleted, self.meta)
        self.assertEqual(mapping[_DELETED_IDS[1]].id, self.surv_372.id)
        self.assertEqual(mapping[_DELETED_IDS[0]].id, self.surv_327.id)
        self.assertEqual(mapping[_DELETED_IDS[2]].id, self.surv_336.id)
        self.assertEqual(mapping[_DELETED_IDS[3]].id, self.surv_363.id)

    def test_explicit_mapping_override(self):
        explicit = _parse_explicit_mapping(
            f'{_DELETED_IDS[0]}:{self.surv_327.id},'
            f'{_DELETED_IDS[1]}:{self.surv_372.id},'
            f'{_DELETED_IDS[2]}:{self.surv_336.id},'
            f'{_DELETED_IDS[3]}:{self.surv_363.id}',
        )
        mapping = match_deleted_modules_to_survivors(
            self.deleted, self.meta, explicit_mapping=explicit,
        )
        self.assertEqual({k: v.id for k, v in mapping.items()}, explicit)

    def test_ensure_edt_creates_when_no_slots(self):
        from formations.audit_recovery import _merge_session_events, _resolve_session, ensure_audit_edt_slots

        SessionModule.objects.filter(module=self.surv_327).delete()
        merged = _merge_session_events(self.deleted[_DELETED_IDS[0]])
        self.assertEqual(len(merged), 2)
        for key in merged:
            self.assertIsNone(
                _resolve_session(self.surv_327, key[0], key[1], {}),
                msg=f'session résiduelle pour {key}',
            )
        edt_stats = ensure_audit_edt_slots(self.surv_327, merged, dry_run=False)
        self.assertEqual(edt_stats['created'], 2)
        self.assertEqual(self.surv_327.sessions.count(), 2)

    def test_apply_recovery_on_empty_survivor(self):
        """Survivant sans horaires : reprise des timestamps audit (EDT déjà présent)."""
        mapping = match_deleted_modules_to_survivors(self.deleted, self.meta)
        stats = apply_session_recovery(
            mapping[_DELETED_IDS[0]], self.deleted[_DELETED_IDS[0]], dry_run=False, create_missing_edt=True,
        )
        self.assertEqual(stats['edt_created'], 0)
        self.assertEqual(stats['updated'], 2)
        self.assertEqual(stats['missing'], 0)
        self.assertEqual(
            SessionModule.objects.filter(
                module=self.surv_327, demarree_le__isnull=False,
            ).count(),
            2,
        )
