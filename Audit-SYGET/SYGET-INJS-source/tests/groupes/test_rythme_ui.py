"""Tests d'intégration UI pour la cadence mensuelle du groupe (héritage / override)."""

import datetime

import pytest
from django.test import Client
from django.urls import reverse

from apps.formations.models import Formation
from apps.groupes.models import Groupe
from apps.referentiels.models import TypeFormation


@pytest.fixture
def logged_client(db):
    from django.contrib.auth.models import User

    User.objects.create_superuser("uitest", "uitest@example.com", "testpass123")
    client = Client()
    client.login(username="uitest", password="testpass123")
    return client


@pytest.fixture
def formation_avec_groupe(db):
    type_form, _ = TypeFormation.objects.get_or_create(code="FAC", defaults={"libelle": "FAC"})
    formation = Formation.objects.create(
        type_formation=type_form,
        intitule="Formation UI Cadence",
        vague="Vague test",
        date_debut=datetime.date(2025, 1, 1),
        date_fin=datetime.date(2025, 1, 31),
        rythme_mensuel="2",
    )
    groupe = Groupe.objects.create(formation=formation, nom="G-UI", max_auditeurs=20)
    return formation, groupe


@pytest.mark.django_db
class TestCadenceGroupeUI:
    def test_liste_groupes_se_rend_avec_section_cadence(self, logged_client, formation_avec_groupe):
        formation, groupe = formation_avec_groupe
        resp = logged_client.get(reverse("groupes:list", kwargs={"formation_pk": formation.pk}))
        assert resp.status_code == 200
        html = resp.content.decode()
        assert "Cadence mensuelle du groupe" in html
        # Héritage par défaut (champ vide) → mention de l'héritage avec la cadence formation
        assert "hérite de la formation" in html
        assert "Deux semaines par mois" in html

    def test_liste_affiche_config_enregistree_du_groupe(self, logged_client, formation_avec_groupe, parametres):
        import datetime

        from apps.groupes.models import ConfigGroupe, JourCours

        formation, groupe = formation_avec_groupe
        ConfigGroupe.objects.create(
            groupe=groupe,
            matin_actif=True,
            matin_heure_debut=datetime.time(7, 15),
            matin_heure_fin=datetime.time(11, 45),
            soir_actif=False,
        )
        JourCours.objects.create(groupe=groupe, jour=1)
        JourCours.objects.create(groupe=groupe, jour=3)
        groupe.rythme_mensuel = "2"
        groupe.save(update_fields=["rythme_mensuel"])

        resp = logged_client.get(reverse("groupes:list", kwargs={"formation_pk": formation.pk}))
        html = resp.content.decode()
        pfx = f"g{groupe.pk}"

        assert 'value="07:15"' in html
        assert 'value="11:45"' in html
        assert f'id_{pfx}-jours_1" checked' in html or f'id_{pfx}-jours_1"  checked' in html
        assert f'id_{pfx}-jours_3" checked' in html or f'id_{pfx}-jours_3"  checked' in html
        assert f'id_{pfx}-rythme_mensuel_1" checked' in html or f'id_{pfx}-rythme_mensuel_1"  checked' in html
        assert "07:15" in html
        assert "Deux semaines par mois" in html

    def test_page_config_se_rend_avec_section_cadence(self, logged_client, formation_avec_groupe):
        _, groupe = formation_avec_groupe
        resp = logged_client.get(reverse("groupes:config", kwargs={"groupe_pk": groupe.pk}))
        assert resp.status_code == 200
        html = resp.content.decode()
        assert "Cadence mensuelle du groupe" in html
        assert "Une semaine par mois" in html  # toutes les options dispo
        assert "Tout le mois" in html
        assert "hérite de la cadence de la formation" in html

    def test_post_config_sauvegarde_override_du_groupe(self, logged_client, formation_avec_groupe):
        formation, groupe = formation_avec_groupe
        pfx = f"g{groupe.pk}"
        resp = logged_client.post(
            reverse("groupes:config", kwargs={"groupe_pk": groupe.pk}),
            {
                f"{pfx}-matin_actif": "on",
                f"{pfx}-matin_heure_debut": "08:00",
                f"{pfx}-matin_heure_fin": "12:00",
                f"{pfx}-soir_heure_debut": "13:00",
                f"{pfx}-soir_heure_fin": "17:00",
                f"{pfx}-jours": ["0"],
                f"{pfx}-rythme_mensuel": ["1"],
            },
        )
        assert resp.status_code == 302
        groupe.refresh_from_db()
        assert groupe.rythme_mensuel == "1"

    def test_post_config_sans_case_revient_a_l_heritage(self, logged_client, formation_avec_groupe):
        formation, groupe = formation_avec_groupe
        groupe.rythme_mensuel = "1"  # override préalable
        groupe.save(update_fields=["rythme_mensuel"])
        pfx = f"g{groupe.pk}"
        resp = logged_client.post(
            reverse("groupes:config", kwargs={"groupe_pk": groupe.pk}),
            {
                f"{pfx}-matin_actif": "on",
                f"{pfx}-matin_heure_debut": "08:00",
                f"{pfx}-matin_heure_fin": "12:00",
                f"{pfx}-soir_heure_debut": "13:00",
                f"{pfx}-soir_heure_fin": "17:00",
                f"{pfx}-jours": ["0"],
                # aucun rythme_mensuel coché → héritage
            },
        )
        assert resp.status_code == 302
        groupe.refresh_from_db()
        assert groupe.rythme_mensuel == ""

    def test_post_config_refuse_plusieurs_cases(self, logged_client, formation_avec_groupe):
        formation, groupe = formation_avec_groupe
        pfx = f"g{groupe.pk}"
        resp = logged_client.post(
            reverse("groupes:config", kwargs={"groupe_pk": groupe.pk}),
            {
                f"{pfx}-matin_actif": "on",
                f"{pfx}-matin_heure_debut": "08:00",
                f"{pfx}-matin_heure_fin": "12:00",
                f"{pfx}-soir_heure_debut": "13:00",
                f"{pfx}-soir_heure_fin": "17:00",
                f"{pfx}-jours": ["0"],
                f"{pfx}-rythme_mensuel": ["1", "2"],
            },
        )
        assert resp.status_code == 200  # re-rendu du form avec erreur
        groupe.refresh_from_db()
        assert groupe.rythme_mensuel == ""  # rien n'a été enregistré
