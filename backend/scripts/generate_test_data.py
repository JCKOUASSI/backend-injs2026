#!/usr/bin/env python

# Script manuel HORS RUNTIME Django (P00-05) : CLI opérateur d'import/reprise.
# Sorties print() de console volontaires ; exclu du garde-fou check_repo_hygiene.
"""
Génère un seul fichier Excel de test : import_test.xlsx

Feuilles :
  - Formations   : 6 modules (3 cat A/A4/GROUPE 1 + 3 cat B/B2/GROUPE 1)
  - Participants : 6 auditeurs auto-matchés par cat+grade+groupe
  - Formateurs   : 5 formateurs
  - Séances      : séances par module + groupe (1 module = 1 formation)

Usage :
  python scripts/generate_test_data.py
  → Fichier généré : import_test.xlsx

Ordre d'import :
  python manage.py import_excel import_test.xlsx
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# ── Styles ────────────────────────────────────────────────────────────────────
hfont  = Font(bold=True, color='FFFFFF', size=11)
fill_g = PatternFill(start_color='093F70', end_color='093F70', fill_type='solid')
fill_b = PatternFill(start_color='0D47A1', end_color='0D47A1', fill_type='solid')
fill_o = PatternFill(start_color='E69700', end_color='E69700', fill_type='solid')
fill_p = PatternFill(start_color='4A148C', end_color='4A148C', fill_type='solid')
fill_r = PatternFill(start_color='E8EFF5', end_color='E8EFF5', fill_type='solid')
thin   = Border(
    left=Side(style='thin', color='CCCCCC'), right=Side(style='thin', color='CCCCCC'),
    top=Side(style='thin', color='CCCCCC'),  bottom=Side(style='thin', color='CCCCCC'),
)


def write_sheet(ws, headers, rows, fill):
    for c, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=c, value=h)
        cell.font = hfont; cell.fill = fill
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        cell.border = thin
    for r, row in enumerate(rows, 2):
        for c, v in enumerate(row, 1):
            cell = ws.cell(row=r, column=c, value=v)
            cell.fill = fill_r; cell.border = thin
            cell.alignment = Alignment(vertical='center')
    for col in range(1, len(headers) + 1):
        max_len = max(
            len(str(ws.cell(row=r2, column=col).value or ''))
            for r2 in range(1, len(rows) + 3)
        )
        ws.column_dimensions[get_column_letter(col)].width = min(max(max_len + 4, 14), 50)


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ══════════════════════════════════════════════════════════════════════════════
# Données partagées
# Chaque module est UNIQUE par intitulé — les séances s'y rattachent via
# formation_titre (= intitulé du module) + groupe.
# Les modules A et B ont des intitulés différents pour éviter toute ambiguïté.
# ══════════════════════════════════════════════════════════════════════════════
# formation (cycle) → Formation.formation
# module            → Module.intitule (rattaché à la formation)
# Les séances se rattachent au module via formation_titre = intitulé du module

FORMATION_A = 'FORMATION EN ADMINISTRATION DE BASE'
FORMATION_B = 'FORMATION EN GESTION PUBLIQUE'

# (formation_cycle, module_titre, date_debut, date_fin, volume_horaire)
MODULES_A = [
    (FORMATION_A, 'Déontologie et Ethique Professionnelle', '2025-09-01 08:00', '2025-09-03 17:00', 24),
    (FORMATION_A, 'Protocole et Savoir-vivre',              '2025-09-04 08:00', '2025-09-05 17:00', 16),
    (FORMATION_A, 'Techniques Administratives',             '2025-09-08 08:00', '2025-09-10 17:00', 24),
]
MODULES_B = [
    (FORMATION_B, 'Droit Administratif',                    '2025-09-01 08:00', '2025-09-03 17:00', 24),
    (FORMATION_B, 'Finances Publiques',                     '2025-09-04 08:00', '2025-09-05 17:00', 16),
    (FORMATION_B, 'Management des Organisations',           '2025-09-08 08:00', '2025-09-09 17:00', 16),
]

# ══════════════════════════════════════════════════════════════════════════════
# 1. FORMATIONS — import_test_formations.xlsx   (feuille : Formations)
# ══════════════════════════════════════════════════════════════════════════════
rows_f = []
for i, (formation, mod, debut, fin, vh) in enumerate(MODULES_A, 1):
    rows_f.append([i, formation, mod, debut, fin, vh, 'A', 'A4', 'GROUPE 1', 'SESSION 2025', 'CPFAE', 'SALLE A'])
for i, (formation, mod, debut, fin, vh) in enumerate(MODULES_B, 1):
    rows_f.append([i, formation, mod, debut, fin, vh, 'B', 'B2', 'GROUPE 1', 'SESSION 2025', 'CPFAE', 'SALLE B'])

wb1 = Workbook()
ws1 = wb1.active; ws1.title = 'Formations'
write_sheet(ws1,
    headers=['N°', 'Formation', 'Module (titre)', 'Date début', 'Date fin',
             'Volume horaire (h)', 'Catégorie', 'Grade', 'Groupe', 'Vague', 'Site', 'Salle'],
    rows=rows_f, fill=fill_g,
)
p1 = os.path.join(BASE_DIR, 'import_test_formations.xlsx')
wb1.save(p1)
print(f'✅ {p1}  ({len(rows_f)} formations)')

# ══════════════════════════════════════════════════════════════════════════════
# 2. PARTICIPANTS — import_test_participants.xlsx   (feuille : Participants)
#    Formation(s) vide → auto-match par Catégorie + Grade + Groupe
# ══════════════════════════════════════════════════════════════════════════════
rows_p = [
    # matricule, Nom, Prénoms, Sexe, Date naiss, Lieu naiss,
    # Tel1, Tel2, Email, Type concours, Libelle concours,
    # Catégorie, Grade, Groupe, Grade-Groupe, Vague, Formation(s)
    ['TEST-A001', 'KOUASSI',   'AMANI JEAN',      'MASCULIN', '15/03/1988', 'ABIDJAN',      '0700111001', '',           'jean.kouassi@test.ci',     'PROFESSIONNEL', 'ADMINISTRATEUR', 'A', 'A4', 'GROUPE 1', 'A4/GROUPE 1', 'SESSION 2025', ''],
    ['TEST-A002', 'BAMBA',     'FATOUMATA',        'FEMININ',  '22/07/1992', 'BOUAKE',       '0700111002', '',           'fatoumata.bamba@test.ci',  'PROFESSIONNEL', 'ADMINISTRATEUR', 'A', 'A4', 'GROUPE 1', 'A4/GROUPE 1', 'SESSION 2025', ''],
    ['TEST-A003', 'TRAORE',    'MOUSSA',            'MASCULIN', '03/11/1985', 'DALOA',        '0700111003', '',           '',                         'PROFESSIONNEL', 'ADMINISTRATEUR', 'A', 'A4', 'GROUPE 1', 'A4/GROUPE 1', 'SESSION 2025', ''],
    ['TEST-A004', 'DIALLO',    'MARIAME',           'FEMININ',  '11/05/1990', 'KORHOGO',      '0700111004', '0500111004', 'm.diallo@test.ci',         'PROFESSIONNEL', 'ADMINISTRATEUR', 'A', 'A4', 'GROUPE 1', 'A4/GROUPE 1', 'SESSION 2025', ''],
    ['TEST-A005', "N'GUESSAN", 'KOFFI FRANCK',     'MASCULIN', '28/09/1987', 'YAMOUSSOUKRO', '0700111005', '',           'koffi.ng@test.ci',         'PROFESSIONNEL', 'ADMINISTRATEUR', 'A', 'A4', 'GROUPE 1', 'A4/GROUPE 1', 'SESSION 2025', ''],
    ['TEST-B001', 'OUATTARA',  'SEYDOU',            'MASCULIN', '07/01/1983', 'MAN',          '0700111006', '',           '',                         'PROFESSIONNEL', 'TECHNICIEN',     'B', 'B2', 'GROUPE 1', 'B2/GROUPE 1', 'SESSION 2025', ''],
    ['TEST-B002', 'KONE',      'AMINATA',           'FEMININ',  '19/06/1994', 'ABIDJAN',      '0700111007', '0500111007', 'aminata.kone@test.ci',     'PROFESSIONNEL', 'TECHNICIEN',     'B', 'B2', 'GROUPE 1', 'B2/GROUPE 1', 'SESSION 2025', ''],
    ['TEST-B003', 'COULIBALY', 'IBRAHIM',           'MASCULIN', '30/12/1989', 'GAGNOA',       '0700111008', '',           '',                         'PROFESSIONNEL', 'TECHNICIEN',     'B', 'B2', 'GROUPE 1', 'B2/GROUPE 1', 'SESSION 2025', ''],
    ['TEST-B004', 'SISSOKO',   'KADIATOU',          'FEMININ',  '14/08/1991', 'ODIENNE',      '0700111009', '',           'kadiatou.sissoko@test.ci', 'PROFESSIONNEL', 'TECHNICIEN',     'B', 'B2', 'GROUPE 1', 'B2/GROUPE 1', 'SESSION 2025', ''],
    ['TEST-B005', 'FOFANA',    'ABOUBACAR',         'MASCULIN', '02/04/1986', 'BONDOUKOU',    '0700111010', '',           '',                         'PROFESSIONNEL', 'TECHNICIEN',     'B', 'B2', 'GROUPE 1', 'B2/GROUPE 1', 'SESSION 2025', ''],
]

wb2 = Workbook()
ws2 = wb2.active; ws2.title = 'Participants'
write_sheet(ws2,
    headers=["N° d'inscription", 'Nom', 'Prénoms', 'Sexe',
             'Date naissance', 'Lieu naissance', 'Téléphone 1', 'Téléphone 2', 'Email',
             'Type concours', 'Libelle concours',
             'Catégorie', 'Grade', 'Groupe', 'Grade-Groupe', 'Vague',
             'Formation(s)'],
    rows=rows_p, fill=fill_b,
)
p2 = os.path.join(BASE_DIR, 'import_test_participants.xlsx')
wb2.save(p2)
print(f'✅ {p2}  ({len(rows_p)} participants)')

# ══════════════════════════════════════════════════════════════════════════════
# 3. FORMATEURS — import_test_formateurs.xlsx   (feuille : Formateurs)
# ══════════════════════════════════════════════════════════════════════════════
rows_fmt = [
    ['FT001', 'MENSAH',    'KOFFI EDOUARD',  'k.mensah@cpfae.ci',    '0700222001', 'Déontologie et Ethique Professionnelle', 'CPFAE'],
    ['FT002', 'DIOMANDE',  'SALIMATA',        's.diomande@cpfae.ci',  '0700222002', 'Protocole et Savoir-vivre',             'CPFAE'],
    ['FT003', 'GBAGBO',    'RICHARD ARMEL',   'r.gbagbo@ena.ci',      '0700222003', 'Techniques Administratives',            'ENA'],
    ['FT004', 'CAMARA',    'LAMINE MAMADOU',  'l.camara@univ.ci',     '0700222004', 'Droit Administratif',                   'Université FHB'],
    ['FT005', 'DOSSO',     'AMINATA',          'a.dosso@mef.ci',       '0700222005', 'Finances Publiques',                    'MEF'],
    ['FT006', 'KOFFI',     'JEAN-BAPTISTE',   'jb.koffi@cpfae.ci',    '0700222006', 'Management des Organisations',          'CPFAE'],
]

wb3 = Workbook()
ws3 = wb3.active; ws3.title = 'Formateurs'
write_sheet(ws3,
    headers=['Numéro', 'Nom', 'Prénoms', 'Email', 'Téléphone', 'Spécialité', 'Organisation'],
    rows=rows_fmt, fill=fill_o,
)
p3 = os.path.join(BASE_DIR, 'import_test_formateurs.xlsx')
wb3.save(p3)
print(f'✅ {p3}  ({len(rows_fmt)} formateurs)')

# ══════════════════════════════════════════════════════════════════════════════
# 4. SÉANCES — import_test_seances.xlsx   (feuille : Séances)
#    formation_titre = intitulé exact du module (doit correspondre à Module.intitule en base)
#    groupe         = filtre la bonne formation quand plusieurs groupes existent
#    Chaque module a un intitulé unique → 1 module = 1 formation = séances sans ambiguïté
# ══════════════════════════════════════════════════════════════════════════════
rows_s = [
    # ── Cat A / A4 / GROUPE 1 ──────────────────────────────────────────────
    ['Déontologie et Ethique Professionnelle', 'GROUPE 1', '2025-09-01', 1, 'Matin',      '08:00', '12:00'],
    ['Déontologie et Ethique Professionnelle', 'GROUPE 1', '2025-09-01', 2, 'Après-midi', '13:30', '17:00'],
    ['Déontologie et Ethique Professionnelle', 'GROUPE 1', '2025-09-02', 1, 'Matin',      '08:00', '12:00'],
    ['Déontologie et Ethique Professionnelle', 'GROUPE 1', '2025-09-02', 2, 'Après-midi', '13:30', '17:00'],
    ['Déontologie et Ethique Professionnelle', 'GROUPE 1', '2025-09-03', 1, 'Matin',      '08:00', '12:00'],
    ['Protocole et Savoir-vivre',              'GROUPE 1', '2025-09-04', 1, 'Matin',      '08:00', '12:00'],
    ['Protocole et Savoir-vivre',              'GROUPE 1', '2025-09-04', 2, 'Après-midi', '13:30', '17:00'],
    ['Protocole et Savoir-vivre',              'GROUPE 1', '2025-09-05', 1, 'Matin',      '08:00', '12:00'],
    ['Techniques Administratives',             'GROUPE 1', '2025-09-08', 1, 'Matin',      '08:00', '12:00'],
    ['Techniques Administratives',             'GROUPE 1', '2025-09-08', 2, 'Après-midi', '13:30', '17:00'],
    ['Techniques Administratives',             'GROUPE 1', '2025-09-09', 1, 'Matin',      '08:00', '12:00'],
    # ── Cat B / B2 / GROUPE 1 ──────────────────────────────────────────────
    ['Droit Administratif',                    'GROUPE 1', '2025-09-01', 1, 'Matin',      '08:00', '12:00'],
    ['Droit Administratif',                    'GROUPE 1', '2025-09-01', 2, 'Après-midi', '13:30', '17:00'],
    ['Droit Administratif',                    'GROUPE 1', '2025-09-02', 1, 'Matin',      '08:00', '12:00'],
    ['Droit Administratif',                    'GROUPE 1', '2025-09-02', 2, 'Après-midi', '13:30', '17:00'],
    ['Droit Administratif',                    'GROUPE 1', '2025-09-03', 1, 'Matin',      '08:00', '12:00'],
    ['Finances Publiques',                     'GROUPE 1', '2025-09-04', 1, 'Matin',      '08:00', '12:00'],
    ['Finances Publiques',                     'GROUPE 1', '2025-09-04', 2, 'Après-midi', '13:30', '17:00'],
    ['Finances Publiques',                     'GROUPE 1', '2025-09-05', 1, 'Matin',      '08:00', '12:00'],
    ['Management des Organisations',           'GROUPE 1', '2025-09-08', 1, 'Matin',      '08:00', '12:00'],
    ['Management des Organisations',           'GROUPE 1', '2025-09-08', 2, 'Après-midi', '13:30', '17:00'],
]

wb4 = Workbook()
ws4 = wb4.active; ws4.title = 'Séances'
write_sheet(ws4,
    headers=['module_titre', 'groupe', 'date_journee', 'numero',
             'intitule', 'heure_debut', 'heure_fin'],
    rows=rows_s, fill=fill_p,
)
p4 = os.path.join(BASE_DIR, 'import_test_seances.xlsx')
wb4.save(p4)
print(f'✅ {p4}  ({len(rows_s)} séances)')

print()
print('Ordre d\'import :')
print('  1. python manage.py import_excel import_test_formateurs.xlsx')
print('  2. python manage.py import_excel import_test_formations.xlsx')
print('  3. python manage.py import_excel import_test_participants.xlsx')
print('  4. python manage.py import_excel import_test_seances.xlsx')
