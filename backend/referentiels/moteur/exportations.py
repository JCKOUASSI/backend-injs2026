"""Générateur d'exports du module Référentiels (mission « Référentiels »).

Quatre formats obligatoires : **Word (.docx)**, **Excel (.xlsx)**, **CSV (.csv)**
et **PDF (.pdf)**. Un seul point de code pour les 27 référentiels du registre :
le format ne connaît que des colonnes et des lignes, jamais un modèle précis.

Chaque document porte l'identification institutionnelle, le nom du
référentiel, le titre, la date et l'heure de génération, les en-têtes, les
données et le nombre total d'enregistrements.

Aucune donnée n'est inventée : une valeur absente est rendue vide, jamais
remplacée par une estimation.
"""

import io
from datetime import datetime, timezone as dt_timezone

from django.utils import timezone

# ── Charte du document ───────────────────────────────────────────────────────
INSTITUTION = 'INSTITUT NATIONAL DE LA JEUNESSE ET DES SPORTS'
INSTITUTION_SUITE = 'INJS — Abidjan (République de Côte d’Ivoire)'
SERVICE = 'Direction des Études et de la Scolarité — Hub Référentiels'

FORMATS = ('xlsx', 'csv', 'docx', 'pdf')

TYPES_MIME = {
    'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'csv': 'text/csv; charset=utf-8',
    'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'pdf': 'application/pdf',
}

# Limite de sécurité : au-delà, le PDF deviendrait illisible et la mémoire
# saturée. Le message est explicite plutôt que de tronquer silencieusement.
LIMITE_LIGNES = 20000


def _horodatage():
    return timezone.localtime(timezone.now())


def _formater(valeur):
    """Rendu texte d'une valeur exportée (booléens et dates lisibles)."""
    if valeur is None:
        return ''
    if isinstance(valeur, bool):
        return 'Oui' if valeur else 'Non'
    if isinstance(valeur, datetime):
        return timezone.localtime(valeur).strftime('%d/%m/%Y %H:%M')
    return str(valeur)


def nom_fichier(slug, format_cible, horodate=None):
    """Nom de fichier déterministe : ``referentiel_AAAAMMJJ-HHMM.xlsx``."""
    horodate = horodate or _horodatage()
    return f'{slug}_{horodate.strftime("%Y%m%d-%H%M")}.{format_cible}'


def _entete(colonnes, lignes, titre, referentiel):
    """Bloc d'identification commun aux quatre formats."""
    return {
        'institution': INSTITUTION,
        'institution_suite': INSTITUTION_SUITE,
        'service': SERVICE,
        'titre': titre or f"Référentiel « {referentiel} »",
        'referentiel': referentiel,
        'genere_le': _horodatage().strftime('%d/%m/%Y à %H:%M:%S'),
        'total': len(lignes),
        'colonnes': colonnes,
    }


def _lignes_matrices(colonnes, lignes):
    """Convertit les enregistrements en matrice [en-têtes, ...lignes]."""
    matrice = [[c['libelle'] for c in colonnes]]
    for ligne in lignes:
        matrice.append([_formater(_valeur(ligne, c['cle'])) for c in colonnes])
    return matrice


def _valeur(ligne, cle):
    if isinstance(ligne, dict):
        if cle in ligne:
            return ligne[cle]
        # Valeurs calculées côté serializer (ex. ``annee_academique_libelle``)
        return ligne.get(f'{cle}_libelle', ligne.get(f'{cle}_nom', ''))
    return getattr(ligne, cle, '')


# ── CSV ──────────────────────────────────────────────────────────────────────
def _csv(colonnes, lignes, titre, referentiel):
    """CSV UTF-8 avec BOM (lisible par Excel), séparateur « ; » francophone."""
    meta = _entete(colonnes, lignes, titre, referentiel)
    tampon = io.StringIO()
    # Métadonnées en commentaires : traçables sans casser le tableau.
    tampon.write(f"# {meta['institution']}\n")
    tampon.write(f"# {meta['institution_suite']}\n")
    tampon.write(f"# {meta['service']}\n")
    tampon.write(f"# Référentiel : {meta['referentiel']}\n")
    tampon.write(f"# Titre : {meta['titre']}\n")
    tampon.write(f"# Généré le : {meta['genere_le']}\n")
    tampon.write(f"# Total : {meta['total']} enregistrement(s)\n")
    tampon.write('\n')

    import csv
    writer = csv.writer(tampon, delimiter=';', quoting=csv.QUOTE_MINIMAL,
                        lineterminator='\r\n')
    for rangee in _lignes_matrices(colonnes, lignes):
        writer.writerow(rangee)
    # BOM UTF-8 : Excel interprète correctement les accents.
    return ('﻿' + tampon.getvalue()).encode('utf-8')


# ── Excel ────────────────────────────────────────────────────────────────────
def _xlsx(colonnes, lignes, titre, referentiel):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    meta = _entete(colonnes, lignes, titre, referentiel)
    classeur = Workbook()
    feuille = classeur.active
    feuille.title = 'Référentiel'[:31]

    bleu = '1F3864'
    gris = 'DCE6F1'
    feuille['A1'] = meta['institution']
    feuille['A1'].font = Font(bold=True, size=14, color=bleu)
    feuille['A2'] = meta['institution_suite']
    feuille['A3'] = meta['service']
    feuille['A3'].font = Font(italic=True, size=9)
    feuille['A5'] = meta['titre']
    feuille['A5'].font = Font(bold=True, size=12)
    feuille['A6'] = f"Référentiel : {meta['referentiel']} — généré le {meta['genere_le']}"
    feuille['A7'] = f"Total : {meta['total']} enregistrement(s)"
    feuille['A7'].font = Font(bold=True)

    ligne_depart = 9
    for index, colonne in enumerate(colonnes, start=1):
        cellule = feuille.cell(row=ligne_depart, column=index, value=colonne['libelle'])
        cellule.font = Font(bold=True, color='FFFFFF')
        cellule.fill = PatternFill('solid', fgColor=bleu)
        cellule.alignment = Alignment(horizontal='center', vertical='center')

    for decalage, ligne in enumerate(lignes, start=ligne_depart + 1):
        for index, colonne in enumerate(colonnes, start=1):
            valeur = _formater(_valeur(ligne, colonne['cle']))
            cellule = feuille.cell(row=decalage, column=index, value=valeur)
            if decalage % 2:
                cellule.fill = PatternFill('solid', fgColor=gris)

    # Largeurs adaptées au contenu (bornées pour rester lisibles).
    for index, colonne in enumerate(colonnes, start=1):
        largeur = len(str(colonne['libelle']))
        for ligne in lignes[:200]:
            largeur = max(largeur, len(str(_formater(_valeur(ligne, colonne['cle'])))))
        feuille.column_dimensions[get_column_letter(index)].width = min(max(largeur + 3, 10), 60)

    if lignes:
        derniere = get_column_letter(len(colonnes))
        feuille.auto_filter.ref = f'A{ligne_depart}:{derniere}{ligne_depart + len(lignes)}'
    feuille.freeze_panes = feuille.cell(row=ligne_depart + 1, column=1)

    tampon = io.BytesIO()
    classeur.save(tampon)
    return tampon.getvalue()


# ── Word ─────────────────────────────────────────────────────────────────────
def _docx(colonnes, lignes, titre, referentiel):
    from docx import Document
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt, RGBColor

    meta = _entete(colonnes, lignes, titre, referentiel)
    document = Document()

    en_tete = document.add_paragraph()
    en_tete.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = en_tete.add_run(meta['institution'])
    run.bold = True
    run.font.size = Pt(14)
    run.font.color.rgb = RGBColor(0x1F, 0x38, 0x64)
    suite = document.add_paragraph()
    suite.alignment = WD_ALIGN_PARAGRAPH.CENTER
    suite.add_run(meta['institution_suite']).italic = True
    service = document.add_paragraph()
    service.alignment = WD_ALIGN_PARAGRAPH.CENTER
    service.add_run(meta['service']).font.size = Pt(9)

    document.add_heading(meta['titre'], level=1)
    sous_titre = document.add_paragraph()
    sous_titre.add_run(f"Référentiel : {meta['referentiel']}\n").bold = True
    sous_titre.add_run(f"Généré le {meta['genere_le']} — ")
    sous_titre.add_run(f"{meta['total']} enregistrement(s)").bold = True

    tableau = document.add_table(rows=1, cols=len(colonnes))
    tableau.style = 'Light Grid Accent 1'
    tableau.alignment = WD_TABLE_ALIGNMENT.CENTER
    for index, colonne in enumerate(colonnes):
        cellule = tableau.rows[0].cells[index]
        cellule.text = str(colonne['libelle'])
        for paragraphe in cellule.paragraphs:
            for run in paragraphe.runs:
                run.bold = True
    # Répétition de l'en-tête sur chaque page du tableau Word.
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    tr_pr = tableau.rows[0]._tr.get_or_add_trPr()
    entete_repetee = OxmlElement('w:tblHeader')
    entete_repetee.set(qn('w:val'), 'true')
    tr_pr.append(entete_repetee)

    for ligne in lignes:
        cellules = tableau.add_row().cells
        for index, colonne in enumerate(colonnes):
            cellules[index].text = _formater(_valeur(ligne, colonne['cle']))

    tampon = io.BytesIO()
    document.save(tampon)
    return tampon.getvalue()


# ── PDF ──────────────────────────────────────────────────────────────────────
def _pdf(colonnes, lignes, titre, referentiel):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import (PageBreak, Paragraph, SimpleDocTemplate,
                                    Spacer, Table, TableStyle)

    meta = _entete(colonnes, lignes, titre, referentiel)
    # Paysage dès que la table est large : sinon les colonnes sont illisibles.
    paysage = len(colonnes) > 5
    format_page = landscape(A4) if paysage else A4

    styles = getSampleStyleSheet()
    style_titre = ParagraphStyle('titre_injs', parent=styles['Title'], fontSize=13,
                                 textColor=colors.HexColor('#1F3864'), spaceAfter=2)
    style_meta = ParagraphStyle('meta_injs', parent=styles['Normal'], fontSize=8,
                                textColor=colors.HexColor('#444444'), spaceAfter=1)

    tampon = io.BytesIO()
    document = SimpleDocTemplate(
        tampon, pagesize=format_page,
        leftMargin=1.4 * cm, rightMargin=1.4 * cm,
        topMargin=1.4 * cm, bottomMargin=1.6 * cm,
        title=meta['titre'], author=INSTITUTION,
    )

    largeur_utile = format_page[0] - 2.8 * cm
    colonnes_utiles = max(len(colonnes), 1)
    largeur_colonne = largeur_utile / colonnes_utiles

    cellule_entete = ParagraphStyle('cellule_entete', parent=styles['Normal'],
                                    fontSize=7.5, textColor=colors.white,
                                    fontName='Helvetica-Bold')
    cellule_corps = ParagraphStyle('cellule_corps', parent=styles['Normal'], fontSize=7.5)

    donnees = [[Paragraph(str(c['libelle']), cellule_entete) for c in colonnes]]
    for ligne in lignes:
        donnees.append([
            Paragraph(_formater(_valeur(ligne, c['cle'])), cellule_corps) for c in colonnes
        ])

    table = Table(donnees, colWidths=[largeur_colonne] * colonnes_utiles, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1F3864')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#B4C6E7')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#EEF3FB')]),
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))

    def _pied(canvas, doc):
        canvas.saveState()
        canvas.setFont('Helvetica', 7.5)
        canvas.setFillColor(colors.HexColor('#666666'))
        canvas.drawString(1.4 * cm, 1 * cm,
                          f"{INSTITUTION_SUITE} — {meta['referentiel']} — généré le {meta['genere_le']}")
        canvas.drawRightString(format_page[0] - 1.4 * cm, 1 * cm, f'Page {doc.page}')
        canvas.restoreState()

    recit = [
        Paragraph(INSTITUTION, style_titre),
        Paragraph(f"{INSTITUTION_SUITE} — {SERVICE}", style_meta),
        Spacer(1, 6),
        Paragraph(meta['titre'], style_titre),
        Paragraph(f"Référentiel : <b>{meta['referentiel']}</b> — "
                  f"{meta['total']} enregistrement(s) — généré le {meta['genere_le']}",
                  style_meta),
        Spacer(1, 8),
    ]
    if donnees and len(donnees) > 1:
        recit.append(table)
    else:
        recit.append(Paragraph('Aucune donnée à exporter pour ce référentiel.', style_meta))
    recit.append(PageBreak()) if False else None
    document.build(recit, onFirstPage=_pied, onLaterPages=_pied)
    return tampon.getvalue()


GENERATEURS = {'csv': _csv, 'xlsx': _xlsx, 'docx': _docx, 'pdf': _pdf}


def generer_export(*, slug, referentiel, colonnes, lignes, format_cible, titre=None):
    """Produit le document.

    Retourne ``(contenu, type_mime, nom_de_fichier)``.
    ``lignes`` est une liste d'enregistrements (objets ou dictionnaires) déjà
    filtrés selon les critères de l'utilisateur — l'export n'élargit jamais le
    périmètre de ce que l'écran affiche.
    """
    if format_cible not in GENERATEURS:
        raise ValueError(f'Format d’export inconnu : {format_cible}. Attendu : {", ".join(FORMATS)}.')
    if len(lignes) > LIMITE_LIGNES:
        raise ValueError(
            f'Export refusé : {len(lignes)} enregistrements demandés, '
            f'la limite est de {LIMITE_LIGNES}. Affinez les filtres.'
        )
    contenu = GENERATEURS[format_cible](colonnes, list(lignes), titre, referentiel)
    return contenu, TYPES_MIME[format_cible], nom_fichier(slug, format_cible)
