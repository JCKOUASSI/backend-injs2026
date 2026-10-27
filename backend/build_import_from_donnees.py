"""
Script manuel HORS RUNTIME Django (P00-05) : CLI opérateur
d'import/reprise — sorties print() de console volontaires ;
exclu du garde-fou check_repo_hygiene.
Génère les fichiers d'import réels depuis donnees
Fichiers sources :
  - FAB 2026 PHASE 1 FICHIER COMPLET.xlsx  → participants (22 feuilles de groupes)
  - Emploi du Temps *.xlsx                 → séances (emploi du temps)

Fichiers produits dans donnees/ :
  - import_participants_FAB2026.xlsx   → feuille "Participants"  (type=participants)
  - import_formations_FAB2026.xlsx     → feuille "Formations"    (type=formations)
  - import_seances_FAB2026.xlsx        → feuille "Emploi du temps" (type=emploi_du_temps)
"""
import openpyxl
import os, re
from datetime import datetime, date, time
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

SRC = 'donnees'
OUT = 'donnees'

# ── Styles ────────────────────────────────────────────────────────────────────
def _hs():
    return dict(
        font=Font(bold=True, color='FFFFFF', size=11),
        fill=PatternFill(start_color='1B3A5C', end_color='1B3A5C', fill_type='solid'),
        alignment=Alignment(horizontal='center', vertical='center', wrap_text=True),
        border=Border(left=Side(style='thin'), right=Side(style='thin'),
                      top=Side(style='thin'), bottom=Side(style='thin')),
    )
def _ds():
    return dict(
        alignment=Alignment(horizontal='left', vertical='center'),
        border=Border(left=Side(style='thin'), right=Side(style='thin'),
                      top=Side(style='thin'), bottom=Side(style='thin')),
    )
def apply(cell, styles):
    for k, v in styles.items(): setattr(cell, k, v)

def set_headers(ws, headers, widths):
    hs = _hs()
    for col, (title, w) in enumerate(zip(headers, widths), 1):
        c = ws.cell(row=1, column=col, value=title)
        apply(c, hs)
        ws.column_dimensions[get_column_letter(col)].width = w
    ws.row_dimensions[1].height = 22

def add_row(ws, row_num, values):
    ds = _ds()
    for col, val in enumerate(values, 1):
        c = ws.cell(row=row_num, column=col, value=val)
        apply(c, ds)

def clean(v):
    if v is None: return ''
    return str(v).strip().replace('\xa0', ' ').strip()

# ── Parsing dates/heures ──────────────────────────────────────────────────────
MONTHS_FR = {
    'JANVIER': 1, 'FEVRIER': 2, 'MARS': 3, 'AVRIL': 4,
    'MAI': 5, 'JUIN': 6, 'JUILLET': 7, 'AOUT': 8,
    'SEPTEMBRE': 9, 'OCTOBRE': 10, 'NOVEMBRE': 11, 'DECEMBRE': 12,
}

def parse_date_fr(s):
    """Parse '17 AVRIL 2026', 'VENDREDI 17 AVRIL 2026', etc."""
    if not s: return None
    s = clean(s).upper()
    # Retirer le jour de la semaine
    s = re.sub(r'^(LUNDI|MARDI|MERCREDI|JEUDI|VENDREDI|SAMEDI|DIMANCHE)\s*', '', s).strip()
    # Format: DD MOIS YYYY
    m = re.match(r'(\d{1,2})\s+(\w+)\s+(\d{4})', s)
    if m:
        day, month_str, year = int(m.group(1)), m.group(2), int(m.group(3))
        month = MONTHS_FR.get(month_str.upper())
        if month:
            try: return date(year, month, day)
            except: return None
    return None

def parse_time_fr(s):
    """Parse '08 H-12 H', '08H-12H', '8H-12H' → (start, end) ou une seule heure."""
    if not s: return None, None
    s = clean(s).upper().replace(' ', '')
    # Format: 8H-12H ou 08H-12H ou 8H30-12H
    m = re.match(r'(\d{1,2})H(\d{0,2})-(\d{1,2})H(\d{0,2})', s)
    if m:
        h1, m1, h2, m2 = m.group(1), m.group(2) or '0', m.group(3), m.group(4) or '0'
        try:
            return time(int(h1), int(m1)), time(int(h2), int(m2))
        except: return None, None
    return None, None

# ══════════════════════════════════════════════════════════════════════════════
# 1. FORMATIONS → 1 ligne par groupe × module réel extrait des EDT
# ══════════════════════════════════════════════════════════════════════════════

# Modules réels extraits des fichiers EDT (filtrés manuellement)
MODULES_REELS = [
    ('CULTURE CIVIQUE',                              16),
    ('DEONTOLOGIE',                                  8),
    ('DROIT ADMINISTRATIF',                          20),
    ('ETHIQUE PUBLIQUE ET LUTTE CONTRE LA CORRUPTION', 8),
    ('FINANCES PUBLIQUES',                           16),
    ('GESTION DU BUDGET FAMILIAL',                   8),
    ('MANAGEMENT DES ADMINISTRATIONS PUBLIQUES',     16),
    ('PROTOCOLE ET SAVOIR-VIVRE',                    16),
    ('REDACTION ADMINISTRATIVE',                     16),
    ('SIGFAE',                                       12),
    ('TECHNIQUES ADMINISTRATIVES',                   16),
    ('TELETRAVAIL',                                  8),
]

# Dates par grade
DATE_MAP = {
    'A4': (datetime(2026, 4, 17, 8, 0), datetime(2026, 5, 30, 17, 0)),
    'A3': (datetime(2026, 4, 17, 8, 0), datetime(2026, 5, 30, 17, 0)),
    'B3': (datetime(2026, 4, 19, 8, 0), datetime(2026, 5, 25, 17, 0)),
}

def build_formations():
    """
    Génère 1 ligne par groupe × module.
    Collecte les groupes depuis FAB COMPLET, croise avec MODULES_REELS.
    """
    wb_src = openpyxl.load_workbook(
        os.path.join(SRC, 'FAB 2026 PHASE 1 FICHIER COMPLET.xlsx'),
        read_only=True, data_only=True,
    )

    formations_seen = {}  # (grade, groupe) -> dict
    skip_sheets = ('TCD', 'RECAP')

    for shname in wb_src.sheetnames:
        if shname in skip_sheets:
            continue
        ws = wb_src[shname]
        rows = list(ws.iter_rows(values_only=True, max_row=3))
        if len(rows) < 2:
            continue
        row = rows[1]
        if not row or all(v is None for v in row):
            continue

        headers = [clean(h) for h in rows[0]]
        def get(col_name):
            for i, h in enumerate(headers):
                if col_name.lower() in h.lower() and i < len(row):
                    return clean(row[i])
            return ''

        categorie = get("CATEGORIE")
        grade     = get("GRADE")
        groupe    = get("GROUPE")
        site      = get("SITE")
        salle     = get("SALLE")

        key = (grade, groupe)
        if key not in formations_seen:
            formations_seen[key] = {
                'categorie': categorie,
                'grade': grade,
                'groupe': groupe,
                'site': site,
                'salle': salle,
            }

    wb_src.close()

    FORMATION_TITLE = "FORMATION EN ADMINISTRATION DE BASE SESSION 2026"

    formation_rows = []
    for key in sorted(formations_seen.keys()):
        f    = formations_seen[key]
        grade = f['grade']
        groupe_norm = re.sub(r'\s+', ' ', f['groupe']).strip().upper()
        date_d, date_f = DATE_MAP.get(grade, DATE_MAP['A4'])

        for module_titre, duree in MODULES_REELS:
            formation_rows.append([
                FORMATION_TITLE,   # Formation (cycle)
                module_titre,      # Module (titre) — réel
                None,              # N° (optionnel)
                f['categorie'],    # Catégorie
                grade,             # Grade
                groupe_norm,       # Groupe
                'PREMIERE VAGUE',  # Vague
                'CPFAE-AGC',       # Lieu
                '',                # Bâtiment
                f['salle'],        # Salle
                date_d,            # Date début
                date_f,            # Date fin
                duree,             # Volume horaire (h)
            ])

    wb_out = openpyxl.Workbook()
    ws_out = wb_out.active
    ws_out.title = 'Formations'

    headers = ['Formation', 'Module (titre)', 'N°', 'Catégorie', 'Grade', 'Groupe',
               'Vague', 'Lieu', 'Bâtiment', 'Salle', 'Date début', 'Date fin', 'Volume horaire (h)']
    widths  = [52, 48, 6, 12, 10, 18, 20, 18, 16, 30, 22, 22, 18]
    set_headers(ws_out, headers, widths)

    for i, row in enumerate(formation_rows, 2):
        add_row(ws_out, i, row)

    path = os.path.join(OUT, 'import_formations_FAB2026.xlsx')
    wb_out.save(path)
    print(f'  ✅ {len(formation_rows)} lignes ({len(formations_seen)} groupes × {len(MODULES_REELS)} modules) → {path}')
    return formation_rows


# ══════════════════════════════════════════════════════════════════════════════
# 2. PARTICIPANTS → depuis FAB 2026 PHASE 1 FICHIER COMPLET (feuilles A4-x, A3-x, B3-x)
# ══════════════════════════════════════════════════════════════════════════════
def build_participants():
    wb_src = openpyxl.load_workbook(
        os.path.join(SRC, 'FAB 2026 PHASE 1 FICHIER COMPLET.xlsx'),
        read_only=True, data_only=True,
    )

    FORMATION_TITLE = "FORMATION EN ADMINISTRATION DE BASE SESSION 2026"
    all_participants = []
    seen_matricules = set()

    skip_sheets = ('TCD', 'RECAP')
    for shname in wb_src.sheetnames:
        if shname in skip_sheets:
            continue
        ws = wb_src[shname]
        rows_iter = ws.iter_rows(values_only=True)
        header_row = next(rows_iter, None)
        if not header_row:
            continue

        # Normaliser headers
        headers = [clean(h).upper().replace('\n', ' ') for h in header_row]

        def col_idx(patterns):
            for i, h in enumerate(headers):
                for p in patterns:
                    if p.upper() in h:
                        return i
            return None

        idx_n        = col_idx(["N° D'INSCRIPTION", "N°D'INSCRIPTION", "FNCP", "INSCRIPTION"])
        idx_nom      = col_idx(["NOM"])
        idx_prenom   = col_idx(["PRENOMS", "PRENOM"])
        idx_genre    = col_idx(["GENRE", "SEXE"])
        idx_dnaiss   = col_idx(["DATE DE NAISSANCE", "DATE_NAISSANCE"])
        idx_lnaiss   = col_idx(["LIEU DE NAISSANCE", "LIEU_NAISSANCE"])
        idx_tel1     = col_idx(["TELEPHONE 1", "TEL1", "TELEPHONE1"])
        idx_tel2     = col_idx(["TELEPHONE 2", "TEL2", "TELEPHONE2"])
        idx_type_c   = col_idx(["TYPE_CONCOURS", "TYPE CONCOURS"])
        idx_lib_c    = col_idx(["LIBELLE CONCOURS", "LIBELLE_CONCOURS"])
        idx_cat      = col_idx(["CATEGORIE"])
        idx_grade    = col_idx(["GRADE"])
        idx_groupe   = col_idx(["GROUPE"])
        idx_gg       = col_idx(["GRADE-GROUPE", "GRADE_GROUPE", "GRADE/GROUPE"])
        def g(row, idx):
            if idx is None or idx >= len(row): return ''
            v = row[idx]
            if v is None: return ''
            s = str(v).strip().replace('\xa0', ' ').strip()
            # Nettoyer les datetime Excel
            if 'datetime' in type(v).__name__.lower() or hasattr(v, 'year'):
                return v  # garder l'objet date pour le formatage
            return s

        for row in rows_iter:
            if not row or all(v is None for v in row):
                continue
            # Vérifier qu'on a au moins un matricule
            matricule = clean(g(row, idx_n))
            if not matricule or matricule == '':
                continue
            # Dédupliquer par matricule
            if matricule in seen_matricules:
                continue
            seen_matricules.add(matricule)

            # Normaliser sexe
            genre = clean(g(row, idx_genre)).upper()
            if genre in ('M', 'MASCULIN', 'H', 'HOMME'): genre = 'MASCULIN'
            elif genre in ('F', 'FEMININ', 'FÉMININ', 'FEMME'): genre = 'FEMININ'

            # Date de naissance
            dnaiss = g(row, idx_dnaiss)
            if hasattr(dnaiss, 'date'):
                dnaiss = dnaiss.date() if callable(dnaiss.date) else dnaiss.date
            elif isinstance(dnaiss, str) and dnaiss:
                for fmt in ('%Y-%m-%d', '%d/%m/%Y'):
                    try:
                        dnaiss = datetime.strptime(dnaiss.split(' ')[0], fmt).date()
                        break
                    except:
                        pass
            elif hasattr(dnaiss, 'year'):
                pass  # déjà date
            else:
                dnaiss = None

            groupe_raw = clean(g(row, idx_groupe)).upper()
            groupe_norm = re.sub(r'\s+', ' ', groupe_raw).strip()

            all_participants.append([
                matricule,                          # N° d'inscription
                clean(g(row, idx_nom)).upper(),     # Nom
                clean(g(row, idx_prenom)),          # Prénom
                genre,                              # Sexe
                dnaiss,                             # Date naissance
                clean(g(row, idx_lnaiss)),          # Lieu naissance
                clean(g(row, idx_cat)).upper(),     # Catégorie
                clean(g(row, idx_grade)).upper(),   # Grade
                clean(g(row, idx_gg)).upper(),      # Grade/Groupe
                groupe_norm,                        # Groupe
                'PREMIERE VAGUE',                   # Vague
                clean(g(row, idx_type_c)),          # Type concours
                clean(g(row, idx_lib_c)),           # Libelle concours
                '',                                 # Email
                clean(g(row, idx_tel1)),            # Téléphone 1
                clean(g(row, idx_tel2)),            # Téléphone 2
                FORMATION_TITLE,                    # Formation(s)
            ])

    wb_src.close()

    # Écrire
    wb_out = openpyxl.Workbook()
    ws_out = wb_out.active
    ws_out.title = 'Participants'

    headers_out = [
        "N° d'inscription", 'Nom', 'Prénom', 'Sexe', 'Date de naissance',
        'Lieu de naissance', 'Catégorie', 'Grade', 'Grade/Groupe', 'Groupe',
        'Vague', 'Type concours', 'Libelle concours', 'Email',
        'Téléphone 1', 'Téléphone 2', 'Formation(s)',
    ]
    widths_out = [20, 22, 28, 12, 18, 28, 12, 10, 18, 16, 20, 30, 45, 28, 15, 15, 55]
    set_headers(ws_out, headers_out, widths_out)

    for i, row in enumerate(all_participants, 2):
        add_row(ws_out, i, row)

    path = os.path.join(OUT, 'import_participants_FAB2026.xlsx')
    wb_out.save(path)
    print(f'  ✅ {len(all_participants)} participants uniques → {path}')


# ══════════════════════════════════════════════════════════════════════════════
# 3. SÉANCES → depuis les fichiers Emploi du Temps *.xlsx
#    Type d'import : seances  (module_titre + groupe + grade + vague)
#    1 séance = 1 module × 1 groupe × 1 grade × 1 date × numéro
# ══════════════════════════════════════════════════════════════════════════════

JOURS_FR = ('LUNDI','MARDI','MERCREDI','JEUDI','VENDREDI','SAMEDI','DIMANCHE')
MOIS_BRUIT = ('JANVIER','FEVRIER','MARS','AVRIL','MAI','JUIN','JUILLET',
               'AOUT','SEPTEMBRE','OCTOBRE','NOVEMBRE','DECEMBRE')

def is_noise_cell(v):
    v = str(v).upper().strip().replace('\xa0','')
    if not v or len(v) < 3: return True
    if any(j in v for j in JOURS_FR): return True
    if any(m in v for m in MOIS_BRUIT): return True
    if re.match(r'^\d+\s*H', v): return True
    if any(k in v for k in ('MINISTERE','DIRECTION','CENTRE DE PERFECTION',
                             'REPUBLIQUE','UNION','FORMATION EN','EMPLOI DU TEMPS',
                             'MATIERES','DU MODULE','RESTANT','FORMATEUR',
                             'SITE','GROUPE','CPFAE','BATIMENT','SALLE',
                             'PERIODE','HORAIRE','VOLUME','FONCTION PUBLIQUE',
                             'RENFORCEMENT','MODERNISATION','AMADOU','--------',
                             'AGC','DNFP','DFRC')): return True
    return False

def parse_edt_sheet(ws, sheet_grade_hint=''):
    """
    Extrait les séances d'une feuille EDT avec grade, groupe et toutes les matières.
    sheet_grade_hint : grade déduit du nom du fichier source (ex: 'B3')
    Retourne : (grade, groupe, [ {module, date, numero, heure_debut, heure_fin} ])
    """
    all_rows = list(ws.iter_rows(values_only=True))

    grade_str = groupe_str = ''
    header_row_idx = None
    col_offset = 0  # colonne où commence MATIERES (décalage)

    for i, row in enumerate(all_rows):
        vals = [clean(v) for v in row]
        full = ' '.join(vals).upper()

        if not grade_str:
            for v in vals:
                if 'EMPLOI DU TEMPS' in v.upper() and ('GRADE' in v.upper() or 'CATEGORIE' in v.upper()):
                    grade_str = v.upper()
                    break
            if not grade_str and 'EMPLOI DU TEMPS' in full and ('GRADE' in full or 'CATEGORIE' in full):
                grade_str = full

        if not groupe_str:
            for v in vals:
                if re.search(r'GROUPE\s*[:\s]*0*\d+', v.upper()):
                    groupe_str = v.strip()
                    break

        if 'MATIERES' in full:
            header_row_idx = i
            # Détecter le décalage : colonne où est "MATIERES"
            for ci, v in enumerate(vals):
                if 'MATIERES' in v.upper():
                    col_offset = ci
                    break
            break

    # Extraire grade
    grade = ''
    m = re.search(r'GRADE\s+([A-Z]\d)', grade_str.upper())
    if m:
        grade = m.group(1)

    if not grade:
        m2 = re.search(r'([A-Z]\d)\s*[-/]?\s*GROUPE', groupe_str.upper())
        if m2: grade = m2.group(1)

    if not grade and 'CATEGORIE B' in grade_str.upper():
        grade = 'B3'
    if not grade and 'CATEGORIE A' in grade_str.upper():
        m_a = re.search(r'A(\d)', grade_str.upper())
        if m_a: grade = f'A{m_a.group(1)}'
    if not grade and sheet_grade_hint:
        grade = sheet_grade_hint

    # Normaliser groupe
    groupe = ''
    m3 = re.search(r'GROUPE\s*[:\s]*0*(\d+)', groupe_str.upper())
    if m3:
        groupe = f'GROUPE {int(m3.group(1))}'

    if header_row_idx is None:
        return grade, groupe, []

    # Sauter ligne de continuation "DU MODULE | RESTANT..."
    data_start = header_row_idx + 1
    if data_start < len(all_rows):
        nv = [clean(v).upper() for v in all_rows[data_start]]
        if any('DU MODULE' in v or 'RESTANT' in v for v in nv):
            data_start += 1

    seances = []
    current_module = ''
    date_numero = {}

    for row in all_rows[data_start:]:
        # Appliquer le décalage : lire à partir de col_offset
        vals_full = [clean(v) for v in row]
        vals = vals_full[col_offset:] if col_offset < len(vals_full) else vals_full
        non_empty = [v for v in vals if v]
        if not non_empty:
            continue

        full = ' '.join(non_empty).upper()
        if any(k in full for k in ('MINISTERE','MATIERES','EMPLOI DU TEMPS',
                                    'DU MODULE','RESTANT','DIRECTION GENERALE',
                                    'DIRECTION DE LA FORMATION','CENTRE DE PERFECTION',
                                    'FONCTION PUBLIQUE','RENFORCEMENT DES CAP')):
            continue

        # Détecter un nouveau module (col 0 après décalage)
        first = vals[0] if vals else ''
        # Ignorer si c'est un volume horaire seul (ex: "16 H")
        if first and not is_noise_cell(first) and not re.match(r'^\d+\s*H?\s*$', first.upper()):
            current_module = first.strip()
            if re.match(r'SIGFAE\s+ET\b', current_module.upper()): current_module = 'SIGFAE'
            date_numero = {}

        if not current_module:
            continue

        # Chercher date(s) et horaire dans la ligne
        for v in non_empty:
            d = parse_date_fr(v)
            if not d:
                continue
            horaire = None
            for hv in non_empty:
                if re.search(r'\d{1,2}\s*H\s*[-–]\s*\d{1,2}\s*H', hv.upper()):
                    horaire = hv
                    break
            h_deb, h_fin = parse_time_fr(horaire) if horaire else (None, None)
            key = (current_module, str(d))
            date_numero[key] = date_numero.get(key, 0) + 1
            seances.append({
                'module':      current_module,
                'date':        d,
                'numero':      date_numero[key],
                'heure_debut': h_deb,
                'heure_fin':   h_fin,
            })

    return grade, groupe, seances


def build_seances():
    edt_files = [f for f in os.listdir(SRC) if 'Emploi' in f and f.endswith('.xlsx')]
    FORMATION_TITLE = "FORMATION EN ADMINISTRATION DE BASE SESSION 2026"
    VAGUE = "PREMIERE VAGUE"

    all_rows = []

    for fname in sorted(edt_files):
        path = os.path.join(SRC, fname)
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        # Déduire grade hint depuis le nom du fichier
        grade_hint = ''
        m_hint = re.search(r'\b(A3|A4|B3|B4|C1)\b', fname.upper())
        if m_hint: grade_hint = m_hint.group(1)

        for shname in wb.sheetnames:
            ws = wb[shname]
            grade, groupe, seances = parse_edt_sheet(ws, sheet_grade_hint=grade_hint)

            if not grade or not groupe:
                continue

            for s in seances:
                all_rows.append([
                    s['module'],       # module_titre  → clé principale
                    s['date'],         # date_journee
                    s['numero'],       # numero
                    s['module'],       # intitule (= module par défaut)
                    s['heure_debut'],  # heure_debut
                    s['heure_fin'],    # heure_fin
                    groupe,            # groupe  → filtre
                    grade,             # grade   → filtre
                    VAGUE,             # vague   → filtre
                ])

        wb.close()

    # Dédupliquer : (module, date, numero, groupe, grade)
    seen = set()
    dedup = []
    for row in all_rows:
        key = (row[0], str(row[1]), row[2], row[6], row[7])
        if key not in seen:
            seen.add(key)
            dedup.append(row)

    # Trier par grade, groupe, module, date, numéro
    dedup.sort(key=lambda r: (str(r[7]), str(r[6]), str(r[0]), str(r[1]), r[2]))

    # Écrire
    wb_out = openpyxl.Workbook()
    ws_out = wb_out.active
    ws_out.title = 'Séances'

    headers = ['module_titre', 'date_journee', 'numero', 'intitule',
               'heure_debut', 'heure_fin', 'groupe', 'grade', 'vague']
    widths  = [50, 14, 10, 50, 14, 14, 16, 10, 20]
    set_headers(ws_out, headers, widths)

    for i, row in enumerate(dedup, 2):
        add_row(ws_out, i, row)

    path = os.path.join(OUT, 'import_seances_FAB2026.xlsx')
    wb_out.save(path)

    # Stats
    grades_found = sorted(set(r[7] for r in dedup))
    for g in grades_found:
        groupes = sorted(set(r[6] for r in dedup if r[7] == g))
        modules = sorted(set(r[0] for r in dedup if r[7] == g))
        nb = sum(1 for r in dedup if r[7] == g)
        print(f'    Grade {g}: {len(groupes)} groupes × {len(modules)} modules = {nb} séances')
    print(f'  ✅ {len(dedup)} séances total → {path}')
    print(f'     (type=seances, colonnes: module_titre + groupe + grade + vague)')


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════
if __name__ == '__main__':
    print('Génération des fichiers d\'import réels depuis les données sources...\n')
    print('1. Formations...')
    build_formations()
    print('2. Participants...')
    build_participants()
    print('3. Séances (emploi du temps)...')
    build_seances()
    print('\n✅ Terminé. 3 fichiers générés dans :', OUT)
    print('\nOrdre d\'import recommandé :')
    print('  1. import_formations_FAB2026.xlsx   → type=formations')
    print('  2. import_participants_FAB2026.xlsx → type=participants')
    print('  3. import_seances_FAB2026.xlsx      → type=emploi_du_temps')
