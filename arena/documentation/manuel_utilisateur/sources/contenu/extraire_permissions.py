"""Produit sources/referentiels/permissions.json depuis le catalogue du backend.

Aucune permission n'est recopiée à la main : le script déplie le catalogue
(module × ressource × action) et écrit les 1 157 permissions atomiques avec
leur module, leur ressource et leur action.

Usage :
    cd backend
    USE_SQLITE=1 SQLITE_PATH=/tmp/demo.sqlite3 SECRET_KEY=x \
        python ../documentation/manuel_utilisateur/sources/contenu/extraire_permissions.py
"""

from __future__ import annotations

import json
import os
import pathlib
import sys


def main() -> int:
    racine = pathlib.Path(__file__).resolve().parents[4]
    backend = racine / "backend"
    if not backend.is_dir():
        print(f"backend introuvable : {backend}", file=sys.stderr)
        return 1

    sys.path.insert(0, str(backend))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    os.environ.setdefault("SECRET_KEY", "extraction-documentation")
    os.environ.setdefault("USE_SQLITE", "1")

    import django

    django.setup()

    from habilitations.referentiel.chargement import deplier_permissions

    perms = sorted(deplier_permissions(), key=lambda d: d["code"])
    cible = pathlib.Path(__file__).resolve().parents[1] / "referentiels" / "permissions.json"
    with cible.open("w", encoding="utf-8") as f:
        json.dump({"total": len(perms), "permissions": perms}, f,
                  ensure_ascii=False, indent=1)
    print(f"{len(perms)} permissions écrites dans {cible}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
