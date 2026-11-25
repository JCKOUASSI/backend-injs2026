"""
Export DOCX — Synthèse UP (Unité Pédagogique) par matière.

Génère un fichier Word (.docx) au format identique au modèle institutionnel
"SYNTHESE UP <MODULE> FAB SESSION <ANNÉE>" :
  - Une page (section) par groupe ayant des séances pour le module ciblé.
  - En-tête institutionnel : République de Côte d'Ivoire / Ministère / CPFAE-AGC.
  - Tableau de 8 colonnes avec fusion verticale des 4 premières colonnes.

Format de page : A4 paysage, marges réduites (comme le document modèle original).

Note : python-docx est importé lazarement dans _build_document() pour éviter un crash
au démarrage du serveur si la librairie n'est pas encore installée.
"""

from __future__ import annotations

import datetime
from collections import defaultdict
from io import BytesIO
from typing import Optional

from .models import Seance
from .repositories import SeanceRepository

# ---------------------------------------------------------------------------
# Constantes de mise en forme (indépendantes de python-docx)
# ---------------------------------------------------------------------------

_JOURS_FR = {
    0: "LUNDI",
    1: "MARDI",
    2: "MERCREDI",
    3: "JEUDI",
    4: "VENDREDI",
    5: "SAMEDI",
    6: "DIMANCHE",
}
_MOIS_FR = {
    1: "JANVIER",
    2: "FÉVRIER",
    3: "MARS",
    4: "AVRIL",
    5: "MAI",
    6: "JUIN",
    7: "JUILLET",
    8: "AOÛT",
    9: "SEPTEMBRE",
    10: "OCTOBRE",
    11: "NOVEMBRE",
    12: "DÉCEMBRE",
}

_COULEUR_ENTETE_TABLEAU = "BFBFBF"
_COULEUR_DONNEES = "FFFFFF"

# Largeurs de colonnes en twips tirées du modèle original (1 twip = 1/1440 pouce)
_LARGEURS_COL = [3096, 1417, 1560, 1700, 2000, 1461, 1746, 2168]

_ENTETES_COL = [
    "MATIÈRES",
    "VOLUME HORAIRE\nDU MODULE",
    "BATIMENT",
    "SALLE",
    "PÉRIODE",
    "HORAIRE DU COURS",
    "VOLUME HORAIRE\nRESTANT APRÈS\nLE COURS",
    "FORMATEURS",
]


# ---------------------------------------------------------------------------
# Helpers de formatage (sans dépendance docx)
# ---------------------------------------------------------------------------


def _fmt_date(d: datetime.date) -> str:
    return f"{_JOURS_FR[d.weekday()]} {d.day:02d} {_MOIS_FR[d.month]} {d.year}"


def _fmt_heure(t: datetime.time) -> str:
    return f"{t.hour:02d} H"


def _fmt_plage(debut: datetime.time, fin: datetime.time) -> str:
    return f"{_fmt_heure(debut)}-{_fmt_heure(fin)}"


def _fmt_volume(heures: int) -> str:
    return f"{heures:02d} H"


def _formateur_libelle(seance: Seance) -> str:
    nom = (seance.formateur_nom or "").strip()
    prenom = (seance.formateur_prenom or "").strip()
    if nom and prenom:
        return f"{nom} {prenom}".upper()
    return (nom or prenom or "").upper()


def _grade_principal(groupe) -> str:
    from collections import Counter

    grades = [
        (m.auditeur.grade or "").strip().upper()
        for m in groupe.membres.all()
        if getattr(m, "auditeur", None) and (m.auditeur.grade or "").strip()
    ]
    if not grades:
        return ""
    return Counter(grades).most_common(1)[0][0]


# ---------------------------------------------------------------------------
# Construction du document (tout le code docx est ici, importé lazarement)
# ---------------------------------------------------------------------------


def _build_document(
    *,
    module_titre: str,
    annee: int,
    categorie: str,
    groupes_data: list[dict],
    salle_to_batiment: Optional[dict[str, str]] = None,
) -> bytes:
    """
    Construit le fichier DOCX complet et retourne son contenu en bytes.

    ``groupes_data`` est une liste de dicts avec les clés :
        grade, num_groupe, volume_total, formateur, batiment, seances

    ``salle_to_batiment`` est un index ``nom_salle.upper() -> batiment_nom``
    utilisé en fallback lorsque ``seance.batiment_nom`` n'a pas été persisté
    (séances anciennes ou importées sans cette information).
    """
    salle_to_batiment = salle_to_batiment or {}
    try:
        from docx import Document
        from docx.enum.section import WD_ORIENT
        from docx.enum.table import WD_TABLE_ALIGNMENT
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
        from docx.shared import Cm, Pt
    except ImportError as exc:
        raise ImportError(
            "python-docx est requis pour la génération DOCX. " "Installez-le avec : pip install python-docx"
        ) from exc

    # ---- Helpers internes (closures sur les imports docx) ----

    def set_cell_color(cell, hex_color: str) -> None:
        tcPr = cell._tc.get_or_add_tcPr()
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear")
        shd.set(qn("w:color"), "auto")
        shd.set(qn("w:fill"), hex_color)
        tcPr.append(shd)

    def set_cell_borders(cell) -> None:
        tcPr = cell._tc.get_or_add_tcPr()
        tcBorders = OxmlElement("w:tcBorders")
        for side, sz in [("top", "18"), ("left", "18"), ("bottom", "18"), ("right", "4")]:
            el = OxmlElement(f"w:{side}")
            el.set(qn("w:val"), "single")
            el.set(qn("w:sz"), sz)
            el.set(qn("w:space"), "0")
            el.set(qn("w:color"), "auto")
            tcBorders.append(el)
        tcPr.append(tcBorders)

    def set_no_border(cell) -> None:
        tcPr = cell._tc.get_or_add_tcPr()
        tcBorders = OxmlElement("w:tcBorders")
        for side in ["top", "left", "bottom", "right", "insideH", "insideV"]:
            el = OxmlElement(f"w:{side}")
            el.set(qn("w:val"), "none")
            el.set(qn("w:sz"), "0")
            el.set(qn("w:space"), "0")
            el.set(qn("w:color"), "auto")
            tcBorders.append(el)
        tcPr.append(tcBorders)

    def set_vmerge(cell, restart: bool = False) -> None:
        tcPr = cell._tc.get_or_add_tcPr()
        vmerge = OxmlElement("w:vMerge")
        if restart:
            vmerge.set(qn("w:val"), "restart")
        tcPr.append(vmerge)

    def set_cell_width(cell, w_twips: int) -> None:
        tcPr = cell._tc.get_or_add_tcPr()
        tcW = OxmlElement("w:tcW")
        tcW.set(qn("w:w"), str(w_twips))
        tcW.set(qn("w:type"), "dxa")
        tcPr.insert(0, tcW)

    def set_cell_valign(cell, align: str = "center") -> None:
        tcPr = cell._tc.get_or_add_tcPr()
        vAlign = OxmlElement("w:vAlign")
        vAlign.set(qn("w:val"), align)
        tcPr.append(vAlign)

    def write_cell(cell, text: str, font: str = "Tahoma", size: float = 10, bold: bool = False) -> None:
        for p in cell.paragraphs:
            p.clear()
        para = cell.paragraphs[0]
        para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = para.add_run(text)
        run.font.name = font
        run.font.size = Pt(size)
        run.font.bold = bold

    def add_run_styled(para, text: str, font: str = "Tahoma", size: float = 10, bold: bool = False) -> None:
        run = para.add_run(text)
        run.font.name = font
        run.font.size = Pt(size)
        run.font.bold = bold

    # ---- Construction du document ----

    doc = Document()

    # A4 paysage avec marges du modèle
    section = doc.sections[0]
    section.orientation = WD_ORIENT.LANDSCAPE
    section.page_width = Cm(29.7)
    section.page_height = Cm(21.0)
    section.top_margin = Cm(0.5)
    section.bottom_margin = Cm(0.5)
    section.left_margin = Cm(1.0)
    section.right_margin = Cm(1.2)

    for idx, gdata in enumerate(groupes_data):
        if idx > 0:
            doc.add_page_break()

        grade = gdata["grade"]
        num_groupe = gdata["num_groupe"]
        volume_total = gdata["volume_total"]
        formateur = gdata["formateur"]
        batiment = gdata["batiment"]
        seances = gdata["seances"]

        # --- En-tête institutionnel (tableau 2 colonnes sans bordure) ---
        tbl_hdr = doc.add_table(rows=1, cols=2)
        tbl_hdr.alignment = WD_TABLE_ALIGNMENT.CENTER

        cell_gauche = tbl_hdr.rows[0].cells[0]
        cell_droite = tbl_hdr.rows[0].cells[1]
        set_no_border(cell_gauche)
        set_no_border(cell_droite)

        lignes_gauche = [
            ("MINISTÈRE D'ÉTAT, MINISTÈRE DE LA FONCTION PUBLIQUE", True),
            ("ET DE LA MODERNISATION DE L'ADMINISTRATION", False),
            ("DIRECTION GÉNÉRALE DE LA FONCTION PUBLIQUE", False),
            ("DIRECTION DE LA FORMATION ET DU RENFORCEMENT DES CAPACITÉS", False),
            ("CENTRE DE PERFECTIONNEMENT DES FONCTIONNAIRES", False),
            ("ET AGENTS DE L'ÉTAT-AMADOU GON COULIBALY", False),
        ]
        cell_gauche.paragraphs[0].clear()
        for i, (txt, bold) in enumerate(lignes_gauche):
            p = cell_gauche.paragraphs[0] if i == 0 else cell_gauche.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            add_run_styled(p, txt, size=8, bold=bold)

        lignes_droite = [
            ("REPUBLIQUE DE COTE D'IVOIRE", True),
            ("Union – Discipline – Travail", False),
        ]
        cell_droite.paragraphs[0].clear()
        for i, (txt, bold) in enumerate(lignes_droite):
            p = cell_droite.paragraphs[0] if i == 0 else cell_droite.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            add_run_styled(p, txt, font="Arial", size=8, bold=bold)

        # --- Titre ---
        p_titre = doc.add_paragraph()
        p_titre.alignment = WD_ALIGN_PARAGRAPH.CENTER
        add_run_styled(p_titre, f"SYNTHESE UP {module_titre.upper()} FAB SESSION {annee}", size=14, bold=True)

        # --- Catégorie / Grade ---
        grade_str = f" / GRADE {grade}" if grade else ""
        p_cat = doc.add_paragraph()
        p_cat.alignment = WD_ALIGN_PARAGRAPH.CENTER
        add_run_styled(p_cat, f"EMPLOI DU TEMPS CATÉGORIE {categorie}{grade_str}", size=12, bold=True)

        # --- Ligne SITE ... GROUPE ---
        p_sg = doc.add_paragraph()
        add_run_styled(p_sg, "SITE : CPFAE-AGC", size=11, bold=True)
        add_run_styled(p_sg, "\t" * 12, size=11)
        add_run_styled(p_sg, f"GROUPE : {num_groupe}", size=11, bold=True)

        # --- Tableau de séances ---
        if not seances:
            p_vide = doc.add_paragraph("Aucune séance planifiée pour ce module.")
            p_vide.alignment = WD_ALIGN_PARAGRAPH.CENTER
            continue

        n = len(seances)
        tbl = doc.add_table(rows=1 + n, cols=8)
        tbl.style = "Table Grid"
        tbl.alignment = WD_TABLE_ALIGNMENT.CENTER

        # Ligne d'en-tête du tableau
        hdr_row = tbl.rows[0]
        for ci, (txt, w) in enumerate(zip(_ENTETES_COL, _LARGEURS_COL)):
            cell = hdr_row.cells[ci]
            set_cell_width(cell, w)
            set_cell_color(cell, _COULEUR_ENTETE_TABLEAU)
            set_cell_valign(cell, "center")
            set_cell_borders(cell)
            write_cell(cell, txt, size=11, bold=True)

        # Lignes de données
        volume_restant = volume_total
        for ri, seance in enumerate(seances):
            row = tbl.rows[1 + ri]
            dt_d = datetime.datetime.combine(seance.date, seance.heure_debut)
            dt_f = datetime.datetime.combine(seance.date, seance.heure_fin)
            duree_h = int((dt_f - dt_d).total_seconds() // 3600)
            volume_restant -= duree_h

            periode = _fmt_date(seance.date)
            horaire = _fmt_plage(seance.heure_debut, seance.heure_fin)
            vol_str = _fmt_volume(max(0, volume_restant))

            fmt_seance = _formateur_libelle(seance) or formateur
            bat_direct = (seance.batiment_nom or "").strip().upper()
            bat_fallback = salle_to_batiment.get((seance.salle_nom or "").strip().upper(), "").strip().upper()
            bat_seance = bat_direct or bat_fallback or batiment.upper()
            salle_seance = (seance.salle_nom or "").strip().upper()

            for ci in range(8):
                cell = row.cells[ci]
                set_cell_width(cell, _LARGEURS_COL[ci])
                set_cell_color(cell, _COULEUR_DONNEES)
                set_cell_valign(cell, "center")
                set_cell_borders(cell)

                # Colonnes fusionnées verticalement (valeurs constantes pour
                # tout le groupe) : MATIÈRES / VOLUME / BATIMENT / SALLE.
                if ci in (0, 1, 2, 3):
                    set_vmerge(cell, restart=(ri == 0))
                    if ri == 0:
                        vals = [
                            module_titre.upper(),
                            _fmt_volume(volume_total),
                            bat_seance,
                            salle_seance,
                        ]
                        write_cell(cell, vals[ci], size=11, bold=(ci == 0))
                elif ci == 4:
                    write_cell(cell, periode, size=11)
                elif ci == 5:
                    write_cell(cell, horaire, size=11)
                elif ci == 6:
                    write_cell(cell, vol_str, size=11)
                else:
                    write_cell(cell, fmt_seance, size=11)

    buffer = BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Service Django
# ---------------------------------------------------------------------------


class SyntheseUPDocxService:
    """
    Génère le fichier DOCX de synthèse UP (Unité Pédagogique) par matière.

    Entrée : formation_id + module_id.
    Sortie : bytes du fichier .docx prêt à télécharger.

    Une page par groupe ayant au moins une séance pour le module donné.
    """

    def __init__(self, repo: Optional[SeanceRepository] = None) -> None:
        self._repo = repo or SeanceRepository()

    def exporter(
        self,
        formation_id: int,
        module_id: int,
        groupe_id: Optional[int] = None,
    ) -> bytes:
        """
        Génère la synthèse DOCX.

        - ``groupe_id=None`` → toutes les pages des groupes de la formation pour ce module.
        - ``groupe_id=<id>`` → uniquement la page du groupe ciblé.
        """
        from apps.formations.models import Formation, FormationModule
        from apps.groupes.models import Groupe
        from apps.parametrage.models import Salle
        from apps.referentiels.models import Module

        formation = Formation.objects.select_related("type_formation").get(pk=formation_id)
        module = Module.objects.get(pk=module_id)

        salle_to_batiment: dict[str, str] = {
            (s.nom or "").strip().upper(): (s.batiment.nom if s.batiment_id and s.batiment else "")
            for s in Salle.objects.select_related("batiment").all()
        }

        fm = FormationModule.objects.filter(formation_id=formation_id, module_id=module_id).first()
        volume_defaut = fm.volume_horaire if fm and fm.volume_horaire else 0
        formateur_defaut = ""
        if fm:
            nom = (fm.formateur_nom or "").strip()
            prenom = (fm.formateur_prenom or "").strip()
            formateur_defaut = f"{nom} {prenom}".upper().strip() if nom and prenom else (nom or prenom or "").upper()

        categorie = fm.grade_cible.split("/")[0].strip().upper() if (fm and fm.grade_cible) else "A"
        annee = formation.date_debut.year if formation.date_debut else datetime.date.today().year

        groupes_qs = (
            Groupe.objects.filter(formation_id=formation_id)
            .select_related("formation", "formation__type_formation", "config")
            .prefetch_related("membres__auditeur")
            .order_by("nom", "pk")
        )
        if groupe_id is not None:
            groupes_qs = groupes_qs.filter(pk=groupe_id)
        groupes = list(groupes_qs)

        seances_qs = Seance.objects.filter(
            groupe__formation_id=formation_id,
            module_id=module_id,
        )
        if groupe_id is not None:
            seances_qs = seances_qs.filter(groupe_id=groupe_id)
        toutes_seances = list(
            seances_qs.select_related("module", "groupe").order_by("date", "heure_debut", "heure_fin", "pk")
        )
        seances_par_groupe: dict[int, list[Seance]] = defaultdict(list)
        for s in toutes_seances:
            seances_par_groupe[s.groupe_id].append(s)

        groupes_data = []
        for groupe in groupes:
            seances = seances_par_groupe.get(groupe.pk, [])
            if not seances:
                continue

            grade = _grade_principal(groupe)
            if not grade and fm and fm.grade_cible:
                grade = fm.grade_cible.upper()

            volume_total = (
                sum(
                    int(
                        (
                            datetime.datetime.combine(s.date, s.heure_fin)
                            - datetime.datetime.combine(s.date, s.heure_debut)
                        ).total_seconds()
                        // 3600
                    )
                    for s in seances
                )
                or volume_defaut
            )

            formateur = next(
                (_formateur_libelle(s) for s in seances if s.formateur_nom),
                formateur_defaut,
            )
            num_groupe = groupe.nom.replace("GROUPE", "").replace("Groupe", "").strip() or groupe.nom

            batiment_groupe = next(
                ((s.batiment_nom or "").strip().upper() for s in seances if (s.batiment_nom or "").strip()),
                "",
            )
            if not batiment_groupe:
                batiment_groupe = next(
                    (
                        salle_to_batiment.get((s.salle_nom or "").strip().upper(), "").strip().upper()
                        for s in seances
                        if (s.salle_nom or "").strip()
                    ),
                    "",
                )

            groupes_data.append(
                {
                    "grade": grade,
                    "num_groupe": num_groupe,
                    "volume_total": volume_total,
                    "formateur": formateur,
                    "batiment": batiment_groupe,
                    "seances": seances,
                }
            )

        return _build_document(
            module_titre=module.titre,
            annee=annee,
            categorie=categorie,
            groupes_data=groupes_data,
            salle_to_batiment=salle_to_batiment,
        )


__all__ = ["SyntheseUPDocxService"]
