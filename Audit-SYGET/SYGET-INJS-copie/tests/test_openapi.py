"""Tests schéma OpenAPI."""

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse


@pytest.fixture
def api_client(db):
    User.objects.create_superuser("openapi", "o@example.com", "testpass123")
    client = Client()
    client.login(username="openapi", password="testpass123")
    return client


@pytest.mark.django_db
def test_openapi_schema_accessible(api_client):
    resp = api_client.get(reverse("api_openapi_schema"))
    assert resp.status_code == 200
    assert resp["Content-Type"].startswith("application/yaml")
    assert b"openapi: 3.0.3" in resp.content
    assert b"/api/formations/" in resp.content
