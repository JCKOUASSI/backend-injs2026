"""Classification des chapitres du manuel selon deux axes de filtrage.

Les deux axes demandés par le cahier des charges (section 9) sont :

* le **type d'opération** — ce que le chapitre apprend à faire ;
* le **niveau de responsabilité** — à quel niveau hiérarchique l'action se situe.

La classification n'est pas arbitraire : elle est **dérivée du contenu réel** du
chapitre. On examine les verbes et les marqueurs présents dans les titres et les
premiers paragraphes, ainsi que les permissions mentionnées. Chaque chapitre
reçoit un type et un niveau, jamais les deux à la fois de façon contradictoire.

Ces deux attributs alimentent les filtres du manuel HTML ; ils n'inventent aucune
fonctionnalité, ils classent seulement ce qui est déjà écrit.
"""

from __future__ import annotations

import re
import unicodedata

# ─────────────────────────────────────────────── types d'opération
#: Ordre de priorité : le premier motif qui correspond l'emporte.
TYPES = [
    ("consultation", (
        r"\bconsulter\b", r"\bconsultation\b", r"\blire\b", r"\bvisualiser\b",
        r"\bcomprendre\b", r"\bprésentation\b", r"\bterminologie\b",
        r"\bse repérer\b", r"\bnavigation\b",
    )),
    ("creation", (
        r"\bcr[ée]er\b", r"\bcr[ée]ation\b", r"\bajouter\b", r"\bsaisir\b",
        r"\benregistrer\b", r"\binscrire\b", r"\bconstruire\b", r"\bélaborer\b",
        r"\bgener[er]?\b", r"\bimporter\b",
    )),
    ("modification", (
        r"\bmodifier\b", r"\bmodification\b", r"\bmettre à jour\b",
        r"\bcorriger\b", r"\brattraper\b", r"\brattrapage\b", r"\breporter\b",
        r"\bd[ée]placer\b", r"\br[ée]activer\b", r"\brenouveler\b",
    )),
    ("validation", (
        r"\bvalider\b", r"\bvalidation\b", r"\bapprouver\b", r"\bcertifier\b",
        r"\bsigner\b", r"\bpublier\b", r"\bpublication\b", r"\bverrouiller\b",
        r"\bcl[oô]turer\b", r"\bd[ée]lib[ée]ration\b", r"\bdipl[oô]mation\b",
        r"\bjury\b", r"\bjurys\b",
    )),
    ("suppression", (
        r"\bsupprimer\b", r"\bsuppression\b", r"\bannuler\b", r"\bannulation\b",
        r"\barchiver\b", r"\bd[ée]sactiver\b", r"\br[ée]voquer\b",
    )),
    ("export", (
        r"\bexporter\b", r"\bexport\b", r"\bexports\b", r"\bimprimer\b",
        r"\bimpression\b", r"\bediter\b", r"\b[ée]diter\b", r"\brelev[ée]\b",
        r"\battestation\b", r"\bfichier\b",
    )),
]

# ─────────────────────────────────────────────── niveaux de responsabilité
#: N1 — tout agent ; N2 — agent formé ; N3 — responsable ; N4 — administration.
NIVEAUX = [
    ("N4-administration", (
        r"\br[oô]le(s)?\b", r"\bpermission", r"\bhabilitation", r"\bparam[èe]tre",
        r"\bcompte utilisateur\b", r"\battribuer\b", r"\bconfiguration\b",
        r"\bd[ée]l[ée]gation\b", r"\baudit\b", r"\btra[çc]abilit[ée]\b",
        r"\bs[ée]curit[ée]\b", r"\bconnexion et\b",
    )),
    ("N3-validation", (
        r"\bvalider\b", r"\bvalidation\b", r"\bd[ée]lib[ée]ration\b",
        r"\bjury\b", r"\bjurys\b", r"\bdipl[oô]me\b", r"\bpublier\b",
        r"\bpublication\b", r"\bsigner\b", r"\bverrouiller\b", r"\bcertifier\b",
        r"\br[ée]voquer\b", r"\bcontr[oô]ler\b", r"\bcontr[oô]le\b",
    )),
    ("N2-saisie", (
        r"\bsaisir\b", r"\bcr[ée]er\b", r"\bmodifier\b", r"\benregistrer\b",
        r"\binscrire\b", r"\bconstruire\b", r"\b[ée]laborer\b",
        r"\b[ée]margement\b", r"\bbadgeage\b", r"\bprogresser\b",
    )),
    ("N1-consultation", (
        r"\bconsulter\b", r"\bconsulter\b", r"\bconsulter\b", r"\bconsulter\b",
        r"\bpr[ée]sentation\b", r"\bcomprendre\b", r"\bterminologie\b",
        r"\bse rep[ée]rer\b", r"\bnavigation\b", r"\bg[ée]n[ée]ral\b",
    )),
]

#: Repli quand aucun motif ne correspond : la consultation est le niveau
#: minimal, elle ne peut pas être fausse par excès.
#: Un chapitre de présentation reste une consultation, quel que soit son corps.
TITRES_PRESENTATION = (
    r"a quoi sert", r"presentation", r"organisation generale",
    r"terminologie", r"prerequis", r"qu'est-ce", r"vue d'ensemble",
    r"introduction", r"comprendre",
)

TYPE_DEFAUT = "consultation"
NIVEAU_DEFAUT = "N1-consultation"


def _normaliser(texte: str) -> str:
    texte = unicodedata.normalize("NFD", texte.lower())
    return "".join(c for c in texte if unicodedata.category(c) != "Mn")


def _texte_chapitre(chapitre: dict) -> str:
    """Concatène le titre et les textes des blocs, en texte brut."""
    morceaux = [chapitre.get("titre", "")]
    for bloc in chapitre.get("blocs", []):
        genre = bloc[0] if bloc else ""
        valeur = bloc[1] if len(bloc) > 1 else None
        if isinstance(valeur, str):
            morceaux.append(valeur)
        elif isinstance(valeur, dict):
            for cle in ("titre", "texte", "legende"):
                if isinstance(valeur.get(cle), str):
                    morceaux.append(valeur[cle])
            for ligne in valeur.get("lignes", []) or []:
                if isinstance(ligne, (list, tuple)):
                    morceaux.extend(str(c) for c in ligne)
        elif isinstance(valeur, (list, tuple)):
            morceaux.extend(str(c) for c in valeur if isinstance(c, str))
    return _normaliser(" ".join(morceaux))


def _correspond(texte_normalise: str, motifs) -> bool:
    return any(re.search(m, texte_normalise) for m in motifs)


def classifier(chapitre: dict) -> tuple[str, str]:
    """Retourne (type d'opération, niveau de responsabilité) du chapitre.

    Le titre est déterminant : un chapitre intitulé « À quoi sert cette
    application » est une présentation, quels que soient les verbes employés
    dans son corps de texte. Le corps ne sert qu'à départager les titres
    muets (par exemple « Opérations sensibles »).
    """
    titre = _normaliser(chapitre.get("titre", ""))
    texte = _texte_chapitre(chapitre)

    # Cas explicite : un chapitre de présentation est une consultation.
    if re.search(TITRES_PRESENTATION[0], titre) or any(
            re.search(m, titre) for m in TITRES_PRESENTATION[1:]):
        return "consultation", "N1-consultation"

    def choisir(catalogue, defaut):
        # 1. le titre seul
        for nom, motifs in catalogue:
            if _correspond(titre, motifs):
                return nom
        # 2. titre + corps
        for nom, motifs in catalogue:
            if _correspond(texte, motifs):
                return nom
        return defaut

    type_ = choisir(TYPES, TYPE_DEFAUT)
    niveau = choisir(NIVEAUX, NIVEAU_DEFAUT)

    # Cohérence : un chapitre de consultation n'est pas classé N4 par un mot
    # isolé. On ne corrige que les cas manifestement contradictoires.
    if type_ == "consultation" and niveau == "N4-administration":
        niveau = "N1-consultation"

    return type_, niveau


def statistiques(chapitres: list) -> dict:
    """Répartition des chapitres par type et par niveau (pour le rapport)."""
    par_type: dict[str, int] = {}
    par_niveau: dict[str, int] = {}
    for ch in chapitres:
        t, n = classifier(ch)
        par_type[t] = par_type.get(t, 0) + 1
        par_niveau[n] = par_niveau.get(n, 0) + 1
    return {"types": par_type, "niveaux": par_niveau, "total": len(chapitres)}


LIBELLES_TYPES = {
    "consultation": "Consultation",
    "creation": "Création",
    "modification": "Modification",
    "validation": "Validation",
    "suppression": "Suppression",
    "export": "Export / impression",
}

LIBELLES_NIVEAUX = {
    "N1-consultation": "N1 — Consultation",
    "N2-saisie": "N2 — Saisie",
    "N3-validation": "N3 — Validation",
    "N4-administration": "N4 — Administration",
}
