#!/usr/bin/env python3
"""Génère le manuel HTML interactif autonome.

Sortie : documentation/manuel_utilisateur/html/index.html
Aucune dépendance externe : CSS et JavaScript sont écrits dans le document.
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

from socle import (
    APPLICATION, CAPTURES, DATE_GENERATION, EDITION, INSTITUTION, LISTE_PROFILS,
    META, MODULES, PALETTE, RACINE, ROLES, SECTIONS, TITRE, VERSION_DOC,
    modules_par_sensibilite, roles_par_famille, roles_sensibles,
)
from fiches import construire_fiches
from matrice import construire_matrice
from classement import classifier, LIBELLES_TYPES, LIBELLES_NIVEAUX


def _charger_permissions() -> frozenset:
    """Les 1 157 permissions réelles, dépliées depuis le catalogue du backend.

    Le fichier `sources/referentiels/permissions.json` est produit par
    `sources/contenu/extraire_permissions.py`, qui lit le catalogue et non une
    liste recopiée à la main : aucune permission ne peut être inventée.
    """
    import json
    from pathlib import Path as _P
    f = _P(__file__).resolve().parents[2] / "sources" / "referentiels" / "permissions.json"
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return frozenset()
    return frozenset(p["code"] for p in d.get("permissions", []))


PERMISSIONS_CONNUES = _charger_permissions()


def _charger_permissions_critiques() -> frozenset:
    """Les 15 permissions critiques, telles que publiées dans le référentiel."""
    import json
    from pathlib import Path as _P
    f = _P(__file__).resolve().parents[2] / "sources" / "referentiels" / "rbac.json"
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return frozenset()
    return frozenset(d.get("permissions_critiques", []) or [])


PERMISSIONS_CRITIQUES = _charger_permissions_critiques()
from parties_1_3 import PARTIE_I, PARTIE_II, PARTIE_III
from parties_4_7 import PARTIE_IV, PARTIE_V, PARTIE_VI, PARTIE_VII
from parties_8_12 import PARTIE_VIII, PARTIE_IX, PARTIE_X, PARTIE_XI, PARTIE_XII

SORTIE = RACINE / "html"
IMAGES = "images"

# ────────────────────────────────────────────────────────── rendu markdown léger
def md(texte: str) -> str:
    """Convertit **gras**, `code` et les retours à la ligne en HTML."""
    t = html.escape(texte)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"`(.+?)`", r"<code>\1</code>", t)
    return t


def esc(texte) -> str:
    return html.escape(str(texte))


# ────────────────────────────────────────────────────────── rendu des blocs
def rendre_bloc(bloc, index_fiche=None) -> str:
    genre = bloc[0]
    valeur = bloc[1] if len(bloc) > 1 else None

    if genre == "p":
        return f"<p>{md(valeur)}</p>"

    if genre == "h3":
        return f"<h3>{md(valeur)}</h3>"

    if genre == "liste":
        items = "".join(f"<li>{md(x)}</li>" for x in valeur)
        return f"<ul class=\"liste-puces\">{items}</ul>"

    if genre == "etapes":
        items = "".join(
            f"<li><span class=\"num\">{i}</span><span>{md(x)}</span></li>"
            for i, x in enumerate(valeur, 1)
        )
        return f"<ol class=\"liste-etapes\">{items}</ol>"

    if genre == "encadre":
        type_ = valeur.get("type", "information")
        icones = {"information": "ℹ", "attention": "⚠", "danger": "⛔"}
        return (
            f"<aside class=\"encadre encadre-{type_}\">"
            f"<div class=\"encadre-titre\"><span class=\"encadre-ico\">"
            f"{icones.get(type_, 'ℹ')}</span>{esc(valeur.get('titre', ''))}</div>"
            f"<div class=\"encadre-corps\">{md(valeur.get('texte', ''))}</div>"
            f"</aside>"
        )

    if genre == "figure":
        img = valeur["image"]
        titre = esc(valeur.get("titre", ""))
        legende = md(valeur.get("legende", ""))
        return (
            f"<figure class=\"figure-capture\">"
            f"<div class=\"figure-cadre\">"
            f"<img src=\"{IMAGES}/{esc(img)}\" alt=\"{titre}\" loading=\"lazy\" "
            f"onclick=\"ouvrirApercu(this.src, this.alt)\">"
            f"</div>"
            f"<figcaption><strong>{titre}</strong><span>{legende}</span>"
            f"<em class=\"figure-zoom\">Cliquer pour agrandir</em></figcaption>"
            f"</figure>"
        )

    if genre == "tableau":
        entetes = "".join(f"<th>{esc(e)}</th>" for e in valeur["entetes"])
        lignes = ""
        for ligne in valeur["lignes"]:
            cellules = "".join(f"<td>{md(c)}</td>" for c in ligne)
            lignes += f"<tr>{cellules}</tr>"
        return (
            f"<div class=\"tableau-defilant\"><table class=\"tableau\">"
            f"<thead><tr>{entetes}</tr></thead><tbody>{lignes}</tbody></table></div>"
        )

    if genre == "formule":
        return f"<div class=\"formule\">{esc(valeur)}</div>"

    if genre == "tableau_modules_navigation":
        lignes = ""
        for s in SECTIONS:
            enfants = len(s["enfants"])
            apercu = ", ".join(e["libelle"] for e in s["enfants"][:3])
            if enfants > 3:
                apercu += f", … (+{enfants - 3})"
            lignes += (
                f"<tr><td><strong>{esc(s['libelle'])}</strong></td>"
                f"<td class=\"num\">{enfants}</td>"
                f"<td><code>{esc(s.get('chemin') or '—')}</code></td>"
                f"<td>{esc(apercu) if apercu else '—'}</td></tr>"
            )
        return (
            "<div class=\"tableau-defilant\"><table class=\"tableau\">"
            "<thead><tr><th>Module de navigation</th><th>Écrans</th>"
            "<th>Point d'entrée</th><th>Écrans principaux</th></tr></thead>"
            f"<tbody>{lignes}</tbody></table></div>"
        )

    if genre == "tableau_modules_rbac":
        lignes = ""
        for m in MODULES:
            badge = "<span class=\"badge badge-sensible\">sensible</span>" if m["sensible"] else ""
            lignes += (
                f"<tr><td><code>{esc(m['code'])}</code></td>"
                f"<td>{esc(m['libelle'])}</td>"
                f"<td><code>{esc(m['app'])}</code></td><td>{badge}</td></tr>"
            )
        return (
            "<div class=\"tableau-defilant\"><table class=\"tableau\">"
            "<thead><tr><th>Code</th><th>Domaine</th><th>Application</th>"
            "<th>Nature</th></tr></thead>"
            f"<tbody>{lignes}</tbody></table></div>"
        )

    if genre == "tableau_permissions_critiques":
        from socle import RBAC
        lignes = ""
        for code in RBAC["permissions_critiques"]:
            lignes += (
                f"<tr><td><code>{esc(code)}</code></td>"
                f"<td>{esc(code.split('.')[0])}</td>"
                f"<td>{esc(code.split('.')[-1])}</td></tr>"
            )
        return (
            "<div class=\"tableau-defilant\"><table class=\"tableau\">"
            "<thead><tr><th>Permission</th><th>Domaine</th><th>Action</th>"
            "</tr></thead>"
            f"<tbody>{lignes}</tbody></table></div>"
        )

    if genre == "roles_par_famille":
        blocs = ""
        for libelle, roles in roles_par_famille():
            lignes = ""
            for r in roles:
                badge = ("<span class=\"badge badge-sensible\">sensible</span>"
                         if r["sensible"] else "")
                lignes += (
                    f"<tr><td><code>{esc(r['code'])}</code></td>"
                    f"<td>{esc(r['libelle'])}</td>"
                    f"<td class=\"centre\">N{r['niveau'][1]}</td>"
                    f"<td>{esc(r['perimetre'])}</td>"
                    f"<td>{badge}</td></tr>"
                )
            blocs += (
                f"<details class=\"famille-roles\" open>"
                f"<summary><span>{esc(libelle)}</span>"
                f"<span class=\"compteur\">{len(roles)} rôles</span></summary>"
                f"<div class=\"tableau-defilant\"><table class=\"tableau\">"
                f"<thead><tr><th>Code</th><th>Libellé</th><th>Niv.</th>"
                f"<th>Périmètre</th><th></th></tr></thead><tbody>{lignes}</tbody>"
                f"</table></div></details>"
            )
        return blocs

    if genre == "glossaire":
        entrees = [
            ("Admission", "Décision par laquelle un candidat est déclaré apte à rejoindre "
                          "l'institut. Distincte de l'inscription."),
            ("Affectation", "Rattachement d'une personne à une structure, une formation ou "
                            "un groupe."),
            ("Bilan", "Synthèse chiffrée produite par le module Statistiques."),
            ("Candidature", "Dossier déposé par un candidat en vue d'une admission."),
            ("Délibération", "Réunion au cours de laquelle le jury arrête les décisions."),
            ("Délégation", "Transfert temporaire et borné de droits à un autre agent."),
            ("ECUE", "Élément constitutif d'une unité d'enseignement."),
            ("ECTS", "Système européen de transfert de crédits. 30 crédits par semestre."),
            ("Émargement", "Enregistrement de la présence des étudiants à une séance."),
            ("Habilitation", "Droit accordé à un compte, résultant d'un rôle et d'un "
                             "périmètre."),
            ("Maquette", "Document décrivant l'organisation des UE d'une formation par "
                         "semestre."),
            ("Périmètre", "Étendue à l'intérieur de laquelle un droit produit ses effets."),
            ("Permission", "Autorisation précise au format module.ressource.action."),
            ("Rôle", "Fonction exercée, porteuse d'un ensemble de permissions."),
            ("Verrouillage", "Clôture de la saisie des notes, rendant toute modification "
                             "soumise à procédure."),
            ("UE", "Unité d'enseignement, composée d'un ou plusieurs ECUE."),
        ]
        lignes = "".join(
            f"<tr><td><strong>{esc(t)}</strong></td><td>{esc(d)}</td></tr>"
            for t, d in sorted(entrees)
        )
        return (
            "<div class=\"tableau-defilant\"><table class=\"tableau glossaire\">"
            "<thead><tr><th>Terme</th><th>Définition</th></tr></thead>"
            f"<tbody>{lignes}</tbody></table></div>"
        )

    if genre == "problemes":
        blocs = ""
        for pb in valeur:
            blocs += (
                f"<div class=\"probleme\" data-recherche=\"{esc(pb['symptome'])}\">"
                f"<h4 class=\"probleme-titre\">{esc(pb['symptome'])}</h4>"
                f"<dl class=\"probleme-grille\">"
                f"<dt>Cause probable</dt><dd>{md(esc(pb['cause']))}</dd>"
                f"<dt>Vérification</dt><dd>{md(esc(pb['verification']))}</dd>"
                f"<dt>Solution</dt><dd class=\"sol\">{md(esc(pb['solution']))}</dd>"
                f"<dt>Contact</dt><dd>{esc(pb['contact'])}</dd>"
                f"</dl></div>"
            )
        return blocs

    return f"<p class=\"erreur-rendu\">[bloc non rendu : {esc(genre)}]</p>"


# ────────────────────────────────────────────────────────── rendu des chapitres
def rendre_chapitre(ch, partie_id, numero_ch, profil_courant=None) -> str:
    blocs = "".join(rendre_bloc(b) for b in ch["blocs"])
    profils = ch.get("profils", ["tous"])
    marques = ", ".join(profils) if profils != ["tous"] else "Tous les profils"
    data_profils = " ".join(profils)
    type_op, niveau_resp = classifier(ch)
    return (
        f"<section class=\"chapitre\" id=\"{ch['id']}\" "
        f"data-profils=\"{esc(data_profils)}\" data-partie=\"{partie_id}\" "
        f"data-operation=\"{esc(type_op)}\" data-niveau=\"{esc(niveau_resp)}\">"
        f"<div class=\"chapitre-entete\">"
        f"<span class=\"chapitre-num\">{partie_id.split('-')[1]}.{numero_ch}</span>"
        f"<h2>{esc(ch['titre'])}</h2></div>"
        f"<p class=\"chapitre-profils\"><span>Profils concernés :</span> "
        f"<strong>{esc(marques)}</strong></p>"
        f"<div class=\"chapitre-corps\">{blocs}</div></section>"
    )


def rendre_partie(partie) -> str:
    pid = partie["id"]
    chapitres = "".join(
        rendre_chapitre(ch, pid, i)
        for i, ch in enumerate(partie["chapitres"], 1)
    )
    return (
        f"<div class=\"partie\" id=\"{pid}\" data-partie=\"{pid}\">"
        f"<header class=\"partie-entete\">"
        f"<span class=\"partie-num\">Partie {partie['numero']}</span>"
        f"<h1>{esc(partie['titre'])}</h1></header>{chapitres}</div>"
    )


# ────────────────────────────────────────────────────────── fiches profils
def rendre_fiche(fiche) -> str:
    sections_html = ""
    for nom_section, menus in fiche["sections"]:
        lignes = "".join(
            f"<tr><td>{esc(m['libelle'])}</td>"
            f"<td><code>{esc(m['chemin'] or '—')}</code></td></tr>"
            for m in menus
        )
        sections_html += (
            f"<details class=\"section-menu\"><summary>{esc(nom_section)}"
            f"<span class=\"compteur\">{len(menus)}</span></summary>"
            f"<div class=\"tableau-defilant\"><table class=\"tableau tableau-compact\">"
            f"<tbody>{lignes}</tbody></table></div></details>"
        )
    if not sections_html:
        sections_html = (
            "<p class=\"vide\">Ce profil n'a aucun écran dans l'interface web. "
            "Ses accès passent par les applications mobiles.</p>"
        )

    capacites = "".join(f"<li>{esc(c)}</li>" for c in fiche["capacites"]) or \
        "<li class=\"vide\">Aucune capacité web</li>"
    interdits = "".join(f"<li>{esc(c)}</li>" for c in fiche["interdits"]) or \
        "<li class=\"vide\">—</li>"

    cas_html = ""
    for titre_cas, contexte, etapes in fiche["cas"]:
        et = "".join(f"<li>{esc(e)}</li>" for e in etapes)
        cas_html += (
            f"<div class=\"cas-pratique\"><h4>{esc(titre_cas)}</h4>"
            f"<p class=\"cas-contexte\">{esc(contexte)}</p>"
            f"<ol class=\"liste-etapes\">{et}</ol></div>"
        )

    erreurs_html = "".join(
        f"<div class=\"erreur-item\"><strong>{esc(s)}</strong>"
        f"<span>{esc(c)}</span></div>"
        for s, c in fiche["erreurs"]
    ) or "<p class=\"vide\">—</p>"

    badge_web = ("<span class=\"badge badge-ok\">Accès web</span>" if fiche["web"]
                 else "<span class=\"badge badge-non\">Sans accès web</span>")

    return f"""
<div class="fiche" id="profil-{fiche['code']}" data-profil="{fiche['code']}"
     data-ecrans="{fiche['ecrans_visibles']}">
  <header class="fiche-entete">
    <div class="fiche-avatar">{esc(fiche['nom'][0])}</div>
    <div class="fiche-titres">
      <h1>{esc(fiche['nom'])}</h1>
      <p>{esc(fiche['fonction'])}</p>
    </div>
    <div class="fiche-badges">
      {badge_web}
      <span class="badge badge-neutre">{fiche['ecrans_visibles']} écrans</span>
    </div>
  </header>

  <div class="fiche-corps">
    <section class="fiche-section">
      <h3>A. Présentation</h3>
      <p>{esc(fiche['description'])}</p>
      <dl class="fiche-meta">
        <dt>Code technique</dt><dd><code>{esc(fiche['code'])}</code></dd>
        <dt>Famille</dt><dd>{esc(fiche['famille'])}</dd>
        <dt>Niveaux d'accès</dt><dd>{esc(fiche['niveaux'])}</dd>
        <dt>Applications</dt><dd>{esc(fiche['apps'])}</dd>
        <dt>Actions backend</dt><dd>{esc(fiche['actions'])}</dd>
      </dl>
    </section>

    <section class="fiche-section">
      <h3>B. Navigation</h3>
      <p class="aide">Sections du menu réellement visibles pour ce profil,
         avec leurs écrans et leur adresse.</p>
      {sections_html}
    </section>

    <section class="fiche-section">
      <h3>C. Autorisations</h3>
      <div class="duo">
        <div class="autorisations-ok">
          <h4>Actions autorisées</h4>
          <ul>{capacites}</ul>
        </div>
        <div class="autorisations-non">
          <h4>Actions interdites</h4>
          <ul>{interdits}</ul>
        </div>
      </div>
    </section>

    <section class="fiche-section">
      <h3>D. Cas pratiques</h3>
      {cas_html or '<p class="vide">—</p>'}
    </section>

    <section class="fiche-section">
      <h3>E. Erreurs fréquentes</h3>
      {erreurs_html}
    </section>
  </div>
</div>
"""


# ─────────────────────────────── index de recherche sémantique
#: Un utilisateur qui cherche « bulletin » doit trouver « relevé de notes »,
#: « absence » doit trouver « présence ». Ces équivalences sont tirées du
#: vocabulaire réellement employé dans les écrans de l'application.
SYNONYMES = {
    "absence": ("presence", "emargement", "assiduite"),
    "presence": ("absence", "emargement", "assiduite"),
    "emargement": ("presence", "absence", "badgeage"),
    "note": ("evaluation", "saisie", "releve", "moyenne", "credit"),
    "bulletin": ("releve", "note", "moyenne", "resultat"),
    "moyenne": ("note", "bulletin", "credit", "resultat"),
    "diplome": ("diplomation", "attestation", "jury", "revocation"),
    "jury": ("deliberation", "diplome", "resultat", "pv"),
    "paiement": ("finance", "recette", "remboursement", "echeance"),
    "frais": ("finance", "paiement", "scolarite"),
    "scolarite": ("finance", "inscription", "paiement"),
    "inscription": ("candidature", "admission", "etudiant"),
    "etudiant": ("apprenant", "inscription", "dossier"),
    "emploi": ("edt", "planning", "creneau", "salle", "seance"),
    "planning": ("emploi", "edt", "creneau", "seance"),
    "salle": ("edt", "planning", "creneau", "reservation"),
    "role": ("permission", "habilitation", "profil", "attribution"),
    "permission": ("role", "habilitation", "droit"),
    "mot": ("passe", "connexion", "authentification"),
    "connexion": ("authentification", "mot de passe", "session"),
    "erreur": ("probleme", "incident", "depannage", "message"),
    "export": ("extraction", "csv", "imprimer", "editer"),
    "rapport": ("etat", "statistique", "indicateur", "tableau"),
}


def _sans_accents(texte: str) -> str:
    import unicodedata
    t = unicodedata.normalize("NFD", texte.lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def construire_index_recherche(chapitres: list) -> str:
    """Sérialise un index JSON : mots-clés, synonymes et permissions réelles.

    L'index est embarqué dans la page : la recherche reste entièrement locale
    et fonctionne hors ligne, sans requête réseau.
    """
    import json
    import re as _re

    entrees = []
    for ch in chapitres:
        corps = []
        for b in ch.get("blocs", []):
            v = b[1] if len(b) > 1 else None
            if isinstance(v, str):
                corps.append(v)
            elif isinstance(v, dict):
                corps.append(str(v.get("titre", "")))
                corps.append(str(v.get("texte", "")))
            elif isinstance(v, (list, tuple)):
                corps.extend(str(x) for x in v if isinstance(x, str))
        texte = _sans_accents(ch.get("titre", "") + " " + " ".join(corps))

        # permissions réelles citées dans le chapitre
        # permissions réelles : celles citées en clair dans le texte, plus
        # celles rendues par un tableau dynamique de permissions critiques.
        candidates = set(_re.findall(r"\b[a-z_]+\.[a-z_]+\.[a-z_]+\b", texte))
        genres = {b[0] for b in ch.get("blocs", []) if b}
        if "tableau_permissions_critiques" in genres:
            candidates.update(PERMISSIONS_CRITIQUES)
        perms = sorted(c for c in candidates if c in PERMISSIONS_CONNUES)

        # mots-clés : termes du titre + synonymes déclenchés
        mots = set(_re.findall(r"[a-z]{4,}", _sans_accents(ch.get("titre", ""))))
        for declencheur, equivalents in SYNONYMES.items():
            if declencheur in texte:
                mots.update(equivalents)

        entrees.append({
            "id": ch["id"],
            "titre": ch.get("titre", ""),
            "mots": sorted(mots),
            "permissions": perms,
        })

    return json.dumps(entrees, ensure_ascii=False, separators=(",", ":"))


def rendre_matrice() -> str:
    """Partie XIV — matrice Profil | Modules | CRUD | Export, en HTML accessible."""
    colonnes, lignes, modules = construire_matrice()
    libelles = dict(modules)
    entetes = ["Profil", "Modules accessibles", "Consultation", "Création",
               "Modification", "Validation", "Suppression", "Export"]
    out = ['<div class="tableau-defilant"><table class="tableau matrice">',
           '<caption>Matrice des habilitations : 12 profils, '
           f'{len(modules)} modules, {len(colonnes)} opérations</caption>',
           '<thead><tr>']
    for h in entetes:
        out.append(f'<th scope="col">{esc(h)}</th>')
    out.append('</tr></thead><tbody>')
    for l in lignes:
        noms = ", ".join(libelles.get(m, m) for m in l["modules"]) or "—"
        if not l["web"]:
            noms = "Aucun — accès web fermé"
        out.append(f'<tr data-profil="{esc(l["profil"])}">')
        out.append(f'<th scope="row">{esc(l["profil"])}</th>')
        out.append(f'<td class="modules">{esc(noms)}</td>')
        for c, _ in colonnes:
            v = l["cellules"].get(c)
            actif = isinstance(v, list) and v
            if actif:
                out.append('<td class="oui" data-etat="oui">'
                           f'<span aria-label="Oui">{len(v)} module(s)</span></td>')
            else:
                out.append('<td class="non" data-etat="non">'
                           '<span aria-label="Non">—</span></td>')
        out.append('</tr>')
    out.append('</tbody></table></div>')

    out.append('<p class="note-matrice">« Oui » signifie que l\'opération est '
               'autorisée sur au moins une ressource du module, dans le périmètre du '
               'profil. Le nombre indique combien de modules sont concernés. '
               'Une opération autorisée ne l\'est pas nécessairement sur '
               '<em>toutes</em> les ressources du module.</p>')

    # légende des modules
    out.append('<div class="legende-modules"><h3>Correspondance des modules</h3><ol>')
    for code, lib in modules:
        out.append(f'<li><span class="code-module">{esc(code)}</span> {esc(lib)}</li>')
    out.append('</ol></div>')
    return "\n".join(out)


def construire():
    SORTIE.mkdir(parents=True, exist_ok=True)

    parties = [rendre_partie(p) for p in (
        PARTIE_I, PARTIE_II, PARTIE_III, PARTIE_IV, PARTIE_V, PARTIE_VI,
        PARTIE_VII, PARTIE_VIII, PARTIE_IX, PARTIE_X, PARTIE_XI, PARTIE_XII,
    )]
    fiches = construire_fiches()
    fiches_html = "".join(rendre_fiche(f) for f in fiches)

    # Sommaire
    sommaire_parties = ""
    for p in (PARTIE_I, PARTIE_II, PARTIE_III, PARTIE_IV, PARTIE_V, PARTIE_VI,
              PARTIE_VII, PARTIE_VIII, PARTIE_IX, PARTIE_X, PARTIE_XI, PARTIE_XII):
        sous = "".join(
            f"<li><a href=\"#{ch['id']}\" data-nav>{esc(ch['titre'])}</a></li>"
            for ch in p["chapitres"]
        )
        sommaire_parties += (
            f"<li class=\"nav-partie\">"
            f"<a href=\"#{p['id']}\" data-nav class=\"nav-partie-lien\">"
            f"<span class=\"nav-num\">{p['numero']}</span>{esc(p['titre'])}</a>"
            f"<ul class=\"nav-sous\">{sous}</ul></li>"
        )
    sommaire_profils = "".join(
        f"<li><a href=\"#profil-{f['code']}\" data-nav>{esc(f['nom'])}"
        f"<span class=\"nav-compte\">{f['ecrans_visibles']}</span></a></li>"
        for f in fiches
    )

    index_recherche = [
        {"t": p["titre"], "u": f"#{p['id']}", "k": "partie"}
        for p in (PARTIE_I, PARTIE_II, PARTIE_III, PARTIE_IV, PARTIE_V, PARTIE_VI,
                  PARTIE_VII, PARTIE_VIII, PARTIE_IX, PARTIE_X, PARTIE_XI, PARTIE_XII)
    ]
    for p in (PARTIE_I, PARTIE_II, PARTIE_III, PARTIE_IV, PARTIE_V, PARTIE_VI,
              PARTIE_VII, PARTIE_VIII, PARTIE_IX, PARTIE_X, PARTIE_XI, PARTIE_XII):
        for ch in p["chapitres"]:
            index_recherche.append({"t": ch["titre"], "u": f"#{ch['id']}",
                                    "k": "chapitre"})
    for f in fiches:
        index_recherche.append({"t": f["nom"], "u": f"#profil-{f['code']}",
                                "k": "profil"})

    stat = {
        "roles": len(ROLES), "sensibles": len(roles_sensibles()),
        "permissions": META["permissions"], "modules": len(MODULES),
        "profils": len(fiches), "ecrans_menu": META["entrees_menu"],
        "captures": len(CAPTURES), "chapitres": sum(
            len(p["chapitres"]) for p in (PARTIE_I, PARTIE_II, PARTIE_III, PARTIE_IV,
                                          PARTIE_V, PARTIE_VI, PARTIE_VII, PARTIE_VIII,
                                          PARTIE_IX, PARTIE_X, PARTIE_XI, PARTIE_XII)),
    }

    gabarit = (Path(__file__).parent / "gabarit.html").read_text(encoding="utf-8")
    contenu = gabarit
    remplacements = {
        "{{INSTITUTION}}": esc(INSTITUTION),
        "{{TITRE}}": esc(TITRE),
        "{{EDITION}}": esc(EDITION),
        "{{APPLICATION}}": esc(APPLICATION),
        "{{VERSION}}": esc(VERSION_DOC),
        "{{DATE}}": esc(DATE_GENERATION),
        "{{SOMMAIRE_PARTIES}}": sommaire_parties,
        "{{SOMMAIRE_PROFILS}}": sommaire_profils,
        "{{PARTIES}}": "".join(parties),
        "{{FICHES}}": fiches_html,
        "{{MATRICE}}": rendre_matrice(),
        "{{INDEX_RECHERCHE}}": construire_index_recherche(
            [ch for p in (PARTIE_I, PARTIE_II, PARTIE_III, PARTIE_IV, PARTIE_V,
                          PARTIE_VI, PARTIE_VII, PARTIE_VIII, PARTIE_IX,
                          PARTIE_X, PARTIE_XI, PARTIE_XII)
             for ch in p["chapitres"]]),
        "{{OPTIONS_OPERATION}}": "".join(
            f'<option value="{c}">{esc(LIBELLES_TYPES[c])}</option>'
            for c, _ in [("consultation", 0), ("creation", 0), ("modification", 0),
                         ("validation", 0), ("suppression", 0), ("export", 0)]),
        "{{OPTIONS_NIVEAU}}": "".join(
            f'<option value="{c}">{esc(LIBELLES_NIVEAUX[c])}</option>'
            for c in ("N1-consultation", "N2-saisie", "N3-validation",
                      "N4-administration")),
        "{{STAT}}": json.dumps(stat, ensure_ascii=False),
        "{{RECHERCHE}}": json.dumps(index_recherche, ensure_ascii=False),
        "{{NB_ROLES}}": f"{stat['roles']}",
        "{{NB_SENSIBLES}}": f"{stat['sensibles']}",
        "{{NB_PERMISSIONS}}": f"{stat['permissions']:,}".replace(",", " "),
        "{{NB_PROFILS}}": f"{stat['profils']}",
        "{{NB_CHAPITRES}}": f"{stat['chapitres']}",
        "{{NB_CAPTURES}}": f"{stat['captures']}",
        "{{NB_MODULES}}": f"{stat['modules']}",
        "{{NB_ECRANS}}": f"{stat['ecrans_menu']}",
    }
    for cle, val in remplacements.items():
        contenu = contenu.replace(cle, val)

    cible = SORTIE / "index.html"
    cible.write_text(contenu, encoding="utf-8")

    # CSS et JS séparés (exigence d'arborescence), mais aussi inlinés en secours
    css = (Path(__file__).parent / "style.css").read_text(encoding="utf-8")
    js = (Path(__file__).parent / "script.js").read_text(encoding="utf-8")
    (SORTIE / "css").mkdir(exist_ok=True)
    (SORTIE / "js").mkdir(exist_ok=True)
    (SORTIE / "css" / "manuel.css").write_text(css, encoding="utf-8")
    (SORTIE / "js" / "manuel.js").write_text(js, encoding="utf-8")

    print(f"HTML généré : {cible} ({cible.stat().st_size:,} octets)")
    print(f"  chapitres : {stat['chapitres']} | fiches : {stat['profils']} "
          f"| captures : {stat['captures']}")
    return cible


if __name__ == "__main__":
    construire()
