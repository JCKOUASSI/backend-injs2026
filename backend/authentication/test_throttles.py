"""Tests unitaires pour le throttling scan."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, SimpleTestCase

from authentication.throttles import LoginRateThrottle, ScanRateThrottle

User = get_user_model()


class ScanRateThrottleKeyTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.throttle = ScanRateThrottle()

    def test_authenticated_request_keys_by_user_not_ip(self):
        user = User(pk=42, username='auditeur42')
        request = self.factory.post(
            '/api/scan/secure/',
            {'token_qr': 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee', 'device_id': 'phone-abc'},
        )
        request.user = user
        request.META['REMOTE_ADDR'] = '10.0.0.1'

        key = self.throttle.get_cache_key(request, view=None)
        self.assertEqual(key, 'scan:user:42:phone-abc')

    def test_different_users_get_different_keys_same_ip(self):
        request_a = self.factory.post('/api/scan/secure/', {'device_id': 'dev1'})
        request_a.user = User(pk=1, username='a')
        request_a.META['REMOTE_ADDR'] = '192.168.1.1'

        request_b = self.factory.post('/api/scan/secure/', {'device_id': 'dev2'})
        request_b.user = User(pk=2, username='b')
        request_b.META['REMOTE_ADDR'] = '192.168.1.1'

        key_a = self.throttle.get_cache_key(request_a, view=None)
        key_b = self.throttle.get_cache_key(request_b, view=None)
        self.assertNotEqual(key_a, key_b)

    def test_anonymous_request_keys_by_ip_and_token(self):
        request = self.factory.post(
            '/api/scan/',
            {'token_qr': 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee', 'numero': 'P001'},
        )
        request.user = AnonymousUser()
        request.META['REMOTE_ADDR'] = '203.0.113.9'

        key = self.throttle.get_cache_key(request, view=None)
        self.assertEqual(key, 'scan:ip:203.0.113.9:aaaaaaaa')

    def test_anonymous_request_uses_first_ip_from_x_forwarded_for(self):
        request = self.factory.post(
            '/api/scan/',
            {'token_qr': 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee', 'numero': 'P001'},
        )
        request.user = AnonymousUser()
        request.META['REMOTE_ADDR'] = '172.19.0.4'
        request.META['HTTP_X_FORWARDED_FOR'] = '203.0.113.9, 172.19.0.4'

        key = self.throttle.get_cache_key(request, view=None)
        self.assertEqual(key, 'scan:ip:203.0.113.9:aaaaaaaa')


class LoginRateThrottleKeyTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.throttle = LoginRateThrottle()

    def test_uses_first_ip_from_x_forwarded_for(self):
        request = self.factory.post('/api/auth/login/', {'username': 'alice'})
        request.META['REMOTE_ADDR'] = '172.19.0.4'
        request.META['HTTP_X_FORWARDED_FOR'] = '203.0.113.42, 172.19.0.4'

        key = self.throttle.get_cache_key(request, view=None)
        self.assertEqual(key, 'login:203.0.113.42')

    def test_falls_back_to_remote_addr_without_x_forwarded_for(self):
        request = self.factory.post('/api/auth/login/', {'username': 'alice'})
        request.META['REMOTE_ADDR'] = '10.0.0.1'

        key = self.throttle.get_cache_key(request, view=None)
        self.assertEqual(key, 'login:10.0.0.1')


class LoginRateThrottleCacheFailureTests(SimpleTestCase):
    """Vérifie le fail-open quand le backend de cache est inaccessible."""

    def setUp(self):
        self.factory = RequestFactory()
        self.throttle = LoginRateThrottle()
        # SimpleRateThrottle.__init__ sets self.rate via get_rate()
        self.request = self.factory.post(
            '/api/auth/login/', {'username': 'alice', 'password': 'pw'},
        )
        self.request.META['REMOTE_ADDR'] = '192.168.1.1'

    def test_allows_request_when_cache_raises_connection_error(self):
        """Redis inaccessible → la requête est autorisée, pas de 500."""
        with patch.object(self.throttle, 'cache') as mock_cache:
            mock_cache.get.side_effect = ConnectionError('Redis down')
            allowed = self.throttle.allow_request(self.request, view=None)
        self.assertTrue(allowed)

    def test_allows_request_when_cache_raises_generic_exception(self):
        """Toute erreur du cache → fail-open."""
        with patch.object(self.throttle, 'cache') as mock_cache:
            mock_cache.get.side_effect = Exception('unexpected')
            allowed = self.throttle.allow_request(self.request, view=None)
        self.assertTrue(allowed)
