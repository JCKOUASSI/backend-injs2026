"""Tests d'isolation des formations par gestionnaire responsable."""

import datetime

import pytest
from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.urls import reverse


@pytest.fixture
def roles(db):
    call_command("seed_roles")


@pytest.fixture
def gestionnaire(roles):
    user = User.objects.create_user("gest_scope", "gest_scope@test.ci", "pass")
    user.groups.add(Group.objects.get(name="GESTIONNAIRE_EDT"))
    return user


@pytest.fixture
def admin_user(roles):
    user = User.objects.create_user("admin_scope", "admin_scope@test.ci", "pass")
    user.groups.add(Group.objects.get(name="ADMIN_EDT"))
    return user


@pytest.fixture
def formation_a(type_formation, gestionnaire):
    from apps.formations.repositories import FormationModuleRepository, FormationRepository
    from apps.formations.services import FormationService

    return FormationService(FormationRepository(), FormationModuleRepository()).creer(
        type_formation_id=type_formation.pk,
        intitule="Formation A",
        vague="V1",
        date_debut=datetime.date(2025, 1, 6),
        date_fin=datetime.date(2025, 3, 28),
        responsable=gestionnaire,
    )


@pytest.fixture
def formation_b(type_formation, admin_user):
    from apps.formations.repositories import FormationModuleRepository, FormationRepository
    from apps.formations.services import FormationService

    return FormationService(FormationRepository(), FormationModuleRepository()).creer(
        type_formation_id=type_formation.pk,
        intitule="Formation B",
        vague="V2",
        date_debut=datetime.date(2025, 4, 1),
        date_fin=datetime.date(2025, 6, 30),
        responsable=admin_user,
    )


@pytest.fixture
def formation_orpheline(type_formation):
    from apps.formations.repositories import FormationModuleRepository, FormationRepository
    from apps.formations.services import FormationService

    return FormationService(FormationRepository(), FormationModuleRepository()).creer(
        type_formation_id=type_formation.pk,
        intitule="Formation orpheline",
        vague="V0",
        date_debut=datetime.date(2024, 1, 6),
        date_fin=datetime.date(2024, 3, 28),
    )


@pytest.mark.django_db
class TestFormationsScope:
    def test_gestionnaire_ne_voit_que_ses_formations(self, gestionnaire, formation_a, formation_b, formation_orpheline):
        from django.test import Client

        client = Client()
        client.force_login(gestionnaire)
        resp = client.get(reverse("formations:list"))
        assert resp.status_code == 200
        ids = {f.pk for f in resp.context["formations"]}
        assert formation_a.pk in ids
        assert formation_b.pk not in ids
        assert formation_orpheline.pk not in ids

    def test_gestionnaire_404_sur_formation_autre(self, gestionnaire, formation_b):
        from django.test import Client

        client = Client()
        client.force_login(gestionnaire)
        resp = client.get(reverse("formations:detail", kwargs={"pk": formation_b.pk}))
        assert resp.status_code == 404

    def test_admin_voit_toutes_les_formations(self, admin_user, formation_a, formation_b, formation_orpheline):
        from django.test import Client

        client = Client()
        client.force_login(admin_user)
        resp = client.get(reverse("formations:list"))
        ids = {f.pk for f in resp.context["formations"]}
        assert {formation_a.pk, formation_b.pk, formation_orpheline.pk}.issubset(ids)

    def test_creation_assigne_responsable(self, gestionnaire, type_formation):
        from django.test import Client

        client = Client()
        client.force_login(gestionnaire)
        resp = client.post(
            reverse("formations:create"),
            {
                "type_formation": type_formation.pk,
                "intitule": "Ma nouvelle formation",
                "vague": "",
                "date_debut": "2025-09-01",
                "date_fin": "2025-12-01",
                "rythme_mensuel": ["4"],
            },
        )
        assert resp.status_code == 302
        from apps.formations.models import Formation

        created = Formation.objects.get(intitule="Ma nouvelle formation")
        assert created.responsable_id == gestionnaire.pk
