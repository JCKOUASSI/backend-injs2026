"""Tests du flux JWT avec cookie HttpOnly (risque R6 — socle L0/L7).

Couvre la rétrocompatibilité mobile (refresh dans le body) et la voie web
(refresh dans le cookie HttpOnly, plus rien en localStorage).
"""
from django.contrib.auth import get_user_model
from django.test import TestCase

User = get_user_model()


class JwtCookieFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='socle_admin',
            password='Socle!2026x',
            role=User.Role.ADMIN,
        )

    def _login(self):
        res = self.client.post(
            '/api/auth/login/',
            data={'username': 'socle_admin', 'password': 'Socle!2026x'},
            content_type='application/json',
        )
        self.assertEqual(res.status_code, 200)
        return res.json()

    def test_login_sets_httponly_refresh_cookie(self):
        data = self._login()
        self.assertTrue(data.get('refresh_in_cookie'))
        cookie = self.client.cookies['refresh_token']
        self.assertTrue(cookie['httponly'])
        self.assertEqual(cookie['path'], '/api/auth/')
        # Rétrocompatibilité mobile : le refresh reste dans le body.
        self.assertIn('refresh', data)

    def test_refresh_via_cookie_without_body(self):
        self._login()
        self.assertIn('refresh_token', self.client.cookies)
        res = self.client.post(
            '/api/auth/token/refresh/',
            data={},
            content_type='application/json',
        )
        self.assertEqual(res.status_code, 200, res.content)
        data = res.json()
        self.assertIn('access', data)
        self.assertTrue(data.get('refresh_in_cookie'))

    def test_refresh_via_body_still_supported_mobile(self):
        data = self._login()
        res = self.client.post(
            '/api/auth/token/refresh/',
            data={'refresh': data['refresh']},
            content_type='application/json',
        )
        self.assertEqual(res.status_code, 200, res.content)
        self.assertIn('access', res.json())

    def test_logout_deletes_cookie(self):
        self._login()
        res = self.client.post('/api/auth/logout/')
        self.assertEqual(res.status_code, 200)
        cookie = self.client.cookies['refresh_token']
        self.assertEqual(cookie.value, '')

    def test_refresh_rejected_without_cookie_or_body(self):
        res = self.client.post(
            '/api/auth/token/refresh/',
            data={},
            content_type='application/json',
        )
        self.assertEqual(res.status_code, 400)
