#!/usr/bin/env python3
"""PDF téléchargeable de la page « Référentiels de l'INJS » (tableau de bord).

Le document reproduit toutes les composantes de la page — en-tête,
indicateurs (KPI), exploration du catalogue, les 27 plaquettes regroupées
par catégorie (description, nombre de valeurs, état, action) et la note sur
les degrés de fiabilité — avec les compteurs **recalculés en base au moment
de la génération**, par la même logique que l'API
`/referentiels/tableau-de-bord/` (réutilise `instantane()` du générateur du
classeur de documentation : une seule logique de comptage).

Usage (depuis la racine du dépôt) :

    backend/.venv/bin/python scripts/generer_pdf_tableau_de_bord.py
    backend/.venv/bin/python scripts/generer_pdf_tableau_de_bord.py --sortie /tmp/page.pdf

Sortie par défaut : dossier_trvx/Referentiels_de_l_INJS_Tableau_de_bord.pdf
"""

import argparse
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / 'scripts'))
os.environ.setdefault('USE_SQLITE', '1')

# Réutilise la logique de comptage du classeur de documentation (import :
# effectue aussi le django.setup()).
from generer_doc_tableau_de_bord import action_affichee, etat_affiche, instantane  # noqa: E402

from reportlab.lib import colors  # noqa: E402
from reportlab.lib.enums import TA_CENTER, TA_LEFT  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import ParagraphStyle  # noqa: E402
from reportlab.lib.units import mm  # noqa: E402
from reportlab.platypus import (  # noqa: E402
    Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

BLEU = colors.HexColor('#1F3864')
BLEU_CLAIR = colors.HexColor('#DCE6F4')
FOND = colors.HexColor('#F2F6FC')
GRIS = colors.HexColor('#595959')
VERT = colors.HexColor('#2E7D32')
VERT_FOND = colors.HexColor('#E2EFDA')
AMBRE = colors.HexColor('#9C6500')
AMBRE_FOND = colors.HexColor('#FFF2CC')
ROUGE = colors.HexColor('#B3261E')
ROUGE_FOND = colors.HexColor('#FCE4EC')
BLANC = colors.white

AUJOURD_HUI = date.today().strftime('%d/%m/%Y')

S_TITRE = ParagraphStyle('titre', fontName='Helvetica-Bold', fontSize=19,
                         leading=22, textColor=BLEU)
S_BADGE = ParagraphStyle('badge', fontName='Helvetica-Bold', fontSize=7.5,
                         leading=9, textColor=BLEU)
S_SOUS_TITRE = ParagraphStyle('sous-titre', fontName='Helvetica', fontSize=9.5,
                              leading=12, textColor=GRIS)
S_KPI_VAL = ParagraphStyle('kpi-val', fontName='Helvetica-Bold', fontSize=15,
                           leading=17, textColor=BLEU, alignment=TA_CENTER)
S_KPI_LIB = ParagraphStyle('kpi-lib', fontName='Helvetica', fontSize=7.5,
                           leading=9, textColor=GRIS, alignment=TA_CENTER)
S_CAT = ParagraphStyle('categorie', fontName='Helvetica-Bold', fontSize=12,
                       leading=14, textColor=BLEU, spaceBefore=10)
S_CAT_DESC = ParagraphStyle('categorie-desc', fontName='Helvetica-Oblique',
                            fontSize=8.5, leading=10.5, textColor=GRIS)
S_CELL = ParagraphStyle('cellule', fontName='Helvetica', fontSize=8.3, leading=10.2)
S_CELL_G = ParagraphStyle('cellule-g', fontName='Helvetica-Bold', fontSize=8.3,
                          leading=10.2)
S_ENTETE = ParagraphStyle('entete', fontName='Helvetica-Bold', fontSize=8.3,
                          leading=10.2, textColor=BLANC)
S_NOTE = ParagraphStyle('note', fontName='Helvetica', fontSize=8.2,
                        leading=11, textColor=colors.HexColor('#333333'))
S_SECTION = ParagraphStyle('section', fontName='Helvetica-Bold', fontSize=10.5,
                           leading=13, textColor=BLEU, spaceBefore=8)

ETATS_STYLE = {
    'Complet': (VERT, VERT_FOND),
    'Provenance non suivie': (AMBRE, AMBRE_FOND),
    'Non renseigné': (ROUGE, ROUGE_FOND),
}


def _p(texte, style=S_CELL):
    return Paragraph(str(texte), style)


def bandeau_entete(synthese):
    gauche = [
        _p('SOURCE UNIQUE DE VÉRITÉ', S_BADGE),
        _p("Référentiels de l'INJS", S_TITRE),
        _p("Données officielles de l'établissement : écoles, filières, "
           'maquettes, lieux et nomenclatures pédagogiques.', S_SOUS_TITRE),
    ]
    pastilles = _p(
        f"<b>{synthese['nb_referentiels']}</b> référentiels"
        f" &nbsp;·&nbsp; <b>{synthese['nb_valeurs']}</b> valeurs",
        ParagraphStyle('pastilles', parent=S_CELL, alignment=TA_LEFT),
    )
    t = Table([[gauche, pastilles]], colWidths=[138 * mm, 42 * mm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), FOND),
        ('BOX', (0, 0), (-1, -1), 0.6, BLEU_CLAIR),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    return t


def bandeau_kpi(synthese):
    taux = synthese['taux_tracabilite']
    cellules = [
        [_p(str(synthese['nb_referentiels']), S_KPI_VAL),
         _p(str(synthese['nb_valeurs']), S_KPI_VAL),
         _p(str(synthese['nb_a_renseigner']), S_KPI_VAL),
         _p(f"{round(taux * 100)} %" if taux is not None else '—', S_KPI_VAL)],
        [_p('RÉFÉRENTIELS', S_KPI_LIB),
         _p('VALEURS RÉFÉRENCÉES', S_KPI_LIB),
         _p('À RENSEIGNER', S_KPI_LIB),
         _p('TAUX DE TRAÇABILITÉ', S_KPI_LIB)],
    ]
    t = Table(cellules, colWidths=[45 * mm] * 4)
    t.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.6, BLEU_CLAIR),
        ('INNERGRID', (0, 0), (-1, -1), 0.4, BLEU_CLAIR),
        ('TOPPADDING', (0, 0), (-1, 0), 6),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 0),
        ('TOPPADDING', (0, 1), (-1, 1), 0),
        ('BOTTOMPADDING', (0, 1), (-1, 1), 6),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    return t


def bloc_explorer(categories):
    puces = ' &nbsp;|&nbsp; '.join(
        ['<b>Toutes</b>'] + [c['libelle'] for c in categories])
    contenu = [
        _p('Explorer le catalogue', S_SECTION),
        _p('Rechercher un référentiel : filtrage instantané par libellé, '
           'description ou slug, combiné aux catégories ci-dessous.', S_NOTE),
        _p(f'Catégories : {puces}', S_NOTE),
    ]
    t = Table([[contenu]], colWidths=[180 * mm])
    t.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.6, BLEU_CLAIR),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
    ]))
    return t


def table_categorie(categorie):
    entetes = [_p('Référentiel', S_ENTETE), _p('Description', S_ENTETE),
               _p('Valeurs', S_ENTETE), _p('État', S_ENTETE), _p('Action', S_ENTETE)]
    lignes = [entetes]
    styles = [
        ('BACKGROUND', (0, 0), (-1, 0), BLEU),
        ('BOX', (0, 0), (-1, -1), 0.6, BLEU),
        ('INNERGRID', (0, 0), (-1, -1), 0.35, BLEU_CLAIR),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]
    for i, e in enumerate(categorie['entrees'], start=1):
        mesures = [f"<b>{e['total']}</b> valeur{'s' if e['total'] > 1 else ''}"]
        if e['a_renseigner']:
            mesures.append(f"<br/>{e['a_renseigner']} à renseigner")
        if e['archives']:
            mesures.append(f"<br/>{e['archives']} archivée(s)")
        etat = etat_affiche(e)
        bouton, _destination = action_affichee(e)
        lignes.append([
            _p(f"<b>{e['libelle']}</b>", S_CELL),
            _p(e['description'], S_CELL),
            _p(''.join(mesures), S_CELL),
            _p(etat, S_CELL_G),
            _p(bouton, S_CELL),
        ])
        couleur, fond = ETATS_STYLE.get(etat, (AMBRE, AMBRE_FOND))
        styles.append(('TEXTCOLOR', (3, i), (3, i), couleur))
        styles.append(('BACKGROUND', (3, i), (3, i), fond))
        if i % 2 == 0:
            styles.append(('BACKGROUND', (0, i), (2, i), FOND))
            styles.append(('BACKGROUND', (4, i), (4, i), FOND))
    t = Table(lignes, colWidths=[38 * mm, 70 * mm, 26 * mm, 26 * mm, 20 * mm],
              repeatRows=1)
    t.setStyle(TableStyle(styles))
    return t


def note_fiabilite():
    texte = (
        'Chaque valeur importée conserve le document qui l’atteste et son '
        'degré de fiabilité : <b>Officiel</b> pour ce que la source affirme, '
        '<b>Modélisé</b> pour les inventaires proposés par la source, '
        '<b>Cadrage</b> pour les catégories de travail et <b>À renseigner</b> '
        'lorsqu’aucune source ne fournit la valeur.'
    )
    t = Table([[_p(texte, S_NOTE)]], colWidths=[180 * mm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), FOND),
        ('BOX', (0, 0), (-1, -1), 0.6, BLEU_CLAIR),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    return t


def pied_de_page(canvas, doc):
    canvas.saveState()
    canvas.setFont('Helvetica', 7)
    canvas.setFillColor(GRIS)
    canvas.drawString(
        15 * mm, 10 * mm,
        "INJS-LMD — Référentiels de l'INJS (page Tableau de bord) — "
        f'document généré le {AUJOURD_HUI} depuis l’application '
        '(API /referentiels/tableau-de-bord/), compteurs à jour à la génération.')
    canvas.drawRightString(A4[0] - 15 * mm, 10 * mm, f'Page {doc.page}')
    canvas.restoreState()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--sortie',
        default=str(RACINE / 'dossier_trvx' / 'Referentiels_de_l_INJS_Tableau_de_bord.pdf'))
    args = parser.parse_args()

    try:
        commit = subprocess.run(
            ['git', 'rev-parse', '--short', 'HEAD'], cwd=RACINE,
            capture_output=True, text=True, timeout=10).stdout.strip() or '—'
    except Exception:
        commit = '—'

    categories, synthese = instantane()

    doc = SimpleDocTemplate(
        args.sortie, pagesize=A4,
        leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=13 * mm, bottomMargin=15 * mm,
        title="Référentiels de l'INJS — Tableau de bord",
        author='Application INJS-LMD',
        subject="Données officielles de l'établissement : écoles, filières, "
                'maquettes, lieux et nomenclatures pédagogiques.',
    )

    elements = [
        bandeau_entete(synthese),
        Spacer(1, 4 * mm),
        bandeau_kpi(synthese),
        Spacer(1, 4 * mm),
        bloc_explorer(categories),
    ]
    for categorie in categories:
        elements.append(_p(categorie['libelle'], S_CAT))
        elements.append(_p(categorie['description'], S_CAT_DESC))
        elements.append(Spacer(1, 1.2 * mm))
        elements.append(table_categorie(categorie))
        nb = len(categorie['entrees'])
        total = sum(e['total'] for e in categorie['entrees'])
        elements.append(_p(
            f'Sous-total : {nb} référentiel(s) · {total} valeurs.', S_CAT_DESC))
        elements.append(Spacer(1, 2.5 * mm))

    elements.append(note_fiabilite())
    elements.append(Spacer(1, 3 * mm))
    elements.append(_p(
        f'Total général : {synthese["nb_referentiels"]} référentiels '
        f'({synthese["nb_referentiels_editables"]} éditables par l’écran générique) · '
        f'{synthese["nb_valeurs"]} valeurs · {synthese["nb_a_renseigner"]} à renseigner · '
        f'{synthese["nb_sans_source"]} sans source. '
        f'Document régénérable : scripts/generer_pdf_tableau_de_bord.py (commit {commit}).',
        S_NOTE))

    doc.build(elements, onFirstPage=pied_de_page, onLaterPages=pied_de_page)
    print(f'PDF écrit : {args.sortie}')
    print(f'Synthèse : {synthese}')


if __name__ == '__main__':
    main()
