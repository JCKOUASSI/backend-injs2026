"""Tests des modules planning extraits et salle_id."""

from __future__ import annotations

import datetime

import pytest
from django.contrib.auth.models import User

from apps.formations.models import Formation, FormationModule
from apps.groupes.models import ConfigGroupe, Groupe, JourCours
from apps.parametrage.models import Batiment, ParametreGeneral, Salle, Site
from apps.referentiels.models import Module, Specialite
from apps.seances.models import Seance
from apps.seances.planning import occupations as planning_occupations
from apps.seances.repositories import SeanceRepository
from apps.seances.services import PlanningService


@pytest.fixture
def site_salle(db):
    site = Site.objects.create(nom="SITE-A", actif=True)
    bat = Batiment.objects.create(site=site, nom="BAT-A", actif=True)
    salle = Salle.objects.create(batiment=bat, nom="SALLE-A", capacite_max=30, actif=True)
    return site, bat, salle


@pytest.mark.django_db
class TestOccupationDetailsSalles:
    def test_masque_noms_formations_pour_gestionnaire(self, site_salle, type_formation):
        site, bat, salle = site_salle
        spec = Specialite.objects.create(code="ECO-MASQ", libelle="Economie masq")
        mod = Module.objects.create(titre="Module test masq", specialite=spec, actif=True)
        user = User.objects.create_user("gest-masq", password="x")
        f1 = Formation.objects.create(
            type_formation=type_formation,
            intitule="Formation visible",
            date_debut=datetime.date(2026, 1, 1),
            date_fin=datetime.date(2026, 6, 30),
            responsable=user,
        )
        f2 = Formation.objects.create(
            type_formation=type_formation,
            intitule="Formation secrète collègue",
            date_debut=datetime.date(2026, 1, 1),
            date_fin=datetime.date(2026, 6, 30),
        )
        g1 = Groupe.objects.create(formation=f1, nom="G1", max_auditeurs=20)
        g2 = Groupe.objects.create(formation=f2, nom="G2", max_auditeurs=20)
        Seance.objects.create(
            groupe=g2,
            module=mod,
            date=datetime.date(2026, 3, 10),
            heure_debut=datetime.time(8, 0),
            heure_fin=datetime.time(12, 0),
            duree_minutes=240,
            site_nom=site.nom,
            batiment_nom=bat.nom,
            salle_nom=salle.nom,
            salle_id=salle.pk,
        )
        details = planning_occupations.occupation_details_salles(
            [salle.nom],
            datetime.date(2026, 3, 1),
            datetime.date(2026, 3, 31),
            g1.pk,
            masquer_noms_formations=True,
        )
        assert "une autre formation" in details
        assert "Formation secrète collègue" not in details

        details_admin = planning_occupations.occupation_details_salles(
            [salle.nom],
            datetime.date(2026, 3, 1),
            datetime.date(2026, 3, 31),
            g1.pk,
            masquer_noms_formations=False,
        )
        assert "Formation secrète collègue" in details_admin


@pytest.mark.django_db
class TestSalleIdCollisions:
    def test_collision_par_salle_id_malgre_renom_affiche(self, site_salle, type_formation_fab):
        _site, _bat, salle = site_salle
        spec = Specialite.objects.create(code="DRO-COLL", libelle="Droit coll")
        mod = Module.objects.create(titre="Mod coll", specialite=spec, actif=True)
        formation = Formation.objects.create(
            type_formation=type_formation_fab,
            intitule="F coll",
            date_debut=datetime.date(2026, 1, 1),
            date_fin=datetime.date(2026, 12, 31),
        )
        g1 = Groupe.objects.create(formation=formation, nom="G1", max_auditeurs=20)
        g2 = Groupe.objects.create(formation=formation, nom="G2", max_auditeurs=20)
        Seance.objects.create(
            groupe=g1,
            module=mod,
            date=datetime.date(2026, 4, 1),
            heure_debut=datetime.time(8, 0),
            heure_fin=datetime.time(12, 0),
            duree_minutes=240,
            salle_nom="ANCIEN NOM",
            salle_id=salle.pk,
        )
        occ = planning_occupations.charger_occupations_existantes(g2.pk)
        key_id = (datetime.date(2026, 4, 1), f"#{salle.pk}")
        assert key_id in occ
        assert not planning_occupations.salle_disponible(
            occ,
            datetime.date(2026, 4, 1),
            salle.nom,
            datetime.time(9, 0),
            datetime.time(11, 0),
            salle_id=salle.pk,
        )


@pytest.mark.django_db
class TestPlanningServiceDelegation:
    def test_charger_localisations_retourne_ids(self, site_salle):
        _site, _bat, salle = site_salle
        mapping, ids = PlanningService._charger_localisations_salles()
        assert mapping[salle.nom.upper()][2] == 30
        assert ids[salle.nom.upper()] == salle.pk

    def test_generer_remplit_salle_id(self, site_salle, type_formation):
        site, bat, salle = site_salle
        ParametreGeneral.get()
        spec = Specialite.objects.create(code="COM-SID", libelle="Compta sid")
        mod = Module.objects.create(titre="Compta init sid", specialite=spec, actif=True)
        formation = Formation.objects.create(
            type_formation=type_formation,
            intitule="Test salle_id",
            date_debut=datetime.date(2026, 5, 1),
            date_fin=datetime.date(2026, 5, 31),
        )
        FormationModule.objects.create(
            formation=formation,
            module=mod,
            site_nom=site.nom,
            volume_horaire=4,
            date_debut=datetime.date(2026, 5, 1),
            date_fin=datetime.date(2026, 5, 31),
        )
        groupe = Groupe.objects.create(formation=formation, nom="G-test", max_auditeurs=10)
        ConfigGroupe.objects.create(
            groupe=groupe,
            matin_actif=True,
            matin_heure_debut=datetime.time(8, 0),
            matin_heure_fin=datetime.time(12, 0),
            soir_actif=False,
        )
        JourCours.objects.create(groupe=groupe, jour=0)
        seances = PlanningService(SeanceRepository()).generer_pour_groupe(groupe.pk)
        assert seances
        assert all(s.salle_id == salle.pk for s in seances if s.salle_nom)
