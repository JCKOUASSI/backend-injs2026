"""Tests des conventions de nommage groupes / exports EMP."""

from shared.utils.groupes import (
    cle_tri_groupes,
    libelle_groupe_export,
    nom_fichier_emploi_du_temps,
    nom_groupe_standard,
    normaliser_nom_groupe_vers_canonique,
    numero_groupe,
)


def test_nom_groupe_standard():
    assert nom_groupe_standard("A4", 1) == "A4_GROUPE1"
    assert nom_groupe_standard("A3", 2) == "A3_GROUPE2"


def test_nom_fichier_emploi_du_temps():
    assert nom_fichier_emploi_du_temps(nom_groupe="A4_GROUPE1", grade="A4", extension="pdf") == "A4_EMP_GROUPE1.pdf"
    assert (
        nom_fichier_emploi_du_temps(nom_groupe="A4_GROUPE1", grade="A4", extension="xlsx", variante="seances")
        == "A4_EMP_GROUPE1_seances.xlsx"
    )


def test_normaliser_ancien_format():
    assert normaliser_nom_groupe_vers_canonique("Groupe 1 A3") == "A3_GROUPE1"
    assert nom_fichier_emploi_du_temps(nom_groupe="Groupe 1 A3", grade="A3", extension="pdf") == "A3_EMP_GROUPE1.pdf"


def test_numero_groupe_et_tri():
    assert numero_groupe("Groupe 10 A3") == 10
    assert numero_groupe("Groupe 1 A3") == 1
    assert numero_groupe("A4_GROUPE2") == 2
    noms = ["Groupe 10 A3", "Groupe 2 A3", "Groupe 1 A4", "Groupe 1 A3"]
    assert sorted(noms, key=cle_tri_groupes) == [
        "Groupe 1 A3",
        "Groupe 1 A4",
        "Groupe 2 A3",
        "Groupe 10 A3",
    ]


def test_libelle_export_canonique():
    assert libelle_groupe_export("A4_GROUPE1", "A4") == "A4_GROUPE1"
    assert libelle_groupe_export("Groupe 1 A3", "A3") == "A3_GROUPE1"
