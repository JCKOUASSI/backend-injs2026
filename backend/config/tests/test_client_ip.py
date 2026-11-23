from django.test import RequestFactory, SimpleTestCase

from config.client_ip import get_client_ip


class GetClientIpTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_prefers_x_forwarded_for_over_remote_addr(self):
        request = self.factory.get('/')
        request.META['REMOTE_ADDR'] = '172.19.0.4'
        request.META['HTTP_X_FORWARDED_FOR'] = '203.0.113.42, 172.19.0.4'

        self.assertEqual(get_client_ip(request), '203.0.113.42')

    def test_falls_back_to_remote_addr(self):
        request = self.factory.get('/')
        request.META['REMOTE_ADDR'] = '10.0.0.1'

        self.assertEqual(get_client_ip(request), '10.0.0.1')
