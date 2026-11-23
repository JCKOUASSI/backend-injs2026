"""Tests du socle technique : format d'erreur harmonisé, configuration."""
from django.conf import settings
from django.test import TestCase


class UnifiedExceptionHandlerTests(TestCase):
    """Le handler préserve le payload DRF et ajoute X-Error-Code."""

    def test_error_response_carries_machine_code_header(self):
        res = self.client.get('/api/auth/me/')  # non authentifié → 401
        self.assertEqual(res.status_code, 401)
        self.assertIn('X-Error-Code', res.headers)
        self.assertTrue(res.headers['X-Error-Code'])

    def test_payload_format_unchanged_for_detail_errors(self):
        res = self.client.get('/api/auth/me/')
        data = res.json()
        # Format DRF historique conservé (compatibilité React + Flutter).
        self.assertIn('detail', data)

    def test_explicit_business_code_exposed_in_header(self):
        # Une exception levée via DRF passe par le handler : refresh avec
        # un token invalide → 401 + code machine en en-tête.
        res = self.client.post(
            '/api/auth/token/refresh/',
            data={'refresh': 'token-invalide'},
            content_type='application/json',
        )
        self.assertEqual(res.status_code, 401)
        self.assertIn('X-Error-Code', res.headers)
        self.assertTrue(res.headers['X-Error-Code'])


class ProductionHardeningTests(TestCase):
    """Risque R5 — ALLOWED_HOSTS stricts."""

    def test_settings_allow_no_wildcard_literal(self):
        # Garde-fou : la configuration chargée ne doit plus contenir de '*'.
        # (En dev le '*' historique a été retiré ; en prod il est filtré.)
        self.assertNotIn('*', settings.ALLOWED_HOSTS)

    def test_logging_configured(self):
        # Risque R8 — le bloc LOGGING est présent avec un handler rotatif.
        handlers = settings.LOGGING.get('handlers', {})
        self.assertIn('file_rotating', handlers)
        self.assertEqual(
            handlers['file_rotating']['class'],
            'logging.handlers.RotatingFileHandler',
        )
        self.assertEqual(handlers['file_rotating']['level'], 'WARNING')
