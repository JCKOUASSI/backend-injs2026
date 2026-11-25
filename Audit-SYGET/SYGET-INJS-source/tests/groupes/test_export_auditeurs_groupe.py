"""Export Excel des auditeurs par groupe."""

import datetime
from io import BytesIO

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse
from openpyxl import load_workbook

from apps.groupes.models import Groupe, GroupeAuditeur


@pytest.fixture
def logged_client(db):
    User.objects.create_superuser("exportguser", "exportg@example.com", "testpass123")
    client = Client()
    client.login(username="exportguser", password="testpass123")
    return client


@pytest.mark.django_db
class TestExportAuditeursGroupe:
    def test_export_groupe_xlsx(self, logged_client, formation, auditeur):
        g = Groupe.objects.create(formation=formation, nom="Groupe A1", max_auditeurs=25)
        GroupeAuditeur.objects.create(groupe=g, auditeur=auditeur)
        url = reverse("groupes:export_auditeurs", kwargs={"groupe_pk": g.pk})
        resp = logged_client.get(url)
        assert resp.status_code == 200
        assert "spreadsheetml" in resp["Content-Type"]
        assert "attachment" in resp["Content-Disposition"].lower()
        wb = load_workbook(BytesIO(resp.content), data_only=True)
        ws = wb["Auditeurs"]
        assert ws.cell(1, 1).value == "Export auditeurs"
        assert ws.cell(3, 1).value == "N° d'inscription"
        assert ws.cell(4, 1).value == auditeur.matricule
        assert ws.cell(4, 14).value == "Groupe A1"
        assert ws.max_row == 4

    def test_export_groupe_vide_entetes_seulement(self, logged_client, formation):
        g = Groupe.objects.create(formation=formation, nom="Groupe vide", max_auditeurs=25)
        resp = logged_client.get(reverse("groupes:export_auditeurs", kwargs={"groupe_pk": g.pk}))
        assert resp.status_code == 200
        wb = load_workbook(BytesIO(resp.content), data_only=True)
        ws = wb["Auditeurs"]
        assert ws.max_row == 3

    def test_export_groupe_inexistant_404(self, logged_client):
        resp = logged_client.get(reverse("groupes:export_auditeurs", kwargs={"groupe_pk": 999999}))
        assert resp.status_code == 404

    def test_export_ne_melange_pas_autres_groupes(self, logged_client, formation, auditeur):
        from apps.auditeurs.models import Auditeur

        g1 = Groupe.objects.create(formation=formation, nom="G1", max_auditeurs=25)
        g2 = Groupe.objects.create(formation=formation, nom="G2", max_auditeurs=25)
        autre = Auditeur.objects.create(
            matricule="EXP-002",
            nom="Autre",
            prenom="Test",
            date_naissance=datetime.date(1990, 1, 1),
        )
        GroupeAuditeur.objects.create(groupe=g1, auditeur=auditeur)
        GroupeAuditeur.objects.create(groupe=g2, auditeur=autre)
        resp = logged_client.get(reverse("groupes:export_auditeurs", kwargs={"groupe_pk": g1.pk}))
        wb = load_workbook(BytesIO(resp.content), data_only=True)
        ws = wb["Auditeurs"]
        assert ws.max_row == 4
        assert ws.cell(4, 1).value == auditeur.matricule
