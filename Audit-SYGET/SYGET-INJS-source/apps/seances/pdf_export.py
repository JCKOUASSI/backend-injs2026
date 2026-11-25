"""
Export PDF de l'emploi du temps.

Deux périmètres :
- ``ExportPlanningPDFService.exporter_groupe`` : PDF d'un groupe.
- ``ExportPlanningPDFService.exporter_formation`` : PDF couvrant tous les
  groupes d'une formation (un en-tête + une section par groupe).

Le tableau reprend le format institutionnel SYNTHESE UP (8 colonnes, fusion
verticale des 4 premières colonnes), aligné sur ``docx_synthese.py``.
"""

from __future__ import annotations

import datetime
from collections import Counter, defaultdict
from io import BytesIO
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from apps.groupes.models import Groupe

from .models import Seance
from .repositories import SeanceRepository

_GRIS_TEXTE = colors.HexColor("#0f172a")

# Tableau SYNTHESE UP (aligné sur docx_synthese.py)
_JOURS_FR_SYNTHESE = {
    0: "LUNDI",
    1: "MARDI",
    2: "MERCREDI",
    3: "JEUDI",
    4: "VENDREDI",
    5: "SAMEDI",
    6: "DIMANCHE",
}
_MOIS_FR_SYNTHESE = {
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
_COULEUR_ENTETE_TABLEAU = colors.HexColor("#BFBFBF")
_ENTETES_COL_SYNTHESE = [
    "MATIÈRES",
    "VOLUME HORAIRE<br/>DU MODULE",
    "BATIMENT",
    "SALLE",
    "PÉRIODE",
    "HORAIRE DU COURS",
    "VOLUME HORAIRE<br/>RESTANT APRÈS<br/>LE COURS",
    "FORMATEURS",
]
_LARGEURS_COL_TWIPS = [3096, 1417, 1560, 1700, 2000, 1461, 1746, 2168]


def _grade_principal(groupe: Groupe) -> str:
    """Retourne le grade dominant des membres du groupe (chaîne vide si inconnu)."""
    grades = [
        (m.auditeur.grade or "").strip().upper() for m in groupe.membres.all() if (m.auditeur.grade or "").strip()
    ]
    if not grades:
        return ""
    return Counter(grades).most_common(1)[0][0]


def _formateur_synthese(seance: Seance, formateur_defaut: str = "") -> str:
    """Libellé formateur en majuscules (format SYNTHESE UP)."""
    nom = (seance.formateur_nom or "").strip()
    prenom = (seance.formateur_prenom or "").strip()
    if nom and prenom:
        return f"{nom} {prenom}".upper()
    if nom or prenom:
        return (nom or prenom).upper()
    return formateur_defaut.upper() if formateur_defaut else "—"


def _fmt_date_synthese(d: datetime.date) -> str:
    return f"{_JOURS_FR_SYNTHESE[d.weekday()]} {d.day:02d} {_MOIS_FR_SYNTHESE[d.month]} {d.year}"


def _fmt_heure_synthese(t: datetime.time) -> str:
    return f"{t.hour:02d} H"


def _fmt_plage_synthese(debut: datetime.time, fin: datetime.time) -> str:
    return f"{_fmt_heure_synthese(debut)}-{_fmt_heure_synthese(fin)}"


def _fmt_volume_synthese(heures: int) -> str:
    return f"{heures:02d} H"


def _num_groupe(groupe: Groupe) -> str:
    return groupe.nom.replace("GROUPE", "").replace("Groupe", "").strip() or groupe.nom


def _largeurs_colonnes_synthese() -> list[float]:
    total_twips = sum(_LARGEURS_COL_TWIPS)
    largeur = 267 * mm
    return [w / total_twips * largeur for w in _LARGEURS_COL_TWIPS]


def _duree_heures_seance(seance: Seance) -> int:
    dt_d = datetime.datetime.combine(seance.date, seance.heure_debut)
    dt_f = datetime.datetime.combine(seance.date, seance.heure_fin)
    return int((dt_f - dt_d).total_seconds() // 3600)


def _volume_total_module(seances: list[Seance], volume_defaut: int) -> int:
    if not seances:
        return volume_defaut
    total = sum(_duree_heures_seance(s) for s in seances)
    return total or volume_defaut


def _batiment_seance(seance: Seance, salle_to_batiment: dict[str, str]) -> str:
    bat_direct = (seance.batiment_nom or "").strip().upper()
    if bat_direct:
        return bat_direct
    return salle_to_batiment.get((seance.salle_nom or "").strip().upper(), "").strip().upper()


def _formateur_defaut_fm(fm) -> str:
    if not fm:
        return ""
    nom = (fm.formateur_nom or "").strip()
    prenom = (fm.formateur_prenom or "").strip()
    if nom and prenom:
        return f"{nom} {prenom}".upper().strip()
    return (nom or prenom or "").upper()


def _categorie_fm(fm) -> str:
    if fm and fm.grade_cible:
        return fm.grade_cible.split("/")[0].strip().upper()
    return "A"


def _charger_salle_to_batiment() -> dict[str, str]:
    from apps.parametrage.models import Salle

    return {
        (s.nom or "").strip().upper(): (s.batiment.nom if s.batiment_id and s.batiment else "")
        for s in Salle.objects.select_related("batiment").all()
    }


def _styles():
    """Construit les styles utilisés dans le document (réutilisables entre groupes)."""
    base = getSampleStyleSheet()
    return {
        "titre": ParagraphStyle(
            "Titre",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=18,
            leading=22,
            textColor=_GRIS_TEXTE,
            alignment=1,
            spaceAfter=2,
        ),
        "sous_titre": ParagraphStyle(
            "SousTitre",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=10.5,
            leading=14,
            textColor=colors.HexColor("#475569"),
            alignment=1,
            spaceAfter=4,
        ),
        "cellule_synthese": ParagraphStyle(
            "CelluleSynthese",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=11,
            textColor=_GRIS_TEXTE,
            alignment=1,
        ),
        "cellule_synthese_bold": ParagraphStyle(
            "CelluleSyntheseBold",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=11,
            textColor=_GRIS_TEXTE,
            alignment=1,
        ),
        "cellule_entete_synthese": ParagraphStyle(
            "CelluleEnteteSynthese",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=11,
            textColor=_GRIS_TEXTE,
            alignment=1,
        ),
        "titre_synthese": ParagraphStyle(
            "TitreSynthese",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=14,
            leading=17,
            textColor=_GRIS_TEXTE,
            alignment=1,
            spaceAfter=4,
        ),
        "sous_titre_synthese": ParagraphStyle(
            "SousTitreSynthese",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=15,
            textColor=_GRIS_TEXTE,
            alignment=1,
            spaceAfter=6,
        ),
        "ligne_site_groupe": ParagraphStyle(
            "LigneSiteGroupe",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            textColor=_GRIS_TEXTE,
            spaceAfter=8,
        ),
        "petit": ParagraphStyle(
            "Petit",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8,
            textColor=colors.HexColor("#475569"),
            leading=10,
        ),
        "footer": ParagraphStyle(
            "Footer",
            parent=base["Normal"],
            fontName="Helvetica-Oblique",
            fontSize=8,
            textColor=colors.HexColor("#64748b"),
            alignment=1,
        ),
        "vide": ParagraphStyle(
            "Vide",
            parent=base["Normal"],
            fontName="Helvetica-Oblique",
            fontSize=10,
            textColor=colors.HexColor("#64748b"),
            alignment=1,
            spaceBefore=18,
            spaceAfter=18,
        ),
        # En-tête institutionnel (gauche) : hiérarchie ministérielle.
        # Centré pour reproduire la mise en page officielle des courriers.
        "entete_inst": ParagraphStyle(
            "EnteteInst",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=11,
            textColor=_GRIS_TEXTE,
            alignment=1,
        ),
        # En-tête institutionnel (droite) : devise / République.
        "entete_devise_titre": ParagraphStyle(
            "EnteteDeviseTitre",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=13,
            textColor=_GRIS_TEXTE,
            alignment=1,
        ),
        "entete_devise_sous_titre": ParagraphStyle(
            "EnteteDeviseSousTitre",
            parent=base["Normal"],
            fontName="Helvetica-Oblique",
            fontSize=9,
            leading=12,
            textColor=_GRIS_TEXTE,
            alignment=1,
        ),
    }


# Texte institutionnel à afficher en en-tête (aligné sur docx_synthese.py).
_HIERARCHIE_GAUCHE = [
    "MINISTÈRE D'ÉTAT, MINISTÈRE DE LA FONCTION PUBLIQUE",
    "ET DE LA MODERNISATION DE L'ADMINISTRATION",
    "DIRECTION GÉNÉRALE DE LA FONCTION PUBLIQUE",
    "DIRECTION DE LA FORMATION ET DU RENFORCEMENT DES CAPACITÉS",
    "CENTRE DE PERFECTIONNEMENT DES FONCTIONNAIRES",
    "ET AGENTS DE L'ÉTAT-AMADOU GON COULIBALY",
]

_REPUBLIQUE_TITRE = "RÉPUBLIQUE DE CÔTE D'IVOIRE"
_REPUBLIQUE_DEVISE = "Union – Discipline – Travail"


def _entete_institutionnel(styles) -> Table:
    """Construit l'en-tête officiel à deux colonnes (ministère / République).

    Colonne gauche : hiérarchie ministérielle (multi-lignes, séparateurs ``----------``).
    Colonne droite : ``RÉPUBLIQUE DE CÔTE D'IVOIRE`` + devise nationale.
    """
    gauche_lignes = "<br/>".join(_HIERARCHIE_GAUCHE)
    cellule_gauche = Paragraph(gauche_lignes, styles["entete_inst"])
    cellule_droite = [
        Paragraph(_REPUBLIQUE_TITRE, styles["entete_devise_titre"]),
        Spacer(1, 2),
        Paragraph(_REPUBLIQUE_DEVISE, styles["entete_devise_sous_titre"]),
    ]
    largeur_totale = 277 * mm
    table = Table(
        [[cellule_gauche, cellule_droite]],
        colWidths=[largeur_totale * 0.55, largeur_totale * 0.45],
    )
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return table


def _table_synthese_up(
    *,
    module_titre: str,
    volume_total: int,
    seances: list[Seance],
    formateur_defaut: str,
    salle_to_batiment: dict[str, str],
    styles,
) -> Table:
    """Tableau 8 colonnes au format SYNTHESE UP (fusion verticale des 4 premières colonnes)."""
    cellule = styles["cellule_synthese"]
    cellule_bold = styles["cellule_synthese_bold"]
    cellule_entete = styles["cellule_entete_synthese"]

    entetes = [Paragraph(txt, cellule_entete) for txt in _ENTETES_COL_SYNTHESE]
    data: list[list] = [entetes]

    premiere = seances[0]
    batiment = _batiment_seance(premiere, salle_to_batiment)
    salle = (premiere.salle_nom or "").strip().upper()
    volume_restant = volume_total

    for seance in seances:
        duree_h = _duree_heures_seance(seance)
        volume_restant -= duree_h
        row = [
            Paragraph(module_titre.upper(), cellule_bold),
            Paragraph(_fmt_volume_synthese(volume_total), cellule),
            Paragraph(batiment, cellule),
            Paragraph(salle, cellule),
            Paragraph(_fmt_date_synthese(seance.date), cellule),
            Paragraph(_fmt_plage_synthese(seance.heure_debut, seance.heure_fin), cellule),
            Paragraph(_fmt_volume_synthese(max(0, volume_restant)), cellule),
            Paragraph(_formateur_synthese(seance, formateur_defaut), cellule),
        ]
        data.append(row)

    table = Table(data, colWidths=_largeurs_colonnes_synthese(), repeatRows=1)
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), _COULEUR_ENTETE_TABLEAU),
        ("BACKGROUND", (0, 1), (-1, -1), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
    ]
    if len(seances) > 1:
        last_row = len(seances)
        for col in range(4):
            style_cmds.append(("SPAN", (col, 1), (col, last_row)))
    table.setStyle(TableStyle(style_cmds))
    return table


def _page_module_synthese(
    *,
    groupe: Groupe,
    module_titre: str,
    seances: list[Seance],
    fm,
    annee: int,
    styles,
    salle_to_batiment: dict[str, str],
) -> list:
    """Une page module : en-tête institutionnel + titre SYNTHESE UP + tableau."""
    grade = _grade_principal(groupe)
    if not grade and fm and fm.grade_cible:
        grade = fm.grade_cible.upper()
    grade_str = f" / GRADE {grade}" if grade else ""
    categorie = _categorie_fm(fm)
    volume_defaut = fm.volume_horaire if fm and fm.volume_horaire else 0
    formateur_defaut = _formateur_defaut_fm(fm)
    volume_total = _volume_total_module(seances, volume_defaut)

    elements: list = [
        _entete_institutionnel(styles),
        Spacer(1, 6),
        Paragraph(
            f" {module_titre.upper()} FAB SESSION {annee}",
            styles["titre_synthese"],
        ),
        Paragraph(
            f"EMPLOI DU TEMPS CATÉGORIE {categorie}{grade_str}",
            styles["sous_titre_synthese"],
        ),
    ]
    site_groupe = Table(
        [
            [
                Paragraph("SITE : CPFAE-AGC", styles["ligne_site_groupe"]),
                Paragraph(f"GROUPE : {_num_groupe(groupe)}", styles["ligne_site_groupe"]),
            ]
        ],
        colWidths=[133 * mm, 134 * mm],
    )
    site_groupe.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (0, 0), "LEFT"),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    elements.append(site_groupe)
    if seances:
        elements.append(
            _table_synthese_up(
                module_titre=module_titre,
                volume_total=volume_total,
                seances=seances,
                formateur_defaut=formateur_defaut,
                salle_to_batiment=salle_to_batiment,
                styles=styles,
            )
        )
    else:
        elements.append(
            Paragraph(
                "Aucune séance planifiée pour ce module.",
                styles["vide"],
            )
        )
    return elements


def _blocs_par_module(
    groupe: Groupe,
    seances: list[Seance],
) -> list[tuple[object | None, str, list[Seance]]]:
    """Découpe les séances d'un groupe en blocs ordonnés (modules de la formation)."""
    from apps.formations.models import FormationModule

    seances_par_module_id: dict[int, list[Seance]] = defaultdict(list)
    for seance in seances:
        if seance.module_id:
            seances_par_module_id[seance.module_id].append(seance)

    def _trier(sess: list[Seance]) -> list[Seance]:
        return sorted(sess, key=lambda s: (s.date, s.heure_debut, s.heure_fin, s.pk))

    formation_id = groupe.formation_id
    if not formation_id:
        if not seances:
            return []
        par_titre: dict[str, list[Seance]] = defaultdict(list)
        for seance in seances:
            titre = (seance.module.titre if seance.module else "—") or "—"
            par_titre[titre].append(seance)
        return [(None, titre, _trier(sess)) for titre, sess in sorted(par_titre.items())]

    blocs: list[tuple[object | None, str, list[Seance]]] = []
    modules_vus: set[int] = set()
    for fm in (
        FormationModule.objects.filter(formation_id=formation_id)
        .select_related("module")
        .order_by("date_debut", "module__titre")
    ):
        modules_vus.add(fm.module_id)
        titre = (fm.module.titre if fm.module else "—") or "—"
        blocs.append((fm, titre, _trier(seances_par_module_id.get(fm.module_id, []))))

    for module_id, sess in seances_par_module_id.items():
        if module_id in modules_vus:
            continue
        titre = (sess[0].module.titre if sess[0].module else "—") or "—"
        blocs.append((None, titre, _trier(sess)))

    return blocs


def _pages_groupe_synthese(
    *,
    groupe: Groupe,
    seances: list[Seance],
    styles,
    salle_to_batiment: dict[str, str],
    annee: int,
) -> list:
    """Ensemble des pages d'un groupe (une page par module, format SYNTHESE UP)."""
    elements: list = []
    blocs = _blocs_par_module(groupe, seances)
    if not blocs:
        elements.append(
            Paragraph(
                "Aucune séance planifiée pour ce groupe à ce jour.",
                styles["vide"],
            )
        )
        return elements

    for index, (fm, titre_module, seances_module) in enumerate(blocs):
        if index > 0:
            elements.append(PageBreak())
        elements.extend(
            _page_module_synthese(
                groupe=groupe,
                module_titre=titre_module,
                seances=seances_module,
                fm=fm,
                annee=annee,
                styles=styles,
                salle_to_batiment=salle_to_batiment,
            )
        )
    return elements


def _build_pied_de_page(canvas, doc):
    """Pied de page avec date d'édition + numéro de page (commun à tous les documents)."""
    canvas.saveState()
    canvas.setFont("Helvetica-Oblique", 8)
    canvas.setFillColor(colors.HexColor("#64748b"))
    largeur, _ = doc.pagesize
    edition = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    canvas.drawString(
        15 * mm,
        10 * mm,
        f"SYGEP-CPFAE — Emploi du temps · édité le {edition}",
    )
    canvas.drawRightString(
        largeur - 15 * mm,
        10 * mm,
        f"Page {doc.page}",
    )
    canvas.restoreState()


def _document(buffer: BytesIO, titre: str) -> SimpleDocTemplate:
    """Document A4 paysage configuré (marges alignées sur le modèle SYNTHESE UP)."""
    return SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        topMargin=5 * mm,
        bottomMargin=5 * mm,
        leftMargin=10 * mm,
        rightMargin=12 * mm,
        title=titre,
        author="SYGET-CPFAE",
        subject="Emploi du temps",
    )


class ExportPlanningPDFService:
    """Génère les exports PDF de synthèse du planning (groupe ou formation)."""

    def __init__(self, repo: Optional[SeanceRepository] = None) -> None:
        self._repo = repo or SeanceRepository()

    def exporter_groupe(self, groupe_id: int) -> bytes:
        """Retourne le PDF emploi du temps pour un groupe (une page par module, format SYNTHESE UP)."""
        groupe = (
            Groupe.objects.select_related("formation", "formation__type_formation", "config")
            .prefetch_related("membres__auditeur")
            .get(pk=groupe_id)
        )
        seances = self._repo.list_by_groupe(groupe_id)
        formation = groupe.formation
        annee = formation.date_debut.year if formation and formation.date_debut else datetime.date.today().year
        styles = _styles()
        salle_to_batiment = _charger_salle_to_batiment()
        buffer = BytesIO()
        doc = _document(
            buffer,
            titre=f"Emploi du temps — {groupe.nom}",
        )
        elements = _pages_groupe_synthese(
            groupe=groupe,
            seances=seances,
            styles=styles,
            salle_to_batiment=salle_to_batiment,
            annee=annee,
        )
        doc.build(elements, onFirstPage=_build_pied_de_page, onLaterPages=_build_pied_de_page)
        return buffer.getvalue()

    def exporter_formation(self, formation_id: int) -> bytes:
        """
        Retourne le PDF emploi du temps pour tous les groupes d'une formation.

        Une page par module et par groupe (format SYNTHESE UP).
        """
        from apps.formations.models import Formation

        formation = Formation.objects.select_related("type_formation").get(pk=formation_id)
        annee = formation.date_debut.year if formation.date_debut else datetime.date.today().year
        groupes = list(
            Groupe.objects.filter(formation_id=formation_id)
            .select_related("formation", "formation__type_formation", "config")
            .prefetch_related("membres__auditeur")
            .order_by("nom", "pk")
        )
        seances_par_groupe: dict[int, list[Seance]] = defaultdict(list)
        for seance in self._repo.list_by_formation(formation_id):
            seances_par_groupe[seance.groupe_id].append(seance)

        styles = _styles()
        salle_to_batiment = _charger_salle_to_batiment()
        buffer = BytesIO()
        doc = _document(
            buffer,
            titre=f"Emploi du temps — {formation.intitule}",
        )
        elements: list = []

        if not groupes:
            elements.append(
                Paragraph(
                    "Aucun groupe rattaché à cette formation pour le moment.",
                    styles["vide"],
                )
            )
        else:
            first_page = True
            for groupe in groupes:
                seances_groupe = sorted(
                    seances_par_groupe.get(groupe.pk, []),
                    key=lambda s: (s.date, s.heure_debut, s.heure_fin, s.pk),
                )
                pages = _pages_groupe_synthese(
                    groupe=groupe,
                    seances=seances_groupe,
                    styles=styles,
                    salle_to_batiment=salle_to_batiment,
                    annee=annee,
                )
                if not pages:
                    continue
                if not first_page:
                    elements.append(PageBreak())
                elements.extend(pages)
                first_page = False

        doc.build(elements, onFirstPage=_build_pied_de_page, onLaterPages=_build_pied_de_page)
        return buffer.getvalue()

    def exporter_formation_zip(self, formation_id: int) -> bytes:
        """
        Retourne une archive ZIP contenant un PDF emploi du temps par groupe
        (``A4_EMP_GROUPE1.pdf``, etc.).
        """
        import zipfile
        from io import BytesIO

        from apps.groupes.models import Groupe
        from shared.utils.groupes import nom_fichier_emploi_du_temps

        buffer = BytesIO()
        groupes = list(
            Groupe.objects.filter(formation_id=formation_id)
            .select_related("formation", "formation__type_formation")
            .prefetch_related("membres__auditeur")
            .order_by("nom", "pk")
        )
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for groupe in groupes:
                contenu = self.exporter_groupe(groupe.pk)
                nom_fichier = nom_fichier_emploi_du_temps(groupe=groupe, extension="pdf")
                archive.writestr(nom_fichier, contenu)
        return buffer.getvalue()


__all__ = ["ExportPlanningPDFService"]
