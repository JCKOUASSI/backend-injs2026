"""KPI globaux — filtre temporel sur tous les indicateurs."""
from datetime import time, timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from authentication.models import User
from formations.models import Formation, Module, ModuleParticipant, Participant, SessionModule
from statistiques.views import _kpis_globaux


def make_user(username, role='INJS_ADMIN', **kwargs):
    return User.objects.create_user(username=username, password='pass', role=role, **kwargs)


class KpisPeriodFilterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.formation = Formation.objects.create(formation='Cycle KPI période')
        cls.module = Module.objects.create(
            formation=cls.formation, intitule='Module période', grade='A3',
        )
        cls.participant = Participant.objects.create(
            matricule='KPI-001', nom='Auditeur', prenom='Test', categorie='A',
        )
        ModuleParticipant.objects.create(module=cls.module, participant=cls.participant)
        cls.jour = timezone.localdate()
        cls.hors_periode = cls.jour - timedelta(days=60)

    def _session(self, jour, numero):
        return SessionModule.objects.create(
            module=self.module,
            date_journee=jour,
            numero=numero,
            heure_debut_prevue=time(8, 0),
            heure_fin_prevue=time(12, 0),
        )

    def test_sans_periode_compte_tout_le_perimetre(self):
        self._session(self.jour, 1)
        self._session(self.hors_periode, 2)
        kpis = _kpis_globaux()
        self.assertEqual(kpis['modules'], 1)
        self.assertEqual(kpis['participants'], 1)
        self.assertEqual(kpis['sessions_total'], 2)

    def test_avec_periode_limite_modules_et_sessions(self):
        self._session(self.jour, 1)
        self._session(self.hors_periode, 2)
        kpis = _kpis_globaux(
            date_debut=self.jour,
            date_fin=self.jour,
        )
        self.assertEqual(kpis['formations'], 1)
        self.assertEqual(kpis['modules'], 1)
        self.assertEqual(kpis['participants'], 1)
        self.assertEqual(kpis['sessions_total'], 1)

    def test_periode_sans_seance_retourne_zeros(self):
        self._session(self.hors_periode, 1)
        futur = self.jour + timedelta(days=90)
        kpis = _kpis_globaux(date_debut=futur, date_fin=futur)
        self.assertEqual(kpis['formations'], 0)
        self.assertEqual(kpis['modules'], 0)
        self.assertEqual(kpis['participants'], 0)
        self.assertEqual(kpis['sessions_total'], 0)

    def test_api_kpis_respecte_preset_mois(self):
        self._session(self.jour, 1)
        self._session(self.hors_periode, 2)
        admin = make_user('admin_kpi_period')
        client = APIClient()
        client.force_authenticate(admin)
        mois = self.jour.strftime('%Y-%m')
        res = client.get(f'/api/statistiques/?sections=kpis&preset=mois&mois={mois}')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['kpis']['sessions_total'], 1)
        self.assertEqual(res.data['kpis']['modules'], 1)
