from datetime import timedelta, time as dt_time

from django.test import TestCase
from django.utils import timezone

from .models import Formation, Module, Formateur, ModuleFormateur, RefModule, SessionModule
from .api_views import (
    _finance_dashboard_modules_breakdown,
    _finance_kpis_from_modules_breakdown,
    _finance_kpis_from_rows,
    _finance_module_planned_minutes,
    _finance_report_rows,
)


def _make_formation(titre='Cycle test'):
    return Formation.objects.create(formation=titre)


def _make_formateur():
    return Formateur.objects.create(numerobadge='F200', nom='Martin', prenom='Paul')


class FinancePlannedVolumeTest(TestCase):

    def setUp(self):
        self.formation = _make_formation()
        self.ref = RefModule.objects.create(intitule='Finances Publiques', volume_horaire=30)
        self.module = Module.objects.create(
            formation=self.formation,
            intitule='Finances Publiques',
            ref_module=self.ref,
            statut='PLANIFIEE',
            grade='A4',
            groupe='GROUPE 6',
            duree_prevue_heures=30,
        )
        self.formateur = _make_formateur()
        ModuleFormateur.objects.create(module=self.module, formateur=self.formateur)
        now = timezone.now()
        # Séance terminée : 48 h de badge réel mais créneau EDT 5 h seulement
        SessionModule.objects.create(
            module=self.module,
            date_journee=timezone.localdate(),
            numero=1,
            demarree_le=now - timedelta(days=2),
            terminee_le=now,
            heure_debut_prevue=dt_time(7, 30),
            heure_fin_prevue=dt_time(12, 30),
        )
        SessionModule.objects.create(
            module=self.module,
            date_journee=timezone.localdate(),
            numero=2,
            heure_debut_prevue=dt_time(13, 0),
            heure_fin_prevue=dt_time(18, 0),
        )

    def test_module_planned_uses_contractual_ref_when_edt_incomplete(self):
        sessions = list(SessionModule.objects.filter(module=self.module))
        planned = _finance_module_planned_minutes(self.module, sessions)
        self.assertEqual(planned, 1800.0)  # ref 30h même si EDT = 2×5h seulement

    def test_report_rows_module_planned_from_contractual_ref(self):
        rows = _finance_report_rows([self.formateur], include_sessions=True)
        self.assertEqual(len(rows), 1)
        mod = rows[0]['modules'][0]
        self.assertEqual(mod['total_duree_minutes'], 1800.0)  # ref 30h
        self.assertEqual(rows[0]['total_duree_minutes'], 1800.0)
        self.assertEqual(mod['sessions_count'], 2)
        sess = rows[0]['sessions']
        self.assertEqual(len(sess), 2)
        self.assertEqual(sess[0]['duree_minutes'], 300.0)

    def test_realized_capped_at_module_planned(self):
        """Somme réalisée séances plafonnée au planifié contractuel (duree_prevue_heures)."""
        small = Module.objects.create(
            formation=self.formation,
            intitule='Petit module',
            ref_module=RefModule.objects.create(intitule='Petit module', volume_horaire=2),
            statut='PLANIFIEE',
            grade='A4',
            groupe='GROUPE 1',
            duree_prevue_heures=2,
        )
        ModuleFormateur.objects.create(module=small, formateur=self.formateur)
        now = timezone.now()
        for n in (1, 2):
            SessionModule.objects.create(
                module=small,
                date_journee=timezone.localdate(),
                numero=n,
                demarree_le=now - timedelta(hours=2),
                terminee_le=now,
                heure_debut_prevue=dt_time(7, 30),
                heure_fin_prevue=dt_time(12, 30),
            )
        rows = _finance_report_rows([self.formateur], include_sessions=False)
        small_mod = next(m for m in rows[0]['modules'] if m['module_id'] == small.id)
        self.assertEqual(small_mod['total_duree_minutes'], 120.0)  # ref 2h même si EDT = 2×5h
        self.assertEqual(small_mod['total_duree_realisee_minutes'], 120.0)  # 2×2h badge plafonnés à 120min
        self.assertLessEqual(small_mod['total_duree_realisee_minutes'], small_mod['total_duree_minutes'])

    def test_dashboard_breakdown_module_planned_from_session_slots(self):
        rows = _finance_report_rows([self.formateur], include_sessions=False)
        breakdown = _finance_dashboard_modules_breakdown(rows, date_debut=None, date_fin=None)
        fin = next(b for b in breakdown if b['module_id'] == self.module.id)
        self.assertEqual(fin['total_duree_minutes'], 1800.0)  # ref 30h
        self.assertEqual(fin['sessions_count'], 2)
        self.assertLessEqual(
            fin['total_duree_realisee_minutes'],
            fin['total_duree_minutes'],
        )

    def test_dashboard_realized_never_exceeds_planned(self):
        rows = _finance_report_rows([self.formateur], include_sessions=False)
        breakdown = _finance_dashboard_modules_breakdown(rows, date_debut=None, date_fin=None)
        for row in breakdown:
            self.assertLessEqual(
                row['total_duree_realisee_minutes'],
                row['total_duree_minutes'],
            )

    def test_partial_period_uses_contractual_when_sessions_in_range(self):
        """Séances dans la période : planifié = volume contractuel, pas seulement Σ EDT période."""
        future = timezone.localdate() + timedelta(days=30)
        SessionModule.objects.create(
            module=self.module,
            date_journee=future,
            numero=3,
            heure_debut_prevue=dt_time(7, 30),
            heure_fin_prevue=dt_time(12, 30),
        )
        sessions = list(SessionModule.objects.filter(module=self.module))
        today = timezone.localdate()
        planned = _finance_module_planned_minutes(
            self.module, sessions, date_debut=today, date_fin=today,
        )
        self.assertEqual(planned, 1800.0)  # ref 30h (EDT du jour = 10h seulement)

    def test_assigned_module_without_sessions_excluded_from_period_recap(self):
        """Module assigné sans séance dans la période filtrée : absent du récap paie."""
        future = timezone.localdate() + timedelta(days=60)
        SessionModule.objects.filter(module=self.module).update(date_journee=future)
        today = timezone.localdate()
        rows = _finance_report_rows(
            [self.formateur],
            include_sessions=True,
            date_debut=today,
            date_fin=today,
        )
        self.assertEqual(len(rows[0]['recap_modules']), 0)
        self.assertEqual(rows[0]['sessions_count'], 0)

    def test_canonical_volume_horaire_uses_contractual_ref(self):
        from .volume_horaire import compute_volume_horaire_from_module_ids

        totals = compute_volume_horaire_from_module_ids([self.module.id])
        self.assertEqual(totals['prevu_minutes'], 1800.0)  # ref 30h
        self.assertEqual(totals['prevu_heures'], 30.0)

    def test_dashboard_kpis_deduplicate_module_planned_with_multiple_formateurs(self):
        """Deux formateurs sur le même module : KPI = une fois le planifié module."""
        formateur2 = Formateur.objects.create(numerobadge='F201', nom='Durand', prenom='Anne')
        ModuleFormateur.objects.create(module=self.module, formateur=formateur2)
        rows = _finance_report_rows([self.formateur, formateur2], include_sessions=False)
        breakdown = _finance_dashboard_modules_breakdown(rows, date_debut=None, date_fin=None)
        kpis_rows = _finance_kpis_from_rows(rows)
        kpis = _finance_kpis_from_modules_breakdown(kpis_rows, breakdown)
        self.assertEqual(breakdown[0]['total_duree_minutes'], 1800.0)
        self.assertEqual(kpis['total_duree_minutes'], 1800.0)
        self.assertNotEqual(
            sum(float(r.get('total_duree_minutes') or 0) for r in rows),
            kpis['total_duree_minutes'],
        )

    def test_incomplete_edt_shows_contractual_hours(self):
        """EDT incomplet (3×4h) : planifié = 16h référentiel, pas 12h EDT."""
        ref = RefModule.objects.create(intitule='BUDGET TEST', volume_horaire=16)
        mod = Module.objects.create(
            formation=self.formation,
            intitule='BUDGET TEST',
            ref_module=ref,
            statut='PLANIFIEE',
            grade='B',
            groupe='GROUPE TEST',
        )
        ModuleFormateur.objects.create(module=mod, formateur=self.formateur)
        for n, h in enumerate([(8, 12), (13, 17), (8, 12)], start=1):
            SessionModule.objects.create(
                module=mod,
                date_journee=timezone.localdate(),
                numero=n,
                heure_debut_prevue=dt_time(h[0], 0),
                heure_fin_prevue=dt_time(h[1], 0),
            )
        sessions = list(SessionModule.objects.filter(module=mod))
        planned = _finance_module_planned_minutes(mod, sessions)
        self.assertEqual(planned, 960.0)  # 16h ref, pas 12h EDT
