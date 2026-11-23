"""Génération PDF des fiches de notes : par module (classe entière) et par auditeur."""
import io
import re

try:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    REPORTLAB_AVAILABLE = True
except Exception:
    REPORTLAB_AVAILABLE = False


_HEADER_LINES = [
    "RÉPUBLIQUE DE CÔTE D'IVOIRE",
    "Ministère de la Promotion des Sports et du Développement de l'Économie Sportive",
    "Institut National de la Jeunesse et des Sports (INJS)",
    "UFR STAPS-JL — Système LMD",
]

CI_GREEN_DARK = colors.HexColor('#1A68AC')
CI_LIGHT_GREEN = colors.HexColor('#E8EFF5')
GREY_LINE = colors.HexColor('#9E9E9E')
ROW_ALT = colors.HexColor('#F7F7F7')
ADMIS_GREEN = colors.HexColor('#093F70')
REFUSE_RED = colors.HexColor('#B71C1C')

MENTION_LABELS = {
    'TRES_BIEN': 'Très bien',
    'BIEN': 'Bien',
    'ASSEZ_BIEN': 'Assez bien',
    'PASSABLE': 'Passable',
    'INSUFFISANT': 'Insuffisant',
}


def _mention_label(code):
    return MENTION_LABELS.get(code or '', '—')


def _fmt(value, suffix=''):
    if value is None or value == '':
        return '—'
    return f'{value}{suffix}'


def _fmt_note(value):
    """Formate une note en supprimant les décimales inutiles (14.00 -> 14, 14.50 -> 14.5)."""
    if value is None or value == '':
        return '—'
    try:
        num = float(value)
    except (TypeError, ValueError):
        return str(value)
    text = f'{num:.2f}'.rstrip('0').rstrip('.')
    return text or '0'


def slugify_filename(value, fallback='fiche'):
    slug = re.sub(r'[^a-z0-9]+', '_', str(value or '').lower()).strip('_')
    return slug or fallback


def _styles():
    base = getSampleStyleSheet()
    return {
        'header': ParagraphStyle(
            'FicheHeader', parent=base['Normal'],
            fontSize=7.5, leading=10, alignment=TA_CENTER, textColor=colors.HexColor('#424242'),
        ),
        'title': ParagraphStyle(
            'FicheTitle', parent=base['Normal'],
            fontSize=14, leading=17, alignment=TA_CENTER, fontName='Helvetica-Bold',
            textColor=CI_GREEN_DARK, spaceBefore=6, spaceAfter=2,
        ),
        'subtitle': ParagraphStyle(
            'FicheSubtitle', parent=base['Normal'],
            fontSize=9.5, leading=13, alignment=TA_CENTER, fontName='Helvetica-Bold',
        ),
        'normal': ParagraphStyle('FicheNormal', parent=base['Normal'], fontSize=8.5, leading=11),
        'small': ParagraphStyle(
            'FicheSmall', parent=base['Normal'],
            fontSize=7.5, leading=10, textColor=colors.HexColor('#616161'),
        ),
        'section': ParagraphStyle(
            'FicheSection', parent=base['Normal'],
            fontSize=10, leading=13, fontName='Helvetica-Bold', textColor=CI_GREEN_DARK,
            spaceBefore=8, spaceAfter=4,
        ),
        'cell': ParagraphStyle('FicheCell', parent=base['Normal'], fontSize=8, leading=9.5),
        'cell_head': ParagraphStyle(
            'FicheCellHead', parent=base['Normal'],
            fontSize=7.5, leading=9, alignment=TA_CENTER,
            fontName='Helvetica-Bold', textColor=colors.white,
        ),
    }


def _institution_header(styles):
    elements = [Paragraph(line, styles['header']) for line in _HEADER_LINES]
    elements.append(Spacer(1, 8))
    return elements


def _meta_table(pairs, styles, total_width, columns=3):
    """Grille libellé/valeur compacte pour les métadonnées d'en-tête."""
    pairs = [(label, value) for label, value in pairs if value not in (None, '', '—')]
    if not pairs:
        return []

    cells = [
        Paragraph(f'<font color="#616161">{label} :</font> <b>{value}</b>', styles['normal'])
        for label, value in pairs
    ]
    rows = [cells[i:i + columns] for i in range(0, len(cells), columns)]
    if rows and len(rows[-1]) < columns:
        rows[-1] += [''] * (columns - len(rows[-1]))

    table = Table(rows, colWidths=[total_width / columns] * columns)
    table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 1.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1.5),
    ]))
    return [table, Spacer(1, 6)]


def _signature_block(labels, total_width, styles):
    """Un trait de signature distinct par signataire, séparé par une gouttière."""
    gap = 1.2 * cm
    signature_width = (total_width - gap * (len(labels) - 1)) / len(labels)

    cells = []
    col_widths = []
    for index, label in enumerate(labels):
        if index:
            cells.append('')
            col_widths.append(gap)
        cells.append(Paragraph(label, styles['small']))
        col_widths.append(signature_width)

    table = Table([cells], colWidths=col_widths, rowHeights=[1.9 * cm])
    style = [
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING', (0, 0), (-1, -1), 2),
    ]
    for column in range(0, len(cells), 2):
        style.append(('LINEBELOW', (column, 0), (column, 0), 0.4, GREY_LINE))
    table.setStyle(TableStyle(style))
    return [Spacer(1, 10), table]


def _module_col_widths(nb_colonnes, total_width):
    """Largeurs adaptatives : les colonnes de notes se partagent l'espace restant."""
    nb_colonnes = max(nb_colonnes, 1)
    head = [1.0, 2.5, 5.6, 1.5]          # N°, N° inscription, Nom & Prénoms, Grade
    tail = [1.7, 2.3, 2.3, 1.4]          # Moyenne, Mention, Cours effectué, Admis
    min_note_width = 1.15
    total_cm = total_width / cm

    available = total_cm - sum(head) - sum(tail)
    per_note = available / nb_colonnes

    if per_note < min_note_width:
        deficit = (min_note_width - per_note) * nb_colonnes
        for index, floor in ((2, 3.4), (1, 1.9)):
            if deficit <= 0:
                break
            taken = min(deficit, head[index] - floor)
            if taken > 0:
                head[index] -= taken
                deficit -= taken
        available = total_cm - sum(head) - sum(tail)
        per_note = max(available / nb_colonnes, 0.62)

    return [w * cm for w in head] + [per_note * cm] * nb_colonnes + [w * cm for w in tail]


def build_fiche_module_pdf(data):
    """Fiche de notes d'un module : tous les auditeurs inscrits, toutes les colonnes."""
    if not REPORTLAB_AVAILABLE:
        raise RuntimeError('reportlab non disponible sur ce serveur.')

    styles = _styles()
    module = data['module']
    criteres = data['criteres']
    colonnes = data['colonnes']
    rows = data['rows']

    buffer = io.BytesIO()
    page_size = landscape(A4)
    margin = 1.1 * cm
    doc = SimpleDocTemplate(
        buffer,
        pagesize=page_size,
        leftMargin=margin, rightMargin=margin,
        topMargin=1.0 * cm, bottomMargin=1.0 * cm,
        title=f"Fiche de notes — {module['intitule']}",
    )
    total_width = page_size[0] - 2 * margin

    elements = _institution_header(styles)
    elements.append(Paragraph('FICHE DE NOTES', styles['title']))
    elements.append(Paragraph(module['intitule'], styles['subtitle']))
    elements.append(Spacer(1, 8))

    elements += _meta_table([
        ('Cycle / Formation', module['formation']),
        ('Grade', module['grade']),
        ('Groupe', module['groupe']),
        ('Vague', module['vague']),
        ('Secrétariat', module['secretariat']),
        ('Lieu', module['lieu']),
        ('Période', module['periode']),
        ('Formateur', module['formateur']),
        ('Encadrant', module['encadrant']),
    ], styles, total_width, columns=3)

    elements.append(Paragraph(
        f"Admis si moyenne ≥ <b>{_fmt_note(criteres['seuil_admission'])}/20</b>"
        f" et temps de cours effectué ≥ <b>{_fmt_note(criteres['taux_presence_min'])}%</b>",
        styles['small'],
    ))
    elements.append(Spacer(1, 8))

    header = [
        Paragraph('N°', styles['cell_head']),
        Paragraph('N° inscription', styles['cell_head']),
        Paragraph('Nom &amp; Prénoms', styles['cell_head']),
        Paragraph('Grade', styles['cell_head']),
    ]
    for colonne in colonnes:
        header.append(Paragraph(
            f"{colonne['libelle']}<br/><font size=6>/ {_fmt_note(colonne['note_max'])}</font>",
            styles['cell_head'],
        ))
    header += [
        Paragraph('Moy.<br/>/20', styles['cell_head']),
        Paragraph('Mention', styles['cell_head']),
        Paragraph('Cours<br/>effectué', styles['cell_head']),
        Paragraph('Admis', styles['cell_head']),
    ]

    table_data = [header]
    admis_cells = []
    refuse_cells = []

    for index, row in enumerate(rows, start=1):
        line = [
            str(index),
            row['matricule'] or '—',
            Paragraph(f"<b>{row['nom']}</b> {row['prenom']}", styles['cell']),
            row['grade'] or '—',
        ]
        for colonne in colonnes:
            line.append(_fmt_note(row['notes'].get(colonne['id'])))
        line += [
            _fmt_note(row['moyenne']),
            _mention_label(row['mention']),
            _fmt(row['taux_presence'], '%'),
            row['admis_label'],
        ]
        table_data.append(line)

        admis_col = len(line) - 1
        if row['admis_label'] == 'Oui':
            admis_cells.append((admis_col, index))
        elif row['admis_label'] == 'Non':
            refuse_cells.append((admis_col, index))

    if len(table_data) == 1:
        elements.append(Paragraph('Aucun étudiant inscrit à ce module.', styles['normal']))
    else:
        table = Table(
            table_data,
            colWidths=_module_col_widths(len(colonnes), total_width),
            repeatRows=1,
        )
        style = [
            ('BACKGROUND', (0, 0), (-1, 0), CI_GREEN_DARK),
            ('GRID', (0, 0), (-1, -1), 0.35, GREY_LINE),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('ALIGN', (0, 0), (0, -1), 'CENTER'),
            ('ALIGN', (3, 1), (-1, -1), 'CENTER'),
            ('LEFTPADDING', (0, 0), (-1, -1), 3),
            ('RIGHTPADDING', (0, 0), (-1, -1), 3),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('FONTNAME', (-4, 1), (-4, -1), 'Helvetica-Bold'),
        ]
        for line_index in range(2, len(table_data), 2):
            style.append(('BACKGROUND', (0, line_index), (-1, line_index), ROW_ALT))
        for col, line_index in admis_cells:
            style.append(('TEXTCOLOR', (col, line_index), (col, line_index), ADMIS_GREEN))
            style.append(('FONTNAME', (col, line_index), (col, line_index), 'Helvetica-Bold'))
        for col, line_index in refuse_cells:
            style.append(('TEXTCOLOR', (col, line_index), (col, line_index), REFUSE_RED))
        table.setStyle(TableStyle(style))
        elements.append(table)

    stats = data['stats']
    elements.append(Spacer(1, 8))
    elements.append(Paragraph(
        f"<b>{stats['total']}</b> étudiant(s) inscrit(s) · <b>{stats['notes']}</b> noté(s)"
        f" · Moyenne de classe : <b>{_fmt_note(stats['moyenne_classe'])}/20</b>"
        f" · Admis : <b>{stats['admis']}</b> · Non admis : <b>{stats['non_admis']}</b>",
        styles['normal'],
    ))

    elements += _signature_block(
        ['Le Formateur', 'Le Chef du Secrétariat', 'La Direction'],
        total_width, styles,
    )
    elements.append(Spacer(1, 6))
    elements.append(Paragraph(data['edite_le_label'], styles['small']))

    doc.build(elements)
    buffer.seek(0)
    return buffer


def build_fiche_auditeur_pdf(data):
    """Fiche de notes individuelle d'un auditeur pour un module."""
    if not REPORTLAB_AVAILABLE:
        raise RuntimeError('reportlab non disponible sur ce serveur.')

    styles = _styles()
    module = data['module']
    criteres = data['criteres']
    colonnes = data['colonnes']
    row = data['row']

    buffer = io.BytesIO()
    margin = 1.6 * cm
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=margin, rightMargin=margin,
        topMargin=1.2 * cm, bottomMargin=1.2 * cm,
        title=f"Fiche de notes — {row['nom']} {row['prenom']}",
    )
    total_width = A4[0] - 2 * margin

    elements = _institution_header(styles)
    elements.append(Paragraph('FICHE DE NOTES INDIVIDUELLE', styles['title']))
    elements.append(Paragraph(f"{row['nom']} {row['prenom']}", styles['subtitle']))
    elements.append(Spacer(1, 10))

    elements.append(Paragraph("Étudiant", styles['section']))
    elements += _meta_table([
        ('N° inscription', row['matricule']),
        ('Grade', row['grade']),
        ('Nom', row['nom']),
        ('Prénoms', row['prenom']),
    ], styles, total_width, columns=2)

    elements.append(Paragraph("Cours", styles['section']))
    elements += _meta_table([
        ('Intitulé', module['intitule']),
        ('Cycle / Formation', module['formation']),
        ('Grade', module['grade']),
        ('Groupe', module['groupe']),
        ('Vague', module['vague']),
        ('Secrétariat', module['secretariat']),
        ('Lieu', module['lieu']),
        ('Période', module['periode']),
        ('Formateur', module['formateur']),
    ], styles, total_width, columns=2)

    elements.append(Paragraph("Notes obtenues", styles['section']))
    table_data = [[
        Paragraph('Épreuve', styles['cell_head']),
        Paragraph('Note', styles['cell_head']),
        Paragraph('Barème', styles['cell_head']),
        Paragraph('Ramenée /20', styles['cell_head']),
    ]]
    for colonne in colonnes:
        table_data.append([
            Paragraph(colonne['libelle'], styles['cell']),
            _fmt_note(row['notes'].get(colonne['id'])),
            f"/ {_fmt_note(colonne['note_max'])}",
            _fmt_note(row['notes_sur_20'].get(colonne['id'])),
        ])

    notes_table = Table(table_data, colWidths=[total_width - 8.1 * cm, 2.7 * cm, 2.7 * cm, 2.7 * cm], repeatRows=1)
    notes_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), CI_GREEN_DARK),
        ('GRID', (0, 0), (-1, -1), 0.35, GREY_LINE),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (1, 1), (1, -1), 'Helvetica-Bold'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(notes_table)
    elements.append(Spacer(1, 4))

    elements.append(Paragraph("Synthèse", styles['section']))
    heures = '—'
    if row['heures_presence'] is not None and row['heures_prevues'] is not None:
        heures = f"{_fmt_note(row['heures_presence'])} h / {_fmt_note(row['heures_prevues'])} h"

    synthese_rows = [
        ['Moyenne générale', f"{_fmt_note(row['moyenne'])} / 20"],
        ['Mention', _mention_label(row['mention'])],
        ['Temps de cours effectué', _fmt(row['taux_presence'], ' %')],
        ['Heures effectuées / prévues', heures],
        ['Décision', row['admis_label_long']],
    ]
    synthese_table = Table(synthese_rows, colWidths=[6.2 * cm, total_width - 6.2 * cm])
    synthese_style = [
        ('GRID', (0, 0), (-1, -1), 0.35, GREY_LINE),
        ('BACKGROUND', (0, 0), (0, -1), CI_LIGHT_GREEN),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('FONTNAME', (1, 0), (1, 0), 'Helvetica-Bold'),
        ('FONTNAME', (1, -1), (1, -1), 'Helvetica-Bold'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]
    if row['admis_label'] == 'Oui':
        synthese_style.append(('TEXTCOLOR', (1, -1), (1, -1), ADMIS_GREEN))
    elif row['admis_label'] == 'Non':
        synthese_style.append(('TEXTCOLOR', (1, -1), (1, -1), REFUSE_RED))
    synthese_table.setStyle(TableStyle(synthese_style))
    elements.append(synthese_table)

    elements.append(Spacer(1, 4))
    elements.append(Paragraph(
        f"Critères d'admission : moyenne ≥ {_fmt_note(criteres['seuil_admission'])}/20"
        f" et temps de cours effectué ≥ {_fmt_note(criteres['taux_presence_min'])}%",
        styles['small'],
    ))

    if row['observations']:
        elements.append(Paragraph("Observations", styles['section']))
        elements.append(Paragraph(row['observations'], styles['normal']))

    elements.append(KeepTogether(
        _signature_block(['Le Formateur', 'Le Chef du Secrétariat'], total_width, styles)
    ))
    elements.append(Spacer(1, 6))
    elements.append(Paragraph(data['edite_le_label'], styles['small']))

    doc.build(elements)
    buffer.seek(0)
    return buffer


def fiche_module_filename(module_data, module_pk):
    return f"fiche_notes_{slugify_filename(module_data['intitule'], 'module')}_{module_pk}.pdf"


def fiche_auditeur_filename(row, module_pk):
    who = slugify_filename(f"{row['nom']}_{row['prenom']}", 'auditeur')
    return f"fiche_notes_{who}_module_{module_pk}.pdf"
