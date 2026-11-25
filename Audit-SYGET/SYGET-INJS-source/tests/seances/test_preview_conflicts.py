"""
Tests de détection de conflits sur la page preview des séances.
"""

import datetime

import pytest

from apps.auditeurs.models import Auditeur
from apps.groupes.models import ConfigGroupe, Groupe, GroupeAuditeur
from apps.parametrage.models import Batiment, JourFerie, Salle, Site
from apps.referentiels.models import Module
from apps.seances.models import Seance
from apps.seances.conflicts import detecter_conflits_planning


def _setup_groupe(formation) -> Groupe:
    groupe = Groupe.objects.create(formation=formation, nom="GRP-CHECK", max_auditeurs=30)
    ConfigGroupe.objects.create(
        groupe=groupe,
        matin_actif=True,
        matin_heure_debut=datetime.time(8, 0),
        matin_heure_fin=datetime.time(12, 0),
        soir_actif=True,
        soir_heure_debut=datetime.time(13, 0),
        soir_heure_fin=datetime.time(17, 0),
    )
    return groupe


@pytest.mark.django_db
def test_detecte_jour_ferie(formation, specialite_generale):
    groupe = _setup_groupe(formation)
    module = Module.objects.create(titre="Module JF", specialite=specialite_generale)
    date_jf = datetime.date(2025, 1, 6)
    JourFerie.objects.create(date=date_jf, libelle="Fête", actif=True)
    seance = Seance.objects.create(
        groupe=groupe,
        module=module,
        date=date_jf,
        heure_debut=datetime.time(8, 0),
        heure_fin=datetime.time(12, 0),
        duree_minutes=240,
        salle_nom="SALLE-X",
    )

    conflits = detecter_conflits_planning(groupe, [seance])
    assert any(c.type == "JOUR_FERIE" for c in conflits)


@pytest.mark.django_db
def test_detecte_capacite_salle_insuffisante(formation, specialite_generale):
    groupe = _setup_groupe(formation)
    module = Module.objects.create(titre="Module CAP", specialite=specialite_generale)
    site = Site.objects.create(nom="SITE-CAP")
    bat = Batiment.objects.create(site=site, nom="BAT-CAP")
    Salle.objects.create(batiment=bat, nom="SALLE-CAP", capacite_max=1, actif=True)

    a1 = Auditeur.objects.create(matricule="A1001", nom="N1", prenom="P1")
    a2 = Auditeur.objects.create(matricule="A1002", nom="N2", prenom="P2")
    GroupeAuditeur.objects.create(groupe=groupe, auditeur=a1)
    GroupeAuditeur.objects.create(groupe=groupe, auditeur=a2)

    seance = Seance.objects.create(
        groupe=groupe,
        module=module,
        date=datetime.date(2025, 1, 7),
        heure_debut=datetime.time(8, 0),
        heure_fin=datetime.time(12, 0),
        duree_minutes=240,
        salle_nom="SALLE-CAP",
    )

    conflits = detecter_conflits_planning(groupe, [seance])
    assert any(c.type == "CAPACITE_SALLE" for c in conflits)


@pytest.mark.django_db
def test_detecte_site_hors_periode_disponibilite(formation, specialite_generale):
    from apps.parametrage.models import PeriodeDisponibiliteSite

    groupe = _setup_groupe(formation)
    module = Module.objects.create(titre="Module SITE", specialite=specialite_generale)
    site = Site.objects.create(nom="SITE-PREV", actif=True)
    PeriodeDisponibiliteSite.objects.create(
        site=site,
        date_debut=datetime.date(2025, 3, 1),
        date_fin=datetime.date(2025, 3, 31),
    )
    seance = Seance.objects.create(
        groupe=groupe,
        module=module,
        date=datetime.date(2025, 1, 7),
        heure_debut=datetime.time(8, 0),
        heure_fin=datetime.time(12, 0),
        duree_minutes=240,
        site_nom="SITE-PREV",
        salle_nom="SALLE-X",
    )

    conflits = detecter_conflits_planning(groupe, [seance])
    assert any(c.type == "SITE_INDISPONIBLE" for c in conflits)


@pytest.mark.django_db
def test_detecte_plusieurs_modules_meme_jour(formation, specialite_generale):
    groupe = _setup_groupe(formation)
    m1 = Module.objects.create(titre="Module A", specialite=specialite_generale)
    m2 = Module.objects.create(titre="Module B", specialite=specialite_generale)
    date = datetime.date(2025, 1, 9)

    s1 = Seance.objects.create(
        groupe=groupe,
        module=m1,
        date=date,
        heure_debut=datetime.time(8, 0),
        heure_fin=datetime.time(12, 0),
        duree_minutes=240,
        salle_nom="S-A",
    )
    s2 = Seance.objects.create(
        groupe=groupe,
        module=m2,
        date=date,
        heure_debut=datetime.time(13, 0),
        heure_fin=datetime.time(17, 0),
        duree_minutes=240,
        salle_nom="S-B",
    )

    conflits = detecter_conflits_planning(groupe, [s1, s2])
    assert sum(1 for c in conflits if c.type == "MODULE_PAR_JOUR") == 2


@pytest.mark.django_db
def test_detecte_depassement_max_seances_par_jour(formation, parametres, specialite_generale):
    parametres.max_seances_par_jour_defaut = 1
    parametres.save(update_fields=["max_seances_par_jour_defaut"])
    groupe = _setup_groupe(formation)
    module = Module.objects.create(titre="Module MAX", specialite=specialite_generale)
    date = datetime.date(2025, 1, 8)

    s1 = Seance.objects.create(
        groupe=groupe,
        module=module,
        date=date,
        heure_debut=datetime.time(8, 0),
        heure_fin=datetime.time(10, 0),
        duree_minutes=120,
        salle_nom="S-1",
    )
    s2 = Seance.objects.create(
        groupe=groupe,
        module=module,
        date=date,
        heure_debut=datetime.time(10, 0),
        heure_fin=datetime.time(12, 0),
        duree_minutes=120,
        salle_nom="S-1",
    )

    conflits = detecter_conflits_planning(groupe, [s1, s2])
    assert sum(1 for c in conflits if c.type == "MAX_SEANCES_JOUR") == 1
