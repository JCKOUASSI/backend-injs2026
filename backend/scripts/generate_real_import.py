"""
Script manuel HORS RUNTIME Django (P00-05) : CLI opérateur
d'import/reprise — sorties print() de console volontaires ;
exclu du garde-fou check_repo_hygiene.
Génère import_formations_reel.xlsx et import_seances_reel.xlsx
en parsant directement les fichiers réels Emploi du Temps A4.

Groupes alignés sur le vrai fichier participants FAB 2026 :
  GROUPE 1, GROUPE 2 ... GROUPE 8  (sans zéro)

Fichiers sources :
  ~/Downloads/Emploi du Temps A4_GROUPES 1, GROUPE 2, GROUPE 3.xlsx
  ~/Downloads/Emploi du Temps A4_GROUPE 4, GROUPE 5, GROUPE 6.xlsx
"""
import os, re
from datetime import date, time, datetime, timedelta
from collections import defaultdict

try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
except ImportError:
    raise SystemExit("openpyxl requis : pip install openpyxl")

OUT_DIR = os.path.join(os.path.dirname(__file__), '..')

# ─── Fichiers EDT sources ─────────────────────────────────────────────────────
HOME = os.path.expanduser('~')
_D = os.path.join(HOME, 'Downloads', 'données')
EDT_FILES = [
    # Nouveaux fichiers V2 : format tabulaire propre avec colonnes
    # MATIERES / Grade / Groupe / VOLUME HORAIRE DU MODULE / Site / BATIMENT / SALLE / PERIODE / HORAIRE DU COURS / ...
    (os.path.join(_D, 'Emploi du Temps  A4_GR1 A GR08 _V2.xlsx'), None, 'A4'),
    (os.path.join(_D, 'Emploi du Temps A3_GR1 A GR10 V2.xlsx'),   None, 'A3'),
    (os.path.join(_D, 'Emploi du Temps B3 GROUPE 1-GROUPE  2-GROUPE  3 V2.xlsx'), None, 'B3'),
]

MOIS = {
    'JANVIER': 1, 'FEVRIER': 2, 'MARS': 3, 'AVRIL': 4,
    'MAI': 5, 'JUIN': 6, 'JUILLET': 7, 'AOUT': 8,
    'SEPTEMBRE': 9, 'OCTOBRE': 10, 'NOVEMBRE': 11, 'DECEMBRE': 12,
}

IGNORE_PREFIXES = (
    'MATIERES', 'MINISTERE', 'DIRECTION', 'CENTRE', 'FORMATION EN',
    'EMPLOI DU TEMPS', 'HORAIRE', 'BATIMENT', 'FORMATEURS', 'VOLUME',
    'SALLE', 'PERIODE', 'DU MODULE', 'RESTANT', '----------',
    'DE LA', 'DU RENFOR', 'ET DU', 'ET AGENTS', 'GRADE', 'SITE',
    'ET DE LA', 'LA FONCT', 'DE LA MODERN',
)

OBJECTIFS = {
    'Culture Civique': 'Renforcer la culture civique et institutionnelle',
    'Protocole Et Savoir-Vivre': 'Maîtriser les règles de protocole et de savoir-vivre',
    'Management Des Administrations Publiques': 'Développer les capacités managériales des agents publics',
    'Gestion Du Budget Familial': 'Gérer son budget personnel et se préparer à la retraite',
    'Droit Administratif': "Connaître le cadre juridique de l'administration publique",
    'Deontologie': 'Intégrer les valeurs déontologiques de la fonction publique',
    'Sigfae Et Teletravail': "Maîtriser les outils numériques de l'administration",
    'Sigfae Et Outils Collaboratifs Et Teletravail': "Maîtriser les outils numériques de l'administration",
    'Ethique Publique Et Lutte Contre La Corruption': "Promouvoir l'éthique et lutter contre la corruption",
    'Redaction Administrative': 'Maîtriser la rédaction des actes et documents administratifs',
    'Finances Publiques': 'Comprendre les mécanismes des finances publiques',
}


def _parse_date_fr(s):
    s = str(s).upper().strip()
    # retirer le jour de la semaine en préfixe (LUNDI, MARDI, …)
    s = re.sub(r'^(LUNDI|MARDI|MERCREDI|JEUDI|VENDREDI|SAMEDI|DIMANCHE)\s+', '', s)
    m = re.search(r'(\d{1,2})\s+(\w+)\s+(\d{4})', s)
    if m:
        d, mo, y = int(m.group(1)), MOIS.get(m.group(2), 0), int(m.group(3))
        if mo:
            return datetime(y, mo, d).date()
    return None


def _parse_heure(s):
    s = str(s).upper().replace(' ', '').replace('\xa0', '')
    m = re.match(r'0*(\d{1,2})H[-\u2013]0*(\d{1,2})H?', s)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None


def _parse_vol(s):
    if not s:
        return None
    m = re.search(r'(\d+)', str(s))
    return int(m.group(1)) if m else None


def _is_module_title(val):
    if not val:
        return False
    v = str(val).strip().upper()
    if len(v) < 4:
        return False
    if any(v.startswith(k) for k in IGNORE_PREFIXES):
        return False
    if not re.search(r'[A-Z]', v):
        return False
    if re.search(r'\d{4}', v):
        return False
    if re.match(r'^[\d\s H]+$', v):
        return False
    return True


def _normalize_module_title(raw):
    """Normalise un titre de module (title case + fusion SIGFAE)."""
    if not raw:
        return None
    v = str(raw).strip()
    if not v:
        return None
    u = v.upper()
    if 'SIGFAE' in u and ('TELETRAVAIL' in u or 'COLLABOR' in u):
        return 'Sigfae Et Outils Collaboratifs Et Teletravail'
    if 'SIGFAE' in u:
        return 'Sigfae Et Outils Collaboratifs Et Teletravail'
    return v.title()


def _parse_edt_sheet(ws):
    """Parse une feuille EDT (format V2 tabulaire) →
    liste de (groupe_int, module_titre, vol_h, date, h_debut, h_fin, site, batiment, salle).

    Format attendu : une ligne d'en-têtes contenant
      MATIERES | Grade | Groupe | VOLUME HORAIRE DU MODULE | Site | BATIMENT | SALLE |
      PERIODE | HORAIRE DU COURS | VOLUME HORAIRE RESTANT ... | FORMATEURS
    suivie de lignes de séances (une par demi-journée).
    La colonne MATIERES peut être vide sur les lignes suivantes (même module) → forward-fill.
    """
    rows = list(ws.iter_rows(values_only=True))
    result = []

    # 1. Localiser la ligne d'en-tête (celle qui contient MATIERES + SALLE)
    header_idx = None
    for ri, row in enumerate(rows):
        vals = [str(v).upper().strip() if v else '' for v in row]
        if 'MATIERES' in vals and 'SALLE' in vals:
            header_idx = ri
            break
    if header_idx is None:
        return result

    headers = [str(v).strip().upper() if v else '' for v in rows[header_idx]]

    def _col(*names):
        for n in names:
            if n in headers:
                return headers.index(n)
        return None

    col_mat    = _col('MATIERES')
    col_grade  = _col('GRADE')
    col_groupe = _col('GROUPE')
    col_vol    = _col('VOLUME HORAIRE DU MODULE')
    col_site   = _col('SITE')
    col_bat    = _col('BATIMENT', 'BÂTIMENT')
    col_salle  = _col('SALLE')
    col_date   = _col('PERIODE')
    col_heure  = _col('HORAIRE DU COURS')

    if col_mat is None or col_date is None or col_heure is None:
        return result

    cur_module = None
    cur_vol    = None
    cur_site   = ''
    cur_bat    = ''
    cur_salle  = ''

    for ri in range(header_idx + 1, len(rows)):
        row = list(rows[ri]) + [None] * 20
        mat_val = row[col_mat]
        if mat_val and str(mat_val).strip():
            norm = _normalize_module_title(mat_val)
            if norm:
                cur_module = norm
                cur_vol = _parse_vol(row[col_vol]) if col_vol is not None else None

        # Site/Bâtiment/Salle : forward-fill si vide
        if col_site  is not None and row[col_site]  and str(row[col_site]).strip():
            cur_site = str(row[col_site]).strip()
        if col_bat   is not None and row[col_bat]   and str(row[col_bat]).strip():
            cur_bat = str(row[col_bat]).strip()
        if col_salle is not None and row[col_salle] and str(row[col_salle]).strip():
            cur_salle = str(row[col_salle]).strip()

        # Groupe : préférer la valeur de ligne, sinon déduire du nom de feuille
        groupe_int = None
        if col_groupe is not None and row[col_groupe]:
            m = re.search(r'0*(\d+)', str(row[col_groupe]))
            if m:
                groupe_int = int(m.group(1))
        if groupe_int is None:
            m = re.search(r'G0*(\d+)$', ws.title.upper())
            if m:
                groupe_int = int(m.group(1))

        date_val  = row[col_date]
        heure_val = row[col_heure]
        if cur_module and date_val and heure_val and groupe_int:
            d = _parse_date_fr(str(date_val))
            h = _parse_heure(str(heure_val))
            if d and h:
                result.append((groupe_int, cur_module, cur_vol, d, h[0], h[1],
                               cur_site, cur_bat, cur_salle))
    return result


def _normalize_groupe(sheet_name, groupe_int):
    """Normalise le nom de groupe vers 'GROUPE N' pour matcher les participants."""
    return f'GROUPE {groupe_int}'


def _grade_to_cat(grade):
    """Retourne le libelle RefTypeSecretariat correspondant au grade."""
    g = grade.upper()
    if g.startswith('B'):
        return 'FAB B'
    if g.startswith('A'):
        return 'FAB A'
    return 'FAB C'


def _parse_all_edt():
    """Retourne {(grade, groupe_int, module_titre): {'vol': int, 'cat': str, 'seances': [(date,hd,hf)]}}"""
    by_gm = defaultdict(lambda: {'vol': None, 'cat': 'FAB A', 'seances': [],
                                   'site': '', 'bat': '', 'salle': ''})
    for fpath, sheets, grade in EDT_FILES:
        cat = _grade_to_cat(grade)
        if not os.path.exists(fpath):
            print(f'  \u26a0\ufe0f  Fichier introuvable : {fpath}')
            continue
        wb = openpyxl.load_workbook(fpath, read_only=True, data_only=True)
        # Si sheets=None, prendre toutes les feuilles du fichier
        sheet_list = sheets if sheets is not None else wb.sheetnames
        for sname in sheet_list:
            if sname not in wb.sheetnames:
                print(f'  \u26a0\ufe0f  Feuille {sname!r} introuvable dans {os.path.basename(fpath)}')
                continue
            ws = wb[sname]
            data = _parse_edt_sheet(ws)
            if not data:
                print(f'    ↳ {sname!r} : 0 séances parsées (feuille vide ou format non reconnu)')
                continue
            print(f'    ↳ {sname!r} (grade={grade}) : {len(data)} séances extraites')
            for tup in data:
                g, mod, vol, d, hd, hf, site, bat, salle = tup
                g_norm = _normalize_groupe(sname, g)
                key = (grade, g_norm, mod)
                by_gm[key]['cat'] = cat
                if vol:
                    by_gm[key]['vol'] = vol
                if site:  by_gm[key]['site']  = site
                if bat:   by_gm[key]['bat']   = bat
                if salle: by_gm[key]['salle'] = salle
                by_gm[key]['seances'].append((d, hd, hf))
        wb.close()
    return by_gm


def _build_formations_and_seances():
    by_gm = _parse_all_edt()
    formations = []
    seances = []
    num = 1

    for (grade, g, mod), info in sorted(by_gm.items()):
        ses = sorted(info['seances'], key=lambda x: (x[0], x[1]))
        if not ses:
            continue
        date_debut = ses[0][0]
        date_fin = ses[-1][0]
        vol = info['vol'] or 0
        cat = info['cat']
        groupe_str = g  # already normalized to 'GROUPE N'
        objectif = OBJECTIFS.get(mod, f'Formation en {mod}')

        formations.append((
            num, mod, objectif, info.get('site') or 'CPFAE',
            info.get('bat') or '', info.get('salle') or '',
            datetime(date_debut.year, date_debut.month, date_debut.day, 8, 0),
            datetime(date_fin.year, date_fin.month, date_fin.day, 17, 0),
            vol, cat, grade, groupe_str, 'SESSION 2026', ''
        ))

        for i, (d, hd, hf) in enumerate(ses, 1):
            intitule = 'Matin' if hd < 12 else 'Après-midi'
            seances.append((mod, grade, groupe_str, d, i,
                            intitule, time(hd, 0), time(hf, 0)))
        num += 1

    return formations, seances


FORMATIONS_STAT = [
    # fallback si fichiers EDT absents — vide intentionnellement
]


def _get_data():
    f, s = _build_formations_and_seances()
    if not f:
        print('⚠️  Aucun fichier EDT trouvé, données statiques utilisées.')
        return FORMATIONS_STAT, []
    return f, s


# ─── DEAD CODE KEPT FOR REFERENCE ─────────────────────────────────────────────
# Les listes statiques FORMATIONS / SEANCES ci-dessous sont remplacées
# par _build_formations_and_seances() — voir _get_data()
FORMATIONS = [
    # ── GROUPE 01 ──────────────────────────────────────────────────────────────
    (1,  'Culture Civique',
         'Renforcer la culture civique et institutionnelle',
         'CPFAE-AGC', '2026-04-13 08:00', '2026-04-14 17:00', 16,
         'A', 'A4', 'GROUPE 01', 'SESSION 2026', ''),

    (2,  'Protocole Et Savoir-Vivre',
         'Maîtriser les règles de protocole et de savoir vivre',
         'CPFAE-AGC', '2026-04-15 08:00', '2026-04-16 17:00', 16,
         'A', 'A4', 'GROUPE 01', 'SESSION 2026', ''),

    (3,  'Management Des Administrations Publiques',
         'Développer les capacités managériales des agents publics',
         'CPFAE-AGC', '2026-05-04 08:00', '2026-05-07 17:00', 30,
         'A', 'A4', 'GROUPE 01', 'SESSION 2026', ''),

    (4,  'Gestion Du Budget Familial',
         'Gérer son budget personnel et se préparer à la retraite',
         'CPFAE-AGC', '2026-05-08 08:00', '2026-05-09 17:00', 16,
         'A', 'A4', 'GROUPE 01', 'SESSION 2026', ''),

    (5,  'Droit Administratif',
         'Connaître le cadre juridique de l\'administration publique',
         'CPFAE-AGC', '2026-05-11 08:00', '2026-05-15 17:00', 30,
         'A', 'A4', 'GROUPE 01', 'SESSION 2026', ''),

    (6,  'Déontologie',
         'Intégrer les valeurs déontologiques de la fonction publique',
         'CPFAE-AGC', '2026-05-16 08:00', '2026-05-20 17:00', 30,
         'A', 'A4', 'GROUPE 01', 'SESSION 2026', ''),

    (7,  'Sigfae Et Outils Collaboratifs Et Teletravail',
         'Maîtriser les outils numériques de l\'administration',
         'CPFAE-AGC', '2026-05-21 08:00', '2026-05-23 17:00', 30,
         'A', 'A4', 'GROUPE 01', 'SESSION 2026', ''),

    (8,  'Ethique Publique Et Lutte Contre La Corruption',
         'Promouvoir l\'éthique et lutter contre la corruption',
         'CPFAE-AGC', '2026-05-26 08:00', '2026-05-28 17:00', 20,
         'A', 'A4', 'GROUPE 01', 'SESSION 2026', ''),

    (9,  'Redaction Administrative',
         'Maîtriser la rédaction des actes et documents administratifs',
         'CPFAE-AGC', '2026-05-29 08:00', '2026-06-02 17:00', 30,
         'A', 'A4', 'GROUPE 01', 'SESSION 2026', ''),

    (10, 'Finances Publiques',
         'Comprendre les mécanismes des finances publiques',
         'CPFAE-AGC', '2026-06-04 08:00', '2026-06-07 17:00', 30,
         'A', 'A4', 'GROUPE 01', 'SESSION 2026', ''),

    # ── GROUPE 02 ──────────────────────────────────────────────────────────────
    (11, 'Culture Civique',
         'Renforcer la culture civique et institutionnelle',
         'CPFAE-AGC', '2026-04-13 08:00', '2026-04-14 17:00', 16,
         'A', 'A4', 'GROUPE 02', 'SESSION 2026', ''),

    (12, 'Protocole Et Savoir-Vivre',
         'Maîtriser les règles de protocole et de savoir vivre',
         'CPFAE-AGC', '2026-04-15 08:00', '2026-04-16 17:00', 16,
         'A', 'A4', 'GROUPE 02', 'SESSION 2026', ''),

    (13, 'Management Des Administrations Publiques',
         'Développer les capacités managériales des agents publics',
         'CPFAE-AGC', '2026-05-04 08:00', '2026-05-07 17:00', 30,
         'A', 'A4', 'GROUPE 02', 'SESSION 2026', ''),

    (14, 'Gestion Du Budget Familial',
         'Gérer son budget personnel et se préparer à la retraite',
         'CPFAE-AGC', '2026-05-08 08:00', '2026-05-09 17:00', 16,
         'A', 'A4', 'GROUPE 02', 'SESSION 2026', ''),

    (15, 'Droit Administratif',
         'Connaître le cadre juridique de l\'administration publique',
         'CPFAE-AGC', '2026-05-11 08:00', '2026-05-15 17:00', 30,
         'A', 'A4', 'GROUPE 02', 'SESSION 2026', ''),

    (16, 'Déontologie',
         'Intégrer les valeurs déontologiques de la fonction publique',
         'CPFAE-AGC', '2026-05-16 08:00', '2026-05-20 17:00', 30,
         'A', 'A4', 'GROUPE 02', 'SESSION 2026', ''),

    (17, 'Sigfae Et Outils Collaboratifs Et Teletravail',
         'Maîtriser les outils numériques de l\'administration',
         'CPFAE-AGC', '2026-05-21 08:00', '2026-05-23 17:00', 30,
         'A', 'A4', 'GROUPE 02', 'SESSION 2026', ''),

    (18, 'Ethique Publique Et Lutte Contre La Corruption',
         'Promouvoir l\'éthique et lutter contre la corruption',
         'CPFAE-AGC', '2026-05-26 08:00', '2026-05-28 17:00', 20,
         'A', 'A4', 'GROUPE 02', 'SESSION 2026', ''),

    (19, 'Redaction Administrative',
         'Maîtriser la rédaction des actes et documents administratifs',
         'CPFAE-AGC', '2026-05-29 08:00', '2026-06-02 17:00', 30,
         'A', 'A4', 'GROUPE 02', 'SESSION 2026', ''),

    (20, 'Finances Publiques',
         'Comprendre les mécanismes des finances publiques',
         'CPFAE-AGC', '2026-06-04 08:00', '2026-06-07 17:00', 30,
         'A', 'A4', 'GROUPE 02', 'SESSION 2026', ''),

    # ── GROUPE 03 ──────────────────────────────────────────────────────────────
    (21, 'Culture Civique',
         'Renforcer la culture civique et institutionnelle',
         'CPFAE-AGC', '2026-04-13 08:00', '2026-04-14 17:00', 16,
         'A', 'A4', 'GROUPE 03', 'SESSION 2026', ''),

    (22, 'Protocole Et Savoir-Vivre',
         'Maîtriser les règles de protocole et de savoir vivre',
         'CPFAE-AGC', '2026-04-15 08:00', '2026-04-16 17:00', 16,
         'A', 'A4', 'GROUPE 03', 'SESSION 2026', ''),

    (23, 'Management Des Administrations Publiques',
         'Développer les capacités managériales des agents publics',
         'CPFAE-AGC', '2026-05-04 08:00', '2026-05-07 17:00', 30,
         'A', 'A4', 'GROUPE 03', 'SESSION 2026', ''),

    (24, 'Gestion Du Budget Familial',
         'Gérer son budget personnel et se préparer à la retraite',
         'CPFAE-AGC', '2026-05-08 08:00', '2026-05-09 17:00', 16,
         'A', 'A4', 'GROUPE 03', 'SESSION 2026', ''),

    (25, 'Droit Administratif',
         'Connaître le cadre juridique de l\'administration publique',
         'CPFAE-AGC', '2026-05-11 08:00', '2026-05-15 17:00', 30,
         'A', 'A4', 'GROUPE 03', 'SESSION 2026', ''),

    (26, 'Déontologie',
         'Intégrer les valeurs déontologiques de la fonction publique',
         'CPFAE-AGC', '2026-05-16 08:00', '2026-05-20 17:00', 30,
         'A', 'A4', 'GROUPE 03', 'SESSION 2026', ''),

    (27, 'Sigfae Et Outils Collaboratifs Et Teletravail',
         'Maîtriser les outils numériques de l\'administration',
         'CPFAE-AGC', '2026-05-21 08:00', '2026-05-23 17:00', 30,
         'A', 'A4', 'GROUPE 03', 'SESSION 2026', ''),

    (28, 'Ethique Publique Et Lutte Contre La Corruption',
         'Promouvoir l\'éthique et lutter contre la corruption',
         'CPFAE-AGC', '2026-05-26 08:00', '2026-05-28 17:00', 20,
         'A', 'A4', 'GROUPE 03', 'SESSION 2026', ''),

    (29, 'Redaction Administrative',
         'Maîtriser la rédaction des actes et documents administratifs',
         'CPFAE-AGC', '2026-05-29 08:00', '2026-06-02 17:00', 30,
         'A', 'A4', 'GROUPE 03', 'SESSION 2026', ''),

    (30, 'Finances Publiques',
         'Comprendre les mécanismes des finances publiques',
         'CPFAE-AGC', '2026-06-04 08:00', '2026-06-07 17:00', 30,
         'A', 'A4', 'GROUPE 03', 'SESSION 2026', ''),
]


# ─── Styles ─────────────────────────────────────────────────────────────────
GREEN_DARK  = 'FF093F70'
GREEN_MED   = 'FF125A99'
GREEN_LIGHT = 'FFE8EFF5'
GREY_LIGHT  = 'FFF5F5F5'
WHITE       = 'FFFFFFFF'

def _hdr_font():  return Font(bold=True, color='FFFFFFFF', size=11)
def _hdr_fill(c): return PatternFill('solid', fgColor=c)
def _border():
    s = Side(style='thin')
    return Border(left=s, right=s, top=s, bottom=s)
def _align(h='left'): return Alignment(horizontal=h, vertical='center', wrap_text=True)

def _auto_width(ws):
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            try:
                val = str(cell.value) if cell.value is not None else ''
                max_len = max(max_len, len(val))
            except: pass
        ws.column_dimensions[col_letter].width = min(max(max_len + 2, 10), 50)

def _write_header(ws, headers, fill_color):
    ws.row_dimensions[1].height = 30
    for ci, h in enumerate(headers, 1):
        c = ws.cell(row=1, column=ci, value=h)
        c.font   = _hdr_font()
        c.fill   = _hdr_fill(fill_color)
        c.border = _border()
        c.alignment = _align('center')

def _write_row(ws, row_i, vals, fill_color):
    ws.row_dimensions[row_i].height = 20
    fill = PatternFill('solid', fgColor=fill_color)
    for ci, val in enumerate(vals, 1):
        c = ws.cell(row=row_i, column=ci, value=val)
        c.fill   = fill
        c.border = _border()
        c.alignment = _align()
        if isinstance(val, datetime):
            c.number_format = 'DD/MM/YYYY HH:MM'
        elif isinstance(val, date):
            c.number_format = 'DD/MM/YYYY'
        elif isinstance(val, time):
            c.number_format = 'HH:MM'


# ─── Générer le fichier Formations ───────────────────────────────────────────
def generate_formations(formations):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Formations'
    ws.freeze_panes = 'A2'

    headers = ['N°', 'Formation (cycle)', 'Module (titre)', 'Objectif', 'Lieu',
               'Bâtiment', 'Salle',
               'Date début', 'Date fin', 'Volume horaire (h)',
               'Catégorie', 'Grade', 'Groupe', 'Vague', 'Programme']
    _write_header(ws, headers, GREEN_DARK)

    CYCLE = 'FORMATION EN ADMINISTRATION DE BASE'
    for ri, f in enumerate(formations, 2):
        num, titre, obj, lieu, bat, salle, d_debut, d_fin, dur, cat, grade, groupe, vague, prog = f
        fill = GREEN_LIGHT if ri % 2 == 0 else WHITE
        _write_row(ws, ri, [num, CYCLE, titre, obj, lieu, bat, salle, d_debut, d_fin, dur, cat, grade, groupe, vague, prog], fill)

    _auto_width(ws)
    out = os.path.join(OUT_DIR, 'import_formations_reel.xlsx')
    wb.save(out)
    print(f'✅ {out}  ({len(formations)} formations)')
    return out


# ─── Générer le fichier Séances ───────────────────────────────────────────────
def generate_seances(seances):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Séances'
    ws.freeze_panes = 'A2'

    headers = ['module_titre', 'grade', 'groupe', 'date_journee', 'numero', 'intitule', 'heure_debut', 'heure_fin']
    _write_header(ws, headers, GREEN_MED)

    for ri, s in enumerate(seances, 2):
        titre, grade, groupe, d, num, intitule, hd, hf = s
        fill = GREEN_LIGHT if ri % 2 == 0 else WHITE
        _write_row(ws, ri, [titre, grade, groupe, d, num, intitule, hd, hf], fill)

    _auto_width(ws)
    out = os.path.join(OUT_DIR, 'import_seances_reel.xlsx')
    wb.save(out)
    print(f'✅ {out}  ({len(seances)} séances)')
    return out


# ─── Générer le fichier Participants ──────────────────────────────────────────
def generate_participants():
    """Convertit FAB 2026 PHASE 1 FICHIER COMPLET.xlsx en import_participants_reel.xlsx."""
    src = os.path.join(_D, 'FAB 2026 PHASE 1 FICHIER COMPLET.xlsx')
    if not os.path.exists(src):
        print(f'  ⚠️  Fichier participants introuvable : {src}')
        return None

    wb_src = openpyxl.load_workbook(src, read_only=True, data_only=True)
    # Trouver la première feuille données (pas TCD/RECAP qui est un tableau croisé)
    # Les feuilles de données sont du type A4-1, A3-2, B3-1, etc.
    all_sheets = wb_src.sheetnames
    data_sheets = [s for s in all_sheets if re.match(r'^[AB]\d+-\d+', s)]
    src_rows = []
    src_headers = None
    for sname in data_sheets:
        ws_src = wb_src[sname]
        rows = list(ws_src.iter_rows(values_only=True))
        if not rows:
            continue
        if src_headers is None:
            src_headers = rows[0]
        src_rows.extend(rows[1:])
    wb_src.close()
    if src_headers is None:
        print(f'  ⚠️  Impossible de lire les headers du fichier participants')
        return None

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Participants'
    ws.freeze_panes = 'A2'

    out_headers = [
        'Matricule', 'Nom', 'Prénoms', 'Sexe',
        'Date naissance', 'Lieu naissance', 'Téléphone 1', 'Téléphone 2', 'Email',
        'Type concours', 'Libelle concours', 'Catégorie', 'Grade', 'Groupe',
        'Grade/Groupe', 'Vague', 'Site', 'Salle', 'Formation(s)',
    ]
    _write_header(ws, out_headers, GREEN_DARK)

    count = 0
    out_row = 2
    for row in src_rows:
        d = dict(zip(src_headers, row))
        numero = str(d.get("N° D'INSCRIPTION") or '').strip()
        if not numero.startswith('FNC'):
            continue

        nom = str(d.get('NOM') or '').strip()
        prenom = str(d.get('PRENOMS') or '').strip()
        sexe = str(d.get('GENRE') or '').strip()
        dnaiss = d.get('DATE DE NAISSANCE')
        lieu = str(d.get('LIEU DE NAISSANCE') or '').strip()
        tel1 = str(d.get('TELEPHONE 1') or '').strip()
        tel2 = str(d.get('TELEPHONE 2') or '').strip()
        type_c = str(d.get('TYPE_CONCOURS') or '').strip()
        lib_c = str(d.get('LIBELLE CONCOURS') or '').strip()
        cat_raw = str(d.get('CATEGORIE') or '').strip().upper()
        # Normaliser catégorie A/B/C → FAB A/FAB B/FAB C
        cat_map = {'A': 'FAB A', 'B': 'FAB B', 'C': 'FAB C'}
        cat = cat_map.get(cat_raw, cat_raw if cat_raw.startswith('FAB') else f'FAB {cat_raw}')
        grade = str(d.get('GRADE') or '').strip()
        groupe_raw = str(d.get('GROUPE') or '').strip().upper()
        # Normaliser GROUPE N (sans zéro padding)
        m_g = re.match(r'GROUPE\s+0*(\d+)', groupe_raw)
        groupe = f'GROUPE {m_g.group(1)}' if m_g else groupe_raw
        grade_groupe = f'{grade}/{groupe}' if grade and groupe else str(d.get('GRADE-GROUPE') or '').strip()
        site = str(d.get('SITE') or '').strip()
        formation_cycle = 'FORMATION EN ADMINISTRATION DE BASE'

        fill = GREEN_LIGHT if out_row % 2 == 0 else WHITE
        vals = [numero, nom, prenom, sexe, dnaiss, lieu, tel1, tel2, '',
                type_c, lib_c, cat, grade, groupe, grade_groupe, 'SESSION 2026',
                'CPFAE-AGC', site, formation_cycle]
        _write_row(ws, out_row, vals, fill)
        out_row += 1
        count += 1

    _auto_width(ws)
    out = os.path.join(OUT_DIR, 'import_participants_reel.xlsx')
    wb.save(out)
    print(f'✅ {out}  ({count} participants)')
    return out


if __name__ == '__main__':
    print('Parsing fichiers Emploi du Temps...')
    formations, seances = _get_data()
    print(f'  → {len(formations)} modules-groupes, {len(seances)} séances extraites')
    print()
    generate_formations(formations)
    generate_seances(seances)
    generate_participants()
    print()
    print('Ordre d\'import :')
    print('  1. Formations   → python manage.py import_excel import_formations_reel.xlsx')
    print('  2. Participants → python manage.py import_excel import_participants_reel.xlsx')
    print('  3. Séances      → python manage.py import_excel import_seances_reel.xlsx')
