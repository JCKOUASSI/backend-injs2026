"""Tests de la régénération du planning formation (sans toucher aux groupes)."""

import datetime

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from apps.formations.models import FormationModule, Inscription
from apps.groupes.models import ConfigGroupe, Groupe, GroupeAuditeur, JourCours
from apps.parametrage.models import Batiment, Salle, Site
from apps.seances.models import Seance


@pytest.fixture
def logged_client(db):
    User.objects.create_superuser("planuser", "plan@example.com", "testpass123")
    client = Client()
    client.login(username="planuser", password="testpass123")
    return client


def _prepare_planning(formation, parametres, groupe):
    parametres.jours_defaut = [0, 1, 2, 3, 4]
    parametres.save(update_fields=["jours_defaut"])
    site = Site.objects.create(nom=f"SITE-{formation.pk}", actif=True)
    bat = Batiment.objects.create(site=site, nom=f"BAT-{formation.pk}", actif=True)
    Salle.objects.create(
        batiment=bat,
        nom=f"SALLE-{formation.pk}",
        capacite_max=40,
        actif=True,
    )
    JourCours.objects.create(groupe=groupe, jour=0)


@pytest.mark.django_db
class TestRegenererPlanningFormationView:
    def test_liste_affiche_bouton_si_groupes(
        self, logged_client, formation, auditeur, module_referentiel, parametres, formateur_general_planning
    ):
        fm = FormationModule.objects.create(
            formation=formation,
            module=module_referentiel,
            volume_horaire=8,
            site_nom=f"SITE-{formation.pk}",
        )
        Inscription.objects.create(formation=formation, formation_module=fm, auditeur=auditeur)
        groupe = Groupe.objects.create(formation=formation, nom="G-PLAN", max_auditeurs=25)
        GroupeAuditeur.objects.create(groupe=groupe, auditeur=auditeur)
        ConfigGroupe.objects.create(groupe=groupe)
        _prepare_planning(formation, parametres, groupe)

        resp = logged_client.get(reverse("groupes:list", kwargs={"formation_pk": formation.pk}))
        assert resp.status_code == 200
        assert "Regénérer le planning" in resp.content.decode()

    def test_post_regenere_seances_sans_changer_membres(
        self,
        logged_client,
        formation,
        auditeur,
        module_referentiel,
        parametres,
        formateur_general_planning,
    ):
        fm = FormationModule.objects.create(
            formation=formation,
            module=module_referentiel,
            volume_horaire=8,
            site_nom=f"SITE-{formation.pk}",
            date_debut=formation.date_debut,
            date_fin=formation.date_fin,
        )
        Inscription.objects.create(formation=formation, formation_module=fm, auditeur=auditeur)
        groupe = Groupe.objects.create(formation=formation, nom="G-PLAN", max_auditeurs=25)
        GroupeAuditeur.objects.create(groupe=groupe, auditeur=auditeur)
        ConfigGroupe.objects.create(
            groupe=groupe,
            matin_actif=True,
            matin_heure_debut=datetime.time(8, 0),
            matin_heure_fin=datetime.time(12, 0),
            soir_actif=False,
            soir_heure_debut=datetime.time(13, 0),
            soir_heure_fin=datetime.time(17, 0),
        )
        _prepare_planning(formation, parametres, groupe)

        url = reverse("groupes:regenerer_planning", kwargs={"formation_pk": formation.pk})
        resp = logged_client.post(url)
        assert resp.status_code == 302
        assert Seance.objects.filter(groupe=groupe).exists()
        assert GroupeAuditeur.objects.filter(groupe=groupe, auditeur=auditeur).exists()

        # Nouvelle période : les membres restent, le planning peut être recalculé.
        formation.date_debut = formation.date_debut.replace(year=formation.date_debut.year + 1)
        formation.date_fin = formation.date_fin.replace(year=formation.date_fin.year + 1)
        formation.save()
        fm.date_debut = formation.date_debut
        fm.date_fin = formation.date_fin
        fm.save()
        Seance.objects.filter(groupe=groupe).delete()

        resp2 = logged_client.post(url)
        assert resp2.status_code == 302
        assert GroupeAuditeur.objects.filter(groupe=groupe, auditeur=auditeur).count() == 1
        assert Seance.objects.filter(groupe=groupe).exists()

    def test_post_sans_groupes_avertit(self, logged_client, formation):
        url = reverse("groupes:regenerer_planning", kwargs={"formation_pk": formation.pk})
        resp = logged_client.post(url)
        assert resp.status_code == 302
        follow = logged_client.get(reverse("groupes:list", kwargs={"formation_pk": formation.pk}))
        assert "Aucun groupe" in follow.content.decode()
