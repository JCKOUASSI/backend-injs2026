"""Utilitaires liés aux libellés et noms de groupes."""

from __future__ import annotations

import re
from collections import Counter

_CANONIQUE_RE = re.compile(r"^([A-Z0-9]+)_GROUPE(\d+)$", re.IGNORECASE)
_LEGACY_AVEC_GRADE_RE = re.compile(r"^Groupe\s*(\d+)\s*([A-Za-z0-9]+)\s*$", re.IGNORECASE)


def nom_groupe_standard(prefixe: str, numero: int) -> str:
    """
    Nom canonique d'un groupe : ``A4_GROUPE1``, ``B_GROUPE2``, etc.
    ``prefixe`` = grade (A4, A3) ou catégorie (A, B) en mode mixage.
    """
    p = (prefixe or "SANS").strip().upper().replace(" ", "_")
    num = max(1, int(numero))
    return f"{p}_GROUPE{num}"[:100]


def numero_groupe(nom: str) -> int:
    """Numéro de groupe extrait du nom (1 pour Groupe 1 / A3_GROUPE1), 0 si indéterminé."""
    brut = (nom or "").strip()
    if not brut:
        return 0

    parsed = parse_nom_groupe_canonique(brut)
    if parsed:
        m = re.search(r"(\d+)$", parsed[1])
        if m:
            return int(m.group(1))

    m = _LEGACY_AVEC_GRADE_RE.match(brut)
    if m:
        return int(m.group(1))

    m_simple = re.match(r"^Groupe\s*(\d+)", brut, re.IGNORECASE)
    if m_simple:
        return int(m_simple.group(1))

    m_canon = re.search(r"_GROUPE(\d+)", brut, re.IGNORECASE)
    if m_canon:
        return int(m_canon.group(1))

    return 0


def prefixe_groupe_tri(nom: str) -> str:
    """Préfixe (grade / catégorie) pour un tri secondaire stable."""
    brut = (nom or "").strip()
    parsed = parse_nom_groupe_canonique(brut)
    if parsed:
        return parsed[0]

    m = _LEGACY_AVEC_GRADE_RE.match(brut)
    if m:
        return m.group(2).upper()

    return brut.upper()


def cle_tri_groupes(nom: str) -> tuple[int, str, str]:
    """Clé de tri : numéro croissant, puis préfixe, puis nom."""
    num = numero_groupe(nom)
    return (num if num > 0 else 999_999, prefixe_groupe_tri(nom), (nom or "").strip().upper())


def parse_nom_groupe_canonique(nom: str) -> tuple[str, str] | None:
    """Extrait (grade/préfixe, GROUPEn) si le nom est déjà au format canonique."""
    slug = re.sub(r"\s+", "", (nom or "").strip()).upper()
    m = _CANONIQUE_RE.match(slug)
    if m:
        return m.group(1).upper(), f"GROUPE{m.group(2)}"
    return None


def normaliser_nom_groupe_vers_canonique(nom: str, *, grade: str = "") -> str:
    """
    Convertit vers ``A4_GROUPE1`` lorsque possible.
    - Déjà canonique → normalisé en majuscules
    - « Groupe 1 A3 » → ``A3_GROUPE1``
    - « Groupe 1 » + grade fourni → ``{grade}_GROUPE1``
    """
    brut = (nom or "").strip()
    if not brut:
        return brut

    parsed = parse_nom_groupe_canonique(brut)
    if parsed:
        return f"{parsed[0]}_{parsed[1]}"

    m = _LEGACY_AVEC_GRADE_RE.match(brut)
    if m:
        return nom_groupe_standard(m.group(2), int(m.group(1)))

    m_simple = re.match(r"^Groupe\s*(\d+)\s*$", brut, re.IGNORECASE)
    if m_simple and grade:
        return nom_groupe_standard(grade, int(m_simple.group(1)))

    return brut


def nom_groupe_sans_grade(nom_groupe: str, grade: str) -> str:
    """
    Retourne un libellé groupe sans redondance du grade.
    Exemples:
      - « Groupe 1 B3 » + grade « B3 » → « Groupe 1 »
      - « A4_GROUPE1 » + grade « A4 » → « GROUPE1 »
    """
    nom = (nom_groupe or "").strip()
    grade_norm = (grade or "").strip().upper()
    if not nom or not grade_norm:
        return nom

    nom_upper = nom.upper()
    prefixes = [f"{grade_norm} ", f"{grade_norm}-", f"{grade_norm}_"]
    for prefix in prefixes:
        if nom_upper.startswith(prefix):
            return nom[len(prefix) :].strip(" _-")

    suffixes = [f" {grade_norm}", f"-{grade_norm}", f"_{grade_norm}"]
    for suffix in suffixes:
        if nom_upper.endswith(suffix):
            return nom[: -len(suffix)].strip(" _-")

    return nom


def grade_principal_groupe(groupe) -> str:
    """Grade du nom canonique, ou majoritaire des auditeurs, ou préfixe hérité."""
    if groupe is not None:
        parsed = parse_nom_groupe_canonique(getattr(groupe, "nom", "") or "")
        if parsed:
            return parsed[0]

    grades = [
        (m.auditeur.grade or "").strip().upper() for m in groupe.membres.all() if (m.auditeur.grade or "").strip()
    ]
    if grades:
        return Counter(grades).most_common(1)[0][0]

    nom = (groupe.nom or "").strip().upper()
    if "_" in nom:
        prefix = nom.split("_", 1)[0].strip()
        if prefix:
            return prefix
    if "-" in nom:
        prefix = nom.split("-", 1)[0].strip()
        if prefix:
            return prefix
    return ""


def libelle_groupe_export(nom_groupe: str, grade: str) -> str:
    """Libellé « Groupe » dans les exports : nom canonique complet si possible."""
    canonique = normaliser_nom_groupe_vers_canonique(nom_groupe, grade=grade)
    if parse_nom_groupe_canonique(canonique):
        return canonique
    sans = nom_groupe_sans_grade(nom_groupe, grade)
    return sans or (nom_groupe or "").strip()


def suffixe_groupe_export(nom_groupe: str, grade: str) -> str:
    """
    Partie « GROUPE* » d'un nom de fichier (sans le grade).
    Ex. A4_GROUPE1 → GROUPE1 ; ancien « Groupe 10 A3 » → GROUPE10.
    """
    canonique = normaliser_nom_groupe_vers_canonique(nom_groupe, grade=grade)
    parsed = parse_nom_groupe_canonique(canonique)
    if parsed:
        return parsed[1]

    base = nom_groupe_sans_grade(nom_groupe, grade) or (nom_groupe or "").strip()
    match = re.match(r"^Groupe\s*(\d+)\s*$", base, re.IGNORECASE)
    if match:
        return f"GROUPE{match.group(1)}"

    slug = re.sub(r"[^A-Za-z0-9]+", "_", base).strip("_").upper()
    if slug.startswith("GROUPE"):
        return slug
    if slug.isdigit():
        return f"GROUPE{slug}"
    return slug[:40] if slug else "GROUPE1"


def nom_fichier_emploi_du_temps(
    *,
    nom_groupe: str = "",
    grade: str = "",
    extension: str = "pdf",
    variante: str = "",
    groupe=None,
) -> str:
    """
    Nom de fichier export planning : ``A4_EMP_GROUPE1.pdf`` ou ``A4_EMP_GROUPE1_cours.xlsx``.
    """
    if groupe is not None:
        nom_groupe = groupe.nom or nom_groupe
        grade = grade_principal_groupe(groupe) or grade

    canonique = normaliser_nom_groupe_vers_canonique(nom_groupe, grade=grade)
    parsed = parse_nom_groupe_canonique(canonique)
    if parsed:
        grade_norm, suffix = parsed
    else:
        grade_norm = (grade or "").strip().upper() or "GROUPE"
        suffix = suffixe_groupe_export(nom_groupe, grade_norm)

    stem = f"{grade_norm}_EMP_{suffix}"
    variante = (variante or "").strip().lower()
    if variante and variante not in {"cours", "pdf"}:
        stem = f"{stem}_{variante}"
    ext = extension.lstrip(".").lower() or "pdf"
    return f"{stem}.{ext}"


def nom_fichier_emploi_du_temps_formation(formation, *, extension: str = "pdf") -> str:
    """Export multi-groupes : ``FAC_EMP_TOUS_GROUPES.pdf``."""
    code = ""
    if getattr(formation, "type_formation", None) is not None:
        code = (formation.type_formation.code or "").strip().upper()
    if not code:
        code = re.sub(r"[^A-Za-z0-9]+", "_", (formation.intitule or "FORMATION")).strip("_").upper()[:20]
    ext = extension.lstrip(".").lower() or "pdf"
    return f"{code or 'FORMATION'}_EMP_TOUS_GROUPES.{ext}"
