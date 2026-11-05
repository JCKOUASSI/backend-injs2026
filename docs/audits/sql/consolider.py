#!/usr/bin/env python3
"""Consolidation des sorties de collecte — audit comparatif INJS.

Ce script ne se connecte à AUCUNE base : il lit uniquement les fichiers texte
produits par run_audit.sh (00_profil_schema.sql et 10_anomalies.sql) et en tire
un rapport de consolidation markdown.

Aucune valeur n'est inventée : toute rubrique absente des fichiers d'entrée est
explicitement marquée « non fourni ».

Usage :
    python3 consolider.py [dossier_collecte] [-o rapport.md]

Convention de nommage attendue (produite par run_audit.sh) :
    <base>__00_profil_schema__<horodatage>.txt
    <base>__10_anomalies__<horodatage>.txt
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import sys
from collections import defaultdict

SECTION_RE = re.compile(r"^=+\s*(\d+)\.\s*(.+?)\s*=+\s*$")
SEP_RE = re.compile(r"^[\s\-+]*-{2,}[\s\-+|:]*$")
END_RE = re.compile(r"^\(\d+ rows?\)")


# --------------------------------------------------------------------------
# Lecture des fichiers de sortie psql
# --------------------------------------------------------------------------
def split_sections(text: str) -> dict[str, list[str]]:
    """Découpe la sortie par marqueur « ===== n. TITRE ===== »."""
    sections: dict[str, list[str]] = {}
    current = None
    for line in text.splitlines():
        m = SECTION_RE.match(line.strip())
        if m:
            current = f"{m.group(1)}. {m.group(2)}"
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    return sections


def parse_blocks(lines: list[str]) -> list[dict]:
    """Extrait les tableaux alignés psql d'une section.

    Un tableau = ligne d'en-tête + ligne de séparation + lignes de données,
    terminées par « (N rows) » ou une ligne vide.
    """
    blocks: list[dict] = []
    i = 0
    while i < len(lines) - 1:
        header = lines[i]
        sep = lines[i + 1]
        if "|" in header and SEP_RE.match(sep) and set(sep.strip()) <= set("-+|: "):
            cols = [c.strip() for c in header.strip().strip("|").split("|")]
            rows: list[list[str]] = []
            j = i + 2
            while j < len(lines):
                raw = lines[j]
                if not raw.strip() or END_RE.match(raw.strip()):
                    break
                cells = [c.strip() for c in raw.strip().strip("|").split("|")]
                if len(cells) == len(cols):
                    rows.append(cells)
                j += 1
            blocks.append({"cols": cols, "rows": rows})
            i = j + 1
        else:
            i += 1
    return blocks


def parse_notices(lines: list[str]) -> list[str]:
    out = []
    for line in lines:
        if "NOTICE:" in line:
            out.append(line.split("NOTICE:", 1)[1].strip())
    return out


def load_collecte(folder: str) -> dict:
    """Charge toutes les sorties, groupées par base et par script."""
    result: dict[str, dict] = defaultdict(dict)
    for path in sorted(glob.glob(os.path.join(folder, "*.txt"))):
        name = os.path.basename(path)
        m = re.match(r"^(?P<base>.+?)__(?P<script>\d{2}_[A-Za-z_]+)__(?P<ts>[0-9TZ]+)\.txt$", name)
        if not m:
            continue
        base, script = m.group("base"), m.group("script")
        with open(path, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
        result[base][script] = {
            "fichier": name,
            "sections": split_sections(text),
            "erreurs": text.count("ERROR:"),
            "lignes": len(text.splitlines()),
        }
    return result


# --------------------------------------------------------------------------
# Extraction de valeurs
# --------------------------------------------------------------------------
def table_counts(sec: dict) -> dict[str, int]:
    """Section 4 du profil : table -> nombre exact de lignes."""
    out: dict[str, int] = {}
    for block in parse_blocks(sec.get("4. COMPTAGE EXACT (toutes les tables, lecture seule)", [])):
        for row in block["rows"]:
            if len(row) >= 2 and row[1].lstrip("-").isdigit():
                out[row[0]] = int(row[1])
    return out


def table_list(sec: dict) -> list[str]:
    out = []
    for block in parse_blocks(sec.get("3. TABLES (nom, type, estimation de lignes)", [])):
        for row in block["rows"]:
            if len(row) >= 2:
                out.append(row[1])
    return out


def migration_counts(sec: dict) -> dict[str, int]:
    out: dict[str, int] = {}
    blocks = parse_blocks(sec.get("10. HISTORIQUE DES MIGRATIONS DJANGO", []))
    for block in blocks:
        if "app" in [c.lower() for c in block["cols"]]:
            for row in block["rows"]:
                if len(row) >= 2 and row[1].isdigit():
                    out[row[0]] = int(row[1])
    return out


def constraints(sec: dict) -> list[list[str]]:
    rows = []
    for block in parse_blocks(sec.get("6. CLES PRIMAIRES ET UNICITE", [])):
        rows.extend(block["rows"])
    return rows


def fks(sec: dict) -> list[list[str]]:
    rows = []
    for block in parse_blocks(sec.get("7. CLES ETRANGERES (graphe de dependances)", [])):
        rows.extend(block["rows"])
    return rows


# --------------------------------------------------------------------------
# Rendu
# --------------------------------------------------------------------------
def app_of(table: str) -> str:
    t = table.split(".")[-1]
    return t.split("_")[0] if "_" in t else t


def build(folder: str) -> str:
    data = load_collecte(folder)
    if not data:
        return ("# Consolidation impossible\n\n"
                "Aucun fichier `*.txt` au format attendu n'a été trouvé dans "
                f"`{folder}`.\n\nFormat attendu : `<base>__00_profil_schema__<horodatage>.txt`.\n")

    out: list[str] = []
    out.append("# Consolidation des mesures — audit comparatif des bases INJS")
    out.append("")
    out.append("> Rapport **généré automatiquement** à partir des sorties brutes de")
    out.append("> `00_profil_schema.sql` et `10_anomalies.sql`. Aucune valeur n'est estimée :")
    out.append("> chaque chiffre est repris tel qu'il figure dans les fichiers listés au §0.")
    out.append("")

    # §0 provenance
    out.append("## 0. Provenance des mesures")
    out.append("")
    out.append("| Base | Script | Fichier | Erreurs détectées |")
    out.append("|---|---|---|---|")
    for base in sorted(data):
        for script in sorted(data[base]):
            d = data[base][script]
            out.append(f"| `{base}` | `{script}` | `{d['fichier']}` | {d['erreurs']} |")
    out.append("")

    # §1 contexte
    out.append("## 1. Contexte des bases")
    out.append("")
    out.append("| Base | Version PostgreSQL | Taille | Tables |")
    out.append("|---|---|---|---|")
    for base in sorted(data):
        sec = data[base].get("00_profil_schema", {}).get("sections", {})
        ctx = parse_blocks(sec.get("1. CONTEXTE", []))
        vol = parse_blocks(sec.get("2. VOLUME PAR SCHÉMA", []))
        version = taille = "-"
        if ctx and ctx[0]["rows"]:
            r = ctx[0]["rows"][0]
            if len(r) >= 3:
                version, taille = r[1], r[2]
        ntables = "-"
        for block in vol:
            for row in block["rows"]:
                if row and row[0] == "public" and len(row) >= 2:
                    ntables = row[1]
        out.append(f"| `{base}` | {version} | {taille} | {ntables} |")
    out.append("")

    # §2 repartition par domaine
    out.append("## 2. Répartition des tables par domaine (préfixe applicatif)")
    out.append("")
    per_base_counts = {}
    for base in sorted(data):
        sec = data[base].get("00_profil_schema", {}).get("sections", {})
        per_base_counts[base] = table_counts(sec)
    domains = sorted({app_of(t) for counts in per_base_counts.values() for t in counts})
    bases = sorted(per_base_counts)
    out.append("| Domaine | " + " | ".join(f"`{b}`" for b in bases) + " |")
    out.append("|---" * (len(bases) + 1) + "|")
    for dom in domains:
        cells = []
        for b in bases:
            n = sum(1 for t in per_base_counts[b] if app_of(t) == dom)
            cells.append(str(n) if n else "—")
        out.append(f"| `{dom}` | " + " | ".join(cells) + " |")
    out.append("")

    # §3 volumes
    out.append("## 3. Volumes exacts (tables non vides, ordre décroissant)")
    out.append("")
    for base in bases:
        counts = per_base_counts[base]
        non_vides = {t: n for t, n in counts.items() if n}
        total = sum(counts.values())
        out.append(f"### `{base}` — {len(counts)} tables, {total} lignes au total, "
                   f"{len(non_vides)} tables non vides")
        out.append("")
        if non_vides:
            out.append("| Table | Lignes |")
            out.append("|---|---|")
            for t, n in sorted(non_vides.items(), key=lambda kv: (-kv[1], kv[0])):
                out.append(f"| `{t}` | {n} |")
        else:
            out.append("_Toutes les tables sont vides._")
        out.append("")

    # §4 structure comparee
    out.append("## 4. Comparatif de structure")
    out.append("")
    out.append("| Indicateur | " + " | ".join(f"`{b}`" for b in bases) + " |")
    out.append("|---" * (len(bases) + 1) + "|")
    rows_ind = [
        ("Tables (schéma public)", lambda s: len(table_counts(s))),
        ("Contraintes PK/UNIQUE", lambda s: len(constraints(s))),
        ("Clés étrangères", lambda s: len(fks(s))),
        ("Applications migrées (django_migrations)", lambda s: len(migration_counts(s))),
        ("Migrations enregistrées", lambda s: sum(migration_counts(s).values())),
        ("Tables sans clé primaire", lambda s: len(
            parse_blocks(s.get("11. TABLES SANS CLE PRIMAIRE (anomalie structurelle)", []))[0]["rows"]
            if parse_blocks(s.get("11. TABLES SANS CLE PRIMAIRE (anomalie structurelle)", [])) else [])),
    ]
    for label, fn in rows_ind:
        cells = []
        for b in bases:
            sec = data[b].get("00_profil_schema", {}).get("sections", {})
            try:
                cells.append(str(fn(sec)))
            except Exception:
                cells.append("non fourni")
        out.append(f"| {label} | " + " | ".join(cells) + " |")
    out.append("")

    # §5 anomalies
    out.append("## 5. Anomalies quantifiées")
    out.append("")
    for base in bases:
        d = data[base].get("10_anomalies")
        if not d:
            out.append(f"### `{base}` — **non fourni** (script `10_anomalies.sql` absent)")
            out.append("")
            continue
        sec = d["sections"]
        out.append(f"### `{base}`")
        out.append("")

        non_validees = parse_blocks(sec.get("A. INTEGRITE PHYSIQUE DES CONTRAINTES", []))
        nb_nv = len(non_validees[0]["rows"]) if non_validees else 0
        out.append(f"- **Contraintes FK non validées** (`convalidated = false`) : **{nb_nv}**")

        orphelins = []
        for block in parse_blocks(sec.get("B. REFERENCES ORPHELINES — detection generique sur toutes les FK", [])):
            if "orphelins" in [c.lower() for c in block["cols"]]:
                orphelins.extend(r for r in block["rows"] if r and r[-1].isdigit())
        total_orphelins = sum(int(r[-1]) for r in orphelins)
        out.append(f"- **Clés étrangères avec orphelins** : **{len(orphelins)}** "
                   f"({total_orphelins} ligne(s) orpheline(s) au total)")
        if orphelins:
            out.append("")
            out.append("| Contrainte | Orphelins |")
            out.append("|---|---|")
            for r in sorted(orphelins, key=lambda x: -int(x[-1])):
                out.append(f"| `{r[0]}` | {r[-1]} |")
            out.append("")

        vides = []
        for block in parse_blocks(sec.get("C. COLONNES TEXTE NOT NULL VIDES", [])):
            vides.extend(block["rows"])
        out.append(f"- **Colonnes texte obligatoires vides** : **{len(vides)}** colonne(s) concernée(s)")
        if vides:
            out.append("")
            out.append("| Table | Colonne | Valeurs vides |")
            out.append("|---|---|---|")
            for r in sorted(vides, key=lambda x: -int(x[2])):
                out.append(f"| `{r[0]}` | `{r[1]}` | {r[2]} |")
            out.append("")

        dates = []
        for block in parse_blocks(sec.get("D. DATES INCOHERENTES (modification anterieure a la creation)", [])):
            dates.extend(block["rows"])
        out.append(f"- **Dates incohérentes** : **{sum(int(r[1]) for r in dates if r[1].isdigit())}** ligne(s)")

        doublons = []
        for block in parse_blocks(sec.get("E. DOUBLONS SUR CLES NATURELLES (matricule, code, numero)", [])):
            doublons.extend(r for r in block["rows"] if len(r) >= 4 and int(r[2]) > 0)
        out.append(f"- **Doublons sur clés naturelles** : **{len(doublons)}** cas")
        if doublons:
            out.append("")
            out.append("| Table | Clé | Groupes | Lignes en cause |")
            out.append("|---|---|---|---|")
            for r in sorted(doublons, key=lambda x: -int(x[3])):
                out.append(f"| `{r[0]}` | `{r[1]}` | {r[2]} | {r[3]} |")
            out.append("")

        for titre in ("G. COMPTES : REPARTITION PAR ROLE (compteurs uniquement)",
                      "H. MOTS DE PASSE : ALGORITHME SEULEMENT (aucun hash affiche)",
                      "F. ORPHELINS METIER SUR LA BASE CIBLE"):
            notices = parse_notices(sec.get(titre, []))
            if notices:
                out.append(f"- **{titre.split('.', 1)[1].strip()}** :")
                for n in notices:
                    out.append(f"  - {n}")
        out.append("")

        distrib = []
        for block in parse_blocks(sec.get("I. DISTRIBUTION DES CODES DE STATUT (valeurs courtes uniquement)", [])):
            distrib.extend(block["rows"])
        if distrib:
            out.append("- **Distribution des codes de statut** :")
            out.append("")
            out.append("| Table | Colonne | Valeur | Occurrences |")
            out.append("|---|---|---|---|")
            for r in distrib:
                out.append(f"| `{r[0]}` | `{r[1]}` | `{r[2]}` | {r[3]} |")
            out.append("")

    # §6 ecart avec les tables attendues en cible
    attendues = charger_tables_attendues(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tables_cibles_attendues.txt"))
    if attendues:
        out.append("## 6. Écart entre les tables attendues (code) et les tables réelles")
        out.append("")
        out.append(f"Référentiel : `docs/audits/tables_cibles_attendues.txt` — "
                   f"**{len(attendues)} tables** attendues d'après les modèles Django.")
        out.append("")
        for base in bases:
            reelles = {t.split(".")[-1] for t in per_base_counts[base]}
            if not reelles:
                continue
            communes = reelles & attendues
            manquantes = sorted(attendues - reelles)
            surnumeraires = sorted(reelles - attendues)
            taux = 100.0 * len(communes) / len(attendues)
            out.append(f"### `{base}` — correspondance {len(communes)}/{len(attendues)} "
                       f"({taux:.1f} %)")
            out.append("")
            if taux >= 50:
                out.append(f"- **Tables attendues absentes de la base : {len(manquantes)}**")
                if manquantes:
                    for t in manquantes[:60]:
                        out.append(f"  - `{t}`")
                    if len(manquantes) > 60:
                        out.append(f"  - … et {len(manquantes) - 60} autres")
                out.append(f"- **Tables présentes hors référentiel : {len(surnumeraires)}**")
                if surnumeraires:
                    for t in surnumeraires[:40]:
                        out.append(f"  - `{t}`")
                    if len(surnumeraires) > 40:
                        out.append(f"  - … et {len(surnumeraires) - 40} autres")
                out.append("")
                out.append("**Lecture** : si cette base est la cible et que l'écart est nul, "
                           "l'hypothèse « 203 = 202 modèles + django_migrations » est confirmée ; "
                           "s'il manque des tables, elles sont à identifier avant tout import.")
            else:
                out.append(f"_Correspondance trop faible ({taux:.1f} %) : cette base n'est "
                           f"pas la cible attendue, comparaison non significative._")
            out.append("")

    return "\n".join(out) + "\n"


def charger_tables_attendues(path: str) -> set[str]:
    """Lit le référentiel des tables attendues (une table par ligne, avant le premier |)."""
    if not os.path.isfile(path):
        return set()
    tables = set()
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            tables.add(line.split("|")[0].strip())
    return tables


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("dossier", nargs="?", default="collecte")
    ap.add_argument("-o", "--sortie", default="CONSOLIDATION.md")
    args = ap.parse_args()
    if not os.path.isdir(args.dossier):
        print(f"Dossier introuvable : {args.dossier}", file=sys.stderr)
        return 2
    rapport = build(args.dossier)
    with open(args.sortie, "w", encoding="utf-8") as fh:
        fh.write(rapport)
    print(f"Rapport écrit : {args.sortie} ({len(rapport.splitlines())} lignes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
