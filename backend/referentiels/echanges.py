"""Import/export tabulaire des trois plaquettes de l'offre de formation.

L'import réutilise le serializer métier et n'effectue aucune écriture partielle :
une ligne invalide annule l'ensemble du fichier.
"""
import csv
import io
from decimal import Decimal, InvalidOperation
from zipfile import BadZipFile
from xml.sax.saxutils import escape

from django.db import transaction
from django.http import HttpResponse
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

SLUGS = frozenset({'formations', 'modules-officiels', 'volumes-modules'})
FORMATS = {'csv', 'xlsx', 'docx', 'pdf'}
MAX_TAILLE = 5 * 1024 * 1024
MAX_LIGNES = 1000


def cellule_sure(value):
    """Empêche une formule CSV/Excel sans altérer les quantités négatives."""
    test = value.lstrip(' \t\r\n')
    dangereux = test.startswith(('=', '+', '@')) or (test.startswith('-') and not test[1:].replace('.', '', 1).isdigit())
    return "'" + value if dangereux else value


def cellule_excel(value, column):
    if value and column in {'ordre', 'duree_annees', 'nb_semestres', 'nb_credites',
                            'heures_cm', 'heures_td', 'heures_tp', 'heures_stage', 'heures_total'}:
        try:
            return float(Decimal(value))
        except InvalidOperation:
            pass
    return cellule_sure(value)


def colonnes(entree):
    return list(dict.fromkeys([
        'id', *(['code'] if entree.get('champ_code', 'code') != entree.get('champ_libelle', 'libelle') else []),
        'libelle', *entree['champs'], *entree['selecteurs'],
        'actif', 'source_document', 'fiabilite',
        *(['description'] if entree['slug'] == 'formations' else []),
    ]))


def exporter(view, request):
    from .registre import REGISTRE
    slug = view._entree()['slug']
    if slug not in SLUGS:
        raise ValidationError({'detail': 'Export non disponible pour ce référentiel.'})
    fmt = request.query_params.get('export', 'csv').lower()
    if fmt not in FORMATS:
        raise ValidationError({'detail': 'Format non pris en charge.'})
    champs = colonnes(REGISTRE[slug])
    objets = view.get_queryset()[:MAX_LIGNES + 1]
    data = view.get_serializer(objets, many=True).data
    if len(data) > MAX_LIGNES:
        raise ValidationError({'detail': 'Plus de 1000 lignes : affinez la sélection.'})
    rows = [[str(item.get(c) if item.get(c) is not None else '') for c in champs] for item in data]

    if fmt == 'csv':
        out = io.StringIO()
        writer = csv.writer(out, delimiter=';')
        writer.writerow(champs)
        writer.writerows([[cellule_sure(v) for v in row] for row in rows])
        content = ('\ufeff' + out.getvalue()).encode('utf-8')
        mime = 'text/csv; charset=utf-8'
    elif fmt == 'xlsx':
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.title = 'Référentiel'
        ws.append(champs)
        for row in rows:
            # openpyxl interprète les chaînes commençant par « = » comme des
            # formules : les données importées doivent rester du texte.
            ws.append([cellule_excel(v, c) for v, c in zip(row, champs)])
        out = io.BytesIO()
        wb.save(out)
        content = out.getvalue()
        mime = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    elif fmt == 'docx':
        from docx import Document
        doc = Document()
        doc.add_heading(REGISTRE[slug]['libelle'], 0)
        table = doc.add_table(rows=1, cols=len(champs))
        for cell, name in zip(table.rows[0].cells, champs):
            cell.text = name
        for row in rows:
            for cell, value in zip(table.add_row().cells, row):
                cell.text = value
        out = io.BytesIO()
        doc.save(out)
        content = out.getvalue()
        mime = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    else:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A3, landscape
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
        out = io.BytesIO()
        doc = SimpleDocTemplate(out, pagesize=landscape(A3), leftMargin=20, rightMargin=20)
        style = getSampleStyleSheet()['BodyText']
        style.fontSize = 6
        # Paragraph effectue le retour à la ligne dans les cellules longues.
        cells = [[Paragraph(escape(value), style) for value in row] for row in [champs, *rows]]
        table = Table(cells, repeatRows=1, hAlign='LEFT')
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#173968')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('GRID', (0, 0), (-1, -1), .25, colors.lightgrey),
        ]))
        doc.build([table])
        content = out.getvalue()
        mime = 'application/pdf'
    response = HttpResponse(content, content_type=mime)
    response['Content-Disposition'] = f'attachment; filename="{slug}.{fmt}"'
    return response


def importer(view, request):
    slug = view._entree()['slug']
    if slug not in SLUGS:
        raise ValidationError({'detail': 'Import non disponible pour ce référentiel.'})
    fichier = request.FILES.get('fichier')
    if not fichier or not fichier.name.lower().endswith(('.csv', '.xlsx')):
        raise ValidationError({'detail': 'Choisissez un fichier .csv ou .xlsx.'})
    if fichier.size > MAX_TAILLE:
        raise ValidationError({'detail': 'Fichier trop volumineux (maximum 5 Mo).'})
    try:
        if fichier.name.lower().endswith('.xlsx'):
            from openpyxl import load_workbook
            wb = load_workbook(fichier, read_only=True, data_only=True)
            try:
                iterator = wb.active.values
                entete = next(iterator, None)
                lignes = list(iterator)
            finally:
                wb.close()
        else:
            texte = fichier.read().decode('utf-8-sig')
            delimiteur = ';' if texte.splitlines() and ';' in texte.splitlines()[0] else ','
            iterator = csv.reader(io.StringIO(texte), delimiter=delimiteur)
            entete = next(iterator, None)
            lignes = list(iterator)
    except (ValueError, UnicodeError, csv.Error, OSError, KeyError, BadZipFile) as exc:
        raise ValidationError({'detail': f'Fichier illisible : {exc}'}) from exc
    from .registre import REGISTRE
    permis = set(colonnes(REGISTRE[slug]))
    entete = [str(c).strip() for c in (entete or [])]
    if not entete or len(entete) != len(set(entete)) or 'libelle' not in entete or set(entete) - permis:
        raise ValidationError({'detail': 'En-têtes invalides : libelle requis, colonnes autorisées : ' + ', '.join(sorted(permis))})
    if len(lignes) > MAX_LIGNES:
        raise ValidationError({'detail': 'Maximum 1000 lignes par fichier.'})
    ajouts = modifications = 0
    with transaction.atomic():
        for numero, valeurs in enumerate(lignes, 2):
            if not any(v is not None and str(v).strip() for v in valeurs):
                continue
            if len(valeurs) != len(entete):
                raise ValidationError({'detail': f'Ligne {numero} : nombre de colonnes incorrect.'})
            donnees = {nom: valeur for nom, valeur in zip(entete, valeurs)
                       if valeur is not None and str(valeur).strip() != '' and nom != 'id'}
            identifiant = valeurs[entete.index('id')] if 'id' in entete else None
            try:
                obj = view.queryset.get(pk=int(identifiant)) if identifiant else None
            except (ValueError, TypeError, view.queryset.model.DoesNotExist) as exc:
                raise ValidationError({'detail': f'Ligne {numero} : identifiant introuvable.'}) from exc
            if obj and obj.archive:
                raise ValidationError({'detail': f'Ligne {numero} : réactivez la valeur archivée avant de la modifier.'})
            serie = view.get_serializer(obj, data=donnees, partial=bool(obj))
            if not serie.is_valid():
                raise ValidationError({'detail': f'Ligne {numero} : {serie.errors}'})
            try:
                if obj:
                    view.perform_update(serie)
                    modifications += 1
                else:
                    view.perform_create(serie)
                    ajouts += 1
            except ValidationError as exc:
                raise ValidationError({'detail': f'Ligne {numero} : {exc.detail}'}) from exc
    return Response({'crees': ajouts, 'modifies': modifications})
