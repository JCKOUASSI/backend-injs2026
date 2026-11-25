"""Tests du module planning.trainer_allocator."""

from __future__ import annotations

import datetime

import pytest

from apps.seances.planning import trainer_allocator as ta


def test_formateur_key_priorise_nom():
    key = ta.formateur_key({"nom": "Dupont", "prenom": "Jean", "numero": "001"})
    assert key == "NOM:DUPONT|PRENOM:JEAN"


def test_formateur_key_numero_si_pas_nom():
    key = ta.formateur_key({"nom": "", "prenom": "", "numero": "F42"})
    assert key == "NUM:F42"


def test_formateur_pk_from_dict():
    assert ta.formateur_pk_from_dict({"formateur_id": "7"}) == 7
    assert ta.formateur_pk_from_dict({"formateur_id": ""}) is None


def test_formateur_disponible_quota():
    occ: ta.FormateurOccupationIndex = {}
    f = {"nom": "A", "prenom": "B", "formateur_id": "1"}
    ta.reserver_formateur(occ, datetime.date(2026, 1, 1), f)
    assert not ta.formateur_disponible(occ, datetime.date(2026, 1, 1), f, max_seances_jour=1)
    assert ta.formateur_disponible(occ, datetime.date(2026, 1, 1), f, max_seances_jour=2)


@pytest.fixture
def site_salle_tr(db):
    from apps.parametrage.models import Batiment, Salle, Site

    site = Site.objects.create(nom="SITE-TR", actif=True)
    bat = Batiment.objects.create(site=site, nom="BAT-TR", actif=True)
    salle = Salle.objects.create(batiment=bat, nom="SALLE-TR", capacite_max=30, actif=True)
    return site, bat, salle


@pytest.mark.django_db
def test_charger_occupations_formateur_par_id(site_salle_tr, type_formation, specialite_generale):
    from apps.formations.models import Formateur, Formation
    from apps.groupes.models import Groupe
    from apps.referentiels.models import Module
    from apps.seances.models import Seance

    site, bat, salle = site_salle_tr
    spec = specialite_generale
    mod = Module.objects.create(titre="M-TR", specialite=spec, actif=True)
    formateur = Formateur.objects.create(
        numero="+TR001",
        nom="Test",
        prenom="Form",
        email="tr@test.ci",
        organisation="TST",
    )
    formateur.specialites.add(spec)
    formation = Formation.objects.create(
        type_formation=type_formation,
        intitule="F",
        date_debut=datetime.date(2026, 1, 1),
        date_fin=datetime.date(2026, 12, 31),
    )
    g1 = Groupe.objects.create(formation=formation, nom="G1", max_auditeurs=20)
    g2 = Groupe.objects.create(formation=formation, nom="G2", max_auditeurs=20)
    Seance.objects.create(
        groupe=g1,
        module=mod,
        date=datetime.date(2026, 6, 1),
        heure_debut=datetime.time(8, 0),
        heure_fin=datetime.time(12, 0),
        duree_minutes=240,
        formateur_nom="ANCIEN",
        formateur_referentiel=formateur,
    )
    occ = ta.charger_occupations_formateurs_existantes(g2.pk)
    assert (datetime.date(2026, 6, 1), f"#{formateur.pk}") in occ
