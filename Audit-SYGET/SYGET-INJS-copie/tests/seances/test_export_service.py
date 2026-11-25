"""
Tests du format d'export Excel des séances (compatibilité import SYGEP).
"""

import datetime
from io import BytesIO

import pytest
from openpyxl import load_workbook

from apps.auditeurs.models import Auditeur
from apps.formations.models import FormationModule
from apps.groupes.models import Groupe, GroupeAuditeur
from apps.referentiels.models import Module
from apps.seances.models import Seance
from apps.seances.repositories import SeanceRepository
from apps.seances.excel_export import ExportSeancesService


def _date_cellule_excel(val, attendu: datetime.date) -> None:
    """openpyxl peut renvoyer ``date`` ou ``datetime`` selon le type de cellule."""
    assert val is not None
    if isinstance(val, datetime.datetime):
        assert val.date() == attendu
    else:
        assert val == attendu


@pytest.mark.django_db
def test_export_seances_format_import_attendu(formation, specialite_generale):
    groupe = Groupe.objects.create(formation=formation, nom="GROUPE 8", max_auditeurs=25)
    auditeur = Auditeur.objects.create(
        matricule="A4EXP001",
        nom="NOM",
        prenom="Prenom",
        grade="A4",
    )
    GroupeAuditeur.objects.create(groupe=groupe, auditeur=auditeur)

    module = Module.objects.create(titre="Culture Civique", specialite=specialite_generale)
    FormationModule.objects.create(
        formation=formation,
        module=module,
        volume_horaire=16,
        site_nom="CPFAE-AGC",
        batiment_nom="JEROME PATRICK ACHI",
        salle_nom="DISTRICT DE LA COMOE",
        date_debut=datetime.date(2026, 4, 25),
        date_fin=datetime.date(2026, 4, 26),
    )
    Seance.objects.create(
        groupe=groupe,
        module=module,
        date=datetime.date(2026, 4, 25),
        heure_debut=datetime.time(8, 0),
        heure_fin=datetime.time(12, 0),
        duree_minutes=240,
        salle_nom="S-01",
    )
    Seance.objects.create(
        groupe=groupe,
        module=module,
        date=datetime.date(2026, 4, 25),
        heure_debut=datetime.time(13, 0),
        heure_fin=datetime.time(17, 0),
        duree_minutes=240,
        salle_nom="S-01",
    )

    contenu = ExportSeancesService(SeanceRepository()).exporter(groupe.pk, format_export="cours")
    wb = load_workbook(BytesIO(contenu), data_only=True)
    assert wb.sheetnames == ["Formations"]

    ws_formations = wb["Formations"]
    formation_headers = [ws_formations.cell(1, c).value for c in range(1, ws_formations.max_column + 1)]
    assert formation_headers == [
        "N°",
        "Formation",
        "Module (titre)",
        "Site",
        "Bâtiment",
        "Salle",
        "Date début",
        "Date fin",
        "Volume horaire (h)",
        "Catégorie",
        "Grade",
        "Groupe",
        "Vague",
    ]
    assert ws_formations.cell(2, 1).value == 1
    assert ws_formations.cell(2, 3).value == "Culture Civique"
    assert ws_formations.cell(2, 4).value == "CPFAE-AGC"
    assert ws_formations.cell(2, 6).value == "S-01"
    assert ws_formations.cell(2, 9).value == 16
    assert ws_formations.cell(2, 11).value == "A4"


@pytest.mark.django_db
def test_export_seances_uniquement(formation, specialite_generale):
    groupe = Groupe.objects.create(formation=formation, nom="GROUPE 9", max_auditeurs=25)
    auditeur = Auditeur.objects.create(
        matricule="A4EXP002",
        nom="NOM2",
        prenom="Prenom2",
        grade="A4",
    )
    GroupeAuditeur.objects.create(groupe=groupe, auditeur=auditeur)
    module = Module.objects.create(titre="Protocole", specialite=specialite_generale)
    Seance.objects.create(
        groupe=groupe,
        module=module,
        date=datetime.date(2026, 5, 1),
        heure_debut=datetime.time(8, 0),
        heure_fin=datetime.time(12, 0),
        duree_minutes=240,
        salle_nom="S-02",
    )

    contenu = ExportSeancesService(SeanceRepository()).exporter(groupe.pk, format_export="seances")
    wb = load_workbook(BytesIO(contenu), data_only=True)
    assert wb.sheetnames == ["Séances"]
    ws_seances = wb["Séances"]
    headers = [ws_seances.cell(1, c).value for c in range(1, ws_seances.max_column + 1)]
    assert headers == [
        "Module (titre)",
        "date_journee",
        "N°",
        "intitule",
        "heure_debut",
        "heure_fin",
        "grade",
        "groupe",
    ]
    assert ws_seances.cell(2, 7).value == "A4"
    assert ws_seances.cell(2, 8).value == "A4_GROUPE9"


@pytest.mark.django_db
def test_export_formation_multi_groupes(formation, specialite_generale):
    groupe_a = Groupe.objects.create(formation=formation, nom="GROUPE A", max_auditeurs=25)
    groupe_b = Groupe.objects.create(formation=formation, nom="GROUPE B", max_auditeurs=25)
    module = Module.objects.create(titre="Droit", specialite=specialite_generale)
    FormationModule.objects.create(
        formation=formation,
        module=module,
        volume_horaire=8,
        date_debut=datetime.date(2026, 5, 3),
        date_fin=datetime.date(2026, 5, 3),
        site_nom="CPFAE-AGC",
        batiment_nom="JEROME PATRICK ACHI",
        salle_nom="DISTRICT DE LA COMOE",
    )
    Seance.objects.create(
        groupe=groupe_a,
        module=module,
        date=datetime.date(2026, 5, 3),
        heure_debut=datetime.time(8, 0),
        heure_fin=datetime.time(12, 0),
        duree_minutes=240,
        salle_nom="S-01",
    )
    Seance.objects.create(
        groupe=groupe_b,
        module=module,
        date=datetime.date(2026, 5, 3),
        heure_debut=datetime.time(13, 0),
        heure_fin=datetime.time(17, 0),
        duree_minutes=240,
        salle_nom="S-02",
    )

    contenu = ExportSeancesService(SeanceRepository()).exporter_par_formation(formation.pk, format_export="seances")
    wb = load_workbook(BytesIO(contenu), data_only=True)
    ws_seances = wb["Séances"]
    assert ws_seances.max_row == 3
    assert ws_seances.cell(2, 7).value in (None, "")
    assert ws_seances.cell(2, 8).value == "GROUPE A"
    assert ws_seances.cell(3, 7).value in (None, "")
    assert ws_seances.cell(3, 8).value == "GROUPE B"


@pytest.mark.django_db
def test_export_colonne_groupe_sans_grade_redondant(formation, specialite_generale):
    groupe = Groupe.objects.create(formation=formation, nom="Groupe 1 B3", max_auditeurs=25)
    auditeur = Auditeur.objects.create(
        matricule="B3EXP001",
        nom="NomB3",
        prenom="PrenomB3",
        grade="B3",
    )
    GroupeAuditeur.objects.create(groupe=groupe, auditeur=auditeur)
    module = Module.objects.create(titre="Procedure", specialite=specialite_generale)
    FormationModule.objects.create(
        formation=formation,
        module=module,
        volume_horaire=8,
        date_debut=datetime.date(2026, 5, 10),
        date_fin=datetime.date(2026, 5, 10),
        site_nom="SITE-B",
        batiment_nom="BAT-B",
        salle_nom="S-03",
    )
    Seance.objects.create(
        groupe=groupe,
        module=module,
        date=datetime.date(2026, 5, 10),
        heure_debut=datetime.time(8, 0),
        heure_fin=datetime.time(12, 0),
        duree_minutes=240,
        salle_nom="S-03",
    )

    contenu_seances = ExportSeancesService(SeanceRepository()).exporter(groupe.pk, format_export="seances")
    wb_seances = load_workbook(BytesIO(contenu_seances), data_only=True)
    ws_seances = wb_seances["Séances"]
    headers_seances = [ws_seances.cell(1, c).value for c in range(1, ws_seances.max_column + 1)]
    assert headers_seances == [
        "Module (titre)",
        "date_journee",
        "N°",
        "intitule",
        "heure_debut",
        "heure_fin",
        "grade",
        "groupe",
    ]
    assert ws_seances.cell(2, 7).value == "B3"
    assert ws_seances.cell(2, 8).value == "B3_GROUPE1"

    contenu_cours = ExportSeancesService(SeanceRepository()).exporter(groupe.pk, format_export="cours")
    wb_cours = load_workbook(BytesIO(contenu_cours), data_only=True)
    ws_formations = wb_cours["Formations"]
    assert ws_formations.cell(2, 11).value == "B3"
    assert ws_formations.cell(2, 12).value == "B3_GROUPE1"


@pytest.mark.django_db
def test_export_formateurs_contient_formateur_et_module(formation, specialite_generale):
    groupe = Groupe.objects.create(formation=formation, nom="GROUPE F", max_auditeurs=25)
    auditeur = Auditeur.objects.create(
        matricule="A3EXP901",
        nom="AUD",
        prenom="Un",
        grade="A3",
    )
    GroupeAuditeur.objects.create(groupe=groupe, auditeur=auditeur)
    module = Module.objects.create(titre="Module Formateur", specialite=specialite_generale)
    Seance.objects.create(
        groupe=groupe,
        module=module,
        formateur_nom="KOUAME Jean",
        formateur_prenom="Armand",
        formateur_numero="+2250102030405",
        formateur_email="kouame.jean@example.com",
        formateur_telephone="+2252721223344",
        formateur_organisation="CPFAE",
        date=datetime.date(2026, 5, 12),
        heure_debut=datetime.time(8, 0),
        heure_fin=datetime.time(12, 0),
        duree_minutes=240,
        salle_nom="S-10",
    )

    contenu = ExportSeancesService(SeanceRepository()).exporter(groupe.pk, format_export="formateurs")
    wb = load_workbook(BytesIO(contenu), data_only=True)
    assert wb.sheetnames == ["Formateurs"]
    ws_formateurs = wb["Formateurs"]
    headers = [ws_formateurs.cell(1, c).value for c in range(1, ws_formateurs.max_column + 1)]
    assert headers == [
        "Numéro",
        "Nom",
        "Prénom",
        "E-mail",
        "Téléphone",
        "Organisation",
        "Spécialité",
        "Grade",
        "Groupe",
        "Date",
        "module_titre",
    ]
    assert ws_formateurs.cell(2, 1).value == "+2250102030405"
    assert ws_formateurs.cell(2, 2).value == "KOUAME Jean"
    assert ws_formateurs.cell(2, 3).value == "Armand"
    assert ws_formateurs.cell(2, 4).value == "kouame.jean@example.com"
    assert ws_formateurs.cell(2, 5).value == "+2252721223344"
    assert ws_formateurs.cell(2, 6).value == "CPFAE"
    # Colonne 7 : Spécialité (vide ici, formateur non présent dans le référentiel Formateur).
    assert ws_formateurs.cell(2, 8).value == "A3"
    assert ws_formateurs.cell(2, 9).value == "GROUPE F"
    _date_cellule_excel(ws_formateurs.cell(2, 10).value, datetime.date(2026, 5, 12))
    assert ws_formateurs.cell(2, 11).value == "Module Formateur"


@pytest.mark.django_db
def test_export_formateurs_colonne_groupe_sans_grade_redondant(formation, specialite_generale):
    """Même logique que l'export « cours » : « Groupe 10 A3 » -> colonne Groupe « Groupe 10 », Grade « A3 »."""
    groupe = Groupe.objects.create(formation=formation, nom="Groupe 10 A3", max_auditeurs=25)
    auditeur = Auditeur.objects.create(
        matricule="A3EXP902",
        nom="X",
        prenom="Y",
        grade="A3",
    )
    GroupeAuditeur.objects.create(groupe=groupe, auditeur=auditeur)
    module = Module.objects.create(titre="Mod X", specialite=specialite_generale)
    Seance.objects.create(
        groupe=groupe,
        module=module,
        formateur_nom="FORM",
        formateur_prenom="Un",
        date=datetime.date(2026, 5, 20),
        heure_debut=datetime.time(8, 0),
        heure_fin=datetime.time(12, 0),
        duree_minutes=240,
        salle_nom="S-11",
    )

    contenu = ExportSeancesService(SeanceRepository()).exporter(groupe.pk, format_export="formateurs")
    wb = load_workbook(BytesIO(contenu), data_only=True)
    ws = wb["Formateurs"]
    assert ws.cell(2, 8).value == "A3"
    assert ws.cell(2, 9).value == "A3_GROUPE10"
    _date_cellule_excel(ws.cell(2, 10).value, datetime.date(2026, 5, 20))


@pytest.mark.django_db
def test_export_formateurs_lignes_triees_par_date_pas_par_module(formation, specialite_generale):
    """L’onglet Formateurs suit le calendrier : la date prime sur l’ordre alphabétique du module."""
    groupe = Groupe.objects.create(formation=formation, nom="G-TRI", max_auditeurs=25)
    auditeur = Auditeur.objects.create(
        matricule="A3EXP904",
        nom="Aud",
        prenom="Un",
        grade="A3",
    )
    GroupeAuditeur.objects.create(groupe=groupe, auditeur=auditeur)
    mod_tot = Module.objects.create(titre="ZZZ Tard en alpha", specialite=specialite_generale)
    mod_deb = Module.objects.create(titre="AAA Tôt en alpha", specialite=specialite_generale)
    for mod, jour in (
        (mod_tot, datetime.date(2026, 6, 1)),
        (mod_deb, datetime.date(2026, 6, 15)),
    ):
        Seance.objects.create(
            groupe=groupe,
            module=mod,
            formateur_nom="DUPONT",
            formateur_prenom="Marie",
            formateur_numero="+2250111222333",
            date=jour,
            heure_debut=datetime.time(8, 0),
            heure_fin=datetime.time(12, 0),
            duree_minutes=240,
            salle_nom="S-01",
        )

    contenu = ExportSeancesService(SeanceRepository()).exporter(groupe.pk, format_export="formateurs")
    wb = load_workbook(BytesIO(contenu), data_only=True)
    ws = wb["Formateurs"]
    assert ws.max_row == 3
    assert ws.cell(2, 11).value == "ZZZ Tard en alpha"
    _date_cellule_excel(ws.cell(2, 10).value, datetime.date(2026, 6, 1))
    assert ws.cell(3, 11).value == "AAA Tôt en alpha"
    _date_cellule_excel(ws.cell(3, 10).value, datetime.date(2026, 6, 15))


@pytest.mark.django_db
def test_export_formateurs_remplit_depuis_affectation_si_seance_sans_nom(formation, specialite_generale):
    """Sans nom sur la séance, l'export reprend le formateur depuis AffectationFormateurGroupe."""
    from apps.formations.models import AffectationFormateurGroupe, Formateur, FormationModule

    groupe = Groupe.objects.create(formation=formation, nom="G-AFF", max_auditeurs=25)
    auditeur = Auditeur.objects.create(
        matricule="A3EXP903",
        nom="Z",
        prenom="W",
        grade="A3",
    )
    GroupeAuditeur.objects.create(groupe=groupe, auditeur=auditeur)
    module = Module.objects.create(titre="Mod Aff Export", specialite=specialite_generale)
    FormationModule.objects.create(
        formation=formation,
        module=module,
        volume_horaire=4,
        site_nom="SITE",
        date_debut=datetime.date(2026, 5, 1),
        date_fin=datetime.date(2026, 5, 2),
    )
    f = Formateur.objects.create(
        numero="+2250999111001",
        nom="AFFO",
        prenom="Export",
        email="e@t.ci",
        telephone="",
        organisation="ORG",
    )
    f.specialites.add(specialite_generale)
    AffectationFormateurGroupe.objects.create(groupe=groupe, module=module, formateur=f)
    Seance.objects.create(
        groupe=groupe,
        module=module,
        date=datetime.date(2026, 5, 1),
        heure_debut=datetime.time(8, 0),
        heure_fin=datetime.time(12, 0),
        duree_minutes=240,
        salle_nom="S-01",
    )

    contenu = ExportSeancesService(SeanceRepository()).exporter(groupe.pk, format_export="formateurs")
    wb = load_workbook(BytesIO(contenu), data_only=True)
    ws = wb["Formateurs"]
    assert ws.max_row >= 2
    assert ws.cell(2, 1).value == "+2250999111001"
    assert ws.cell(2, 2).value == "AFFO"
    _date_cellule_excel(ws.cell(2, 10).value, datetime.date(2026, 5, 1))
    assert ws.cell(2, 11).value == "Mod Aff Export"


@pytest.mark.django_db
def test_export_formateurs_formation_sans_seance_mais_avec_affectation(formation, specialite_generale):
    """Export formation : aucune séance mais affectations groupe/module → lignes formateurs."""
    from apps.formations.models import AffectationFormateurGroupe, Formateur, FormationModule
    from tests.conftest import configurer_periode_principale

    configurer_periode_principale(
        formation,
        date_debut=datetime.date(2026, 6, 1),
        date_fin=datetime.date(2026, 6, 2),
    )
    groupe = Groupe.objects.create(formation=formation, nom="G vide", max_auditeurs=25)
    module = Module.objects.create(titre="Mod seul aff", specialite=specialite_generale)
    FormationModule.objects.create(
        formation=formation,
        module=module,
        volume_horaire=4,
        site_nom="SITE",
    )
    f = Formateur.objects.create(
        numero="+2250999111002",
        nom="SEUL",
        prenom="Aff",
        email="s@t.ci",
        telephone="",
        organisation="O",
    )
    f.specialites.add(specialite_generale)
    AffectationFormateurGroupe.objects.create(groupe=groupe, module=module, formateur=f)

    contenu = ExportSeancesService(SeanceRepository()).exporter_par_formation(formation.pk, format_export="formateurs")
    wb = load_workbook(BytesIO(contenu), data_only=True)
    ws = wb["Formateurs"]
    assert ws.max_row == 2
    assert ws.cell(2, 2).value == "SEUL"
    _date_cellule_excel(ws.cell(2, 10).value, datetime.date(2026, 6, 1))
    assert ws.cell(2, 11).value == "Mod seul aff"


@pytest.mark.django_db
def test_export_formateurs_date_depuis_seance_si_module_formation_sans_dates(formation, specialite_generale):
    """Affectation seule : FM sans date_debut/date_fin → on reprend la date la plus tôt des séances du module."""
    from apps.formations.models import AffectationFormateurGroupe, Formateur, FormationModule

    groupe = Groupe.objects.create(formation=formation, nom="G-FM vides", max_auditeurs=25)
    module = Module.objects.create(titre="Mod sans dates FM", specialite=specialite_generale)
    FormationModule.objects.create(
        formation=formation,
        module=module,
        volume_horaire=4,
        site_nom="SITE",
        date_debut=None,
        date_fin=None,
    )
    f = Formateur.objects.create(
        numero="+2250999111003",
        nom="SANS",
        prenom="DatesFM",
        email="x@t.ci",
        telephone="",
        organisation="O",
    )
    f.specialites.add(specialite_generale)
    AffectationFormateurGroupe.objects.create(groupe=groupe, module=module, formateur=f)
    Seance.objects.create(
        groupe=groupe,
        module=module,
        date=datetime.date(2026, 8, 15),
        heure_debut=datetime.time(9, 0),
        heure_fin=datetime.time(11, 0),
        duree_minutes=120,
        salle_nom="S-X",
    )

    contenu = ExportSeancesService(SeanceRepository()).exporter(groupe.pk, format_export="formateurs")
    wb = load_workbook(BytesIO(contenu), data_only=True)
    ws = wb["Formateurs"]
    assert ws.max_row == 2
    assert ws.cell(2, 2).value == "SANS"
    _date_cellule_excel(ws.cell(2, 10).value, datetime.date(2026, 8, 15))
    assert ws.cell(2, 11).value == "Mod sans dates FM"


@pytest.mark.django_db
def test_export_formateurs_date_depuis_formation_si_fm_vide_et_aucune_seance(formation, specialite_generale):
    """Export formation sans séance : FM sans dates → date de début de la formation."""
    from apps.formations.models import AffectationFormateurGroupe, Formateur, FormationModule

    groupe = Groupe.objects.create(formation=formation, nom="G-ISO", max_auditeurs=25)
    module = Module.objects.create(titre="Mod iso date form", specialite=specialite_generale)
    FormationModule.objects.create(
        formation=formation,
        module=module,
        volume_horaire=4,
        site_nom="SITE",
        date_debut=None,
        date_fin=None,
    )
    f = Formateur.objects.create(
        numero="+2250999111004",
        nom="ISO",
        prenom="Date",
        email="iso@t.ci",
        telephone="",
        organisation="O",
    )
    f.specialites.add(specialite_generale)
    AffectationFormateurGroupe.objects.create(groupe=groupe, module=module, formateur=f)

    contenu = ExportSeancesService(SeanceRepository()).exporter_par_formation(formation.pk, format_export="formateurs")
    wb = load_workbook(BytesIO(contenu), data_only=True)
    ws = wb["Formateurs"]
    assert ws.max_row == 2
    _date_cellule_excel(ws.cell(2, 10).value, datetime.date(2025, 1, 6))


@pytest.mark.django_db
def test_export_cours_volume_horaire_fm_malgre_dispatch_refuse_pour_grade(formation, specialite_generale):
    """Volume saisi sur le programme : visible à l'export même si ``pour_dispatch`` renverrait None."""
    from apps.parametrage.models import ModuleTypeFormation

    groupe = Groupe.objects.create(formation=formation, nom="G-VOL-EXP", max_auditeurs=25)
    auditeur = Auditeur.objects.create(
        matricule="A4EXPVOL",
        nom="N",
        prenom="P",
        grade="A4",
    )
    GroupeAuditeur.objects.create(groupe=groupe, auditeur=auditeur)
    module = Module.objects.create(titre="Module Vol Export Unique", specialite=specialite_generale)

    ModuleTypeFormation.objects.filter(
        module_id=module.pk,
        type_formation_id=formation.type_formation_id,
    ).delete()
    ModuleTypeFormation.objects.create(
        module=module,
        type_formation=formation.type_formation,
        grade_cible="B3",
        volume_horaire_defaut=99,
    )

    FormationModule.objects.create(
        formation=formation,
        module=module,
        volume_horaire=14,
        site_nom="SITE",
        batiment_nom="BAT",
        salle_nom="SALLEREF",
        date_debut=datetime.date(2026, 6, 1),
        date_fin=datetime.date(2026, 6, 2),
    )
    Seance.objects.create(
        groupe=groupe,
        module=module,
        date=datetime.date(2026, 6, 1),
        heure_debut=datetime.time(8, 0),
        heure_fin=datetime.time(12, 0),
        duree_minutes=240,
        salle_nom="S-X",
    )

    contenu = ExportSeancesService(SeanceRepository()).exporter(groupe.pk, format_export="cours")
    wb = load_workbook(BytesIO(contenu), data_only=True)
    ws = wb["Formations"]
    assert ws.cell(2, 9).value == 14


@pytest.mark.django_db
def test_export_cours_salle_depuis_seances_si_formation_module_sans_salle(formation, specialite_generale):
    """L'export « cours » doit reprendre la salle des séances si le programme n'a pas salle_nom."""
    groupe = Groupe.objects.create(formation=formation, nom="G-SALLE", max_auditeurs=25)
    module = Module.objects.create(titre="Module Salle Seance", specialite=specialite_generale)
    FormationModule.objects.create(
        formation=formation,
        module=module,
        volume_horaire=4,
        site_nom="Site-Ref",
        batiment_nom="",
        salle_nom="",
        date_debut=datetime.date(2026, 6, 1),
        date_fin=datetime.date(2026, 6, 1),
    )
    Seance.objects.create(
        groupe=groupe,
        module=module,
        site_nom="Site-Ref",
        batiment_nom="Bat-1",
        salle_nom="Amphi Nord",
        date=datetime.date(2026, 6, 1),
        heure_debut=datetime.time(8, 0),
        heure_fin=datetime.time(12, 0),
        duree_minutes=240,
    )

    contenu = ExportSeancesService(SeanceRepository()).exporter(groupe.pk, format_export="cours")
    wb = load_workbook(BytesIO(contenu), data_only=True)
    ws = wb["Formations"]
    assert ws.cell(2, 4).value == "Site-Ref"
    assert ws.cell(2, 5).value == "Bat-1"
    assert ws.cell(2, 6).value == "Amphi Nord"
