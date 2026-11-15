"""Export et import des référentiels du registre (lot Référentiels).

Un seul moteur, piloté par le registre : les colonnes sont celles de l'écran
de gestion (code, libellé, champs métier, sélecteurs résolus en libellé,
provenance, cycle de vie). L'export reprend les mêmes filtres que la liste
(``?archives=1``, ``?actif=…``, filtres déclarés par l'entrée).

Formats d'export : Excel (.xlsx), CSV (.csv), Word (.docx), PDF (.pdf).
Formats d'import : Excel (.xlsx), CSV (.csv) — avec rejeu en aller-retour
des colonnes produites par l'export (les en-têtes français sont reconnus,
de même que les noms de champs de l'API).

Aucune valeur n'est inventée : un fichier invalide est rejeté avec le détail
ligne par ligne, et rien n'est persisté si une ligne échoue (transaction).
"""
from __future__ import annotations

import csv
import io
import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone

from .models import Fiabilite, ReferentielJournal
from .registre import REGISTRE, modele_de
from .serializers import serializer_pour_ref

FORMATS_EXPORT = ('xlsx', 'csv', 'docx', 'pdf')
FORMATS_IMPORT = ('xlsx', 'csv')
TAILLE_MAX_IMPORT = 5 * 1024 * 1024  # 5 Mo
LIGNES_MAX_IMPORT = 5000

# Libellés français des colonnes (miroir du tableau de bord) : ils servent à
# la fois d'en-tête d'export et d'alias d'import — l'aller-retour fichier
# produit par l'export est donc toujours réimportable.
LIBELLES = {
    'code': 'Code',
    'libelle': 'Libellé',
    'description': 'Description',
    'actif': 'Actif',
    'archive': 'Archivé',
    'source_document': 'Source documentaire',
    'fiabilite': 'Fiabilité',
    'nom_complet': 'Dénomination complète',
    'ordre': "Ordre d'affichage",
    'abrege': 'Abréviation',
    'est_stage': 'Correspond à un stage',
    'est_ouvert': 'Autorise les candidatures',
    'ecole': 'École',
    'mention': 'Mention',
    'type_cursus': 'Nature de cursus',
    'code_dossier': 'Code dossier',
    'etat_ventilation': 'État de ventilation',
    'cycle': 'Cycle',
    'credits_requis': 'Crédits ECTS requis',
    'numero': 'Numéro global',
    'niveau': 'Niveau',
    'ref_formation': 'Cycle de formation',
    'type_formation': 'Type de formation',
    'type_lieu': 'Type de lieu',
    'capacite': 'Capacité',
    'equipements': 'Équipements',
    'indisponible_du': 'Indisponible du',
    'indisponible_au': 'Indisponible au',
    'geofence_latitude': 'Latitude (géorepérage)',
    'geofence_longitude': 'Longitude (géorepérage)',
    'geofence_rayon_m': 'Rayon de géorepérage (m)',
    'site': 'Site',
    'batiment': 'Bâtiment',
    'type_espace': "Type d'espace sportif",
    'formation': 'Formation (cycle)',
    'filiere': 'Filière',
    'statut': 'Statut',
    'periode_debut': 'Début de période',
    'periode_fin': 'Fin de période',
    'effectif_prevu': 'Effectif prévu',
    'effectif_reel': 'Effectif réel',
    'date_debut': 'Date de début',
    'date_fin': 'Date de fin',
    'courante': 'Année courante',
    'cloturee': 'Clôturée',
    'date_cloture': 'Date de clôture',
    'type_diplome': 'Type de diplôme',
    'domaine': 'Domaine',
    'duree_annees': 'Durée (années)',
    'nb_semestres': 'Nombre de semestres',
    'nb_credites': 'Crédits ECTS visés',
    'filiere_code': 'Filière',
    'semestre': 'Semestre',
    'intitule_module': 'Module',
    'heures_cm': 'Heures CM',
    'heures_td': 'Heures TD',
    'heures_tp': 'Heures TP',
    'heures_stage': 'Heures stage',
    'heures_total': 'Total',
    'intitule': 'Intitulé',
    'nom': 'Nom',
}

# Alias supplémentaires acceptés à l'import, par nom de champ.
_ALIAS_EXTRA = {
    'code': ['code_metier', 'code_m_tier'],
    'libelle': ['libelle_officiel', 'intitule', 'intitul', 'nom'],
    'description': ['desc'],
    'fiabilite': ['fiabilit', 'fiabilite_source'],
    'source_document': ['source', 'source_documentaire'],
    'actif': ['valeur_active', 'etat'],
    'archive': ['archiv'],
    'formation': ['formation_intitule', 'cycle', 'cycle_de_formation', 'formation_cycle', 'rattachement'],
    'filiere': ['filiere_officielle', 'filiere_libelle'],
    'intitule_module': ['module', 'libelle_module', 'intitul_du_module'],
    'etat_ventilation': ['ventilation', 'ventilation_maquette'],
    'type_diplome': ['diplome', 'nature_diplome'],
    'filiere_code': ['filiere', 'code_filiere', 'code_filiere_metier'],
    'heures_cm': ['cm', 'heurescm'],
    'heures_td': ['td', 'heurestd'],
    'heures_tp': ['tp', 'heurestp'],
    'heures_stage': ['stage', 'heuresstage'],
    'heures_total': ['total', 'heurestotal', 'total_heures'],
}


class ImportReferentielError(Exception):
    """Rejet d'un import, avec le détail ligne par ligne."""

    def __init__(self, detail, erreurs=()):
        super().__init__(detail)
        self.detail = detail
        self.erreurs = list(erreurs)


# ─────────────────────────────────────────────────────────────────────────────
# Colonnes du registre
# ─────────────────────────────────────────────────────────────────────────────

def _a_le_champ(modele, nom):
    return any(f.name == nom for f in modele._meta.concrete_fields)


def colonnes_pour(entree):
    """Colonnes d'export/import d'un référentiel, dans l'ordre de l'écran."""
    modele = modele_de(entree)
    champ_libelle = entree.get('champ_libelle', 'libelle')
    champ_code = entree.get('champ_code', 'code')
    colonnes = []
    if _a_le_champ(modele, champ_code) and champ_code != champ_libelle:
        colonnes.append({'cle': 'code', 'libelle': LIBELLES['code'], 'champ': champ_code})
    colonnes.append({'cle': 'libelle', 'libelle': LIBELLES['libelle'], 'champ': champ_libelle})
    for nom in entree.get('champs', []):
        if _a_le_champ(modele, nom):
            colonnes.append({'cle': nom, 'libelle': LIBELLES.get(nom, nom), 'champ': nom})
    for fk in entree.get('selecteurs', []):
        colonnes.append({'cle': f'{fk}_libelle', 'libelle': LIBELLES.get(fk, fk), 'fk': fk})
    if _a_le_champ(modele, 'fiabilite'):
        colonnes.append({'cle': 'fiabilite', 'libelle': LIBELLES['fiabilite'], 'champ': 'fiabilite'})
    if _a_le_champ(modele, 'source_document'):
        colonnes.append({'cle': 'source_document', 'libelle': LIBELLES['source_document'], 'champ': 'source_document'})
    if _a_le_champ(modele, 'description'):
        colonnes.append({'cle': 'description', 'libelle': LIBELLES['description'], 'champ': 'description'})
    if _a_le_champ(modele, 'actif'):
        colonnes.append({'cle': 'actif', 'libelle': LIBELLES['actif'], 'champ': 'actif'})
    if _a_le_champ(modele, 'archive'):
        colonnes.append({'cle': 'archive', 'libelle': LIBELLES['archive'], 'champ': 'archive'})
    return colonnes


def _choix_par_champ(modele, entree):
    """{nom_de_champ: {valeur_normalisée: valeur_canonique, …}} pour les choix."""
    choix = {}
    noms = list(entree.get('champs', [])) + ['fiabilite']
    for nom in noms:
        if not _a_le_champ(modele, nom):
            continue
        field = modele._meta.get_field(nom)
        if not field.choices:
            continue
        table = {}
        for valeur, libelle in field.choices:
            table[_normaliser(str(valeur))] = str(valeur)
            table[_normaliser(str(libelle))] = str(valeur)
        choix[nom] = table
    return choix


_NORMALISER_RE = re.compile(r'[^a-z0-9]+')


def _normaliser(texte):
    """Clé comparable : sans accents, sans casse, tirets/espaces → underscore."""
    if texte is None:
        return ''
    decompose = unicodedata.normalize('NFKD', str(texte))
    sans_accents = ''.join(c for c in decompose if not unicodedata.combining(c))
    return _NORMALISER_RE.sub('_', sans_accents.casefold()).strip('_')


def _alias_de(colonne):
    """Ensemble des en-têtes normalisés reconnus pour une colonne."""
    cle = colonne['cle']
    alias = {_normaliser(cle), _normaliser(colonne['libelle'])}
    if colonne.get('fk'):
        fk = colonne['fk']
        alias.add(_normaliser(fk))
        alias.add(_normaliser(f'{fk}_libelle'))
        alias.add(_normaliser(f'{fk}_intitule'))
        for extra in _ALIAS_EXTRA.get(fk, []):
            alias.add(_normaliser(extra))
    for extra in _ALIAS_EXTRA.get(cle, []):
        alias.add(_normaliser(extra))
    alias.discard('')
    return alias


# ─────────────────────────────────────────────────────────────────────────────
# Requête source (alignée sur la liste générique)
# ─────────────────────────────────────────────────────────────────────────────

def requete_source(entree, params):
    modele = modele_de(entree)
    qs = modele._default_manager.all().select_related(*entree.get('selecteurs', []))
    if _a_le_champ(modele, 'archive') and params.get('archives') not in ('1', 'true'):
        qs = qs.filter(archive=False)
    actif = params.get('actif')
    if actif is not None and _a_le_champ(modele, 'actif'):
        qs = qs.filter(actif=str(actif).lower() in ('true', '1', 'yes', 'oui'))
    for param, champ in (entree.get('filtres_liste') or {}).items():
        valeur = params.get(param)
        if valeur not in (None, ''):
            qs = qs.filter(**{champ: valeur})
    return qs


def _formater_nombre(valeur):
    texte = format(valeur, 'f')
    if '.' in texte:
        texte = texte.rstrip('0').rstrip('.')
    return texte


def _valeur_export(modele, entree, colonne, brut, choix):
    """Rend une valeur cellule (str), jamais inventée : vide si inconnue."""
    if colonne.get('fk'):
        return brut.get(f"{colonne['fk']}_libelle") or ''
    champ = colonne['champ']
    cle = colonne['cle']
    valeur = brut.get(cle)
    if valeur is None:
        return ''
    if isinstance(valeur, bool):
        return 'Oui' if valeur else 'Non'
    table = choix.get(cle) or choix.get(champ)
    if table is not None and isinstance(valeur, str):
        # Choix : on exporte le libellé métier, l'import accepte les deux.
        field = None
        try:
            field = modele._meta.get_field(champ)
        except Exception:
            field = None
        if field is not None and field.choices:
            return str(dict(field.choices).get(valeur, valeur))
        return str(dict(Fiabilite.choices).get(valeur, valeur))
    if isinstance(valeur, Decimal):
        return _formater_nombre(valeur)
    if isinstance(valeur, str) and re.fullmatch(r'-?\d+\.\d+', valeur):
        # DRF sérialise les DecimalField en chaîne : on re-normalise.
        try:
            return _formater_nombre(Decimal(valeur))
        except InvalidOperation:
            pass
    if isinstance(valeur, (datetime, date)):
        return valeur.isoformat()
    return str(valeur)


def lignes_export(entree, params):
    """(colonnes, en-têtes, lignes[str]) pour la source filtrée."""
    modele = modele_de(entree)
    colonnes = colonnes_pour(entree)
    choix = _choix_par_champ(modele, entree)
    serialiseur = serializer_pour_ref(entree['slug'])
    lignes = []
    for obj in requete_source(entree, params):
        brut = serialiseur(obj).data
        lignes.append([_valeur_export(modele, entree, c, brut, choix) for c in colonnes])
    return colonnes, lignes


# ─────────────────────────────────────────────────────────────────────────────
# Export XLSX / CSV / DOCX / PDF
# ─────────────────────────────────────────────────────────────────────────────

def _nom_fichier(entree, extension):
    horodatage = timezone.now().strftime('%Y%m%d-%H%M')
    return f"{entree['slug']}-{horodatage}.{extension}"


def exporter_xlsx(entree, colonnes, lignes):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    classeur = Workbook()
    feuille = classeur.active
    feuille.title = (entree['libelle'] or entree['slug'])[:31]
    feuille.append([c['libelle'] for c in colonnes])
    for cellule in feuille[1]:
        cellule.font = Font(bold=True, color='FFFFFF', size=11)
        cellule.fill = PatternFill('solid', fgColor='163D6A')
        cellule.alignment = Alignment(vertical='center')
    for ligne in lignes:
        feuille.append(ligne)
    feuille.freeze_panes = 'A2'
    if colonnes:
        feuille.auto_filter.ref = f'A1:{get_column_letter(len(colonnes))}{len(lignes) + 1}'
    for index, colonne in enumerate(colonnes, start=1):
        largeur = len(colonne['libelle']) + 2
        for ligne in lignes:
            largeur = max(largeur, len(str(ligne[index - 1])) + 2)
        feuille.column_dimensions[get_column_letter(index)].width = min(largeur, 48)
    tampon = io.BytesIO()
    classeur.save(tampon)
    return tampon.getvalue()


def exporter_csv(entree, colonnes, lignes):
    tampon = io.StringIO()
    redacteur = csv.writer(tampon, delimiter=';', quoting=csv.QUOTE_MINIMAL, lineterminator='\r\n')
    redacteur.writerow([c['libelle'] for c in colonnes])
    for ligne in lignes:
        redacteur.writerow(ligne)
    # BOM UTF-8 : Excel ouvre le fichier sans casser les accents.
    return ('\ufeff' + tampon.getvalue()).encode('utf-8')


def exporter_docx(entree, colonnes, lignes):
    from docx import Document
    from docx.enum.section import WD_ORIENT
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt, RGBColor

    document = Document()
    section = document.sections[0]
    if len(colonnes) > 6:
        section.orientation = WD_ORIENT.LANDSCAPE
        section.page_width, section.page_height = section.page_height, section.page_width
    section.top_margin, section.bottom_margin = Cm(1.6), Cm(1.6)
    section.left_margin, section.right_margin = Cm(1.6), Cm(1.6)

    entête = document.add_paragraph()
    entête.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = entête.add_run('INSTITUT NATIONAL DE LA JEUNESSE ET DES SPORTS')
    run.bold = True
    run.font.size = Pt(9)
    run.font.color.rgb = RGBColor(0x16, 0x3D, 0x6A)

    titre = document.add_paragraph()
    titre.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = titre.add_run(entree['libelle'])
    run.bold = True
    run.font.size = Pt(17)
    run.font.color.rgb = RGBColor(0x16, 0x3D, 0x6A)

    sous_titre = document.add_paragraph()
    sous_titre.alignment = WD_ALIGN_PARAGRAPH.CENTER
    total = len(lignes)
    sous_titre.add_run(
        f'Export généré le {timezone.localtime().strftime("%d/%m/%Y à %H:%M")} — '
        f'{total} valeur{"s" if total > 1 else ""}'
    ).font.size = Pt(9)
    if entree.get('source'):
        source = document.add_paragraph()
        source.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = source.add_run(f'Source : {entree["source"]}')
        run.italic = True
        run.font.size = Pt(8)
        run.font.color.rgb = RGBColor(0x5A, 0x6A, 0x7E)

    table = document.add_table(rows=1, cols=max(len(colonnes), 1))
    table.style = 'Table Grid'
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    def _teindre(cellule, couleur):
        tcPr = cellule._tc.get_or_add_tcPr()
        shd = OxmlElement('w:shd')
        shd.set(qn('w:val'), 'clear')
        shd.set(qn('w:color'), 'auto')
        shd.set(qn('w:fill'), couleur)
        tcPr.append(shd)

    for index, colonne in enumerate(colonnes):
        cellule = table.rows[0].cells[index]
        cellule.text = ''
        paragraphe = cellule.paragraphs[0]
        run = paragraphe.add_run(colonne['libelle'])
        run.bold = True
        run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        run.font.size = Pt(8.5)
        _teindre(cellule, '163D6A')

    for numero, ligne in enumerate(lignes):
        cellules = table.add_row().cells
        for index, valeur in enumerate(ligne):
            paragraphe = cellules[index].paragraphs[0]
            run = paragraphe.add_run(str(valeur))
            run.font.size = Pt(8.5)
            if numero % 2 == 1:
                _teindre(cellules[index], 'F4F8FC')

    tampon = io.BytesIO()
    document.save(tampon)
    return tampon.getvalue()


def exporter_pdf(entree, colonnes, lignes):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.pdfgen import canvas as canvasmod
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    class _CanvasNumerote(canvasmod.Canvas):
        """« Page X/Y » sur chaque page, en pied."""

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._etats = []

        def showPage(self):
            self._etats.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self._etats)
            for index, etat in enumerate(self._etats, start=1):
                self.__dict__.update(etat)
                self.setFont('Helvetica', 7)
                self.setFillColor(colors.HexColor('#5A6A7E'))
                largeur = self._pagesize[0]
                self.drawString(1.6 * cm, 0.9 * cm,
                                'INJS — Institut National de la Jeunesse et des Sports (Marcory)')
                self.drawRightString(largeur - 1.6 * cm, 0.9 * cm, f'Page {index}/{total}')
                super().showPage()
            super().save()

    grand = len(colonnes) > 6
    page = landscape(A4) if grand else A4
    styles = getSampleStyleSheet()
    style_cellule = ParagraphStyle('cellule', parent=styles['Normal'], fontSize=7.5, leading=9.5)
    style_entete = ParagraphStyle(
        'entete', parent=style_cellule, fontName='Helvetica-Bold',
        textColor=colors.white,
    )
    style_titre = ParagraphStyle(
        'titre', parent=styles['Title'], fontSize=16,
        textColor=colors.HexColor('#163D6A'), alignment=1, spaceAfter=2,
    )
    style_sous = ParagraphStyle(
        'sous', parent=styles['Normal'], fontSize=8.5,
        textColor=colors.HexColor('#5A6A7E'), alignment=1, spaceAfter=10,
    )

    histoire = [
        Paragraph('INSTITUT NATIONAL DE LA JEUNESSE ET DES SPORTS', style_sous),
        Paragraph(entree['libelle'], style_titre),
        Paragraph(
            f'Export généré le {timezone.localtime().strftime("%d/%m/%Y à %H:%M")} — '
            f'{len(lignes)} valeur{"s" if len(lignes) > 1 else ""}'
            + (f'<br/>Source : {entree["source"]}' if entree.get('source') else ''),
            style_sous,
        ),
    ]

    entete = [Paragraph(f'<b>{c["libelle"]}</b>', style_entete) for c in colonnes]
    corps = [
        [Paragraph(str(valeur), style_cellule) for valeur in ligne]
        for ligne in lignes
    ]
    table = Table(
        [entete, *corps],
        repeatRows=1,
        colWidths=[(page[0] - 3.2 * cm) / max(len(colonnes), 1)] * max(len(colonnes), 1),
    )
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#163D6A')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F4F8FC')]),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#C9D6E2')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
    ]))
    histoire.append(table)

    tampon = io.BytesIO()
    SimpleDocTemplate(
        tampon, pagesize=page,
        leftMargin=1.6 * cm, rightMargin=1.6 * cm,
        topMargin=1.4 * cm, bottomMargin=1.6 * cm,
        title=entree['libelle'],
        author='INJS — Référentiels',
    ).build(histoire, canvasmaker=_CanvasNumerote)
    return tampon.getvalue()


EXPORTEURS = {
    'xlsx': exporter_xlsx,
    'csv': exporter_csv,
    'docx': exporter_docx,
    'pdf': exporter_pdf,
}

CONTENT_TYPES = {
    'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'csv': 'text/csv; charset=utf-8',
    'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'pdf': 'application/pdf',
}


def construire_export(slug, params, format_):
    """(contenu_bytes, nom_fichier, content_type) pour un slug du registre."""
    entree = REGISTRE.get(slug)
    if entree is None:
        raise KeyError(slug)
    colonnes, lignes = lignes_export(entree, params)
    contenu = EXPORTEURS[format_](entree, colonnes, lignes)
    return contenu, _nom_fichier(entree, format_), CONTENT_TYPES[format_]


# ─────────────────────────────────────────────────────────────────────────────
# Import XLSX / CSV
# ─────────────────────────────────────────────────────────────────────────────

class _ErreurLigne(Exception):
    """Erreur fonctionnelle rattachée à une ligne du fichier importé."""


_BOOLEENS = {
    'oui': True, 'o': True, 'yes': True, 'true': True, 'vrai': True, '1': True,
    'actif': True, 'active': True,
    'non': False, 'n': False, 'no': False, 'false': False, 'faux': False, '0': False,
    'inactif': False, 'inactive': False,
}


def _extension(nom):
    nom = (nom or '').lower().strip()
    if nom.endswith('.xlsx'):
        return 'xlsx'
    if nom.endswith('.csv'):
        return 'csv'
    return None


def _lire_xlsx(contenu):
    from openpyxl import load_workbook

    classeur = load_workbook(io.BytesIO(contenu), read_only=True, data_only=True)
    try:
        feuille = classeur.active
        return [list(ligne) for ligne in feuille.iter_rows(values_only=True)]
    finally:
        classeur.close()


def _lire_csv(contenu):
    texte = None
    for encodage in ('utf-8-sig', 'cp1252', 'latin-1'):
        try:
            texte = contenu.decode(encodage)
            break
        except UnicodeDecodeError:
            continue
    if texte is None:
        raise ImportReferentielError(
            'Fichier CSV illisible : enregistrez le fichier en UTF-8 ou Excel.'
        )
    premiere = next((ligne for ligne in texte.splitlines() if ligne.strip()), '')
    try:
        dialecte = csv.Sniffer().sniff(premiere, delimiters=';,\t')
        separateur = dialecte.delimiter
    except csv.Error:
        separateur = ';' if premiere.count(';') >= premiere.count(',') else ','
    return [ligne for ligne in csv.reader(io.StringIO(texte), delimiter=separateur)]


_LECTEURS = {'xlsx': _lire_xlsx, 'csv': _lire_csv}


def _cellule_texte(valeur):
    if valeur is None:
        return ''
    if isinstance(valeur, bool):
        return 'Oui' if valeur else 'Non'
    if isinstance(valeur, float) and valeur.is_integer():
        return str(int(valeur))
    return str(valeur).strip()


def _champs_import(entree, colonnes):
    """Clés d'upsert : déclarées au registre, sinon code (ou libellé)."""
    champ_libelle = entree.get('champ_libelle', 'libelle')
    champ_code = entree.get('champ_code', 'code')
    if entree.get('cle_import'):
        return list(entree['cle_import'])
    modele = modele_de(entree)
    concrets = {f.name for f in modele._meta.concrete_fields}
    if champ_code in concrets and champ_code != champ_libelle:
        return [champ_code]
    return [champ_libelle]


def _cle_pour(colonnes, nom):
    """Colonne d'échange correspondant à un champ (ou un sélecteur)."""
    for colonne in colonnes:
        if colonne.get('fk') == nom or colonne.get('champ') == nom:
            return colonne['cle']
    return nom


def _resoudre_pk(modele, fk, texte):
    """Texte d'une cellule → pk de la cible du sélecteur (jamais devinée)."""
    champ = modele._meta.get_field(fk)
    cible = champ.related_model
    texte = texte.strip()
    if texte.isdigit() and cible._default_manager.filter(pk=int(texte)).exists():
        return int(texte)
    concretes = {f.name for f in cible._meta.concrete_fields}
    for attribut in ('libelle', 'intitule', 'nom', 'code'):
        if attribut not in concretes:
            continue
        correspondances = list(
            cible._default_manager.filter(**{f'{attribut}__iexact': texte})[:2]
        )
        if len(correspondances) == 1:
            return correspondances[0].pk
        if len(correspondances) > 1:
            raise _ErreurLigne(
                f'« {texte} » correspond à plusieurs lignes de la cible : '
                'précisez l’identifiant.'
            )
    raise _ErreurLigne(f'{LIBELLES.get(fk, fk)} « {texte} » introuvable.')


def _parser_booleen(texte):
    return _BOOLEENS.get(_normaliser(texte))


def _parser_entier(texte, champ, positif):
    brut = texte.replace('\u202f', '').replace(' ', '').replace(',', '.')
    try:
        nombre = int(Decimal(brut))
    except (InvalidOperation, ValueError):
        return None, f'« {texte} » n’est pas un entier valide pour « {LIBELLES.get(champ, champ)} ».'
    if positif and nombre < 0:
        return None, f'« {LIBELLES.get(champ, champ)} » ne peut pas être négatif.'
    return nombre, None


def _parser_decimal(texte, champ):
    brut = texte.replace('\u202f', '').replace(' ', '').replace(',', '.')
    try:
        nombre = Decimal(brut)
    except (InvalidOperation, ValueError):
        return None, f'« {texte} » n’est pas un nombre valide pour « {LIBELLES.get(champ, champ)} ».'
    if champ.startswith('heures_') and nombre < 0:
        return None, f'« {LIBELLES.get(champ, champ)} » ne peut pas être négatif.'
    return nombre, None


def _parser_date(texte, champ):
    for format_ in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%d.%m.%Y'):
        try:
            return datetime.strptime(texte.strip(), format_).date(), None
        except ValueError:
            continue
    return None, f'« {texte} » n’est pas une date valide pour « {LIBELLES.get(champ, champ)} » (formats : AAAA-MM-JJ, JJ/MM/AAAA).'


def _aplatir_erreurs(errors):
    morceaux = []
    for champ, messages in (errors or {}).items():
        if isinstance(messages, (list, tuple)):
            detail = ' ; '.join(str(m) for m in messages)
        else:
            detail = str(messages)
        morceaux.append(f'{champ} : {detail}')
    return ' — '.join(morceaux)


def _champ_positif(field):
    from django.db import models as db_models

    return isinstance(field, (db_models.PositiveIntegerField, db_models.PositiveSmallIntegerField,
                              db_models.PositiveBigIntegerField))


def _lookup_depuis(entree, modele, colonnes, cellule_de, fk_resolus):
    """Filtres d'upsert, ou None si la clé est incomplète (→ création)."""
    champs_import = _champs_import(entree, colonnes)
    filtre = {}
    selecteurs = set(entree.get('selecteurs', []))
    for nom in champs_import:
        if nom in selecteurs:
            if fk_resolus.get(nom) is None:
                return None
            filtre[nom] = fk_resolus[nom]
            continue
        texte = cellule_de(_cle_pour(colonnes, nom)).strip()
        if not texte:
            return None
        field = modele._meta.get_field(nom)
        from django.db import models as db_models

        if isinstance(field, (db_models.CharField, db_models.TextField)):
            filtre[f'{nom}__iexact'] = texte
        elif isinstance(field, db_models.DateField):
            valeur, erreur = _parser_date(texte, nom)
            if erreur:
                return None
            filtre[nom] = valeur
        else:
            try:
                filtre[nom] = Decimal(texte.replace(',', '.'))
            except (InvalidOperation, ValueError):
                try:
                    filtre[nom] = int(texte)
                except ValueError:
                    return None
    return filtre


def importer_referentiel(slug, fichier, utilisateur=None):
    """Importe (crée ou met à jour) les lignes d'un fichier .xlsx ou .csv.

    L'import est atomique : la moindre ligne invalide rejette tout le fichier,
    avec le détail ligne par ligne dans ``ImportReferentielError.erreurs``.
    """
    entree = REGISTRE.get(slug)
    if entree is None:
        raise ImportReferentielError('Référentiel inconnu.')
    if not entree.get('editable'):
        raise ImportReferentielError(
            'Ce référentiel n’est pas éditable depuis cet écran : l’import est refusé.'
        )
    format_ = _extension(getattr(fichier, 'name', ''))
    if format_ is None:
        raise ImportReferentielError('Formats acceptés : .xlsx (Excel) et .csv (CSV).')
    contenu = fichier.read()
    if len(contenu) > TAILLE_MAX_IMPORT:
        raise ImportReferentielError('Fichier trop volumineux (5 Mo maximum).')
    try:
        lignes_brutes = _LECTEURS[format_](contenu)
    except ImportReferentielError:
        raise
    except Exception as exc:
        raise ImportReferentielError(
            'Fichier illisible : vérifiez qu’il s’agit bien d’un classeur Excel '
            '(.xlsx) ou CSV.'
        ) from exc
    lignes_brutes = [ligne for ligne in lignes_brutes if any(
        _cellule_texte(c) for c in ligne)]
    if not lignes_brutes:
        raise ImportReferentielError('Fichier vide : aucune ligne exploitable.')
    if len(lignes_brutes) - 1 > LIGNES_MAX_IMPORT:
        raise ImportReferentielError(f'Fichier trop volumineux : {LIGNES_MAX_IMPORT} lignes maximum.')

    modele = modele_de(entree)
    colonnes = colonnes_pour(entree)
    choix = _choix_par_champ(modele, entree)
    selecteurs = set(entree.get('selecteurs', []))

    entetes = [_normaliser(c) for c in lignes_brutes[0]]
    associes = {}
    colonnes_ignorees = []
    for index, norme in enumerate(entetes):
        if not norme:
            continue
        cle = next(
            (c['cle'] for c in colonnes if norme in _alias_de(c) and c['cle'] not in associes),
            None,
        )
        if cle is None:
            colonnes_ignorees.append(_cellule_texte(lignes_brutes[0][index]))
        else:
            associes[cle] = index
    if 'libelle' not in associes:
        cible = LIBELLES['libelle']
        raise ImportReferentielError(
            f'Colonne « {cible} » introuvable : l’en-tête attendu est « {cible} » '
            f'(ou « libelle »). En-têtes lus : {", ".join(entetes) or "(aucun)"}.'
        )

    def cellule_de(cle):
        index = associes.get(cle)
        if index is None or index >= len(ligne_courante):
            return ''
        return _cellule_texte(ligne_courante[index])

    erreurs = []
    pendantes = []
    for numero_ligne, ligne_brute in enumerate(lignes_brutes[1:], start=2):
        ligne_courante = ligne_brute
        erreurs_ligne = []

        # 1. Sélecteurs : texte → pk (jamais de rattachement deviné).
        fk_resolus = {}
        for colonne in colonnes:
            fk = colonne.get('fk')
            if not fk:
                continue
            texte = cellule_de(colonne['cle'])
            if not texte:
                fk_resolus[fk] = None
                continue
            try:
                fk_resolus[fk] = _resoudre_pk(modele, fk, texte)
            except _ErreurLigne as exc:
                erreurs_ligne.append(str(exc))

        # 2. Champs typés.
        data = {}
        for colonne in colonnes:
            if colonne.get('fk'):
                if fk_resolus.get(colonne['fk']) is not None:
                    data[colonne['fk']] = fk_resolus[colonne['fk']]
                continue
            champ = colonne['champ']
            cle = colonne['cle']
            texte = cellule_de(cle)
            if texte == '':
                # Vide : ni écrasement d'une valeur existante, ni invention.
                continue
            # Le sérialiseur unifie le contrat sous ``code`` / ``libelle``
            # (l'entrée de registre aliasse vers le champ réel) : l'import
            # alimente donc ces clés, jamais les noms de champs internes.
            if cle == 'code':
                data['code'] = texte.upper() if champ == 'code' else texte
                continue
            if cle == 'libelle':
                data['libelle'] = texte
                continue
            field = modele._meta.get_field(champ)
            from django.db import models as db_models

            if isinstance(field, db_models.BooleanField):
                booleen = _parser_booleen(texte)
                if booleen is None:
                    erreurs_ligne.append(
                        f'« {texte} » n’est pas un booléen valide pour « {colonne["libelle"]} » (oui/non).'
                    )
                else:
                    data[champ] = booleen
                continue
            table_choix = choix.get(champ)
            if table_choix is not None:
                canonique = table_choix.get(_normaliser(texte))
                if canonique is None:
                    autorisees = ', '.join(dict(field.choices).values())
                    erreurs_ligne.append(
                        f'« {texte} » n’est pas une valeur connue pour « {colonne["libelle"]} » (attendu : {autorisees}).'
                    )
                else:
                    data[champ] = canonique
                continue
            if isinstance(field, (db_models.PositiveIntegerField, db_models.PositiveSmallIntegerField,
                                  db_models.PositiveBigIntegerField, db_models.IntegerField,
                                  db_models.SmallIntegerField, db_models.BigIntegerField)):
                entier, erreur = _parser_entier(texte, champ, _champ_positif(field))
                if erreur:
                    erreurs_ligne.append(erreur)
                else:
                    data[champ] = entier
                continue
            if isinstance(field, db_models.DecimalField):
                decimal, erreur = _parser_decimal(texte, champ)
                if erreur:
                    erreurs_ligne.append(erreur)
                else:
                    data[champ] = decimal
                continue
            if isinstance(field, db_models.DateField):
                valeur_date, erreur = _parser_date(texte, champ)
                if erreur:
                    erreurs_ligne.append(erreur)
                else:
                    data[champ] = valeur_date
                continue
            data[champ] = texte

        # 3. Cible de l'upsert.
        instance = None
        filtre = _lookup_depuis(
            entree, modele, colonnes, cellule_de, fk_resolus,
        )
        if filtre:
            instance = modele._default_manager.filter(**filtre).order_by('pk').first()

        # 4. Validation par le sérialiseur du registre.
        classe_serie = serializer_pour_ref(slug)
        serializer = (
            classe_serie(instance=instance, data=data, partial=True)
            if instance is not None
            else classe_serie(data=data)
        )
        if not serializer.is_valid():
            erreurs_ligne.append(_aplatir_erreurs(serializer.errors))

        if erreurs_ligne:
            erreurs.append(f'Ligne {numero_ligne} : ' + ' ; '.join(erreurs_ligne))
        else:
            pendantes.append((numero_ligne, instance, serializer))

    if erreurs:
        raise ImportReferentielError(
            'Aucune donnée importée : corrigez les lignes indiquées puis relancez l’import.',
            erreurs,
        )

    created = updated = 0
    utilisateur = utilisateur if (utilisateur and utilisateur.is_authenticated) else None
    with transaction.atomic():
        for numero_ligne, instance, serializer in pendantes:
            objet = serializer.save()
            action = (
                ReferentielJournal.Action.MODIFICATION
                if instance is not None
                else ReferentielJournal.Action.CREATION
            )
            ReferentielJournal.objects.create(
                content_type=ContentType.objects.get_for_model(objet),
                object_id=objet.pk,
                action=action,
                utilisateur=utilisateur,
                detail={'import': getattr(fichier, 'name', 'import') or 'import', 'ligne': numero_ligne},
            )
            if instance is not None:
                updated += 1
            else:
                created += 1
    return {
        'created': created,
        'updated': updated,
        'processed': len(pendantes),
        'colonnes_ignorees': colonnes_ignorees,
    }
