"""Tests : conservation des groupes lors du filtre formation source."""

import datetime

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from apps.auditeurs.models import Auditeur
from apps.formations.models import Formation
from apps.groupes.models import ConfigGroupe, Groupe, GroupeAuditeur
from apps.groupes.services import GroupeService
from apps.referentiels.models import TypeFormation


@pytest.fixture
def logged_client(db):
    User.objects.create_superuser("srcgrp", "srcgrp@example.com", "testpass123")
    client = Client()
    client.login(username="srcgrp", password="testpass123")
    return client


@pytest.fixture
def formations_source_cible(db):
    type_form, _ = TypeFormation.objects.get_or_create(code="FAC", defaults={"libelle": "FAC"})
    source = Formation.objects.create(
        type_formation=type_form,
        intitule="Formation source",
        date_debut=datetime.date(2024, 1, 1),
        date_fin=datetime.date(2024, 6, 30),
    )
    cible = Formation.objects.create(
        type_formation=type_form,
        intitule="Formation cible",
        date_debut=datetime.date(2025, 1, 1),
        date_fin=datetime.date(2025, 6, 30),
    )
    return source, cible


def _service():
    from apps.groupes.repositories import ConfigGroupeRepository, GroupeRepository, JourCoursRepository

    return GroupeService(GroupeRepository(), ConfigGroupeRepository(), JourCoursRepository())


@pytest.mark.django_db
class TestSourceFormationGroupes:
    def test_modales_filtrent_par_nom_groupe_homologue(
        self, logged_client, formations_source_cible, module_referentiel
    ):
        source, cible = formations_source_cible
        aud_a = Auditeur.objects.create(nom="Alpha", prenom="Un", matricule="SRCA001", grade="A3")
        aud_b = Auditeur.objects.create(nom="Bravo", prenom="Deux", matricule="SRCB002", grade="B")
        g_src_a = Groupe.objects.create(formation=source, nom="A3_GROUPE1", max_auditeurs=25)
        g_src_b = Groupe.objects.create(formation=source, nom="B_GROUPE1", max_auditeurs=25)
        GroupeAuditeur.objects.create(groupe=g_src_a, auditeur=aud_a)
        GroupeAuditeur.objects.create(groupe=g_src_b, auditeur=aud_b)

        g_cible_a = Groupe.objects.create(formation=cible, nom="A3_GROUPE1", max_auditeurs=25)
        g_cible_b = Groupe.objects.create(formation=cible, nom="B_GROUPE1", max_auditeurs=25)
        ConfigGroupe.objects.create(groupe=g_cible_a)
        ConfigGroupe.objects.create(groupe=g_cible_b)

        url = reverse("groupes:list", kwargs={"formation_pk": cible.pk})
        resp = logged_client.get(f"{url}?source_formation={source.pk}")
        html = resp.content.decode()

        idx_a = html.find(f'id="modalMembres{g_cible_a.pk}"')
        idx_b = html.find(f'id="modalMembres{g_cible_b.pk}"')
        assert idx_a >= 0 and idx_b > idx_a
        modal_a = html[idx_a:idx_b]
        modal_b = html[idx_b:]

        def _checkbox_auditeur(chunk: str, aud_pk: int) -> bool:
            needle = f'name="auditeur_ids" value="{aud_pk}"'
            return needle in chunk

        assert _checkbox_auditeur(modal_a, aud_a.pk)
        assert not _checkbox_auditeur(modal_a, aud_b.pk)
        assert _checkbox_auditeur(modal_b, aud_b.pk)
        assert not _checkbox_auditeur(modal_b, aud_a.pk)

    def test_membre_add_refuse_mauvais_groupe_homologue(self, logged_client, formations_source_cible):
        source, cible = formations_source_cible
        aud = Auditeur.objects.create(nom="X", prenom="Y", matricule="SRCX001", grade="A3")
        Groupe.objects.create(formation=source, nom="A3_GROUPE1", max_auditeurs=25)
        ga = GroupeAuditeur.objects.create(
            groupe=Groupe.objects.get(formation=source, nom="A3_GROUPE1"),
            auditeur=aud,
        )
        g_cible_b = Groupe.objects.create(formation=cible, nom="B_GROUPE1", max_auditeurs=25)

        url = reverse("groupes:membre_add", kwargs={"groupe_pk": g_cible_b.pk})
        resp = logged_client.post(
            url,
            {"auditeur_ids": [aud.pk], "source_formation": source.pk},
        )
        assert resp.status_code == 302
        assert not GroupeAuditeur.objects.filter(groupe=g_cible_b, auditeur=aud).exists()
        assert GroupeAuditeur.objects.filter(pk=ga.pk).exists()

    def test_reporter_cree_groupe_homologue_si_absent(self, formations_source_cible, parametres):
        source, cible = formations_source_cible
        aud = Auditeur.objects.create(nom="Z", prenom="W", matricule="SRCZ001", grade="A3")
        Groupe.objects.create(formation=source, nom="A3_GROUPE1", max_auditeurs=30)
        GroupeAuditeur.objects.create(
            groupe=Groupe.objects.get(formation=source, nom="A3_GROUPE1"),
            auditeur=aud,
        )
        assert not Groupe.objects.filter(formation=cible).exists()

        stats = _service().reporter_membres_depuis_formation_source(cible.pk, source.pk)
        assert stats["groupes_crees"] == 1
        assert stats["ajoutes"] == 1
        g_cible = Groupe.objects.get(formation=cible, nom="A3_GROUPE1")
        assert g_cible.max_auditeurs == 30
        assert GroupeAuditeur.objects.filter(groupe=g_cible, auditeur=aud).exists()

    def test_filtre_source_cree_groupes_homologues_via_post(self, logged_client, formations_source_cible, parametres):
        source, cible = formations_source_cible
        Groupe.objects.create(formation=source, nom="A3_GROUPE1", max_auditeurs=25)
        Groupe.objects.create(formation=source, nom="B_GROUPE1", max_auditeurs=25)

        url = reverse("groupes:assurer_homologues", kwargs={"formation_pk": cible.pk})
        resp = logged_client.post(url, {"source_formation": source.pk})
        assert resp.status_code == 302
        noms = set(Groupe.objects.filter(formation=cible).values_list("nom", flat=True))
        assert noms == {"A3_GROUPE1", "B_GROUPE1"}

        list_url = reverse("groupes:list", kwargs={"formation_pk": cible.pk})
        resp_get = logged_client.get(f"{list_url}?source_formation={source.pk}")
        assert resp_get.status_code == 200
        assert Groupe.objects.filter(formation=cible).count() == 2

    def test_reporter_http(self, logged_client, formations_source_cible, parametres):
        source, cible = formations_source_cible
        aud = Auditeur.objects.create(nom="R", prenom="T", matricule="SRCR001", grade="A3")
        Groupe.objects.create(formation=source, nom="A3_GROUPE1", max_auditeurs=25)
        GroupeAuditeur.objects.create(
            groupe=Groupe.objects.get(formation=source, nom="A3_GROUPE1"),
            auditeur=aud,
        )

        url = reverse("groupes:reporter_depuis_source", kwargs={"formation_pk": cible.pk})
        resp = logged_client.post(url, {"source_formation": source.pk})
        assert resp.status_code == 302
        g_cible = Groupe.objects.get(formation=cible, nom="A3_GROUPE1")
        assert GroupeAuditeur.objects.filter(groupe=g_cible, auditeur=aud).exists()

    def test_assurer_groupes_copie_config_depuis_source(self, formations_source_cible, parametres):
        import datetime

        from apps.groupes.models import ConfigGroupe, JourCours

        source, cible = formations_source_cible
        g_src = Groupe.objects.create(formation=source, nom="A3_GROUPE1", max_auditeurs=30, rythme_mensuel="2")
        ConfigGroupe.objects.create(
            groupe=g_src,
            matin_actif=True,
            matin_heure_debut=datetime.time(7, 30),
            matin_heure_fin=datetime.time(11, 30),
            soir_actif=False,
            soir_heure_debut=datetime.time(13, 0),
            soir_heure_fin=datetime.time(17, 0),
        )
        JourCours.objects.create(groupe=g_src, jour=0)
        JourCours.objects.create(groupe=g_src, jour=2)

        nb = _service().assurer_groupes_homologues_depuis_source(cible.pk, source.pk)
        assert nb == 1
        g_dst = Groupe.objects.get(formation=cible, nom="A3_GROUPE1")
        assert g_dst.max_auditeurs == 30
        assert g_dst.rythme_mensuel == "2"
        assert g_dst.config.matin_heure_debut == datetime.time(7, 30)
        assert set(g_dst.jours_cours.values_list("jour", flat=True)) == {0, 2}

    def test_creer_groupe_manuel_http(self, logged_client, formation, parametres):
        url = reverse("groupes:create", kwargs={"formation_pk": formation.pk})
        resp = logged_client.post(url, {"nom": "Groupe manuel", "max_auditeurs": 20})
        assert resp.status_code == 302
        assert Groupe.objects.filter(formation=formation, nom="Groupe manuel").exists()
