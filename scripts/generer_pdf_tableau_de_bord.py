#!/usr/bin/env python3
"""PDF téléchargeable de la page « Référentiels de l'INJS », valeurs détaillées.

Le document comprend deux parties :

1. **La page Tableau de bord** reproduite à l'identique (en-tête,
   indicateurs, exploration du catalogue, les 27 plaquettes par catégorie,
   note sur les degrés de fiabilité) ;
2. **Le détail des valeurs** de chaque référentiel, avec les colonnes de
   l'écran de gestion (code, libellé, champs métier, rattachements,
   fiabilité) : par exemple les 8 filières avec code dossier, ordre
   d'affichage, école, mention et nature de cursus.

Tout est **recalculé en base au moment de la génération** : compteurs par
la même logique que l'API `/referentiels/tableau-de-bord/` (`instantane()`
du générateur du classeur), valeurs par le même sérialiseur que l'écran
générique (`serializer_pour_ref`) — le PDF ne peut pas diverger de
l'application. Les 4 référentiels non éditables sont détaillés via leurs
sérialiseurs de lecture (modules officiels, volumes) ou leurs champs
métier (cycles de formation, UE des maquettes).

Usage (depuis la racine du dépôt) :

    backend/.venv/bin/python scripts/generer_pdf_tableau_de_bord.py
    backend/.venv/bin/python scripts/generer_pdf_tableau_de_bord.py --sortie /tmp/page.pdf

Sortie par défaut : dossier_trvx/Referentiels_de_l_INJS_Tableau_de_bord.pdf
"""

import argparse
import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / 'scripts'))
sys.path.insert(0, str(RACINE / 'backend'))
os.environ.setdefault('USE_SQLITE', '1')

# Réutilise la logique de comptage du classeur (effectue aussi django.setup()).
from generer_doc_tableau_de_bord import (  # noqa: E402
    _a_le_champ, action_affichee, etat_affiche, instantane,
)

from django.db.models import Count  # noqa: E402

from formations.models import RefFormation  # noqa: E402
from referentiels.registre import REGISTRE, modele_de  # noqa: E402
from referentiels.serializers import (  # noqa: E402
    RefModuleOfficielSerializer, RefVolumeHoraireFormationSerializer,
    serializer_pour_ref,
)
from scolarite.models import UE  # noqa: E402

from reportlab.lib import colors  # noqa: E402
from reportlab.lib.enums import TA_CENTER, TA_LEFT  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import ParagraphStyle  # noqa: E402
from reportlab.lib.units import mm  # noqa: E402
from reportlab.platypus import (  # noqa: E402
    KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
    TableStyle,
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
LARGEUR = 180  # mm utiles (A4 portrait, marges 15 mm)

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
S_PARTIE = ParagraphStyle('partie', fontName='Helvetica-Bold', fontSize=15,
                          leading=18, textColor=BLEU)
S_CAT = ParagraphStyle('categorie', fontName='Helvetica-Bold', fontSize=12,
                       leading=14, textColor=BLEU, spaceBefore=10)
S_CAT_DESC = ParagraphStyle('categorie-desc', fontName='Helvetica-Oblique',
                            fontSize=8.5, leading=10.5, textColor=GRIS)
S_REF = ParagraphStyle('ref-titre', fontName='Helvetica-Bold', fontSize=11.5,
                       leading=13.5, textColor=BLEU, spaceBefore=9)
S_REF_SOUS = ParagraphStyle('ref-sous', fontName='Helvetica', fontSize=8.6,
                            leading=10.6, textColor=colors.HexColor('#333333'))
S_META = ParagraphStyle('meta', fontName='Helvetica-Oblique', fontSize=7.4,
                        leading=9.2, textColor=GRIS)
S_CELL = ParagraphStyle('cellule', fontName='Helvetica', fontSize=7.6, leading=9.3)
S_CELL_G = ParagraphStyle('cellule-g', fontName='Helvetica-Bold', fontSize=7.6,
                          leading=9.3)
S_DESC = ParagraphStyle('description', fontName='Helvetica', fontSize=6.4,
                        leading=7.6, textColor=GRIS)
S_ENTETE = ParagraphStyle('entete', fontName='Helvetica-Bold', fontSize=7.2,
                          leading=9.3, textColor=BLANC)
S_NOTE = ParagraphStyle('note', fontName='Helvetica', fontSize=8.2,
                        leading=11, textColor=colors.HexColor('#333333'))
S_SECTION = ParagraphStyle('section', fontName='Helvetica-Bold', fontSize=10.5,
                           leading=13, textColor=BLEU, spaceBefore=8)

ETATS_STYLE = {
    'Complet': (VERT, VERT_FOND),
    'Provenance non suivie': (AMBRE, AMBRE_FOND),
    'Non renseigné': (ROUGE, ROUGE_FOND),
}

# Miroirs des constantes d'affichage de l'écran (ReferentielGenerique.jsx).
LIBELLES_CHAMPS = {
    'code': 'Code', 'libelle': 'Libellé', 'description': 'Description',
    'actif': 'Actif', 'source_document': 'Source documentaire',
    'fiabilite': 'Fiabilité', 'nom_complet': 'Dénomination complète',
    'ordre': "Ordre d'affichage", 'abrege': 'Abréviation',
    'est_stage': 'Correspond à un stage',
    'est_ouvert': 'Autorise les candidatures', 'ecole': 'École',
    'mention': 'Mention', 'type_cursus': 'Nature de cursus',
    'code_dossier': 'Code dossier', 'etat_ventilation': 'État de ventilation',
    'cycle': 'Cycle', 'credits_requis': 'Crédits ECTS requis',
    'numero': 'Numéro global', 'niveau': 'Niveau',
    'ref_formation': 'Cycle de formation', 'type_formation': 'Type de formation',
    'type_lieu': 'Type de lieu', 'capacite': 'Capacité',
    'equipements': 'Équipements', 'indisponible_du': 'Indisponible du',
    'indisponible_au': 'Indisponible au',
    'geofence_latitude': 'Latitude (géorepérage)',
    'geofence_longitude': 'Longitude (géorepérage)',
    'geofence_rayon_m': 'Rayon de géorepérage (m)', 'site': 'Site',
    'batiment': 'Bâtiment', 'type_espace': "Type d'espace sportif",
    'formation': 'Formation (cycle)', 'statut': 'Statut',
    'periode_debut': 'Début de période', 'periode_fin': 'Fin de période',
    'effectif_prevu': 'Effectif prévu', 'effectif_reel': 'Effectif réel',
    'date_debut': 'Date de début', 'date_fin': 'Date de fin',
    'courante': 'Année courante', 'cloturee': 'Clôturée',
    'date_cloture': 'Date de clôture',
}
LIBELLE_TECHNIQUE = {
    'formation_intitule': 'Cycle de rattachement', 'filiere_code': 'Filière',
    'semestre': 'Semestre', 'ordre': 'Ordre',
    'etat_ventilation': 'État de ventilation', 'intitule_module': 'Module',
    'heures_cm': 'Heures CM', 'heures_td': 'Heures TD', 'heures_tp': 'Heures TP',
    'heures_stage': 'Heures stage', 'heures_total': 'Total',
    'fiabilite': 'Fiabilité', 'source_document': 'Source documentaire',
}
ORDRE_LECTURE_SEULE = [
    'filiere_code', 'semestre', 'libelle', 'formation_intitule', 'ordre',
    'etat_ventilation', 'intitule_module', 'heures_cm', 'heures_td',
    'heures_tp', 'heures_stage', 'heures_total', 'source_document', 'fiabilite',
]
VALEURS_TECHNIQUES = {
    'A_VENTILER': 'À ventiler', 'VENTILE': 'Ventilé', 'HORS_MAQUETTE': 'Hors maquette',
}
LIBELLE_FIABILITE = {
    'OFFICIEL': 'Officiel', 'MODELISE': 'Modélisé', 'CADRAGE': 'Cadrage',
    'A_RENSEIGNER': 'À renseigner',
}
COULEUR_FIABILITE = {
    'Officiel': VERT, 'Modélisé': BLEU, 'Cadrage': AMBRE, 'À renseigner': ROUGE,
}


def _p(texte, style=S_CELL):
    return Paragraph(str(texte), style)


def _e(texte):
    """Échappe le texte pour Paragraph et autorise la coupure de ligne après
    -, _, / et (micro-espace invisible — <wbr/> laisserait un glyphe parasite)."""
    coupure = '<font size="1"> </font>'
    # Substitution en un seul passage : les remplacements enchaînés
    # réécriraient le « / » de la balise </font> déjà insérée.
    return re.sub(r'[-_/(]', lambda m: m.group(0) + coupure, escape(str(texte)))


# ── Partie 1 : la page Tableau de bord ──────────────────────────────────────
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


# ── Partie 2 : détail des valeurs ───────────────────────────────────────────
def _choix_du_modele(modele, champ):
    try:
        f = modele._meta.get_field(champ)
    except Exception:
        return {}
    return {str(v): str(lib) for v, lib in (getattr(f, 'choices', None) or [])}


def formater(valeur, choix=None):
    """Même mise en forme que l'écran (formaterValeur), adaptée à l'impression."""
    if valeur is None or valeur == '':
        return '—'
    if isinstance(valeur, bool):
        return 'Oui' if valeur else 'Non'
    texte = str(valeur)
    if texte in VALEURS_TECHNIQUES:
        return VALEURS_TECHNIQUES[texte]
    if choix and texte in choix:
        return choix[texte]
    if re.fullmatch(r'-?\d+\.\d{2}', texte):
        texte = texte.replace('.00', '')
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', texte):
        a, m, j = texte.split('-')
        return f'{j}/{m}/{a}'
    return texte


def lignes_de(entree):
    """Valeurs sérialisées d'un référentiel, comme les reçoit l'écran."""
    slug = entree['slug']
    modele = modele_de(entree)
    if entree['editable']:
        qs = modele._default_manager.all()
        if entree['selecteurs']:
            qs = qs.select_related(*entree['selecteurs'])
        return serializer_pour_ref(slug)(qs, many=True).data
    if slug == 'modules-officiels':
        qs = modele._default_manager.all().select_related('formation')
        return RefModuleOfficielSerializer(qs, many=True).data
    if slug == 'volumes-modules':
        qs = modele._default_manager.all().select_related('formation')
        return RefVolumeHoraireFormationSerializer(qs, many=True).data
    if slug == 'formations':
        diplomes = dict(RefFormation.TypeDiplome.choices) \
            if hasattr(RefFormation, 'TypeDiplome') else {}
        lignes = []
        for f in RefFormation.objects.select_related('filiere'):
            lignes.append({
                'code': f.code or f.filiere_code or '',
                'libelle': f.intitule,
                'diplome': diplomes.get(f.type_diplome, f.type_diplome or ''),
                'filiere': (f.filiere.libelle if f.filiere_id else '') or f.filiere_code or '',
                'duree_annees': f.duree_annees, 'nb_semestres': f.nb_semestres,
                'nb_credites': f.nb_credites, 'perimetre': f.perimetre or '',
                'description': f.description or '', 'actif': f.actif,
            })
        return lignes
    if slug == 'ue-ecue':
        accesseur = next(
            (r.get_accessor_name() for r in UE._meta.related_objects
             if r.related_model.__name__ == 'ECUE'), 'ecue_set')
        qs = (UE.objects
              .select_related('maquette__ref_formation', 'maquette__niveau', 'semestre')
              .annotate(nb_ecue=Count(accesseur)))
        caracteres = _choix_du_modele(UE, 'caractere')
        statuts = _choix_du_modele(UE, 'statut')
        lignes = []
        for ue in qs:
            lignes.append({
                'code': ue.code, 'libelle': ue.intitule,
                'cycle': ue.maquette.ref_formation.intitule if ue.maquette_id else '',
                'niveau': ue.maquette.niveau.code if ue.maquette_id and ue.maquette.niveau_id else '',
                'semestre': ue.semestre.libelle if ue.semestre_id else '',
                'credits': ue.credits,
                'caractere': caracteres.get(str(ue.caractere), ue.caractere or ''),
                'nb_ecue': ue.nb_ecue,
                'statut': statuts.get(str(ue.statut), ue.statut or ''),
            })
        return lignes
    return []


COLONNES_MANUELLES = {
    'formations': [
        ('code', 'Code'), ('libelle', 'Cycle de formation'), ('diplome', 'Diplôme'),
        ('filiere', 'Filière'), ('duree_annees', 'Durée (ans)'),
        ('nb_semestres', 'Semestres'), ('nb_credites', 'Crédits ECTS'),
        ('perimetre', 'Périmètre'),
    ],
    'ue-ecue': [
        ('code', 'Code'), ('libelle', 'Unité d’enseignement'), ('cycle', 'Cycle'),
        ('niveau', 'Niveau'), ('semestre', 'Semestre'), ('credits', 'Crédits'),
        ('caractere', 'Caractère'), ('nb_ecue', 'ECUE'), ('statut', 'Statut'),
    ],
}


def colonnes_de(entree, lignes):
    """Colonnes affichées — même logique que l'écran (editable / lecture seule)."""
    slug = entree['slug']
    if slug in COLONNES_MANUELLES:
        return COLONNES_MANUELLES[slug]
    if entree['editable']:
        cols = []
        if _a_un_code(entree):
            cols.append(('code', 'Code'))
        cols.append(('libelle', 'Libellé'))
        for c in entree.get('champs', []):
            if c not in ('actif', 'description', 'source_document'):
                cols.append((c, LIBELLES_CHAMPS.get(c, c)))
        for fk in entree.get('selecteurs', []):
            cols.append((f'{fk}_libelle', LIBELLES_CHAMPS.get(fk, fk)))
        return cols
    # Lecture seule importée (modules officiels, volumes horaires).
    if not lignes:
        return [('libelle', 'Libellé')]
    disponibles = [
        cle for cle in lignes[0].keys()
        if cle not in ('id', 'formation', 'cree_le', 'modifie_le', 'annee_academique')
    ]
    constantes = {
        cle for cle in disponibles
        if cle == 'source_document'
        and len({str(l.get(cle)) for l in lignes}) <= 1
    }
    ordonnees = (
        [c for c in ORDRE_LECTURE_SEULE if c in disponibles and c not in constantes]
        + [c for c in disponibles if c not in ORDRE_LECTURE_SEULE and c not in constantes]
    )
    return [(c, LIBELLE_TECHNIQUE.get(c) or LIBELLES_CHAMPS.get(c, c)) for c in ordonnees]


def _a_un_code(entree):
    modele = modele_de(entree)
    champ_code = entree.get('champ_code', 'code')
    return (
        _a_le_champ(modele, champ_code)
        and champ_code != entree.get('champ_libelle', 'libelle')
    )


def _largeurs(entree, colonnes, avec_fiabilite):
    """Répartit les 180 mm utiles entre les colonnes."""
    modele = modele_de(entree)
    poids = {}
    for cle, _libelle in colonnes:
        nom = cle.removesuffix('_libelle') if cle.endswith('_libelle') and cle[:-9] in entree.get('selecteurs', []) else cle
        f = None
        try:
            f = modele._meta.get_field(nom)
        except Exception:
            pass
        nature = type(f).__name__ if f is not None else ''
        if cle == 'code':
            poids[cle] = 19
        elif cle == 'libelle':
            poids[cle] = 0  # reçoit le reste
        elif nature == 'DateField':
            poids[cle] = 17
        elif nature == 'BooleanField':
            poids[cle] = 13
        elif nature in ('IntegerField', 'PositiveIntegerField', 'DecimalField',
                        'FloatField'):
            poids[cle] = 15.5
        elif cle.endswith('_libelle'):
            poids[cle] = 24
        else:
            poids[cle] = 20
    souple = next((c for c in ('libelle', 'intitule_module')
                   if any(cle == c for cle, _l in colonnes)), None)
    fixe = (15 if avec_fiabilite else 0) + 13  # fiabilité + état
    budget = LARGEUR - fixe - 30  # colonne souple minimale 30 mm
    somme = sum(v for k, v in poids.items() if k != souple)
    if somme > budget and somme:
        facteur = budget / somme
        for cle in poids:
            if cle != souple:
                poids[cle] = max(10.5, poids[cle] * facteur)
    if souple:
        reste = LARGEUR - fixe - sum(v for k, v in poids.items() if k != souple)
        poids[souple] = max(24, reste)
    largeurs = [poids.get(cle, 20) * mm for cle, _l in colonnes]
    if avec_fiabilite:
        largeurs.append(15 * mm)
    largeurs.append(13 * mm)
    return largeurs


def section_detail(entree, categorie_libelle):
    """Une section par référentiel : en-tête façon écran + tableau des valeurs."""
    lignes = lignes_de(entree)
    modele = modele_de(entree)
    provenance = _a_le_champ(modele, 'source_document')
    bouton, destination = action_affichee(entree)
    nb = len(lignes)

    elements = [
        KeepTogether([
            _p(entree['libelle'], S_REF),
            _p(f"{entree['description']} <b>{nb} valeur{'s' if nb > 1 else ''}</b>",
               S_REF_SOUS),
        ]),
    ]
    meta = [
        f'Catégorie : {categorie_libelle}',
        f"Modèle : {modele._meta.app_label}.{modele.__name__}",
        ('Écran de gestion (Gérer)' if entree['editable']
         else f'Consultation : {destination}'),
    ]
    if entree.get('source'):
        meta.append(f"Source (registre) : {entree['source']}")
    sources = sorted({str(l.get('source_document') or '').strip() for l in lignes} - {''}) if lignes else []
    if len(sources) == 1:
        meta.append(f'Source documentaire des valeurs : {sources[0]}')
    elif 2 <= len(sources) <= 3:
        meta.append('Sources documentaires des valeurs : ' + ' ; '.join(sources))
    elif sources:
        meta.append(f'{len(sources)} sources documentaires distinctes '
                    '(détail par valeur : écran de gestion et classeur, '
                    'feuille Traçabilité)')
    elements.append(_p(_e(' · '.join(meta)), S_META))
    if entree.get('avertissement'):
        elements.append(_p(_e(f"Réserve : {entree['avertissement']}"), S_META))
    elements.append(Spacer(1, 1.5 * mm))

    if not lignes:
        elements.append(_p('Aucune valeur.', S_NOTE))
        return elements, 0

    colonnes = colonnes_de(entree, lignes)
    choix = {cle: _choix_du_modele(modele, cle) for cle, _l in colonnes}
    entetes = [_p(_e(libelle), S_ENTETE) for _cle, libelle in colonnes]
    if provenance:
        entetes.append(_p('Fiabilité', S_ENTETE))
    entetes.append(_p('État', S_ENTETE))

    corps = [entetes]
    styles = [
        ('BACKGROUND', (0, 0), (-1, 0), BLEU),
        ('BOX', (0, 0), (-1, -1), 0.6, BLEU),
        ('INNERGRID', (0, 0), (-1, -1), 0.3, BLEU_CLAIR),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 3.5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3.5),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]
    for i, ligne in enumerate(lignes, start=1):
        cellules = []
        for cle, _libelle in colonnes:
            valeur = ligne.get(cle)
            if cle == 'libelle':
                bloc = [_p(f"<b>{_e(formater(valeur))}</b>", S_CELL)]
                description = str(ligne.get('description') or '').strip()
                if description:
                    bloc.append(_p(_e(description), S_DESC))
                cellules.append(bloc)
            elif cle == 'code':
                cellules.append(_p(_e(formater(valeur)), S_CELL_G))
            elif cle == 'fiabilite':
                cellules.append(_p(_e(LIBELLE_FIABILITE.get(str(valeur), formater(valeur))),
                                   S_CELL_G))
            else:
                cellules.append(_p(_e(formater(valeur, choix.get(cle))), S_CELL))
        if provenance:
            fib = LIBELLE_FIABILITE.get(str(ligne.get('fiabilite')),
                                         formater(ligne.get('fiabilite')))
            cellules.append([_p(_e(fib), ParagraphStyle(
                'fib', parent=S_CELL_G, textColor=COULEUR_FIABILITE.get(fib, GRIS)))])
        if ligne.get('archive'):
            etat = 'Archivée'
        elif 'actif' in ligne:
            etat = 'Actif' if ligne['actif'] else 'Inactif'
        else:
            etat = 'Actif'
        cellules.append(_p(etat, ParagraphStyle(
            'etat', parent=S_CELL,
            textColor=VERT if etat == 'Actif' else (GRIS if etat == 'Archivée' else ROUGE))))
        corps.append(cellules)
        if i % 2 == 0:
            styles.append(('BACKGROUND', (0, i), (-1, i), FOND))

    t = Table(corps, colWidths=_largeurs(entree, colonnes, provenance),
              repeatRows=1)
    t.setStyle(TableStyle(styles))
    elements.append(t)
    elements.append(Spacer(1, 3 * mm))
    return elements, nb


def pied_de_page(canvas, doc):
    canvas.saveState()
    canvas.setFont('Helvetica', 7)
    canvas.setFillColor(GRIS)
    canvas.drawString(
        15 * mm, 10 * mm,
        "INJS-LMD — Référentiels de l'INJS (tableau de bord et détail des valeurs) — "
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
        title="Référentiels de l'INJS — Tableau de bord et détail des valeurs",
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

    # ── Partie 2 : le détail des valeurs, référentiel par référentiel ──────
    elements.append(PageBreak())
    elements.append(_p('Détail des valeurs par référentiel', S_PARTIE))
    elements.append(_p(
        'Chaque section reprend l’en-tête de l’écran de gestion (titre, '
        'description, nombre de valeurs) et le tableau de ses valeurs avec les '
        'colonnes de l’écran : code (lorsqu’il est distinct du libellé), '
        'libellé — suivi de sa description en petit lorsqu’elle existe —, '
        'champs métier, rattachements, fiabilité et état. Contrairement à '
        'l’écran, filtré par défaut sur « Actifs », toutes les valeurs sont '
        'listées ici : actives, inactives et archivées (colonne État). '
        'Les sources documentaires des valeurs sont indiquées en tête de chaque '
        'section ; le détail par valeur figure dans le classeur de documentation.',
        S_NOTE))
    total_detail = 0
    for categorie in categories:
        for entree in categorie['entrees']:
            bloc, nb = section_detail(entree, categorie['libelle'])
            elements.extend(bloc)
            total_detail += nb

    doc.build(elements, onFirstPage=pied_de_page, onLaterPages=pied_de_page)
    print(f'PDF écrit : {args.sortie}')
    print(f'Synthèse : {synthese}')
    print(f'Valeurs détaillées : {total_detail} '
          f"(contrôle : {'OK' if total_detail == synthese['nb_valeurs'] else 'ÉCART'})")


if __name__ == '__main__':
    main()
