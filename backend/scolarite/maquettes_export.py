"""Exports des maquettes pédagogiques LMD — Word, PDF, Excel, CSV.

Un seul module pour les quatre formats, afin que les colonnes, les libellés et
les règles de sécurité restent identiques d'un format à l'autre :

* **synthèse** : une ligne par maquette (identité, statut, UE, crédits) ;
* **détail pédagogique** : une ligne par ECUE, avec son UE, son semestre, ses
  crédits, son coefficient et ses volumes CM/TD/TP.

Sécurité : les valeurs texte sont neutralisées avant écriture (injection de
formules CSV/Excel). Une cellule commençant par ``=``, ``+``, ``-``, ``@``,
une tabulation ou un retour chariot est préfixée par une apostrophe, ce qui la
fait traiter comme du texte par Excel/LibreOffice et non comme une formule.

Les maquettes reçues doivent déjà être filtrées par l'appelant : ce module ne
connaît ni les droits ni les filtres de l'écran.
"""

from __future__ import annotations

import csv
import io
from datetime import date

from django.http import HttpResponse
from django.utils import timezone

# ── Formats ─────────────────────────────────────────────────────────────────
FORMATS = ('csv', 'xlsx', 'docx', 'pdf')

CONTENT_TYPES = {
    'csv': 'text/csv; charset=utf-8',
    'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'pdf': 'application/pdf',
}

EXTENSIONS = {'csv': 'csv', 'xlsx': 'xlsx', 'docx': 'docx', 'pdf': 'pdf'}

# Colonnes de la vue synthétique.
COLONNES_SYNTHESE = [
    'ANNEE', 'FORMATION', 'PARCOURS', 'NIVEAU', 'VERSION', 'STATUT',
    'LIBELLE', 'NB_UE', 'CREDITS_ECTS',
]

# Colonnes du détail pédagogique (une ligne par ECUE).
COLONNES_DETAIL = [
    'ANNEE', 'FORMATION', 'PARCOURS', 'NIVEAU', 'VERSION', 'STATUT',
    'SEMESTRE', 'UE_CODE', 'UE_INTITULE', 'UE_CREDITS', 'UE_CARACTERE',
    'ECUE_CODE', 'ECUE_INTITULE', 'ECUE_CREDITS', 'COEFFICIENT',
    'CM', 'TD', 'TP', 'VOLUME_TOTAL',
]

# Caractères déclencheurs d'une formule dans un tableur.
_PREFIXES_DANGEREUX = ('=', '+', '-', '@', '\t', '\r')


def neutraliser(valeur):
    """Neutralise une valeur texte destinée à un tableur (anti-formule)."""
    if valeur is None:
        return ''
    texte = str(valeur)
    if texte and texte[0] in _PREFIXES_DANGEREUX:
        return "'" + texte
    return texte


# ── Données ─────────────────────────────────────────────────────────────────
def _statut(maquette):
    return maquette.get_statut_display() if hasattr(maquette, 'get_statut_display') else maquette.statut


def lignes_synthese(maquettes):
    """Une ligne de dictionnaire par maquette (colonnes de ``COLONNES_SYNTHESE``)."""
    lignes = []
    for maquette in maquettes:
        unites = list(maquette.unites_enseignement.all())
        lignes.append({
            'ANNEE': maquette.annee_academique.libelle,
            'FORMATION': maquette.ref_formation.intitule,
            'PARCOURS': maquette.parcours.intitule if maquette.parcours_id else '',
            'NIVEAU': maquette.niveau.code,
            'VERSION': maquette.version,
            'STATUT': _statut(maquette),
            'LIBELLE': str(maquette),
            'NB_UE': len(unites),
            'CREDITS_ECTS': sum(ue.credits or 0 for ue in unites),
        })
    return lignes


def lignes_detail(maquettes):
    """Une ligne par ECUE, l'UE étant répétée (format « table à plat »)."""
    lignes = []
    for maquette in maquettes:
        unites = (
            maquette.unites_enseignement
            .select_related('semestre')
            .prefetch_related('ecues')
            .order_by('semestre__numero', 'ordre', 'code')
        )
        for ue in unites:
            ecues = sorted(ue.ecues.all(), key=lambda e: (e.ordre, e.code))
            if not ecues:
                # UE sans ECUE : la ligne existe quand même, sinon l'UE
                # disparaîtrait silencieusement de l'export détaillé.
                lignes.append(_ligne_detail(maquette, ue, None))
                continue
            for ecue in ecues:
                lignes.append(_ligne_detail(maquette, ue, ecue))
    return lignes


def _ligne_detail(maquette, ue, ecue):
    return {
        'ANNEE': maquette.annee_academique.libelle,
        'FORMATION': maquette.ref_formation.intitule,
        'PARCOURS': maquette.parcours.intitule if maquette.parcours_id else '',
        'NIVEAU': maquette.niveau.code,
        'VERSION': maquette.version,
        'STATUT': _statut(maquette),
        'SEMESTRE': ue.semestre.libelle if ue.semestre_id else '',
        'UE_CODE': ue.code,
        'UE_INTITULE': ue.intitule,
        'UE_CREDITS': ue.credits or 0,
        'UE_CARACTERE': ue.get_caractere_display() if hasattr(ue, 'get_caractere_display') else ue.caractere,
        'ECUE_CODE': ecue.code if ecue else '',
        'ECUE_INTITULE': ecue.intitule if ecue else '',
        'ECUE_CREDITS': (ecue.credits or 0) if ecue else 0,
        'COEFFICIENT': float(ecue.coefficient) if ecue and ecue.coefficient is not None else 0,
        'CM': float(ecue.volume_cm or 0) if ecue else 0,
        'TD': float(ecue.volume_td or 0) if ecue else 0,
        'TP': float(ecue.volume_tp or 0) if ecue else 0,
        'VOLUME_TOTAL': float(ecue.volume_total or 0) if ecue else 0,
    }


def _colonnes(avec_detail):
    return COLONNES_DETAIL if avec_detail else COLONNES_SYNTHESE


def _lignes(maquettes, avec_detail):
    return lignes_detail(maquettes) if avec_detail else lignes_synthese(maquettes)


# ── CSV ─────────────────────────────────────────────────────────────────────
def construire_csv(maquettes, avec_detail=False):
    """CSV UTF-8 avec BOM et séparateur « ; » (convention du projet, Excel FR)."""
    colonnes = _colonnes(avec_detail)
    tampon = io.StringIO()
    redacteur = csv.DictWriter(tampon, fieldnames=colonnes, delimiter=';', lineterminator='\r\n')
    redacteur.writeheader()
    for ligne in _lignes(maquettes, avec_detail):
        redacteur.writerow({colonne: neutraliser(ligne.get(colonne)) for colonne in colonnes})
    # Le BOM rend le fichier lisible par Excel en UTF-8 (accents des intitulés).
    return tampon.getvalue().encode('utf-8-sig')


# ── Excel ───────────────────────────────────────────────────────────────────
def construire_xlsx(maquettes, avec_detail=False):
    """Classeur Excel : feuille de synthèse + feuille de détail pédagogique.

    La synthèse est toujours présente (vue d'ensemble), la feuille de détail
    n'est ajoutée que si elle est demandée : deux niveaux de lecture dans un
    seul fichier, sans feuille vide.
    """
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    classeur = Workbook()
    entete_font = Font(bold=True, color='FFFFFF')
    entete_fill = PatternFill('solid', fgColor='1A68AC')

    def _ecrire_feuille(feuille, titre, colonnes, lignes):
        feuille.title = titre
        feuille.append(colonnes)
        for cellule in feuille[1]:
            cellule.font = entete_font
            cellule.fill = entete_fill
            cellule.alignment = Alignment(horizontal='center', vertical='center')
        for ligne in lignes:
            feuille.append([ligne.get(colonne) for colonne in colonnes])
        feuille.freeze_panes = 'A2'
        feuille.auto_filter.ref = feuille.dimensions
        for index, colonne in enumerate(colonnes, start=1):
            plus_long = max(
                [len(str(colonne))] + [len(str(ligne.get(colonne) or '')) for ligne in lignes],
            )
            feuille.column_dimensions[get_column_letter(index)].width = min(max(plus_long + 3, 12), 52)
        return feuille

    synthese = _ecrire_feuille(
        classeur.active, 'Maquettes', COLONNES_SYNTHESE, lignes_synthese(maquettes),
    )
    synthese.sheet_view.showGridLines = False

    if avec_detail:
        _ecrire_feuille(
            classeur.create_sheet('Détail pédagogique'),
            'Détail pédagogique',
            COLONNES_DETAIL,
            lignes_detail(maquettes),
        )

    # Onglet de contexte : utile quand le fichier circule hors de l'application.
    infos = classeur.create_sheet('Informations')
    infos['A1'] = 'Export des maquettes pédagogiques — INJS-LMD'
    infos['A1'].font = Font(bold=True, size=13)
    infos['A3'] = 'Généré le'
    infos['B3'] = timezone.localtime().strftime('%d/%m/%Y à %H:%M')
    infos['A4'] = 'Maquettes exportées'
    infos['B4'] = len(list(maquettes))
    infos['A5'] = 'Contenu'
    infos['B5'] = 'Synthèse + détail pédagogique (UE/ECUE)' if avec_detail else 'Synthèse'
    infos.column_dimensions['A'].width = 24
    infos.column_dimensions['B'].width = 46

    flux = io.BytesIO()
    classeur.save(flux)
    return flux.getvalue()


# ── Word ────────────────────────────────────────────────────────────────────
def construire_docx(maquettes, avec_detail=False):
    """Document Word structuré, paginé et lisible à l'impression."""
    from docx import Document
    from docx.enum.section import WD_ORIENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Cm, Pt, RGBColor

    bleu = RGBColor(0x1A, 0x68, 0xAC)
    document = Document()

    section = document.sections[0]
    section.orientation = WD_ORIENT.LANDSCAPE
    section.page_width, section.page_height = section.page_height, section.page_width
    for marge in ('left_margin', 'right_margin', 'top_margin', 'bottom_margin'):
        setattr(section, marge, Cm(1.6))

    titre = document.add_heading('Maquettes pédagogiques LMD', level=0)
    titre.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for run in titre.runs:
        run.font.color.rgb = bleu

    sous_titre = document.add_paragraph(
        'Institut National de la Jeunesse et des Sports — export du '
        + timezone.localtime().strftime('%d/%m/%Y à %H:%M'),
    )
    sous_titre.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for run in sous_titre.runs:
        run.font.size = Pt(10)
        run.font.color.rgb = RGBColor(0x55, 0x65, 0x77)

    liste = list(maquettes)
    document.add_paragraph(
        f'{len(liste)} maquette(s) exportée(s) — synthèse'
        + (' et détail pédagogique (UE/ECUE)' if avec_detail else ''),
    )

    def _tableau(colonnes, lignes):
        table = document.add_table(rows=1, cols=len(colonnes))
        table.style = 'Light Grid Accent 1'
        entetes = table.rows[0].cells
        for index, colonne in enumerate(colonnes):
            entetes[index].text = colonne
            for paragraphe in entetes[index].paragraphs:
                for run in paragraphe.runs:
                    run.font.bold = True
                    run.font.size = Pt(8)
        for ligne in lignes:
            cellules = table.add_row().cells
            for index, colonne in enumerate(colonnes):
                valeur = ligne.get(colonne)
                cellules[index].text = '' if valeur is None else str(valeur)
                for paragraphe in cellules[index].paragraphs:
                    for run in paragraphe.runs:
                        run.font.size = Pt(8)
        return table

    document.add_heading('Synthèse', level=1)
    _tableau(
        ['ANNEE', 'FORMATION', 'PARCOURS', 'NIVEAU', 'VERSION', 'STATUT', 'NB_UE', 'CREDITS_ECTS'],
        lignes_synthese(liste),
    )

    if avec_detail:
        document.add_page_break()
        document.add_heading('Détail pédagogique', level=1)
        for maquette in liste:
            document.add_heading(str(maquette), level=2)
            unites = (
                maquette.unites_enseignement
                .select_related('semestre')
                .prefetch_related('ecues')
                .order_by('semestre__numero', 'ordre', 'code')
            )
            lignes = [
                {
                    'SEMESTRE': ue.semestre.libelle if ue.semestre_id else '',
                    'UE': f'{ue.code} — {ue.intitule}',
                    'CREDITS_UE': ue.credits or 0,
                    'ECUE': f'{ecue.code} — {ecue.intitule}' if ecue else '—',
                    'CREDITS': (ecue.credits or 0) if ecue else 0,
                    'COEF': float(ecue.coefficient) if ecue and ecue.coefficient is not None else 0,
                    'CM': float(ecue.volume_cm or 0) if ecue else 0,
                    'TD': float(ecue.volume_td or 0) if ecue else 0,
                    'TP': float(ecue.volume_tp or 0) if ecue else 0,
                }
                for ue in unites
                for ecue in (sorted(ue.ecues.all(), key=lambda e: (e.ordre, e.code)) or [None])
            ]
            _tableau(['SEMESTRE', 'UE', 'CREDITS_UE', 'ECUE', 'CREDITS', 'COEF', 'CM', 'TD', 'TP'], lignes)

    flux = io.BytesIO()
    document.save(flux)
    return flux.getvalue()


# ── PDF ─────────────────────────────────────────────────────────────────────
def construire_pdf(maquettes, avec_detail=False):
    """PDF A4 paysage, tableaux répétés en en-tête à chaque page."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
    )

    bleu = colors.HexColor('#1A68AC')
    gris = colors.HexColor('#EEF4FF')
    styles = getSampleStyleSheet()
    style_titre = ParagraphStyle(
        'TitreMaquettes', parent=styles['Title'], fontSize=17, textColor=bleu, spaceAfter=4,
    )
    style_sous_titre = ParagraphStyle(
        'SousTitreMaquettes', parent=styles['Normal'], fontSize=9,
        textColor=colors.HexColor('#556577'), alignment=TA_CENTER, spaceAfter=12,
    )
    style_h2 = ParagraphStyle(
        'MaquetteH2', parent=styles['Heading2'], fontSize=11, textColor=bleu, spaceBefore=10,
    )
    style_cellule = ParagraphStyle('CelluleMaquettes', parent=styles['Normal'], fontSize=7, leading=8.6)

    flux = io.BytesIO()
    document = SimpleDocTemplate(
        flux, pagesize=landscape(A4),
        leftMargin=12 * mm, rightMargin=12 * mm, topMargin=12 * mm, bottomMargin=12 * mm,
        title='Maquettes pédagogiques LMD — INJS',
    )
    elements = [
        Paragraph('Maquettes pédagogiques LMD', style_titre),
        Paragraph(
            'Institut National de la Jeunesse et des Sports — export du '
            + timezone.localtime().strftime('%d/%m/%Y à %H:%M'),
            style_sous_titre,
        ),
    ]

    def _tableau(colonnes, lignes, largeurs=None):
        donnees = [[Paragraph(f'<b>{colonne}</b>', style_cellule) for colonne in colonnes]]
        for ligne in lignes:
            donnees.append([
                Paragraph(neutraliser(ligne.get(colonne)), style_cellule) for colonne in colonnes
            ])
        table = Table(donnees, colWidths=largeurs, repeatRows=1)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), bleu),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 7),
            ('GRID', (0, 0), (-1, -1), 0.35, colors.HexColor('#B9C6D6')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, gris]),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(table)

    liste = list(maquettes)
    elements.append(Paragraph(
        f'{len(liste)} maquette(s) exportée(s) — synthèse'
        + (' et détail pédagogique (UE/ECUE)' if avec_detail else ''),
        styles['Normal'],
    ))
    elements.append(Spacer(1, 6))
    _tableau(
        ['ANNEE', 'FORMATION', 'PARCOURS', 'NIVEAU', 'VERSION', 'STATUT', 'NB_UE', 'CREDITS_ECTS'],
        lignes_synthese(liste),
    )

    if avec_detail:
        elements.append(PageBreak())
        elements.append(Paragraph('Détail pédagogique', style_titre))
        for maquette in liste:
            elements.append(Paragraph(str(maquette), style_h2))
            unites = (
                maquette.unites_enseignement
                .select_related('semestre')
                .prefetch_related('ecues')
                .order_by('semestre__numero', 'ordre', 'code')
            )
            lignes = [
                {
                    'SEMESTRE': ue.semestre.libelle if ue.semestre_id else '',
                    'UE': f'{ue.code} — {ue.intitule}',
                    'UE_CREDITS': str(ue.credits or 0),
                    'ECUE': f'{ecue.code} — {ecue.intitule}' if ecue else '—',
                    'ECUE_CREDITS': str((ecue.credits or 0) if ecue else 0),
                    'COEF': str(float(ecue.coefficient) if ecue and ecue.coefficient is not None else 0),
                    'CM': str(float(ecue.volume_cm or 0) if ecue else 0),
                    'TD': str(float(ecue.volume_td or 0) if ecue else 0),
                    'TP': str(float(ecue.volume_tp or 0) if ecue else 0),
                }
                for ue in unites
                for ecue in (sorted(ue.ecues.all(), key=lambda e: (e.ordre, e.code)) or [None])
            ]
            _tableau(
                ['SEMESTRE', 'UE', 'UE_CREDITS', 'ECUE', 'ECUE_CREDITS', 'COEF', 'CM', 'TD', 'TP'],
                lignes,
                largeurs=[22 * mm, 62 * mm, 18 * mm, 62 * mm, 17 * mm, 13 * mm, 13 * mm, 13 * mm, 13 * mm],
            )

    def _pied_de_page(canvas, doc):
        canvas.saveState()
        canvas.setFont('Helvetica', 7)
        canvas.setFillColor(colors.HexColor('#6B7B8C'))
        canvas.drawString(12 * mm, 7 * mm, 'INJS-LMD — maquettes pédagogiques')
        canvas.drawRightString(
            landscape(A4)[0] - 12 * mm, 7 * mm, f'Page {canvas.getPageNumber()}',
        )
        canvas.restoreState()

    document.build(elements, onFirstPage=_pied_de_page, onLaterPages=_pied_de_page)
    return flux.getvalue()


# ── Réponse HTTP ────────────────────────────────────────────────────────────
_constructeurs = {
    'csv': construire_csv,
    'xlsx': construire_xlsx,
    'docx': construire_docx,
    'pdf': construire_pdf,
}


def nom_fichier(fmt, avec_detail=False):
    """Nom de fichier stable et daté (pas d'accent, pas d'espace)."""
    suffixe = '_detail' if avec_detail else ''
    return f'maquettes{suffixe}_{date.today().isoformat()}.{EXTENSIONS[fmt]}'


def reponse_export(maquettes, fmt, avec_detail=False):
    """Construit la réponse HTTP de téléchargement pour le format demandé."""
    contenu = _constructeurs[fmt](maquettes, avec_detail=avec_detail)
    reponse = HttpResponse(contenu, content_type=CONTENT_TYPES[fmt])
    reponse['Content-Disposition'] = f'attachment; filename="{nom_fichier(fmt, avec_detail)}"'
    reponse['Content-Length'] = str(len(contenu))
    # Un export ne doit jamais être mis en cache par un intermédiaire : le
    # contenu dépend des droits et des filtres de l'appelant.
    reponse['Cache-Control'] = 'private, no-store'
    return reponse
