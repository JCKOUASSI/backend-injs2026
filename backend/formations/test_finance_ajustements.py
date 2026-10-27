from datetime import timedelta, time as dt_time

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from presences.models import AuditLog
from .models import (
    Formation, Module, Formateur, ModuleFormateur, SessionModule, FinanceAjustement,
)
from .finance_ajustements import (
    propose_ajustement,
    valider_ajustement,
    rejeter_ajustement,
    preview_realise_after_adjustment,
)
from .volume_horaire import _session_realise_minutes
from .api_views import _finance_report_rows

User = get_user_model()


def _make_session(module, hours=2, slot_hours=2):
    now = timezone.now()
    return SessionModule.objects.create(
        module=module,
        date_journee=timezone.localdate(),
        numero=1,
        demarree_le=now - timedelta(hours=hours),
        terminee_le=now,
        heure_debut_prevue=dt_time(8, 0),
        heure_fin_prevue=dt_time(8 + slot_hours, 0),
    )


class FinanceAjustementsTest(TestCase):

    def setUp(self):
        self.finance_user = User.objects.create_user(
            username='finance1', password='test', role='FINANCE',
        )
        self.direction_user = User.objects.create_user(
            username='dir1', password='test', role='DIRECTION',
        )
        self.formation = Formation.objects.create(formation='Cycle test')
        self.module = Module.objects.create(
            formation=self.formation,
            intitule='Déontologie',
            statut='PLANIFIEE',
            grade='A4',
            groupe='GROUPE 4',
            duree_prevue_heures=4,
        )
        self.formateur = Formateur.objects.create(
            numerobadge='F200', nom='Martin', prenom='Paul',
        )
        ModuleFormateur.objects.create(module=self.module, formateur=self.formateur)
        self.session = _make_session(self.module)
        self.client = APIClient()

    def test_preview_add_minutes(self):
        avant = _session_realise_minutes(self.session)
        apres = preview_realise_after_adjustment(self.session, 30)
        self.assertEqual(apres, round(avant + 30, 1))

    def test_validate_adjustment_updates_session_and_pay(self):
        avant = round(_session_realise_minutes(self.session), 1)
        ajustement, errors = propose_ajustement(
            self.session, self.formateur, -30, 'Retard constaté', self.finance_user,
        )
        self.assertEqual(errors, [])
        self.assertEqual(ajustement.statut, FinanceAjustement.Statut.EN_ATTENTE)

        ajustement, errors = valider_ajustement(ajustement, self.direction_user)
        self.assertEqual(errors, [])
        self.session.refresh_from_db()
        apres = round(_session_realise_minutes(self.session), 1)
        self.assertEqual(apres, avant - 30)

        rows = _finance_report_rows([self.formateur], include_sessions=True)
        self.assertEqual(rows[0]['total_duree_realisee_minutes'], apres)

    def test_reject_does_not_modify_session(self):
        avant = round(_session_realise_minutes(self.session), 1)
        ajustement, _ = propose_ajustement(
            self.session, self.formateur, -15, 'Test rejet', self.finance_user,
        )
        ajustement, errors = rejeter_ajustement(
            ajustement, self.direction_user, rejection_motif='Non justifié',
        )
        self.assertEqual(errors, [])
        self.session.refresh_from_db()
        self.assertEqual(round(_session_realise_minutes(self.session), 1), avant)
        self.assertEqual(ajustement.statut, FinanceAjustement.Statut.REJETE)

    def test_api_workflow_with_audit(self):
        self.client.force_authenticate(user=self.finance_user)
        res = self.client.post(
            '/api/formations/finance/ajustements/',
            {
                'session_id': self.session.id,
                'formateur_id': self.formateur.id,
                'minutes_delta': 20,
                'motif': 'Séance prolongée',
            },
            format='json',
        )
        self.assertEqual(res.status_code, 201)
        ajustement_id = res.json()['id']

        self.assertTrue(
            AuditLog.objects.filter(
                action='FINANCE_AJUSTEMENT_PROPOSE',
                extra__ajustement_id=ajustement_id,
            ).exists()
        )

        self.client.force_authenticate(user=self.direction_user)
        res_val = self.client.post(
            f'/api/formations/finance/ajustements/{ajustement_id}/valider/',
            format='json',
        )
        self.assertEqual(res_val.status_code, 200)
        self.assertEqual(res_val.json()['statut'], 'VALIDE')
        self.assertTrue(
            AuditLog.objects.filter(
                action='FINANCE_AJUSTEMENT_VALIDE',
                extra__ajustement_id=ajustement_id,
            ).exists()
        )

    def test_cannot_propose_on_non_terminated_session(self):
        session = SessionModule.objects.create(
            module=self.module,
            date_journee=timezone.localdate(),
            numero=2,
            heure_debut_prevue=dt_time(14, 0),
            heure_fin_prevue=dt_time(16, 0),
        )
        _, errors = propose_ajustement(
            session, self.formateur, 10, 'Test', self.finance_user,
        )
        self.assertIn('Seules les séances terminées peuvent être ajustées.', errors)
