"""Cache GET /api/statistiques/ par sections, scope et période."""
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.core.cache import cache
from rest_framework.test import APIClient

from authentication.models import User


def make_user(username, role='INJS_ADMIN', **kwargs):
    return User.objects.create_user(username=username, password='pass', role=role, **kwargs)


@override_settings(
    CACHES={
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'stats-dashboard-cache-test',
        }
    }
)
class StatsDashboardCacheTests(TestCase):
    def setUp(self):
        # Isolation : LocMemCache est partagée au niveau du LOCATION du module ;
        # on la purge pour qu'un test précédent ne pollue pas les assertions de cache.
        cache.clear()
        self.admin = make_user('admin_stats_cache')
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    @patch('statistiques.views._build_dashboard_payload')
    def test_second_identical_request_uses_cache(self, mock_build):
        mock_build.return_value = {'kpis': {'modules': 0}}

        url = '/api/statistiques/?sections=kpis&preset=tout'
        res1 = self.client.get(url)
        res2 = self.client.get(url)

        self.assertEqual(res1.status_code, 200)
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(mock_build.call_count, 1)

    @patch('statistiques.views._build_dashboard_payload')
    def test_different_sections_bypass_cache(self, mock_build):
        mock_build.return_value = {'kpis': {'modules': 0}}

        self.client.get('/api/statistiques/?sections=kpis&preset=tout')
        self.client.get('/api/statistiques/?sections=historique&preset=tout')

        self.assertEqual(mock_build.call_count, 2)

    @patch('statistiques.views._build_dashboard_payload')
    def test_different_period_bypass_cache(self, mock_build):
        mock_build.return_value = {'kpis': {'modules': 0}}

        self.client.get('/api/statistiques/?sections=kpis&preset=tout')
        self.client.get('/api/statistiques/?sections=kpis&preset=mois&mois=2024-06')

        self.assertEqual(mock_build.call_count, 2)


@override_settings(
    CACHES={
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'stats-secretariats-cache-test',
        }
    }
)
class StatsSecretariatsCacheTests(TestCase):
    def setUp(self):
        # Isolation : LocMemCache est partagée au niveau du LOCATION du module ;
        # on la purge pour qu'un test précédent ne pollue pas les assertions de cache.
        cache.clear()
        self.admin = make_user('admin_sec_cache')
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    @patch('statistiques.views._build_secretariats_stats_payload')
    def test_second_identical_request_uses_cache(self, mock_build):
        mock_build.return_value = {'secretariats': [], 'total': 0}

        url = '/api/statistiques/secretariats/?preset=tout'
        res1 = self.client.get(url)
        res2 = self.client.get(url)

        self.assertEqual(res1.status_code, 200)
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(mock_build.call_count, 1)

    @patch('statistiques.views._build_secretariats_stats_payload')
    def test_different_period_bypass_cache(self, mock_build):
        mock_build.return_value = {'secretariats': [], 'total': 0}

        self.client.get('/api/statistiques/secretariats/?preset=tout')
        self.client.get('/api/statistiques/secretariats/?preset=mois&mois=2024-06')

        self.assertEqual(mock_build.call_count, 2)


@override_settings(
    CACHES={
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'stats-bilans-cache-test',
        }
    }
)
class StatsBilansCacheTests(TestCase):
    def setUp(self):
        # Isolation : LocMemCache est partagée au niveau du LOCATION du module ;
        # on la purge pour qu'un test précédent ne pollue pas les assertions de cache.
        cache.clear()
        self.admin = make_user('admin_bilans_cache')
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    @patch('statistiques.views._build_bilans_payload')
    def test_second_identical_request_uses_cache(self, mock_build):
        mock_build.return_value = ({'bilans': []}, None)

        url = '/api/statistiques/bilans/?annee=2024&dimension=module'
        res1 = self.client.get(url)
        res2 = self.client.get(url)

        self.assertEqual(res1.status_code, 200)
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(mock_build.call_count, 1)

    @patch('statistiques.views._build_bilans_payload')
    def test_tous_tableaux_separate_cache_key(self, mock_build):
        mock_build.return_value = ({'bilans': []}, None)

        self.client.get('/api/statistiques/bilans/?annee=2024&dimension=module')
        self.client.get('/api/statistiques/bilans/?annee=2024&dimension=module&tous_tableaux=1')

        self.assertEqual(mock_build.call_count, 2)

    @patch('statistiques.views._build_bilans_payload')
    def test_error_response_not_cached(self, mock_build):
        from rest_framework.response import Response
        mock_build.return_value = (
            None,
            Response({'detail': 'Introuvable.'}, status=404),
        )

        # Sans module_id dans l'URL : sinon resolve_stats_scope renvoie 403 avant le mock.
        url = '/api/statistiques/bilans/?annee=2024&dimension=module&detail=1'
        res1 = self.client.get(url)
        res2 = self.client.get(url)

        self.assertEqual(res1.status_code, 404)
        self.assertEqual(res2.status_code, 404)
        self.assertEqual(mock_build.call_count, 2)
