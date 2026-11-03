"""Exports pédagogiques LMD — sans montants ni coordonnées bancaires."""
from io import BytesIO
from xml.sax.saxutils import escape

from django.http import HttpResponse


NON_DISPONIBLE = 'Non disponible'


def _lignes(fiche):
    yield ['Année académique', fiche['annee_academique'] or NON_DISPONIBLE]
    yield ['Grade', fiche['grade_label'] or NON_DISPONIBLE]
    yield ['Spécialité', fiche['specialite'] or NON_DISPONIBLE]
    yield ['Formations LMD', fiche['nb_formations']]
    yield ['ECUE distinctes', fiche['nb_ecue']]
    yield ['Heures affectées', fiche['heures_affectees']]
    yield ['Heures effectuées', NON_DISPONIBLE]
    yield ['Taux de présence enseignant', NON_DISPONIBLE]
    yield ['Satisfaction étudiants', NON_DISPONIBLE]


def exporter(fiche, format):
    nom = f"{fiche['nom']} {fiche['prenom']}".strip()
    titre = f"Fiche enseignant — {nom}" + (' [Exemple]' if fiche['est_exemple'] else '')
    entetes = ['ECUE', 'Intitulé', 'Formation', 'Niveau', 'Semestre', 'Groupe',
               'Type', 'Heures', 'Statut', 'Source']
    rows = [[a['ecue_code'], a['ecue_intitule'], a['formation'], a['niveau'],
             a['semestre'], a['groupe'] or NON_DISPONIBLE, a['type_enseignement'],
             a['heures'], a['statut_label'], '[Exemple]' if a['est_exemple'] else 'Saisie']
            for a in fiche['affectations']]
    buffer = BytesIO()
    if format == 'xlsx':
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill
        wb = Workbook()
        ws = wb.active
        ws.title = 'Enseignant'
        ws.append([titre])
        ws.append(['Identifiant', fiche['numerobadge']])
        for ligne in _lignes(fiche):
            ws.append(ligne)
        ws.append([])
        ws.append(['Affectations pédagogiques'])
        ws.append(entetes)
        for row in rows:
            ws.append(row)
        if not rows:
            ws.append(['Aucune affectation pédagogique pour l’année courante'])
        ws.append([])
        ws.append(['Observations', fiche['observations'] or NON_DISPONIBLE])
        ws.append(['Périmètre des indicateurs', fiche['disponibilite_indicateurs']])
        for cell in ws[1]:
            cell.font = Font(bold=True, size=14, color='FFFFFF')
            cell.fill = PatternFill('solid', fgColor='1C4789')
        ws.freeze_panes = 'A13'
        for column in ws.columns:
            ws.column_dimensions[column[0].column_letter].width = min(
                48, max(16, max(len(str(c.value or '')) for c in column) + 2))
        wb.save(buffer)
        content_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    else:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        styles = getSampleStyleSheet()
        story = [Paragraph(escape(titre), styles['Title']),
                 Paragraph(f"Identifiant : {escape(fiche['numerobadge'] or NON_DISPONIBLE)}", styles['Normal'])]
        resume = Table(list(_lignes(fiche)), hAlign='LEFT', colWidths=[7 * cm, 16 * cm])
        resume.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#DFEAF4')),
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#EAF1FE')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        story += [resume, Spacer(1, 0.5 * cm), Paragraph('Affectations pédagogiques', styles['Heading2'])]
        if rows:
            table = Table([entetes] + rows, repeatRows=1, hAlign='LEFT')
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1C4789')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTSIZE', (0, 0), (-1, -1), 7),
                ('GRID', (0, 0), (-1, -1), 0.3, colors.HexColor('#DFEAF4')),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ]))
            story.append(table)
        else:
            story.append(Paragraph('Aucune affectation pédagogique pour l’année courante.', styles['Normal']))
        story += [Spacer(1, 0.4 * cm),
                  Paragraph(escape(fiche['disponibilite_indicateurs']), styles['Normal']),
                  Spacer(1, 0.3 * cm),
                  Paragraph(escape(fiche['observations'] or ''), styles['Normal'])]
        SimpleDocTemplate(buffer, pagesize=landscape(A4), topMargin=1.3 * cm,
                          bottomMargin=1.3 * cm).build(story)
        content_type = 'application/pdf'
    response = HttpResponse(buffer.getvalue(), content_type=content_type)
    response['Content-Disposition'] = f'attachment; filename="enseignant_{fiche["id"]}.{format}"'
    return response
