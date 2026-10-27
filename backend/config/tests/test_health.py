"""Tests du healthcheck /api/health/ (socle L0/L7)."""
from unittest import mock

from django.test import TestCase


class HealthCheckTests(TestCase):
    url = '/api/health/'

    def test_health_returns_ok_when_db_reachable(self):
        res = self.client.get(self.url)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data['status'], 'ok')
        self.assertEqual(data['database'], 'ok')
        self.assertIn('timestamp', data)

    def test_health_returns_503_when_db_unavailable(self):
        with mock.patch('config.health.connection.cursor', side_effect=Exception('db down')):
            res = self.client.get(self.url)
        self.assertEqual(res.status_code, 503)
        data = res.json()
        self.assertEqual(data['status'], 'degraded')
        self.assertEqual(data['database'], 'unavailable')

    def test_health_does_not_leak_sensitive_info(self):
        res = self.client.get(self.url)
        data = res.json()
        for key in ('debug', 'secret', 'password', 'db_name', 'database_name'):
            self.assertNotIn(key, data)
