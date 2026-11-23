"""Construit la page de téléchargement du manuel.

La page liste chaque fichier livré avec sa taille réelle et son empreinte
SHA-256, et pointe des liens de type pièce jointe (`download`). Les chemins
sont relatifs, ce qui permet d'ouvrir la page en local comme depuis un serveur.

La page est régénérée à chaque publication : les tailles et empreintes ne
peuvent donc pas se désynchroniser des fichiers.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

PDF = "MANUEL_UTILISATEUR_OFFICIEL_INJS_2026.pdf"


def empreinte(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


def _taille(n: int) -> str:
    if n >= 1 << 20:
        return f"{n / (1 << 20):.1f} Mo".replace(".", ",")
    if n >= 1 << 10:
        return f"{n / (1 << 10):.0f} Ko"
    return f"{n} o"


def _carte(titre: str, description: str, fichier: str, page: Path,
           bouton: str, second=None) -> str:
    """Carte de téléchargement d'un fichier, avec sa taille et son empreinte."""
    p = page / fichier
    if p.exists():
        taille = _taille(p.stat().st_size)
        court = empreinte(p)[:16]
    else:
        taille, court = "—", "—"
    second_html = ""
    if second:
        libelle, cible = second
        second_html = (
            f'<a class="btn btn-second" href="{cible}" target="_blank" '
            f'rel="noopener">{libelle}</a>'
        )
    return f'''      <article class="carte">
        <h2>{titre}</h2>
        <p>{description}</p>
        <p class="meta">{taille} · SHA-256 <code>{court}…</code></p>
        <div class="actions">
          <a class="btn" href="{fichier}" download>{bouton}</a>
          {second_html}
        </div>
      </article>'''


def construire_page(dossier, pdf: str, zip_html: str, zip_complet: str) -> str:
    """Retourne le HTML complet de la page de téléchargement."""
    dossier = Path(dossier)
    page = dossier / "telechargements"
    css = dossier / "html" / "assets" / "css" / "manuel.css"
    lien_css = ("../html/assets/css/manuel.css" if css.exists()
                else "../html/css/manuel.css")
    manuel_html = dossier / "html" / "index.html"
    nb_images = len(list((dossier / "html" / "assets" / "images").glob("*")))
    date = datetime.now(timezone.utc).strftime("%d/%m/%Y")

    cartes = "\n".join([
        _carte(
            "Manuel complet — archive ZIP",
            "Tout le manuel : PDF, HTML, sources et captures. À conserver comme "
            "référence de l'édition 2026.",
            zip_complet, page, "⤓ Télécharger l'archive complète",
        ),
        _carte(
            "Manuel imprimable — PDF A4",
            "Version paginée, avec sommaire, signets, index des profils et glossaire. "
            "Prête à imprimer et à diffuser.",
            pdf, page, "⤓ Télécharger le PDF",
            ("Ouvrir dans le navigateur", pdf),
        ),
        _carte(
            "Manuel interactif — HTML autonome",
            "Version consultable hors ligne : recherche locale, filtres par profil, "
            "par module, par type d'opération et par niveau de responsabilité.",
            zip_html, page, "⤓ Télécharger le HTML",
            ("Ouvrir le manuel en ligne", "../html/index.html"),
        ),
        _carte(
            "Rapport de production",
            "Méthode, sources, vérifications et limites assumées de cette édition.",
            "RAPPORT_PRODUCTION.md", page, "⤓ Télécharger le rapport",
        ),
    ])

    return f'''<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Téléchargements — Manuel utilisateur officiel INJS 2026</title>
<link rel="stylesheet" href="{lien_css}">
<style>
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; font-family: "Inter", "Segoe UI", Roboto, system-ui, sans-serif;
    background: #EAF3FB; color: #1E293B; line-height: 1.6;
  }}
  .bandeau {{
    background: linear-gradient(120deg, #0B2545, #073763 60%, #0d3f70);
    color: #fff; padding: 34px 22px 30px;
  }}
  .bandeau-inner, .enveloppe {{ max-width: 980px; margin: 0 auto; }}
  .sur-titre {{
    font-size: 11px; letter-spacing: .16em; text-transform: uppercase;
    color: #9EC8F0; font-weight: 700; margin: 0 0 8px;
  }}
  .bandeau h1 {{ font-size: clamp(24px, 4vw, 34px); margin: 0 0 6px; line-height: 1.2; }}
  .bandeau p {{ margin: 0; color: #C9DEF2; font-size: 15px; }}
  .enveloppe {{ padding: 26px 22px 60px; }}
  .grille {{
    display: grid; grid-template-columns: repeat(auto-fill, minmax(295px, 1fr));
    gap: 18px; margin-top: 24px;
  }}
  .carte {{
    background: #fff; border: 1px solid #CBD5E1; border-radius: 12px;
    padding: 20px; display: flex; flex-direction: column;
    box-shadow: 0 1px 3px rgba(15,23,42,.06);
  }}
  .carte h2 {{ font-size: 17px; margin: 0 0 8px; color: #073763; line-height: 1.3; }}
  .carte p {{ margin: 0 0 10px; font-size: 14px; color: #475569; flex: 1; }}
  .meta {{ font-size: 12px; color: #64748B; }}
  .meta code {{ font-family: ui-monospace, monospace; font-size: 11px; }}
  .actions {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }}
  .btn {{
    display: inline-block; padding: 10px 16px; border-radius: 8px;
    background: #073763; color: #fff; text-decoration: none;
    font-size: 13.5px; font-weight: 600; border: 1px solid #073763;
  }}
  .btn:hover {{ background: #0B2545; }}
  .btn-second {{ background: #fff; color: #073763; }}
  .btn-second:hover {{ background: #EAF3FB; }}
  .note {{
    margin-top: 30px; padding: 16px 18px; background: #fff;
    border-left: 4px solid #4A90D9; border-radius: 0 8px 8px 0;
    font-size: 13.5px; color: #475569;
  }}
  .note strong {{ color: #073763; }}
  footer {{ max-width: 980px; margin: 0 auto; padding: 0 22px 40px;
            font-size: 12px; color: #64748B; }}
</style>
</head>
<body>
<header class="bandeau">
  <div class="bandeau-inner">
    <p class="sur-titre">Institut National de la Jeunesse et des Sports — Abidjan</p>
    <h1>Manuel utilisateur officiel — Édition 2026</h1>
    <p>Tous les fichiers de l'édition, prêts à télécharger.</p>
  </div>
</header>

<main class="enveloppe">
  <div class="grille">
{cartes}
  </div>

  <div class="note">
    <p><strong>Comment utiliser ces fichiers.</strong> Le PDF est destiné à
    l'impression et à la diffusion. L'archive HTML se décompresse et s'ouvre
    avec n'importe quel navigateur, sans connexion Internet : la recherche et
    les filtres fonctionnent en local.</p>
    <p><strong>Contenu du manuel interactif.</strong> {nb_images} captures
    d'écran, recherche locale, filtres combinables et bascule clair / sombre.
    Rien n'est chargé depuis un serveur extérieur.</p>
    <p><strong>Édition du {date}.</strong> Les empreintes SHA-256 affichées
    permettent de vérifier qu'un fichier téléchargé est intact.</p>
  </div>
</main>

<footer>
  <p>Manuel utilisateur officiel INJS 2026 — document de formation interne.
  Aucune donnée personnelle n'y figure.</p>
</footer>
</body>
</html>
'''
