"""Écriture de tableaux dans les quatre formats du module (CSV, XLSX, DOCX, PDF).

Un seul implémenteur pour tout le module : les exports des référentiels et
celui des UE/ECUE partagent ainsi les mêmes polices, les mêmes en-têtes
répétés et **la même protection contre l'injection de formules** (chaque
cellule passe par :func:`scolarite.maquettes_export.neutraliser`).

Les appelants fournissent une liste de colonnes (libellés humains) et une
liste de lignes (dicts indexés par ces libellés) : aucune connaissance métier
n'entre ici.
"""

from __future__ import annotations

import csv
import io

from django.http import HttpResponse
from django.utils import timezone

from .maquettes_export import CONTENT_TYPES, EXTENSIONS, FORMATS, neutraliser


def _propre(valeur):
    return '' if valeur is None else neutraliser(valeur)


def construire_csv(colonnes, lignes):
    """CSV UTF-8 avec BOM et séparateur ``;``, ouvert directement par Excel."""
    tampon = io.StringIO()
    redacteur = csv.DictWriter(
        tampon, fieldnames=colonnes, delimiter=';', lineterminator='\r\n',
        quoting=csv.QUOTE_MINIMAL, extrasaction='ignore',
    )
    redacteur.writeheader()
    for ligne in lignes:
        redacteur.writerow({colonne: _propre(ligne.get(colonne)) for colonne in colonnes})
    return tampon.getvalue().encode('utf-8-sig')


def construire_xlsx(colonnes, lignes, feuille='Données', titre='', sous_titre=''):
    """Classeur Excel : feuille de données + feuille d'informations."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.table import Table, TableStyleInfo

    classeur = Workbook()
    onglet = classeur.active
    onglet.title = feuille[:31]
    onglet.append(colonnes)
    for ligne in lignes:
        onglet.append([_propre(ligne.get(colonne)) for colonne in colonnes])

    bleu = PatternFill('solid', fgColor='1A68AC')
    for cellule in onglet[1]:
        cellule.font = Font(bold=True, color='FFFFFF')
        cellule.fill = bleu
        cellule.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
    onglet.freeze_panes = 'A2'
    if lignes:
        table = Table(
            displayName='Export',
            ref=f'A1:{get_column_letter(len(colonnes))}{len(lignes) + 1}',
        )
        table.tableStyleInfo = TableStyleInfo(
            name='TableStyleMedium2', showRowStripes=True, showColumnStripes=False,
        )
        onglet.add_table(table)
    for index, colonne in enumerate(colonnes, start=1):
        largeur = max([len(colonne)] + [len(str(ligne.get(colonne, ''))) for ligne in lignes])
        onglet.column_dimensions[get_column_letter(index)].width = min(max(largeur + 2, 10), 52)

    infos = classeur.create_sheet('Informations')
    infos.append(('Objet', titre or feuille))
    infos.append(('Détail', sous_titre or '—'))
    infos.append(('Export', timezone.localtime().strftime('%d/%m/%Y %H:%M')))
    infos.append(('Lignes', len(lignes)))
    infos.append(('Formats acceptés à l’import', '.xlsx, .csv'))
    infos.column_dimensions['A'].width = 30
    infos.column_dimensions['B'].width = 60
    infos['A1'].font = Font(bold=True)

    flux = io.BytesIO()
    classeur.save(flux)
    return flux.getvalue()


def construire_docx(colonnes, lignes, titre='', sous_titre='', **_):
    """Document Word paginé, tableau à en-tête répété."""
    from docx import Document
    from docx.enum.section import WD_ORIENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Cm, Pt, RGBColor

    document = Document()
    section = document.sections[0]
    section.orientation = WD_ORIENT.LANDSCAPE
    section.page_width, section.page_height = section.page_height, section.page_width
    for marge in ('left_margin', 'right_margin', 'top_margin', 'bottom_margin'):
        setattr(section, marge, Cm(1.5))

    entete = document.add_heading(titre or 'Export', level=0)
    entete.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for run in entete.runs:
        run.font.color.rgb = RGBColor(0x1A, 0x68, 0xAC)

    paragraphe = document.add_paragraph()
    paragraphe.alignment = WD_ALIGN_PARAGRAPH.CENTER
    course = paragraphe.add_run(
        (sous_titre + ' — ' if sous_titre else '')
        + 'export du ' + timezone.localtime().strftime('%d/%m/%Y à %H:%M')
        + f' — {len(lignes)} ligne(s)',
    )
    course.font.size = Pt(9)
    course.font.color.rgb = RGBColor(0x55, 0x65, 0x77)

    table = document.add_table(rows=1, cols=len(colonnes))
    table.style = 'Light Grid Accent 1'
    for index, colonne in enumerate(colonnes):
        cellule = table.rows[0].cells[index]
        cellule.text = colonne
        for paragraph in cellule.paragraphs:
            for run in paragraph.runs:
                run.bold = True
                run.font.size = Pt(7)
    for ligne in lignes:
        cellules = table.add_row().cells
        for index, colonne in enumerate(colonnes):
            cellules[index].text = str(_propre(ligne.get(colonne, '')))
            for paragraph in cellules[index].paragraphs:
                for run in paragraph.runs:
                    run.font.size = Pt(7)

    # En-tête de tableau répété sur chaque page.
    table.rows[0]._tr.get_or_add_trPr().append(
        document.element.body.makeelement(
            '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}tblHeader', {},
        ),
    )

    flux = io.BytesIO()
    document.save(flux)
    return flux.getvalue()


def construire_pdf(colonnes, lignes, titre='', sous_titre='', **_):
    """PDF A4 paysage, en-tête répété et pied de page paginé."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle

    bleu = colors.HexColor('#1A68AC')
    gris = colors.HexColor('#EEF4FF')
    styles = getSampleStyleSheet()
    style_titre = ParagraphStyle(
        'TitreExport', parent=styles['Title'], fontSize=16, textColor=bleu, spaceAfter=4,
    )
    style_sous_titre = ParagraphStyle(
        'SousTitreExport', parent=styles['Normal'], fontSize=9,
        textColor=colors.HexColor('#556577'), alignment=TA_CENTER, spaceAfter=12,
    )
    style_cellule = ParagraphStyle(
        'CelluleExport', parent=styles['Normal'], fontSize=7, leading=8.6,
    )

    flux = io.BytesIO()
    document = SimpleDocTemplate(
        flux, pagesize=landscape(A4),
        leftMargin=12 * mm, rightMargin=12 * mm, topMargin=12 * mm, bottomMargin=14 * mm,
        title=titre or 'Export', author='INJS',
    )
    elements = [
        Paragraph(titre or 'Export', style_titre),
        Paragraph(
            (sous_titre + ' — ' if sous_titre else '')
            + 'Institut National de la Jeunesse et des Sports — export du '
            + timezone.localtime().strftime('%d/%m/%Y à %H:%M')
            + f' — {len(lignes)} ligne(s)',
            style_sous_titre,
        ),
    ]
    corps = [[Paragraph(f'<b>{colonne}</b>', style_cellule) for colonne in colonnes]]
    for ligne in lignes:
        corps.append([
            Paragraph(str(_propre(ligne.get(colonne, ''))), style_cellule) for colonne in colonnes
        ])
    table = Table(corps, repeatRows=1, colWidths=[(273 * mm) / max(len(colonnes), 1)] * len(colonnes))
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

    def _pied(canevas, doc):
        canevas.saveState()
        canevas.setFont('Helvetica', 7)
        canevas.setFillColor(colors.HexColor('#556577'))
        canevas.drawString(12 * mm, 8 * mm, 'INJS — référentiels pédagogiques')
        canevas.drawRightString(285 * mm, 8 * mm, f'Page {doc.page}')
        canevas.restoreState()

    document.build(elements, onFirstPage=_pied, onLaterPages=_pied)
    return flux.getvalue()


_CONSTRUCTEURS = {
    'csv': lambda colonnes, lignes, **_: construire_csv(colonnes, lignes),
    'xlsx': construire_xlsx,
    'docx': construire_docx,
    'pdf': construire_pdf,
}


def construire(colonnes, lignes, fmt, **options):
    """Contenu binaire du tableau dans le format demandé."""
    return _CONSTRUCTEURS[fmt](colonnes, lignes, **options)


def reponse(colonnes, lignes, fmt, nom_fichier, **options):
    """Réponse HTTP de téléchargement (jamais mise en cache)."""
    contenu = construire(colonnes, lignes, fmt, **options)
    reponse_http = HttpResponse(contenu, content_type=CONTENT_TYPES[fmt])
    reponse_http['Content-Disposition'] = f'attachment; filename="{nom_fichier}"'
    reponse_http['Content-Length'] = str(len(contenu))
    reponse_http['Cache-Control'] = 'private, no-store'
    return reponse_http


__all__ = ['FORMATS', 'EXTENSIONS', 'construire', 'reponse']
