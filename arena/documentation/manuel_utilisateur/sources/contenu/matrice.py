"""Matrice « Profil | Modules accessibles | Consultation | Création | Modification |
Validation | Suppression | Export ».

La matrice n'est pas rédigée à la main : elle est **dérivée** de deux sources
vérifiées dans le code de l'application.

1. ``backend/habilitations/referentiel/catalogue_matrice.py`` (``NIVEAUX``)
   donne, pour chaque rôle du catalogue, un niveau N0–N4 par module.
2. ``backend/habilitations/referentiel/catalogue_modules.py`` (``NIVEAU_VERBE``)
   indique le niveau minimal requis pour chaque verbe métier.

La colonne « niveau minimum » d'un profil est le **minimum** des niveaux de ses
rôles pour un verbe donné : une opération n'est donc déclarée possible que si
au moins un des rôles portés par le profil l'autorise réellement.

Un profil peut cumuler plusieurs rôles (``CORRESPONDANCE_LEGACY``). Les profils
sans accès web (FORMATEUR, AUDITEUR) sont conservés : la matrice indique
explicitement qu'aucun module n'est atteignable pour eux.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[4]
BACKEND = RACINE / "backend"

# Verbes de la matrice affichée → verbe(s) du catalogue pris en compte.
# « Modification » couvre modifier et soumettre ; « Export » couvre exporter
# et imprimer, qui partagent le même niveau minimal (N1).
COLONNES = (
    ("consultation", ("consulter",)),
    ("creation", ("creer", "saisir", "editer", "deposer")),
    ("modification", ("modifier", "soumettre", "remplacer")),
    ("validation", ("valider", "rejeter", "publier", "signer", "verrouiller",
                    "decider", "certifier", "cloturer", "instruire")),
    ("suppression", ("supprimer", "archiver", "annuler")),
    ("export", ("exporter", "imprimer", "generer")),
)

# Profil opérationnel (User.Role) → rôles du catalogue réellement portés.
# Source : backend/habilitations/referentiel/catalogue_matrice.py,
# CORRESPONDANCE_LEGACY (relevé à la ligne 308-326).
PROFIL_VERS_ROLES = {
    "ADMIN": ["ADMIN_SYSTEME"],
    "CHEF_INJS_ADMIN": ["ADMIN_SYSTEME", "DIRECTION_ETUDES"],
    "INJS_ADMIN": ["SCOLARITE", "GESTIONNAIRE_COURS"],
    "DIRECTION": ["DIRECTION_GENERALE"],
    "CHEF_SECRETARIAT": ["SCOLARITE", "AGENT_INSCRIPTIONS", "AGENT_ADMISSIONS",
                          "GESTIONNAIRE_ETUDIANTS"],
    "SECRETARIAT": ["AGENT_INSCRIPTIONS", "AGENT_ADMISSIONS", "GESTIONNAIRE_ETUDIANTS"],
    "FINANCE": ["GESTIONNAIRE_FINANCES_ETUD", "GESTIONNAIRE_VACATIONS"],
    "ARCHIVE": ["ARCHIVISTE"],
    "ENCADRANT": ["ENSEIGNANT", "GESTIONNAIRE_GROUPES"],
    "SUPERVISEUR": ["RESPONSABLE_PEDAGOGIQUE"],
    "FORMATEUR": ["ENSEIGNANT"],
    "AUDITEUR": ["ETUDIANT"],
}

# Profils dont l'accès à l'interface web est fermé
# (backend/authentication/role_groups.py, ALLOWED_WEB_ROLES l.57-68).
SANS_ACCES_WEB = {"FORMATEUR", "AUDITEUR"}

SYM = {"oui": "Oui", "non": "—", "lecture": "Lecture seule"}


def _charger_backend():
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))
    import os

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    os.environ.setdefault("SECRET_KEY", "documentation-locale-uniquement")
    try:
        import django

        django.setup()
    except Exception:
        # le référentiel est importable sans initialiser Django
        pass
    matrice = importlib.import_module("habilitations.referentiel.catalogue_matrice")
    modules = importlib.import_module("habilitations.referentiel.catalogue_modules")
    return matrice, modules


_MAT = _MOD = None


def _sources():
    global _MAT, _MOD
    if _MAT is None:
        _MAT, _MOD = _charger_backend()
    return _MAT, _MOD


def _niveau_min(roles: list[str], module: str) -> int | None:
    """Plus petit niveau détenu par l'un des rôles sur le module (None si aucun)."""
    matrice, _ = _sources()
    detenus = []
    for role in roles:
        niveaux = dict(matrice.NIVEAUX.get(role, {}))
        niveaux.update(matrice.NIVEAUX_EXTRA_PROVISOIRES.get(role, {}))
        if module in niveaux:
            detenus.append(int(str(niveaux[module]).lstrip("N")))
    return min(detenus) if detenus else None


def _verbe_requis(verbes: tuple[str, ...]) -> int | None:
    _, modules = _sources()
    niveaux = [modules.NIVEAU_VERBE.get(v) for v in verbes
               if modules.NIVEAU_VERBE.get(v) is not None]
    return min(niveaux) if niveaux else None


def _cellule(niveau_profil: int | None, niveau_verbe: int | None) -> str:
    if niveau_profil is None or niveau_verbe is None:
        return "—"
    return "Oui" if niveau_profil >= niveau_verbe else "—"


def construire_matrice():
    """Retourne (entetes, lignes, modules, meta) de la matrice complète."""
    matrice, modules = _sources()
    liste_modules = [(code, libelle) for code, (libelle, _app, _c) in
                     modules.MODULES.items()]

    lignes = []
    for profil, roles in PROFIL_VERS_ROLES.items():
        if profil in SANS_ACCES_WEB:
            lignes.append({
                "profil": profil,
                "web": False,
                "modules": [],
                "cellules": {c: "—" for c, _ in COLONNES},
                "note": "Accès web fermé : aucun module atteignable dans l'application web.",
            })
            continue

        accessibles = []
        cellules = {}
        for code, _lib in liste_modules:
            niveau = _niveau_min(roles, code)
            if niveau is None:
                continue
            etat = {}
            for colonne, verbes in COLONNES:
                etat[colonne] = _cellule(niveau, _verbe_requis(verbes))
            if etat["consultation"] == "Oui" or any(
                    v == "Oui" for v in etat.values()):
                accessibles.append(code)
                for colonne, valeur in etat.items():
                    if valeur == "Oui":
                        cellules.setdefault(colonne, [])
                        cellules[colonne].append(code)
        lignes.append({
            "profil": profil,
            "web": True,
            "modules": accessibles,
            "cellules": cellules,
            "note": "",
        })
    return COLONNES, lignes, liste_modules


def synthese():
    """Résumé chiffré utilisé dans le rapport et dans les annexes."""
    colonnes, lignes, modules = construire_matrice()
    return {
        "nb_profils": len(lignes),
        "nb_modules": len(modules),
        "nb_colonnes": len(colonnes),
        "profils_sans_web": sum(1 for l in lignes if not l["web"]),
        "modules_max": max((len(l["modules"]) for l in lignes), default=0),
        "modules_min_actifs": min((len(l["modules"]) for l in lignes if l["web"]),
                                  default=0),
    }


if __name__ == "__main__":
    colonnes, lignes, modules = construire_matrice()
    print(f"{'profil':>18} | modules | " + " | ".join(c for c, _ in colonnes))
    for l in lignes:
        marques = []
        for c, _ in colonnes:
            n = len(l["cellules"].get(c, [])) if isinstance(l["cellules"].get(c), list) else 0
            marques.append(f"{n:>3}")
        print(f"{l['profil']:>18} | {len(l['modules']):>7} | " + " | ".join(marques))
    print()
    print(synthese())
