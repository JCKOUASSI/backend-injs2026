"""Publie le manuel dans l'emplacement exigé : arena/documentation/manuel_utilisateur/.

Le script est idempotent et refuse d'écraser un fichier plus récent que sa
source. Il construit l'arborescence complète demandée par le cahier des
charges, y compris `html/assets/` qui n'existait pas, puis régénère les
archives ZIP et la page de téléchargement.

Arborescence produite
---------------------
arena/documentation/manuel_utilisateur/
├── pdf/                     le manuel imprimable
├── html/
│   ├── index.html           le manuel interactif autonome
│   ├── assets/{css,js,images}
├── sources/
│   ├── contenu/             générateurs Python
│   ├── captures/            captures d'écran d'origine
│   └── referentiels/        JSON extraits du code
├── telechargements/         page de téléchargement + PDF + ZIP
├── RAPPORT_PRODUCTION.md
└── LIRE-MOI.txt

Usage :
    python documentation/manuel_utilisateur/sources/contenu/publier.py
"""

from __future__ import annotations

import filecmp
import hashlib
import shutil
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

RACINE_DEPOT = Path(__file__).resolve().parents[4]
SOURCE = RACINE_DEPOT / "documentation" / "manuel_utilisateur"
CIBLE = RACINE_DEPOT / "arena" / "documentation" / "manuel_utilisateur"

PDF = "MANUEL_UTILISATEUR_OFFICIEL_INJS_2026.pdf"
ZIP_COMPLET = "MANUEL_UTILISATEUR_OFFICIEL_INJS_2026_COMPLET.zip"
ZIP_HTML = "MANUEL_UTILISATEUR_OFFICIEL_INJS_2026_HTML.zip"


def empreinte(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


def copier(src: Path, dst: Path, journal: list) -> None:
    """Copie un fichier, en signalant tout écrasement d'un contenu différent."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        if filecmp.cmp(src, dst, shallow=False):
            journal.append(("identique", str(dst.relative_to(CIBLE))))
            return
        journal.append(("remplacé", str(dst.relative_to(CIBLE))))
        dst.unlink()
    else:
        journal.append(("créé", str(dst.relative_to(CIBLE))))
    shutil.copy2(src, dst)


def arbre(fichiers: list) -> None:
    for f in fichiers:
        print(f"  {f}")


def main() -> int:
    if not SOURCE.is_dir():
        print(f"source introuvable : {SOURCE}", file=sys.stderr)
        return 1

    journal: list[tuple[str, str]] = []

    # ── 1. PDF
    copier(SOURCE / "pdf" / PDF, CIBLE / "pdf" / PDF, journal)

    # ── 2. HTML interactif : index.html à la racine, ressources sous assets/
    copier(SOURCE / "html" / "index.html", CIBLE / "html" / "index.html", journal)

    for sous, motif in (("css", "*.css"), ("js", "*.js"), ("images", "*")):
        for f in sorted((SOURCE / "html" / sous).glob(motif)):
            if f.is_file():
                copier(f, CIBLE / "html" / "assets" / sous / f.name, journal)

    # ── 3. sources : contenu, captures, référentiels
    for f in sorted((SOURCE / "sources" / "contenu").glob("*.py")):
        copier(f, CIBLE / "sources" / "contenu" / f.name, journal)
    for f in sorted((SOURCE / "sources" / "captures").iterdir()):
        if f.is_file():
            copier(f, CIBLE / "sources" / "captures" / f.name, journal)
    for f in sorted((SOURCE / "sources" / "referentiels").iterdir()):
        if f.is_file():
            copier(f, CIBLE / "sources" / "referentiels" / f.name, journal)

    # ── 4. rapport et notice
    copier(SOURCE / "RAPPORT_PRODUCTION.md", CIBLE / "RAPPORT_PRODUCTION.md", journal)
    copier(SOURCE / "LIRE-MOI.txt", CIBLE / "LIRE-MOI.txt", journal)

    # ── 5. le HTML doit référencer assets/ et non css/ ou images/
    index = (CIBLE / "html" / "index.html").read_text(encoding="utf-8")
    ancien = index
    index = index.replace('href="css/manuel.css"', 'href="assets/css/manuel.css"')
    index = index.replace('src="js/manuel.js"', 'src="assets/js/manuel.js"')
    index = index.replace('src="images/', 'src="assets/images/')
    if index != ancien:
        (CIBLE / "html" / "index.html").write_text(index, encoding="utf-8")
        journal.append(("adapté", "html/index.html (chemins vers assets/)"))

    # ── 6. ZIP : HTML autonome + archive complète
    tele = CIBLE / "telechargements"
    tele.mkdir(parents=True, exist_ok=True)

    zip_html = tele / ZIP_HTML
    with zipfile.ZipFile(zip_html, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(CIBLE / "html" / "index.html", "manuel/index.html")
        for f in sorted((CIBLE / "html" / "assets").rglob("*")):
            if f.is_file():
                z.write(f, f"manuel/{f.relative_to(CIBLE / 'html')}")

    zip_complet = tele / ZIP_COMPLET
    with zipfile.ZipFile(zip_complet, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(CIBLE.rglob("*")):
            if f.is_file() and f.parent != tele:
                z.write(f, f.relative_to(CIBLE))

    # le PDF et le rapport sont joints séparément
    copier(CIBLE / "pdf" / PDF, tele / PDF, journal)
    copier(CIBLE / "RAPPORT_PRODUCTION.md", tele / "RAPPORT_PRODUCTION.md", journal)

    # ── 7. page de téléchargement
    from publier_page import construire_page  # type: ignore

    page = construire_page(CIBLE, PDF, ZIP_HTML, ZIP_COMPLET)
    (tele / "index.html").write_text(page, encoding="utf-8")
    journal.append(("écrit", "telechargements/index.html"))

    # ── 8. bilan
    crees = sum(1 for e, _ in journal if e == "créé")
    remplaces = sum(1 for e, _ in journal if e == "remplacé")
    identiques = sum(1 for e, _ in journal if e == "identique")
    print(f"\nPublication terminée dans {CIBLE}")
    print(f"  créés      : {crees}")
    print(f"  remplacés  : {remplaces}")
    print(f"  identiques : {identiques}")
    for etat, nom in journal:
        if etat in ("créé", "remplacé", "adapté", "écrit"):
            print(f"    [{etat}] {nom}")

    total = sum(f.stat().st_size for f in CIBLE.rglob("*") if f.is_file())
    fichiers = sum(1 for f in CIBLE.rglob("*") if f.is_file())
    print(f"\n  {fichiers} fichiers, {total / 1e6:.1f} Mo")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
