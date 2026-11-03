"""Export de la liste d'un groupe pédagogique LMD (PDF et Excel).

La « liste de classe » historique (`exports.participants_list_export`)
travaille sur le champ libre `Participant.groupe` de la formation
continue : elle ne connaît pas les sections TD/TP du cycle LMD
(`scolarite.Groupe` + `AffectationGroupe`). Ce module produit l'équivalent
LMD : la liste nominative des étudiants affectés à un groupe, avec colonne
d'émargement pour les séances de TD/TP.
"""

import io
import re
from datetime import datetime

try:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    REPORTLAB_AVAILABLE = True
except ImportError:  # pragma: no cover - ReportLab fait partie des dépendances
    REPORTLAB_AVAILABLE = False

try:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    OPENPYXL_AVAILABLE = True
except ImportError:  # pragma: no cover
    OPENPYXL_AVAILABLE = False

_HEADER_LINES = [
    "RÉPUBLIQUE DE CÔTE D'IVOIRE",
    "Institut National de la Jeunesse et des Sports — INJS",
    "Scolarité LMD",
]

_TABLE_HEADERS = ['N°', 'Matricule', 'Nom', 'Prénom(s)', 'Sexe', 'Téléphone', 'Émargement']


def groupe_membres(groupe):
    """Étudiants affectés activement au groupe, triés alphabétiquement."""
    participants = [
        affectation.inscription.etudiant.participant
        for affectation in (
            groupe.affectations
            .filter(active=True)
            .select_related('inscription__etudiant__participant')
        )
    ]
    return sorted(
        participants,
        key=lambda p: ((p.nom or '').upper(), (p.prenom or '').upper()),
    )


def _sexe_label(participant):
    return {'MASCULIN': 'M', 'FEMININ': 'F'}.get(participant.sexe, '—')


def _lignes(groupe):
    return [
        [
            str(numero),
            participant.matricule or '—',
            (participant.nom or '').upper(),
            participant.prenom or '',
            _sexe_label(participant),
            participant.telephone or '—',
            '',
        ]
        for numero, participant in enumerate(groupe_membres(groupe), start=1)
    ]


def _meta_lignes(groupe, effectif):
    return [
        f'Année académique : {groupe.annee_academique.libelle}',
        f'Formation : {groupe.ref_formation.intitule}',
        f'Niveau : {groupe.niveau.code} — Groupe : {groupe.nom}',
        f'Effectif : {effectif} étudiant(s)',
    ]


def export_groupe_pdf(groupe):
    if not REPORTLAB_AVAILABLE:
        raise RuntimeError('ReportLab non disponible')

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=1.2 * cm, rightMargin=1.2 * cm,
        topMargin=1.0 * cm, bottomMargin=1.0 * cm,
    )
    styles = getSampleStyleSheet()
    style_inst = ParagraphStyle(
        'Inst', parent=styles['Normal'], fontSize=8, alignment=TA_CENTER,
        textColor=colors.HexColor('#555555'), spaceAfter=1)
    style_title = ParagraphStyle(
        'Title', parent=styles['Title'], fontSize=14,
        textColor=colors.HexColor('#1A68AC'), alignment=TA_CENTER, spaceAfter=4)
    style_sub = ParagraphStyle(
        'Sub', parent=styles['Normal'], fontSize=9, alignment=TA_CENTER,
        textColor=colors.HexColor('#444444'), spaceAfter=2)
    cell_normal = ParagraphStyle('Cell', parent=styles['Normal'], fontSize=8, leading=10)
    cell_header = ParagraphStyle(
        'Hdr', parent=cell_normal, fontName='Helvetica-Bold',
        textColor=colors.white, alignment=TA_CENTER)

    def _p(text, hdr=False):
        safe = str(text).replace('&', '&amp;').replace('<', '&lt;')
        return Paragraph(safe, cell_header if hdr else cell_normal)

    lignes = _lignes(groupe)
    elements = []
    for line in _HEADER_LINES:
        elements.append(Paragraph(line, style_inst))
    elements.append(Spacer(1, 0.2 * cm))
    elements.append(Paragraph('LISTE DU GROUPE — SECTIONS TD/TP', style_title))
    for ligne_meta in _meta_lignes(groupe, len(lignes)):
        elements.append(Paragraph(ligne_meta, style_sub))
    elements.append(Paragraph(
        f"Exporté le {datetime.now().strftime('%d/%m/%Y à %H:%M')}", style_sub))
    elements.append(Spacer(1, 0.25 * cm))

    if not lignes:
        elements.append(Paragraph('Aucun étudiant affecté à ce groupe.', style_sub))
    else:
        data = [[_p(h, hdr=True) for h in _TABLE_HEADERS]]
        data += [[_p(v) for v in ligne] for ligne in lignes]
        table = Table(
            data, repeatRows=1,
            colWidths=[0.8 * cm, 2.6 * cm, 4.2 * cm, 4.2 * cm, 1.1 * cm, 2.6 * cm, 3.1 * cm],
        )
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1A68AC')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#CCCCCC')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN', (0, 1), (0, -1), 'CENTER'),
            ('ALIGN', (4, 1), (4, -1), 'CENTER'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1),
             [colors.white, colors.HexColor('#F4F7FB')]),
        ]))
        elements.append(table)

    doc.build(elements)
    buffer.seek(0)
    return buffer


def export_groupe_excel(groupe):
    if not OPENPYXL_AVAILABLE:
        raise RuntimeError('openpyxl non disponible')

    lignes = _lignes(groupe)
    wb = Workbook()
    ws = wb.active
    titre = re.sub(r'[\\/*?:\[\]]', ' ', f'{groupe.nom} {groupe.niveau.code}')[:28].strip()
    ws.title = titre or 'Groupe'

    gras = Font(bold=True)
    entete_fill = PatternFill('solid', fgColor='1A68AC')
    entete_font = Font(bold=True, color='FFFFFF')

    ligne = 1
    for texte in _HEADER_LINES:
        ws.cell(row=ligne, column=1, value=texte).font = Font(size=9, color='555555')
        ligne += 1
    ligne += 1
    ws.cell(row=ligne, column=1, value='LISTE DU GROUPE — SECTIONS TD/TP').font = Font(
        bold=True, size=13, color='1A68AC')
    ligne += 1
    for ligne_meta in _meta_lignes(groupe, len(lignes)):
        ws.cell(row=ligne, column=1, value=ligne_meta)
        ligne += 1
    ligne += 1

    for colonne, entete in enumerate(_TABLE_HEADERS, start=1):
        cellule = ws.cell(row=ligne, column=colonne, value=entete)
        cellule.font = entete_font
        cellule.fill = entete_fill
        cellule.alignment = Alignment(horizontal='center')
    ligne += 1
    for valeurs in lignes:
        for colonne, valeur in enumerate(valeurs, start=1):
            ws.cell(row=ligne, column=colonne, value=valeur)
        ligne += 1

    for colonne, largeur in enumerate([5, 14, 24, 24, 7, 16, 18], start=1):
        ws.column_dimensions[chr(64 + colonne)].width = largeur

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer


def groupe_liste_filename(groupe, fmt):
    slug = re.sub(r'[^\w\-]+', '_', f'{groupe.nom}_{groupe.niveau.code}').strip('_')
    return f'liste_groupe_{slug}.{"pdf" if fmt == "pdf" else "xlsx"}'
