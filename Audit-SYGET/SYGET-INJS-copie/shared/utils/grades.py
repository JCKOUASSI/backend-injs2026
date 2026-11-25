"""
Utilitaires de normalisation et de matching des grades cibles.
"""

from __future__ import annotations

from collections import OrderedDict

ALL_GRADES_TOKENS = {"*", "ALL", "TOUS", "TOUS_GRADES", "__ALL__"}


def split_grade_cibles(raw_value: str) -> list[str]:
    """
    Découpe et normalise une valeur de grades cibles (CSV/;/|) en liste unique.
    """
    value = (raw_value or "").strip().upper()
    if not value:
        return []
    tokens = value.replace(";", ",").replace("|", ",").split(",")
    cleaned = [token.strip() for token in tokens if token.strip()]
    # Conserve l'ordre d'apparition tout en supprimant les doublons.
    return list(OrderedDict.fromkeys(cleaned))


def encode_grade_cibles(selected_grades: list[str] | str | None) -> str:
    """
    Encode les grades cibles pour stockage.
    Retourne chaîne vide pour "tous les grades".
    """
    if selected_grades is None:
        return ""
    if isinstance(selected_grades, str):
        tokens = split_grade_cibles(selected_grades)
    else:
        tokens: list[str] = []
        for grade in selected_grades:
            tokens.extend(split_grade_cibles(grade))

    if not tokens:
        return ""
    if any(token in ALL_GRADES_TOKENS for token in tokens):
        return ""
    return ", ".join(tokens)


def deduire_categorie(categorie: str, grade: str) -> str:
    """
    Retourne la catégorie normalisée.
    Si absente, déduit la lettre depuis le grade (ex. A3 → A, B2 → B), comme SYGEP.
    """
    cat = (categorie or "").strip().upper()
    if cat:
        return cat
    grade_norm = (grade or "").strip().upper()
    if grade_norm and grade_norm[0] in ("A", "B", "C"):
        return grade_norm[0]
    return ""


def grade_cible_matches(grade_cible: str, grade_value: str) -> bool:
    """
    Vérifie si une règle grade_cible couvre un grade donné.

    - règle vide => tous les grades
    - règle multiple (CSV) => au moins une règle doit matcher
    - règle parent (ex: B) couvre B3/B4
    """
    tokens = split_grade_cibles(grade_cible)
    if not tokens:
        return True
    if any(token in ALL_GRADES_TOKENS for token in tokens):
        return True

    grade = (grade_value or "").strip().upper()
    if not grade:
        return False

    for token in tokens:
        if grade == token or grade.startswith(token):
            return True
    return False
