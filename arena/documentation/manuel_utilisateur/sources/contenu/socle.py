"""Socle de données du manuel utilisateur INJS 2026.

Charge les référentiels extraits du code (RBAC, navigation, profils) et expose
les structures communes au HTML et au PDF. **Aucune donnée n'est inventée** :
tout provient de `sources/referentiels/*.json`, eux-mêmes extraits du dépôt.
"""
from __future__ import annotations

import json
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]          # documentation/manuel_utilisateur
REFS = RACINE / "sources" / "referentiels"

TITRE = "Manuel utilisateur officiel"
EDITION = "Édition 2026"
INSTITUTION = "Institut National de la Jeunesse et des Sports d'Abidjan"
APPLICATION = "Application de gestion intégrée INJS"
VERSION_DOC = "1.0"
DATE_GENERATION = "9 novembre 2026"

PALETTE = {
    "navy": "#073763",
    "profond": "#0B2545",
    "clair": "#4A90D9",
    "tres_clair": "#EAF3FB",
    "blanc": "#FFFFFF",
    "succes": "#059669",
    "alerte": "#D97706",
    "danger": "#DC2626",
    "texte": "#1E293B",
    "texte_doux": "#475569",
    "bordure": "#CBD5E1",
    "surface": "#F8FAFC",
}


def _charger(nom: str):
    with open(REFS / nom, encoding="utf-8") as f:
        return json.load(f)


RBAC = _charger("rbac.json")
NAVIGATION = _charger("navigation.json")
PROFILS = _charger("profils.json")
CAPTURES = _charger("captures.json")
ROUTES = _charger("routes_gardes.json")

ROLES = RBAC["roles"]
MODULES = RBAC["modules"]
META = PROFILS["meta"]
LISTE_PROFILS = PROFILS["profils"]
SECTIONS = NAVIGATION["sections"]

#: Familles du catalogue, dans l'ordre de présentation.
FAMILLES = [
    ("ADMINISTRATION", "Administration et direction"),
    ("ADMINISTRATION_GENERALE", "Administration générale et services"),
    ("CANDIDATURES", "Candidatures, concours et admissions"),
    ("SCOLARITE", "Scolarité"),
    ("PEDAGOGIE", "Pédagogie et organisation des enseignements"),
    ("ENSEIGNANTS", "Enseignants et charges d'enseignement"),
    ("EVALUATIONS", "Évaluations et jurys"),
    ("DIPLOMATION", "Diplômation et graduation"),
    ("FINANCE", "Finances"),
    ("RH", "Ressources humaines"),
    ("PATRIMOINE", "Patrimoine et espaces"),
    ("STAGES", "Stages et conventions"),
    ("TECHNIQUE", "Technique et systèmes d'information"),
    ("DESTINATAIRES", "Destinataires du service"),
]

ORDRE_DOMAINE = {code: i for i, (code, _) in enumerate(FAMILLES)}
ORDRE_DOMAINE.setdefault("ADMINISTRATION_GENERALE", 99)


def roles_par_famille():
    """[(libellé famille, [rôles triés])] — l'ordre suit FAMILLES."""
    groupes: dict[str, list] = {}
    for role in ROLES:
        groupes.setdefault(role["domaine"], []).append(role)
    sortie = []
    for code, libelle in FAMILLES:
        if code in groupes:
            sortie.append((libelle, sorted(groupes[code], key=lambda r: r["ordre"])))
    for code, liste in groupes.items():           # domaines non répertoriés
        if code not in ORDRE_DOMAINE:
            sortie.append((code, sorted(liste, key=lambda r: r["ordre"])))
    return sortie


def roles_sensibles():
    return [r for r in ROLES if r["sensible"]]


def modules_par_sensibilite():
    return (
        [m for m in MODULES if not m["sensible"]],
        [m for m in MODULES if m["sensible"]],
    )


def capture(fichier: str):
    for c in CAPTURES:
        if c["fichier"] == fichier:
            return c
    return None


def menus_du_profil(code: str):
    for p in LISTE_PROFILS:
        if p["code"] == code:
            return p.get("menus", [])
    return []
