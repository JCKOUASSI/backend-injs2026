#!/usr/bin/env python3
"""Génère la liste exhaustive INJS-LMD au format Excel (téléchargeable).

Contenu : niveaux, semestres, parcours, maquettes, UE et ECUE du processus
métier et académique LMD de l'INJS d'Abidjan, tels qu'ils sont **en base**
après `init_referentiels_lmd` + `configurer_referentiel_injs` (source :
classeur « INJS D'ABIDJAN — RÉFÉRENTIEL EXHAUSTIF DE L'OFFRE DE FORMATION »,
extrait dans `backend/scolarite/data/referentiel_offre_formation.json`).

Le classeur n'invente rien : ce que le référentiel ne publie pas (maquettes
STASE F05–F08, semestre MS S8, crédits par ECUE, volumes CM/TD/TP) est
explicitement marqué comme tel. Les codes UE/ECUE (`EM-S1-UE01`) sont les
codes **techniques** de l'application, dérivés du rang — le référentiel ne
publie aucune codification officielle.

Usage (depuis la racine du dépôt) :

    backend/.venv/bin/python scripts/generer_liste_lmd.py
    backend/.venv/bin/python scripts/generer_liste_lmd.py --sortie /tmp/liste.xlsx

Le fichier .xlsx produit est ignoré par Git (règle « classeurs d'import ») :
ce script versionné est la source durable, le classeur se régénère.
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
BACKEND = RACINE / 'backend'
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(RACINE))
os.environ.setdefault('USE_SQLITE', '1')
# Profil d'aperçu si disponible (bac à sable), sinon configuration standard.
os.environ.setdefault(
    'DJANGO_SETTINGS_MODULE',
    'arena.settings_sandbox' if (RACINE / 'arena' / 'settings_sandbox.py').exists()
    else 'config.settings',
)

import django  # noqa: E402

django.setup()

from django.db.models import Count, Sum  # noqa: E402

from scolarite.models import ECUE, UE, Maquette, Niveau, Parcours, Semestre  # noqa: E402

from openpyxl import Workbook  # noqa: E402
from openpyxl.styles import Alignment, Font, PatternFill  # noqa: E402
from openpyxl.utils import get_column_letter  # noqa: E402

JEU_DONNEES = BACKEND / 'scolarite' / 'data' / 'referentiel_offre_formation.json'

BLEU = '1F3864'
BLEU_CLAIR = 'D9E2F3'
GRIS_LIGNE = 'F2F6FC'
ORANGE_RESERVE = 'FFF2CC'

# Libellés « référentiel » des semestres (feuille Listes du classeur source).
LIBELLES_SEMESTRES = {
    1: 'Semestre 1', 2: 'Semestre 2', 3: 'Semestre 3',
    4: 'Semestre 4', 5: 'Semestre 5', 6: 'Semestre 6',
    7: 'Semestre 1 (M1/S7)', 8: 'Semestre 2 (M1/S8)',
    9: 'Semestre 3 (M2/S9)', 10: 'Semestre 4 (M2/S10)',
}

SOURCE_CLASSEUR = (
    "Classeur « INJS D'ABIDJAN — RÉFÉRENTIEL EXHAUSTIF DE L'OFFRE DE FORMATION » "
    "(compilation du site officiel www.injsabidjan.ci), "
    "jeu de données backend/scolarite/data/referentiel_offre_formation.json"
)


# ── Style ────────────────────────────────────────────────────────────────────
def _titre(ws, texte, sous_titre, nb_col):
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=nb_col)
    c = ws.cell(row=1, column=1, value=texte)
    c.font = Font(size=14, bold=True, color=BLEU)
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=nb_col)
    c = ws.cell(row=2, column=1, value=sous_titre)
    c.font = Font(size=10, italic=True, color='595959')
    c.alignment = Alignment(wrap_text=True, vertical='top')
    ws.row_dimensions[2].height = 30


def _entetes(ws, ligne, colonnes):
    remplissage = PatternFill('solid', fgColor=BLEU)
    for j, nom in enumerate(colonnes, 1):
        c = ws.cell(row=ligne, column=j, value=nom)
        c.font = Font(bold=True, color='FFFFFF', size=10)
        c.fill = remplissage
        c.alignment = Alignment(wrap_text=True, vertical='center')
    ws.row_dimensions[ligne].height = 32


def _table(ws, colonnes, lignes, largeurs, reserves=()):
    """Écrit en-têtes (ligne 4) + lignes, filtres et largeurs. `reserves` =
    indices (0-based) des lignes à teinter (réserves documentaires)."""
    _entetes(ws, 4, colonnes)
    fond = PatternFill('solid', fgColor=GRIS_LIGNE)
    fond_reserve = PatternFill('solid', fgColor=ORANGE_RESERVE)
    for i, valeurs in enumerate(lignes):
        for j, valeur in enumerate(valeurs, 1):
            c = ws.cell(row=5 + i, column=j, value=valeur)
            c.font = Font(size=10)
            c.alignment = Alignment(wrap_text=True, vertical='top')
            if i in reserves:
                c.fill = fond_reserve
            elif i % 2:
                c.fill = fond
    for j, largeur in enumerate(largeurs, 1):
        ws.column_dimensions[get_column_letter(j)].width = largeur
    ws.freeze_panes = 'A5'
    if lignes:
        ws.auto_filter.ref = f'A4:{get_column_letter(len(colonnes))}{4 + len(lignes)}'
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.orientation = 'landscape'
    ws.page_setup.fitToWidth = 1
    ws.print_title_rows = '1:4'


# ── Données d'appui (jeu de données du référentiel) ─────────────────────────
def _charger_jeu():
    return json.loads(JEU_DONNEES.read_text(encoding='utf-8'))


def _cles_sources(jeu):
    """(sigle, n° semestre, rang) → clé métier officielle du classeur."""
    cles = {}
    for sigle, par_semestre in jeu['maquettes'].items():
        for numero, ues in par_semestre.items():
            for rang, ue in enumerate(ues, 1):
                cles[(sigle, int(numero), rang)] = ue.get('cle_source', '')
    return cles


# ── Feuilles ─────────────────────────────────────────────────────────────────
def feuille_niveaux(wb, jeu):
    ws = wb.create_sheet('1_Niveaux')
    ws.sheet_properties.tabColor = BLEU
    _titre(ws, 'NIVEAUX LMD — INJS d’Abidjan',
           'Paliers du cursus universitaire (60 ECTS par niveau annuel). '
           'Source : référentiel, feuille « 4. Semestres & Grades » ; base scolarité (modèle Niveau).', 9)
    colonnes = ['Code', 'Libellé', 'Cycle', 'Ordre', 'Semestres',
                'Crédits / an', 'Crédits cumulés (cycle)', 'Sanction (diplôme)',
                'État dans l’application']
    sanctions = {p['palier']: p['sanction'] for p in jeu['paliers']}
    correspondances = {'L1': 'Licence 1', 'L2': 'Licence 2', 'L3': 'Licence 3',
                       'M1': 'Master 1', 'M2': 'Master 2'}
    lignes, reserves = [], []
    cumul = {}
    for n in Niveau.objects.order_by('ordre'):
        sems = sorted(n.semestres.values_list('numero', flat=True))
        cumul[n.cycle] = cumul.get(n.cycle, 0) + n.credits_requis
        lignes.append([
            n.code, n.libelle, n.get_cycle_display(), n.ordre,
            ' + '.join(f'S{s}' for s in sems), n.credits_requis, cumul[n.cycle],
            sanctions.get(correspondances.get(n.code, ''), '—'), 'En base (actif)' if n.actif else 'En base',
        ])
    reserves.append(len(lignes))
    lignes.append(['D1–D3', 'Doctorat (années 1 à 3)', 'Doctorat', '6–8',
                   'S11 à S16', '180 (cycle)', 180,
                   sanctions.get('Doctorat 1-3', 'Doctorat (BAC+8)'),
                   'Mentionné par le référentiel — non modélisé dans l’application'])
    for palier, code, libelle in (
        ('Cycle professionnel', 'PRO', 'Cycle professionnel (2 ans)'),
        ('Professorat de collège (concours)', 'PC', 'Professorat de collège (concours, 3 ans)'),
    ):
        p = next(x for x in jeu['paliers'] if x['palier'] == palier)
        reserves.append(len(lignes))
        lignes.append([code, libelle, 'Hors LMD', '—', p['semestres'],
                       '—', '—', p['sanction'],
                       'Hors périmètre LMD — cité pour l’exhaustivité du processus'])
    _table(ws, colonnes, lignes, [10, 30, 12, 8, 16, 12, 16, 42, 40], reserves)
    return len(lignes)


def feuille_semestres(wb, jeu):
    ws = wb.create_sheet('2_Semestres')
    ws.sheet_properties.tabColor = BLEU
    _titre(ws, 'SEMESTRES LMD — INJS d’Abidjan',
           'S1 à S10 (30 ECTS par semestre). Libellés Master : S7 = M.S1, S8 = M.S2, '
           'S9 = M.S3, S10 = M.S4. Source : référentiel, feuilles « 4. Semestres & Grades » et « Listes ».', 9)
    colonnes = ['N° global', 'Code', 'Libellé (référentiel)', 'Niveau', 'Cycle',
                'Rang dans le niveau', 'Crédits ECTS', 'Cumul depuis L1',
                'État dans l’application']
    lignes, reserves = [], []
    cumul = 0
    for s in Semestre.objects.select_related('niveau').order_by('numero'):
        cumul += 30
        rang = 1 if s.numero % 2 == 1 else 2
        lignes.append([s.numero, s.libelle, LIBELLES_SEMESTRES.get(s.numero, s.libelle),
                       s.niveau.code, s.niveau.get_cycle_display(), rang, 30, cumul,
                       'En base (actif)' if s.actif else 'En base'])
    for numero in range(11, 17):
        reserves.append(len(lignes))
        lignes.append([numero, f'S{numero}', f'Semestre {numero} (Doctorat)',
                       f'D{(numero - 9) // 2}', 'Doctorat', 1 if numero % 2 else 2,
                       '—', '—', 'Mentionné par le référentiel — non modélisé'])
    _table(ws, colonnes, lignes, [11, 9, 26, 10, 12, 17, 12, 15, 42], reserves)
    return len(lignes)


def feuille_parcours(wb, jeu):
    ws = wb.create_sheet('3_Parcours')
    ws.sheet_properties.tabColor = BLEU
    _titre(ws, 'PARCOURS — INJS d’Abidjan',
           'Trois blocs à ne pas confondre : A) parcours diplômants LMD (Licence/Master de '
           'chaque filière, grille du classeur §1.2) ; B) parcours historiques codés dans '
           'l’application (à confirmer par la scolarité) ; C) sports de spécialité (APS de '
           'spécialité des maquettes). Aucun parcours n’est créé en base : le référentiel '
           'décrit des filières, pas des parcours distincts (cf. configurer_referentiel_injs).', 11)
    colonnes = ['Bloc', 'Code', 'Intitulé du parcours', 'Filière / cycle de rattachement',
                'École', 'Mention', 'Diplôme délivré', 'Durée', 'Crédits',
                'Maquette publiée', 'État / source']
    lignes, reserves = [], []
    en_base = Parcours.objects.count()
    # Bloc A — 16 parcours diplômants
    for code in sorted(jeu['filieres']):
        f = jeu['filieres'][code]
        ecole = f['ecole'].split(' ')[0]
        publiee = 'Oui (EM/MS/ES/APA)' if f['sigle'] in jeu['maquettes'] else 'Non publiée'
        for diplome, duree, credits in (('Licence', '3 ans', 180), ('Master', '2 ans', 120)):
            lignes.append([
                'A — Diplômant LMD', f"{code}-{diplome.upper()}",
                f"{diplome} professionnelle {f['mention']} — {f['libelle']} ({f['sigle']})",
                f"{code} {f['sigle']} — {f['libelle']}", ecole, f['mention'],
                f"{diplome} pro {f['mention']}", duree, credits, publiee,
                'Structure attestée (classeur §1.2)' + ('' if publiee.startswith('Oui')
                 else ' — contenu à obtenir auprès de la scolarité DENSEP'),
            ])
    # Bloc B — parcours historiques de l'application
    for code_p, intitule in (
        ('EM', 'Éducation et Motricité'), ('ES', 'Entraînement Sportif'),
        ('MS', 'Management du Sport'), ('APAS', 'Activité Physique Adaptée et Santé'),
        ('ASE', 'Animation Socio-Éducative'), ('MJ', 'Métiers de la Jeunesse'),
    ):
        reserves.append(len(lignes))
        lignes.append(['B — Historique (application)', code_p, intitule,
                       'Premier cycle actif (rattachement historique)', '—', '—', '—',
                       '—', '—', '—',
                       'Codé dans init_referentiels_lmd (PARCOURS_INJS) — à confirmer '
                       'par la scolarité ; non créé en base'])
    # Bloc C — sports de spécialité
    for sport in jeu['listes'].get('Sport de spécialité', []):
        lignes.append(['C — Spécialité APS', sport.upper()[:12],
                       f'Spécialisation théorique et pratique — {sport}',
                       'UE « Spécialisation théorique et pratique dans une APS » des maquettes ENSEPS',
                       'ENSEPS', 'STAPS', '—', 'Par semestre', 'Selon maquette',
                       'Oui (dans les UE de spécialisation)',
                       'Liste du référentiel (feuille Listes)'])
    _table(ws, colonnes, lignes, [24, 14, 48, 36, 10, 10, 18, 10, 13, 22, 46], reserves)
    return len(lignes), en_base


def feuille_maquettes(wb, jeu):
    ws = wb.create_sheet('4_Maquettes')
    ws.sheet_properties.tabColor = BLEU
    _titre(ws, 'MAQUETTES PÉDAGOGIQUES — INJS d’Abidjan',
           'Une maquette = un niveau d’une formation (cycle) pour une année académique. '
           '20 maquettes en base (statut BROUILLON : validation/activation = décision '
           'institutionnelle), soit 39 programmes semestriels documentés. Les maquettes '
           'STASE (F05–F08) ne sont pas publiées par le référentiel.', 13)
    colonnes = ['Filière (dossier)', 'Sigle', 'Formation (cycle)', 'Niveau',
                'Libellé de la maquette', 'Année académique', 'Version', 'Statut',
                'Semestres couverts', 'Nb UE', 'Nb ECUE', 'Crédits (cible 60)', 'État / source']
    lignes, reserves = [], []
    maquettes = (Maquette.objects
                 .select_related('ref_formation__filiere', 'niveau', 'annee_academique')
                 .annotate(nb_ue=Count('unites_enseignement', distinct=True),
                           nb_ecue=Count('unites_enseignement__ecues', distinct=True))
                 .order_by('ref_formation__filiere__code_dossier', 'niveau__ordre'))
    # Crédits calculés hors jointure ECUE (une Sum() dans l'annotate ci-dessus
    # compterait les crédits d'une UE autant de fois qu'elle a d'ECUE).
    credits_par_maquette = {
        r['maquette_id']: r['s']
        for r in UE.objects.values('maquette_id').annotate(s=Sum('credits'))
    }
    for m in maquettes:
        filiere = m.ref_formation.filiere
        semestres = sorted(set(m.unites_enseignement.values_list('semestre__numero', flat=True)))
        credits = credits_par_maquette.get(m.id, 0)
        incomplet = credits != 60
        if incomplet:
            reserves.append(len(lignes))
        lignes.append([
            filiere.code_dossier if filiere else '—',
            filiere.code if filiere else '—',
            m.ref_formation.intitule, m.niveau.code, m.libelle,
            m.annee_academique.libelle, m.version, m.get_statut_display(),
            ', '.join(f'S{s}' for s in semestres), m.nb_ue, m.nb_ecue, credits,
            'En base — maquette publiée (site INJS)'
            + (' ; INCOMPLÈTE : un semestre est absent du référentiel (cf. MS S8)' if incomplet else ''),
        ])
    for code in ('F05', 'F06', 'F07', 'F08'):
        f = jeu['filieres'][code]
        for diplome, niveaux in (('LICENCE', 'L1, L2, L3'), ('MASTER', 'M1, M2')):
            reserves.append(len(lignes))
            lignes.append([code, f['sigle'], f"{f['libelle'].upper()} — {diplome}", niveaux,
                           '—', '—', '—', 'Non créée', '—', 0, 0, 0,
                           'Maquette non publiée par le référentiel — à obtenir '
                           'auprès de la scolarité DENSEP (aucune UE inventée)'])
    _table(ws, colonnes, lignes,
           [14, 8, 42, 12, 34, 15, 9, 12, 17, 8, 9, 14, 52], reserves)
    return len(lignes)


def feuille_ue(wb, cles):
    ws = wb.create_sheet('5_UE')
    ws.sheet_properties.tabColor = BLEU
    _titre(ws, 'UNITÉS D’ENSEIGNEMENT (UE) — INJS d’Abidjan',
           'Les 323 UE des 4 maquettes publiées (EM, MS, ES, APA). Les codes sont '
           'TECHNIQUES (dérivés du rang) : le référentiel ne publie aucun code officiel. '
           'La « clé source » est la clé métier du classeur (Filière|Semestre|UE).', 13)
    colonnes = ['Filière', 'Formation (cycle)', 'Niveau', 'Semestre (n°)',
                'Semestre (référentiel)', 'Rang', 'Code technique', 'Intitulé de l’UE',
                'Famille de modules', 'Crédits ECTS', 'Caractère', 'Nb ECUE', 'Clé source']
    ues = (UE.objects
           .select_related('maquette__ref_formation__filiere', 'maquette__niveau',
                           'semestre', 'famille')
           .annotate(nb_ecue=Count('ecues'))
           .order_by('maquette__ref_formation__filiere__code_dossier',
                     'semestre__numero', 'ordre'))
    lignes = []
    for ue in ues:
        sigle = ue.code.split('-')[0]
        filiere = ue.maquette.ref_formation.filiere
        lignes.append([
            f"{filiere.code_dossier} — {sigle}" if filiere else sigle,
            ue.maquette.ref_formation.intitule, ue.maquette.niveau.code,
            ue.semestre.numero, LIBELLES_SEMESTRES.get(ue.semestre.numero, ''),
            ue.ordre, ue.code, ue.intitule,
            ue.famille.libelle if ue.famille else '—', ue.credits,
            ue.get_caractere_display(), ue.nb_ecue,
            cles.get((sigle, ue.semestre.numero, ue.ordre), ''),
        ])
    _table(ws, colonnes, lignes, [13, 40, 9, 12, 21, 7, 15, 52, 28, 11, 12, 9, 46])
    return len(lignes)


def feuille_ecue(wb):
    ws = wb.create_sheet('6_ECUE')
    ws.sheet_properties.tabColor = BLEU
    _titre(ws, 'ÉLÉMENTS CONSTITUTIFS D’UE (ECUE) — INJS d’Abidjan',
           'Les 397 ECUE des 323 UE. Crédits ECUE et volumes CM/TD/TP : non publiés '
           'par le référentiel (les crédits sont portés par l’UE) — valeurs à 0, '
           'jamais estimées. Codes techniques dérivés du rang.', 10)
    colonnes = ['Code UE', 'Intitulé de l’UE', 'Rang', 'Code technique ECUE',
                'Intitulé de l’ECUE', 'Crédits ECUE', 'Coefficient',
                'Volume CM (h)', 'Volume TD (h)', 'Volume TP (h)']
    ecues = (ECUE.objects.select_related('ue')
             .order_by('ue__maquette__ref_formation__filiere__code_dossier',
                       'ue__semestre__numero', 'ue__ordre', 'ordre'))
    lignes = [[e.ue.code, e.ue.intitule, e.ordre, e.code, e.intitule, e.credits,
               float(e.coefficient), float(e.volume_cm), float(e.volume_td),
               float(e.volume_tp)] for e in ecues]
    _table(ws, colonnes, lignes, [15, 48, 7, 19, 62, 12, 12, 12, 12, 12])
    return len(lignes)


def feuille_controles(wb):
    ws = wb.create_sheet('7_Controles')
    ws.sheet_properties.tabColor = '548235'
    _titre(ws, 'CONTRÔLES DE COHÉRENCE (recalculés depuis la base)',
           'Mêmes contrôles que RAPPORT-CONTROLE-323-UE.md et la commande '
           'controler_referentiel_injs. Les réserves sont documentaires '
           '(elles viennent de la source), aucune donnée n’a été inventée pour les combler.', 4)
    colonnes = ['Contrôle', 'Attendu (source)', 'Obtenu (base)', 'Résultat / réserve']
    attendus = {'EM': (86, 100, 300), 'MS': (73, 94, 270), 'ES': (81, 99, 300), 'APA': (83, 104, 300)}
    lignes, reserves = [], []
    for sigle, (ue_a, ecue_a, cr_a) in attendus.items():
        ue_o = UE.objects.filter(code__startswith=f'{sigle}-').count()
        ecue_o = ECUE.objects.filter(ue__code__startswith=f'{sigle}-').count()
        cr_o = UE.objects.filter(code__startswith=f'{sigle}-').aggregate(s=Sum('credits'))['s'] or 0
        ok = (ue_o, ecue_o, cr_o) == (ue_a, ecue_a, cr_a)
        if not ok:
            reserves.append(len(lignes))
        lignes.append([f'{sigle} — UE / ECUE / crédits', f'{ue_a} / {ecue_a} / {cr_a}',
                       f'{ue_o} / {ecue_o} / {cr_o}', 'Conforme' if ok else 'Écart à analyser'])
    tot_ue, tot_ecue = UE.objects.count(), ECUE.objects.count()
    tot_cr = UE.objects.aggregate(s=Sum('credits'))['s'] or 0
    lignes.append(['TOTAL UE / ECUE / crédits', '323 / 397 / 1170',
                   f'{tot_ue} / {tot_ecue} / {tot_cr}',
                   'Conforme' if (tot_ue, tot_ecue, tot_cr) == (323, 397, 1170) else 'Écart'])
    ecarts = []
    for r in (UE.objects.values('maquette__ref_formation__filiere__code', 'semestre__numero')
              .annotate(s=Sum('credits')).order_by('semestre__numero')):
        if r['s'] != 30:
            ecarts.append(f"{r['maquette__ref_formation__filiere__code']} S{r['semestre__numero']}={r['s']}")
    lignes.append(['Semestres à 30 ECTS (39 programmes semestriels documentés)',
                   '39/39 à 30', '39/39 à 30' if not ecarts else ' ; '.join(ecarts),
                   'Conforme' if not ecarts else 'Écart'])
    for reserve, detail in (
        ('MS S8 absent', 'Le référentiel ne contient aucune UE pour Management du Sport / M1 S8 : '
         'Master MS = 270 crédits au lieu de 300. Décision institutionnelle requise.'),
        ('F05–F08 sans maquette', 'Andragogie, Loisir, ECJP, Gérontologie : filières décrites, '
         'aucun tableau UE/ECUE publié (scolarité DENSEP). 0 UE créée.'),
        ('Codes UE/ECUE', 'Aucun code officiel publié : codes techniques dérivés du rang '
         '(EM-S1-UE01, EM-S1-UE01-EC01) — ne jamais les présenter comme officiels.'),
        ('Crédits ECUE / volumes horaires', 'Non publiés : crédits portés par l’UE ; '
         'CM/TD/TP à 0 dans l’application, en attendant les maquettes horaires.'),
        ('Maquettes en BROUILLON', 'Aucune maquette n’est activée automatiquement : '
         'validation puis activation dans l’application (processus métier).'),
        ('Parcours en base : 0', 'Le référentiel décrit des filières, pas des parcours '
         'distincts ; aucun parcours inventé (voir feuille 3_Parcours).'),
    ):
        reserves.append(len(lignes))
        lignes.append([f'Réserve — {reserve}', '—', '—', detail])
    _table(ws, colonnes, lignes, [52, 20, 22, 78], reserves)
    return len(lignes)


def feuille_lisez_moi(wb, compteurs, date_gen):
    ws = wb['Lisez-moi'] if 'Lisez-moi' in wb.sheetnames else wb.active
    ws.title = 'Lisez-moi'
    ws.sheet_properties.tabColor = BLEU
    ws.column_dimensions['A'].width = 26
    ws.column_dimensions['B'].width = 104
    titre = ws.cell(row=1, column=1,
                    value='INJS D’ABIDJAN — LISTE EXHAUSTIVE DU SYSTÈME LMD')
    titre.font = Font(size=15, bold=True, color=BLEU)
    lignes = [
        ('Objet', 'Liste complète et détaillée des niveaux, semestres, parcours, '
                  'maquettes, UE et ECUE du processus métier et académique LMD de '
                  'l’INJS d’Abidjan — générée depuis la base de l’application '
                  'INJS-LMD 2026 (les valeurs sont donc identiques à celles de l’application).'),
        ('Généré le', date_gen),
        ('Source des données', SOURCE_CLASSEUR + '. Compilation du classeur depuis le site '
                               'officiel www.injsabidjan.ci (maquettes publiées EM/MS/ES/APA).'),
        ('Chaîne métier', 'ÉCOLE → MENTION → FILIÈRE → FORMATION (cycle Licence/Master) → '
                          'PARCOURS → NIVEAU → SEMESTRE → UE → ECUE.'),
        ('1_Niveaux', f"{compteurs['niveaux']} lignes : L1, L2, L3, M1, M2 (60 ECTS/an) "
                      '+ Doctorat et paliers hors LMD mentionnés par le référentiel.'),
        ('2_Semestres', f"{compteurs['semestres']} lignes : S1 à S10 (30 ECTS) + S11 à S16 (Doctorat, mention)."),
        ('3_Parcours', f"{compteurs['parcours']} lignes en 3 blocs : 16 parcours diplômants "
                       'LMD (8 filières × Licence/Master), 6 parcours historiques de '
                       'l’application (à confirmer), 13 sports de spécialité. En base : '
                       f"{compteurs['parcours_base']} parcours créé (aucun parcours inventé)."),
        ('4_Maquettes', f"{compteurs['maquettes']} lignes : 20 maquettes en base (une par "
                        'niveau, statut BROUILLON, année 2026-2027) couvrant 39 programmes '
                        'semestriels + 8 cycles STASE dont la maquette n’est pas publiée.'),
        ('5_UE', f"{compteurs['ue']} UE avec crédits ECTS, famille de modules et clé source."),
        ('6_ECUE', f"{compteurs['ecue']} ECUE (crédits par ECUE et volumes horaires non "
                   'publiés par le référentiel : 0, jamais estimés).'),
        ('7_Controles', 'Contrôles recalculés (323 UE / 397 ECUE / 1 170 crédits, semestres '
                        'à 30 ECTS) et réserves documentaires (MS S8, F05–F08, codes techniques).'),
        ('Codes UE/ECUE', 'Codes TECHNIQUES de l’application, dérivés du rang '
                          '(EM-S1-UE01, EM-S1-UE01-EC01). Le référentiel ne publie '
                          'aucune codification officielle.'),
        ('Lignes sur fond jaune', 'Réserves documentaires : éléments mentionnés ou attendus '
                                  'mais non publiés/non modélisés — aucune valeur inventée.'),
        ('Régénération', 'backend/.venv/bin/python scripts/generer_liste_lmd.py '
                         '(après init_referentiels_lmd + configurer_referentiel_injs). '
                         'Le classeur .xlsx est ignoré par Git ; le script est la source durable.'),
    ]
    for i, (cle, valeur) in enumerate(lignes, 3):
        a = ws.cell(row=i, column=1, value=cle)
        a.font = Font(size=10, bold=True, color=BLEU)
        a.alignment = Alignment(vertical='top')
        b = ws.cell(row=i, column=2, value=valeur)
        b.font = Font(size=10)
        b.alignment = Alignment(wrap_text=True, vertical='top')
        ws.row_dimensions[i].height = 42
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.orientation = 'portrait'
    ws.page_setup.fitToWidth = 1


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--sortie', default=str(RACINE / 'INJS-LMD_Liste-exhaustive.xlsx'))
    args = parser.parse_args()

    if UE.objects.count() == 0:
        raise SystemExit(
            'Base vide côté LMD : lancer d’abord '
            '`manage.py init_referentiels_lmd` puis `manage.py configurer_referentiel_injs`.'
        )
    jeu = _charger_jeu()
    cles = _cles_sources(jeu)

    wb = Workbook()
    compteurs = {}
    compteurs['niveaux'] = feuille_niveaux(wb, jeu)
    compteurs['semestres'] = feuille_semestres(wb, jeu)
    compteurs['parcours'], compteurs['parcours_base'] = feuille_parcours(wb, jeu)
    compteurs['maquettes'] = feuille_maquettes(wb, jeu)
    compteurs['ue'] = feuille_ue(wb, cles)
    compteurs['ecue'] = feuille_ecue(wb)
    feuille_controles(wb)
    feuille_lisez_moi(wb, compteurs, datetime.now().strftime('%d/%m/%Y %H:%M'))
    wb.move_sheet('Lisez-moi', offset=-(len(wb.sheetnames) - 1))
    wb.active = wb['Lisez-moi']

    wb.save(args.sortie)
    print(f'Classeur écrit : {args.sortie}')
    print('Compteurs : ' + ', '.join(f'{k}={v}' for k, v in compteurs.items()))


if __name__ == '__main__':
    main()
