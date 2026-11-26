import pytest
from django.test import Client
from django.urls import reverse

from apps.referentiels.models import Module


@pytest.fixture
def logged_client(db):
    from django.contrib.auth.models import User

    User.objects.create_superuser("refuser", "ref@example.com", "testpass123")
    client = Client()
    client.login(username="refuser", password="testpass123")
    return client


@pytest.mark.django_db
class TestReferentielsViews:
    def test_module_update(self, logged_client, specialite_generale):
        module = Module.objects.create(titre="Module A", specialite=specialite_generale)
        url = reverse("referentiels:module_update", kwargs={"pk": module.pk})
        resp = logged_client.post(url, {"titre": "Module B", "specialite": specialite_generale.pk})
        assert resp.status_code == 302
        module.refresh_from_db()
        assert module.titre == "Module B"

    def test_module_delete(self, logged_client, specialite_generale):
        module = Module.objects.create(titre="Module C", specialite=specialite_generale)
        url = reverse("referentiels:module_delete", kwargs={"pk": module.pk})
        resp = logged_client.post(url)
        assert resp.status_code == 302
        assert not Module.objects.filter(pk=module.pk).exists()
