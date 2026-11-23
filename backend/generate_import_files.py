"""
Script manuel HORS RUNTIME Django (P00-05) : CLI opérateur
d'import/reprise — sorties print() de console volontaires ;
exclu du garde-fou check_repo_hygiene.
Script de génération des fichiers Excel d'import réels.
Usage : python generate_import_files.py
"""
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from datetime import date, time, datetime
import os

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Styles ───────────────────────────────────────────────────────────────────

def _hs():
    return dict(
        font=Font(bold=True, color='FFFFFF', size=11),
        fill=PatternFill(start_color='1B3A5C', end_color='1B3A5C', fill_type='solid'),
        alignment=Alignment(horizontal='center', vertical='center', wrap_text=True),
        border=Border(
            left=Side(style='thin'), right=Side(style='thin'),
            top=Side(style='thin'),  bottom=Side(style='thin'),
        ),
    )

def _ds():
    return dict(
        alignment=Alignment(horizontal='left', vertical='center'),
        border=Border(
            left=Side(style='thin'), right=Side(style='thin'),
            top=Side(style='thin'),  bottom=Side(style='thin'),
        ),
    )

def apply(cell, styles):
    for k, v in styles.items():
        setattr(cell, k, v)

def set_headers(ws, headers, widths):
    hs = _hs()
    for col, (title, width) in enumerate(zip(headers, widths), 1):
        c = ws.cell(row=1, column=col, value=title)
        apply(c, hs)
        ws.column_dimensions[get_column_letter(col)].width = width
    ws.row_dimensions[1].height = 22

def add_row(ws, row_num, values):
    ds = _ds()
    for col, val in enumerate(values, 1):
        c = ws.cell(row=row_num, column=col, value=val)
        apply(c, ds)

def add_notes(ws, start_row, start_col, notes):
    ws.cell(row=start_row, column=start_col, value='Notes :').font = Font(bold=True, size=10)
    for i, n in enumerate(notes, start_row + 1):
        c = ws.cell(row=i, column=start_col, value=n)
        c.font = Font(italic=True, color='555555', size=9)


# ══════════════════════════════════════════════════════════════════════════════
# 1. FORMATIONS  →  import_reel_formations.xlsx
#    Feuille : "Formations"
#    Colonnes reconnues par import_excel._import_formations (sheet_type='formation')
# ══════════════════════════════════════════════════════════════════════════════
def gen_formations():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Formations'

    headers = [
        'Formation',           # → formation  (cycle, OBLIGATOIRE)
        'Module (titre)',      # → module     (intitulé Module lié, OBLIGATOIRE)
        'N°',                  # → numero_formation
        'Catégorie',           # → categorie  (A/B/C/D — pour auto-secrétariat)
        'Grade',               # → grade
        'Groupe',              # → groupe
        'Vague',               # → vague
        'Lieu',                # → site
        'Bâtiment',            # → batiment
        'Salle',               # → salle
        'Date début',          # → date_debut (AAAA-MM-JJ HH:MM ou JJ/MM/AAAA)
        'Date fin',            # → date_fin
        'Volume horaire (h)',  # → duree_prevue_heures
    ]
    widths = [42, 36, 6, 12, 12, 18, 22, 26, 20, 15, 22, 22, 18]
    set_headers(ws, headers, widths)

    rows = [
        ['FORMATION EN ADMINISTRATION DE BASE', 'Droit Administratif', 1, 'A', 'A4', 'GROUPE 1', 'PREMIERE VAGUE',  'CPFAE', 'Bâtiment A', 'Salle 101', datetime(2026, 5, 5, 8, 0), datetime(2026, 5, 30, 17, 0), 120],
        ['FORMATION EN ADMINISTRATION DE BASE', 'Droit Administratif', 1, 'A', 'A4', 'GROUPE 2', 'PREMIERE VAGUE',  'CPFAE', 'Bâtiment A', 'Salle 102', datetime(2026, 5, 5, 8, 0), datetime(2026, 5, 30, 17, 0), 120],
        ['FORMATION EN ADMINISTRATION DE BASE', 'Finances Publiques',  2, 'B', 'B1', 'GROUPE 1', 'DEUXIEME VAGUE',  'CPFAE', 'Bâtiment B', 'Salle 201', datetime(2026, 6, 1, 8, 0),  datetime(2026, 6, 25, 17, 0), 80],
        ['FORMATION SPECIALISEE EN GESTION',    'Management Public',   1, 'A', 'A3', 'GROUPE 1', 'PREMIERE VAGUE',  'ENAFOP', 'Bloc C',    'Salle 301', datetime(2026, 7, 1, 8, 0),  datetime(2026, 7, 20, 17, 0), 60],
    ]
    for i, row in enumerate(rows, 2):
        add_row(ws, i, row)

    add_notes(ws, 8, 1, [
        "• Formation    : intitulé du CYCLE de formation (champ 'formation' en base) — OBLIGATOIRE",
        "• Module (titre) : intitulé du module rattaché à cette formation — OBLIGATOIRE",
        "  → Crée ou met à jour automatiquement le Module lié",
        "• N°           : numéro de la formation dans le cycle (optionnel)",
        "• Catégorie    : A, B, C ou D — utilisé pour l'affectation automatique au secrétariat",
        "• Grade        : grade cible (A4, A3, B1…)",
        "• Groupe       : GROUPE 1, GROUPE 2… (optionnel)",
        "• Vague        : PREMIERE VAGUE, DEUXIEME VAGUE… (optionnel)",
        "• Date début/fin : format AAAA-MM-JJ HH:MM  ou  JJ/MM/AAAA",
        "• Volume horaire : nombre d'heures (décimal accepté, ex: 120 ou 80.5)",
    ])

    path = os.path.join(OUTPUT_DIR, 'import_reel_formations.xlsx')
    wb.save(path)
    print(f'  ✅ {path}')


# ══════════════════════════════════════════════════════════════════════════════
# 2. PARTICIPANTS  →  import_reel_participants.xlsx
#    Feuille : "Participants"
#    Colonnes reconnues par import_excel._import_participants (sheet_type='participant')
# ══════════════════════════════════════════════════════════════════════════════
def gen_participants():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Participants'

    headers = [
        "N° d'inscription",   # → matricule   (UNIQUE, OBLIGATOIRE)
        'Nom',                 # → nom         (OBLIGATOIRE)
        'Prénom',              # → prenom      (OBLIGATOIRE)
        'Sexe',                # → sexe        (MASCULIN / FEMININ)
        'Date de naissance',   # → date_naissance
        'Lieu de naissance',   # → lieu_naissance
        'Catégorie',           # → categorie
        'Grade',               # → grade
        'Grade/Groupe',        # → grade_groupe  (ex: A4/GROUPE 1)
        'Groupe',              # → groupe
        'Vague',               # → vague
        'Type concours',       # → type_concours
        'Libelle concours',    # → libelle_concours
        'Email',               # → email
        'Téléphone 1',         # → telephone
        'Téléphone 2',         # → telephone2
        'Formation(s)',        # → inscription auto (séparateur |)
    ]
    widths = [18, 20, 22, 12, 18, 24, 12, 12, 18, 18, 22, 20, 34, 30, 16, 16, 50]
    set_headers(ws, headers, widths)

    rows = [
        ['MAT001', 'DUPONT',   'Jean',        'MASCULIN', date(1990, 3, 15),  'Abidjan',  'A', 'A4', 'A4/GROUPE 1', 'GROUPE 1', 'PREMIERE VAGUE',  'Concours direct',       'Concours Administrateur Civil',  'jean.dupont@exemple.ci',   '0701000001', '',           'FORMATION EN ADMINISTRATION DE BASE'],
        ['MAT002', 'KONAN',    'Aya Marie',   'FEMININ',  date(1992, 7, 22),  'Bouaké',   'A', 'A4', 'A4/GROUPE 1', 'GROUPE 1', 'PREMIERE VAGUE',  'Concours direct',       'Concours Administrateur Civil',  'aya.konan@exemple.ci',     '0702000002', '',           'FORMATION EN ADMINISTRATION DE BASE'],
        ['MAT003', 'BAMBA',    'Oumar',       'MASCULIN', date(1988, 11, 5),  'Korhogo',  'B', 'B1', 'B1/GROUPE 1', 'GROUPE 1', 'DEUXIEME VAGUE',  'Concours professionnel','Concours Attaché Administration', 'oumar.bamba@exemple.ci',   '0703000003', '0703000099', 'FORMATION EN ADMINISTRATION DE BASE'],
        ['MAT004', 'YAO',      'Kouassi',     'MASCULIN', date(1985, 4, 10),  'Yamoussoukro', 'A', 'A3', 'A3/GROUPE 1', 'GROUPE 1', 'PREMIERE VAGUE', 'Concours direct',  'Concours Administrateur Principal', 'kouassi.yao@exemple.ci', '0704000004', '',           'FORMATION SPECIALISEE EN GESTION'],
        ['MAT005', 'COULIBALY', 'Aminata',   'FEMININ',  date(1995, 9, 30),  'Man',      'A', 'A4', 'A4/GROUPE 2', 'GROUPE 2', 'PREMIERE VAGUE',  'Concours direct',       'Concours Administrateur Civil',  'aminata.coulibaly@exemple.ci', '0705000005', '',        'FORMATION EN ADMINISTRATION DE BASE'],
    ]
    for i, row in enumerate(rows, 2):
        add_row(ws, i, row)

    add_notes(ws, 9, 1, [
        "• N° d'inscription : matricule UNIQUE et OBLIGATOIRE (clé de déduplication)",
        "• Sexe             : MASCULIN ou FEMININ (en majuscules)",
        "• Date de naissance: format JJ/MM/AAAA ou AAAA-MM-JJ",
        "• Formation(s)     : titre(s) EXACT(S) de formation(s). Séparateur | pour plusieurs.",
        "  Ex: FORMATION EN ADMINISTRATION DE BASE|FORMATION SPECIALISEE EN GESTION",
        "• Si Formation(s) vide → auto-match strict Catégorie + Grade + Groupe (tous 3 requis)",
        "• Grade/Groupe     : champ combiné pour affichage (ex: A4/GROUPE 1) — optionnel",
        "• Catégorie        : détermine l'affectation automatique au secrétariat (A→Séc.A, etc.)",
    ])

    path = os.path.join(OUTPUT_DIR, 'import_reel_participants.xlsx')
    wb.save(path)
    print(f'  ✅ {path}')


# ══════════════════════════════════════════════════════════════════════════════
# 3. FORMATEURS  →  import_reel_formateurs.xlsx
#    Feuille : "Formateurs"
#    Colonnes reconnues par import_excel._import_formateurs
# ══════════════════════════════════════════════════════════════════════════════
def gen_formateurs():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Formateurs'

    headers = [
        'Numéro',        # → numero       (UNIQUE, OBLIGATOIRE)
        'Nom',           # → nom          (OBLIGATOIRE)
        'Prénom',        # → prenom       (OBLIGATOIRE)
        'Email',         # → email
        'Téléphone',     # → telephone
        'Spécialité',    # → specialite
        'Organisation',  # → organisation
    ]
    widths = [15, 22, 22, 32, 16, 36, 36]
    set_headers(ws, headers, widths)

    rows = [
        ['FOR001', 'KOUASSI',  'Émile',        'emile.kouassi@exemple.ci',   '0701111001', 'Droit Public',              'Ministère de la Fonction Publique'],
        ['FOR002', 'TRAORE',   'Fatou',         'fatou.traore@exemple.ci',    '0702222002', 'Finances Publiques',        'Direction Générale du Budget'],
        ['FOR003', 'DIALLO',   'Mamadou Séga',  'mamadou.diallo@exemple.ci',  '0703333003', 'Management Public',         'CPFAE'],
        ['FOR004', 'N\'GUESSAN','Hervé',         'herve.nguessan@exemple.ci', '0704444004', 'Informatique Décisionnelle','ENAFOP'],
    ]
    for i, row in enumerate(rows, 2):
        add_row(ws, i, row)

    add_notes(ws, 8, 1, [
        "• Numéro      : identifiant UNIQUE et OBLIGATOIRE (ex: FOR001)",
        "• Si Numéro existe déjà → mise à jour des autres champs",
        "• Si Numéro absent → recherche par Nom + Prénom (insensible à la casse)",
        "• Spécialité  : domaine de compétence principal",
        "• Organisation: institution ou ministère d'appartenance",
    ])

    path = os.path.join(OUTPUT_DIR, 'import_reel_formateurs.xlsx')
    wb.save(path)
    print(f'  ✅ {path}')


# ══════════════════════════════════════════════════════════════════════════════
# 4. SÉANCES  →  import_reel_seances.xlsx
#    Deux feuilles :
#    • "Emploi du temps" → type=emploi_du_temps  (par titre formation)
#    • "Séances"         → type=seances           (par module_titre)
# ══════════════════════════════════════════════════════════════════════════════
def gen_seances():
    wb = openpyxl.Workbook()

    # ── Feuille 1 : Emploi du temps ──────────────────────────────────────────
    ws1 = wb.active
    ws1.title = 'Emploi du temps'

    h1 = ['Formation', 'Date', 'Numéro', 'Intitulé', 'Heure début', 'Heure fin', 'Auto-démarrage']
    w1 = [42, 14, 10, 20, 14, 14, 16]
    set_headers(ws1, h1, w1)

    rows1 = [
        ['FORMATION EN ADMINISTRATION DE BASE', date(2026, 5, 5),  1, 'Matin',      time(8, 30),  time(12, 0),  'Oui'],
        ['FORMATION EN ADMINISTRATION DE BASE', date(2026, 5, 5),  2, 'Après-midi', time(14, 0),  time(17, 30), 'Oui'],
        ['FORMATION EN ADMINISTRATION DE BASE', date(2026, 5, 6),  1, 'Matin',      time(8, 30),  time(12, 0),  'Oui'],
        ['FORMATION EN ADMINISTRATION DE BASE', date(2026, 5, 6),  2, 'Après-midi', time(14, 0),  time(17, 30), 'Oui'],
        ['FORMATION EN ADMINISTRATION DE BASE', date(2026, 5, 7),  1, 'Matin',      time(8, 30),  time(12, 0),  'Oui'],
        ['FORMATION EN ADMINISTRATION DE BASE', date(2026, 5, 7),  2, 'Après-midi', time(14, 0),  time(17, 30), 'Oui'],
        ['FORMATION SPECIALISEE EN GESTION',    date(2026, 7, 1),  1, 'Matin',      time(8, 30),  time(12, 0),  'Oui'],
        ['FORMATION SPECIALISEE EN GESTION',    date(2026, 7, 1),  2, 'Après-midi', time(14, 0),  time(17, 30), 'Oui'],
    ]
    for i, row in enumerate(rows1, 2):
        add_row(ws1, i, row)

    add_notes(ws1, 12, 1, [
        "• Formation       : titre EXACT de la formation telle qu'en base (champ 'formation')",
        "• Date            : format JJ/MM/AAAA ou AAAA-MM-JJ",
        "• Numéro          : ordre dans la journée (1=matin, 2=après-midi…) — OBLIGATOIRE",
        "• Intitulé        : libellé libre (optionnel). Ex: Matin, Après-midi, Module 3",
        "• Heure début/fin : format HH:MM (ex: 08:30). Obligatoire si Auto-démarrage=Oui",
        "• Auto-démarrage  : Oui / Non (défaut: Oui)",
        "• Utiliser type='emploi_du_temps' pour importer cette feuille",
    ])

    # ── Feuille 2 : Séances (par module) ────────────────────────────────────
    ws2 = wb.create_sheet(title='Séances')

    h2 = ['module_titre', 'grade', 'groupe', 'vague', 'date_journee', 'numero', 'intitule', 'heure_debut', 'heure_fin']
    w2 = [36, 10, 18, 22, 14, 10, 20, 14, 14]
    set_headers(ws2, h2, w2)

    rows2 = [
        ['Droit Administratif', 'A4', 'GROUPE 1', 'PREMIERE VAGUE', date(2026, 5, 5),  1, 'Matin',      time(8, 30),  time(12, 0)],
        ['Droit Administratif', 'A4', 'GROUPE 1', 'PREMIERE VAGUE', date(2026, 5, 5),  2, 'Après-midi', time(14, 0),  time(17, 30)],
        ['Droit Administratif', 'A4', 'GROUPE 2', 'PREMIERE VAGUE', date(2026, 5, 5),  1, 'Matin',      time(8, 30),  time(12, 0)],
        ['Droit Administratif', 'A4', 'GROUPE 2', 'PREMIERE VAGUE', date(2026, 5, 5),  2, 'Après-midi', time(14, 0),  time(17, 30)],
        ['Finances Publiques',  'B1', 'GROUPE 1', 'DEUXIEME VAGUE', date(2026, 6, 1),  1, 'Matin',      time(8, 30),  time(12, 0)],
        ['Finances Publiques',  'B1', 'GROUPE 1', 'DEUXIEME VAGUE', date(2026, 6, 1),  2, 'Après-midi', time(14, 0),  time(17, 30)],
        ['Management Public',   'A3', 'GROUPE 1', 'PREMIERE VAGUE', date(2026, 7, 1),  1, 'Matin',      time(8, 30),  time(12, 0)],
    ]
    for i, row in enumerate(rows2, 2):
        add_row(ws2, i, row)

    add_notes(ws2, 11, 1, [
        "• module_titre  : intitulé exact du Module (ex: Droit Administratif) — OBLIGATOIRE",
        "• grade         : grade du cours (ex: A4) — OBLIGATOIRE, doit correspondre à la feuille Formations",
        "• groupe        : GROUPE 1, GROUPE 2… — OBLIGATOIRE",
        "• vague         : PREMIERE VAGUE, DEUXIEME VAGUE… — OBLIGATOIRE",
        "• date_journee  : format JJ/MM/AAAA ou AAAA-MM-JJ",
        "• numero        : ordre de la séance dans la journée — OBLIGATOIRE",
        "• Utiliser type='seances' pour importer cette feuille",
    ])

    path = os.path.join(OUTPUT_DIR, 'import_reel_seances.xlsx')
    wb.save(path)
    print(f'  ✅ {path}')


if __name__ == '__main__':
    print('Génération des fichiers Excel d\'import...\n')
    gen_formations()
    gen_participants()
    gen_formateurs()
    gen_seances()
    print('\n✅ Terminé. 4 fichiers générés dans backend/')
