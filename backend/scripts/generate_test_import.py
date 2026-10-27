"""
Script manuel HORS RUNTIME Django (P00-05) : CLI opérateur
d'import/reprise — sorties print() de console volontaires ;
exclu du garde-fou check_repo_hygiene.
Génère un fichier Excel de test pour l'import formations + séances.
Basé sur la structure observée dans les emplois du temps (image) et
le format attendu par import_excel.py.

Usage :
  python scripts/generate_test_import.py
  → Produit : test_import_formations_seances.xlsx
"""
from datetime import date, time, datetime
import os

try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
except ImportError:
    raise SystemExit("openpyxl requis : pip install openpyxl")

OUTPUT = os.path.join(os.path.dirname(__file__), '..', 'test_import_formations_seances.xlsx')

# ─── Données de test ──────────────────────────────────────────────────────────
# Calquées sur la structure de l'image (emploi du temps DFRC) :
# plusieurs formations, catégories A/B/C, grades A4/A3/B2, groupes 1 & 2, vagues

FORMATION_CYCLE = 'FORMATION EN ADMINISTRATION DE BASE'

FORMATIONS = [
    # (N°, formation(cycle), module(titre), objectif, lieu, date_debut, date_fin, duree_h, categorie, grade, groupe, vague)
    # ── FAB A / Grade A4 / GROUPE 1 ──────────────────────────────────
    (1,  FORMATION_CYCLE, "Rédaction Administrative",
         "Maîtriser la rédaction des actes administratifs",
         "CPFAE", "Bâtiment Principal", "Salle Polyvalente", "2026-05-05 08:00", "2026-05-09 17:00", 40,
         "FAB A", "A4", "GROUPE 1", "SESSION 2026", ""),

    (2,  FORMATION_CYCLE, "Droit Administratif",
         "Connaître le cadre juridique de l'administration publique",
         "CPFAE", "Bâtiment Principal", "Salle Polyvalente", "2026-05-12 08:00", "2026-05-16 17:00", 40,
         "FAB A", "A4", "GROUPE 1", "SESSION 2026", ""),

    (3,  FORMATION_CYCLE, "Finances Publiques",
         "Comprendre les mécanismes des finances publiques",
         "CPFAE", "Bâtiment Principal", "Salle Polyvalente", "2026-05-19 08:00", "2026-05-22 17:00", 30,
         "FAB A", "A4", "GROUPE 1", "SESSION 2026", ""),

    # ── FAB A / Grade A4 / GROUPE 2 ──────────────────────────────────
    (4,  FORMATION_CYCLE, "Rédaction Administrative",
         "Maîtriser la rédaction des actes administratifs",
         "CPFAE", "Bâtiment Principal", "Salle Polyvalente", "2026-05-05 08:00", "2026-05-09 17:00", 40,
         "FAB A", "A4", "GROUPE 2", "SESSION 2026", ""),

    (5,  FORMATION_CYCLE, "Droit Administratif",
         "Connaître le cadre juridique de l'administration publique",
         "CPFAE", "Bâtiment Principal", "Salle Polyvalente", "2026-05-12 08:00", "2026-05-16 17:00", 40,
         "FAB A", "A4", "GROUPE 2", "SESSION 2026", ""),

    # ── FAB A / Grade A3 / GROUPE 1 ──────────────────────────────────
    (6,  FORMATION_CYCLE, "Management des Administrations Publiques",
         "Développer les capacités manégariales des agents publics",
         "CPFAE", "Bâtiment Principal", "Salle Polyvalente", "2026-06-02 08:00", "2026-06-06 17:00", 40,
         "FAB A", "A3", "GROUPE 1", "SESSION 2026", ""),

    (7,  FORMATION_CYCLE, "Culture Civique",
         "Renforcer la culture civique et institutionnelle",
         "CPFAE", "Bâtiment Principal", "Salle Polyvalente", "2026-06-09 08:00", "2026-06-10 17:00", 16,
         "FAB A", "A3", "GROUPE 1", "SESSION 2026", ""),

    # ── FAB B / Grade B3 / GROUPE 1 ──────────────────────────────────
    (8,  FORMATION_CYCLE, "Commande Publique",
         "Maîtriser les procédures de passation des marchés",
         "CPFAE", "Bâtiment Principal", "Salle Polyvalente", "2026-05-05 08:00", "2026-05-09 17:00", 40,
         "FAB B", "B3", "GROUPE 1", "SESSION 2026", ""),

    (9,  FORMATION_CYCLE, "Bureautique et Outils Numériques",
         "Utiliser les outils bureautiques courants",
         "CPFAE", "Bâtiment Principal", "Salle Polyvalente", "2026-05-12 08:00", "2026-05-15 17:00", 30,
         "FAB B", "B3", "GROUPE 1", "SESSION 2026", ""),

    # ── FAB B / Grade B3 / GROUPE 2 ──────────────────────────────────
    (10, FORMATION_CYCLE, "Gestion des Ressources Humaines",
         "Comprendre les fondements de la GRH publique",
         "CPFAE", "Bâtiment Principal", "Salle Polyvalente", "2026-05-05 08:00", "2026-05-08 17:00", 32,
         "FAB B", "B3", "GROUPE 2", "SESSION 2026", ""),
]

# Séances : (module_titre, grade, groupe, vague, date_journee, numero, intitule, heure_debut, heure_fin)
def _seances_for(module_titre, grade, groupe, vague, debut_date, nb_jours):
    """Génère des séances matin/après-midi sur nb_jours jours consécutifs."""
    from datetime import timedelta
    rows = []
    d = debut_date
    seq = 1
    for _ in range(nb_jours):
        rows.append((module_titre, grade, groupe, vague, d, seq,     "Matin",      time(8, 30),  time(12, 0)))
        rows.append((module_titre, grade, groupe, vague, d, seq + 1, "Après-midi", time(14, 0),  time(17, 30)))
        d += timedelta(days=1)
        seq += 2
    return rows

# (module_titre, grade, groupe, vague, date_debut, nb_jours)
SEANCE_DEFS = [
    ("Rédaction Administrative",                "A4", "GROUPE 1", "SESSION 2026", date(2026, 5, 5),  3),
    ("Droit Administratif",                     "A4", "GROUPE 1", "SESSION 2026", date(2026, 5, 12), 3),
    ("Finances Publiques",                      "A4", "GROUPE 1", "SESSION 2026", date(2026, 5, 19), 2),
    ("Rédaction Administrative",                "A4", "GROUPE 2", "SESSION 2026", date(2026, 5, 5),  3),
    ("Droit Administratif",                     "A4", "GROUPE 2", "SESSION 2026", date(2026, 5, 12), 3),
    ("Management des Administrations Publiques","A3", "GROUPE 1", "SESSION 2026", date(2026, 6, 2),  3),
    ("Culture Civique",                         "A3", "GROUPE 1", "SESSION 2026", date(2026, 6, 9),  2),
    ("Commande Publique",                       "B3", "GROUPE 1", "SESSION 2026", date(2026, 5, 5),  3),
    ("Bureautique et Outils Numériques",        "B3", "GROUPE 1", "SESSION 2026", date(2026, 5, 12), 2),
    ("Gestion des Ressources Humaines",         "B3", "GROUPE 2", "SESSION 2026", date(2026, 5, 5),  2),
]
SEANCES = []
for mod, grade, grp, vague, debut, nb in SEANCE_DEFS:
    SEANCES.extend(_seances_for(mod, grade, grp, vague, debut, nb))


# ─── Styles ──────────────────────────────────────────────────────────────────

def _header_style():
    return {
        'font': Font(bold=True, color='FFFFFF', size=11),
        'fill': PatternFill('solid', fgColor='1F4E79'),
        'alignment': Alignment(horizontal='center', vertical='center', wrap_text=True),
        'border': Border(
            left=Side(style='thin'),  right=Side(style='thin'),
            top=Side(style='thin'),   bottom=Side(style='thin'),
        ),
    }

def _apply(cell, styles):
    for k, v in styles.items():
        setattr(cell, k, v)

def _auto_width(ws, min_w=10, max_w=45):
    for col_cells in ws.columns:
        length = max(
            len(str(c.value)) if c.value is not None else 0
            for c in col_cells
        )
        col_letter = get_column_letter(col_cells[0].column)
        ws.column_dimensions[col_letter].width = min(max(length + 2, min_w), max_w)


# ─── Feuille Formations ───────────────────────────────────────────────

def _build_formations(wb):
    ws = wb.create_sheet("Formations")
    ws.row_dimensions[1].height = 30

    headers = [
        "N°", "Formation (cycle)", "Module (titre)", "Objectif", "Lieu",
        "Bâtiment", "Salle",
        "Date début", "Date fin", "Volume horaire (h)",
        "Catégorie", "Grade", "Groupe", "Vague", "Programme",
    ]
    hs = _header_style()
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        _apply(cell, hs)

    fills = [
        PatternFill('solid', fgColor='EBF5FB'),
        PatternFill('solid', fgColor='D6E4F0'),
    ]
    for row_i, f in enumerate(FORMATIONS, 2):
        fill = fills[row_i % 2]
        for col_i, val in enumerate(f, 1):
            cell = ws.cell(row=row_i, column=col_i, value=val)
            cell.alignment = Alignment(vertical='center', wrap_text=(col_i == 4))
            cell.border = Border(
                left=Side(style='thin'), right=Side(style='thin'),
                top=Side(style='thin'),  bottom=Side(style='thin'),
            )
            if col_i not in (4, 13):
                cell.fill = fill

    ws.freeze_panes = 'A2'
    _auto_width(ws)
    return ws


# ─── Feuille Séances ───────────────────────────────────────────────────

def _build_seances(wb):
    ws = wb.create_sheet("Séances")
    ws.row_dimensions[1].height = 28

    headers = [
        "module_titre", "grade", "groupe", "vague", "date_journee", "numero",
        "intitule", "heure_debut", "heure_fin",
    ]
    hs = _header_style()
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        _apply(cell, hs)

    grp_fills = {
        "Matin":       PatternFill('solid', fgColor='FFF6CC'),
        "Après-midi":  PatternFill('solid', fgColor='DDEBF7'),
    }
    for row_i, s in enumerate(SEANCES, 2):
        mod_titre, grade, groupe, vague, d, num, intitule, h_deb, h_fin = s
        vals = [mod_titre, grade, groupe, vague, d, num, intitule, h_deb, h_fin]
        fill = grp_fills.get(intitule, PatternFill('solid', fgColor='F2F2F2'))
        for col_i, val in enumerate(vals, 1):
            cell = ws.cell(row=row_i, column=col_i, value=val)
            cell.fill = fill
            cell.alignment = Alignment(vertical='center')
            cell.border = Border(
                left=Side(style='thin'), right=Side(style='thin'),
                top=Side(style='thin'),  bottom=Side(style='thin'),
            )
            if col_i == 5:  # date_journee
                if isinstance(val, datetime):
                    cell.value = val.date()
                cell.number_format = 'DD/MM/YYYY'
            elif col_i in (8, 9):  # heure_debut, heure_fin
                cell.number_format = 'HH:MM'

    ws.freeze_panes = 'A2'
    _auto_width(ws)
    return ws


# ─── Feuille Formateurs ───────────────────────────────────────────────

FORMATEURS = [
    ('F0001', 'KONE',    'Ibrahim',      'kone.ibrahim@cpfae.ci',   '0701000001', 'Droit administratif',              'CPFAE'),
    ('F0002', 'TRAORE',  'Awa Solange',  'traore.awa@cpfae.ci',     '0702000002', 'Rédaction administrative',           'CPFAE'),
    ('F0003', 'DIALLO',  'Mamadou',      'diallo.m@enaref.ci',      '0703000003', 'Finances publiques',                'ENAREF'),
    ('F0004', 'COULIBALY','Adjoa',       'coulibaly.a@enaref.ci',   '0704000004', 'Management des organisations',      'ENAREF'),
    ('F0005', 'BAMBA',   'Siaka',        'bamba.s@gouv.ci',         '0705000005', 'Commande publique',                 'Ministère'),
]

def _build_formateurs(wb):
    ws = wb.create_sheet("Formateurs")
    ws.row_dimensions[1].height = 28
    headers = ['Numéro', 'Nom', 'Prénoms', 'Email', 'Téléphone', 'Spécialité', 'Organisation']
    hs = _header_style()
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        _apply(cell, hs)
    fill = PatternFill('solid', fgColor='EBF5FB')
    for row_i, f in enumerate(FORMATEURS, 2):
        for col_i, val in enumerate(f, 1):
            cell = ws.cell(row=row_i, column=col_i, value=val)
            cell.fill = fill
            cell.alignment = Alignment(vertical='center')
            cell.border = Border(left=Side(style='thin'), right=Side(style='thin'),
                                 top=Side(style='thin'), bottom=Side(style='thin'))
    ws.freeze_panes = 'A2'
    _auto_width(ws)
    return ws


# ─── Feuille Participants ─────────────────────────────────────────────

PARTICIPANTS = [
    # (matricule, nom, prenom, sexe, date_naiss, lieu_naiss, categorie, grade, grade_groupe, groupe, vague, type_c, libelle_c, email, tel, tel2, site, salle, formations)
    ('FNCP26-001', 'KOUAME',    'Jean-Marc',    'MASCULIN', '15/03/1990', 'Abidjan',  'FAB A', 'A4', 'A4/GROUPE 1', 'GROUPE 1', 'SESSION 2026', 'Concours direct', 'Administrateur Civil',    'jm.kouame@gouv.ci',    '0701001001', '',           'CPFAE', 'SALLE A', FORMATION_CYCLE),
    ('FNCP26-002', 'DIALLO',    'Mariam',       'FEMININ',  '22/07/1992', 'Bouaké',   'FAB A', 'A4', 'A4/GROUPE 1', 'GROUPE 1', 'SESSION 2026', 'Concours direct', 'Administrateur Civil',    'diallo.m@gouv.ci',     '0702002002', '',           'CPFAE', 'SALLE A', FORMATION_CYCLE),
    ('FNCP26-003', 'BAMBA',     'Oumar',        'MASCULIN', '05/11/1988', 'Korhogo',  'FAB A', 'A4', 'A4/GROUPE 2', 'GROUPE 2', 'SESSION 2026', 'Concours direct', 'Administrateur Civil',    'bamba.o@gouv.ci',      '0703003003', '',           'CPFAE', 'SALLE B', FORMATION_CYCLE),
    ('FNCP26-004', 'TRAORE',    'Fatoumata',    'FEMININ',  '18/05/1995', 'Daloa',    'FAB A', 'A4', 'A4/GROUPE 2', 'GROUPE 2', 'SESSION 2026', 'Concours direct', 'Administrateur Civil',    'traore.f@gouv.ci',     '0704004004', '',           'CPFAE', 'SALLE B', FORMATION_CYCLE),
    ('FNCP26-005', 'COULIBALY', 'Mamadou',      'MASCULIN', '30/01/1985', 'Man',      'FAB A', 'A3', 'A3/GROUPE 1', 'GROUPE 1', 'SESSION 2026', 'Concours professionnel', 'Attaché Administration', 'coulibaly.m@gouv.ci',  '0705005005', '',           'CPFAE', 'SALLE C', FORMATION_CYCLE),
    ('FNCP26-006', 'KONE',      'Aissatou',     'FEMININ',  '12/09/1993', 'Abidjan',  'FAB B', 'B3', 'B3/GROUPE 1', 'GROUPE 1', 'SESSION 2026', 'Concours direct', 'Agent administratif',     'kone.a@gouv.ci',       '0706006006', '',           'CPFAE', 'SALLE D', FORMATION_CYCLE),
    ('FNCP26-007', 'TOURE',     'Ibrahim',      'MASCULIN', '08/04/1991', 'Yamoussoukro','FAB B', 'B3', 'B3/GROUPE 1', 'GROUPE 1', 'SESSION 2026', 'Concours direct', 'Agent administratif',  'toure.i@gouv.ci',      '0707007007', '',           'CPFAE', 'SALLE D', FORMATION_CYCLE),
    ('FNCP26-008', 'YAO',       'Kouassi Serge','MASCULIN', '25/06/1987', 'Aboisso',  'FAB B', 'B3', 'B3/GROUPE 2', 'GROUPE 2', 'SESSION 2026', 'Concours direct', 'Agent administratif',     'yao.ks@gouv.ci',       '0708008008', '0708008099', 'CPFAE', 'SALLE E', FORMATION_CYCLE),
]

def _build_participants(wb):
    ws = wb.create_sheet("Participants")
    ws.row_dimensions[1].height = 28
    headers = [
        "N\u00b0 d'inscription", 'Nom', 'Prénom', 'Sexe', 'Date de naissance', 'Lieu de naissance',
        'Catégorie', 'Grade', 'Grade/Groupe', 'Groupe', 'Vague',
        'Type concours', 'Libelle concours', 'Email', 'Téléphone 1', 'Téléphone 2',
        'Lieu', 'Salle', 'Formation(s)',
    ]
    hs = _header_style()
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        _apply(cell, hs)
    fills = [
        PatternFill('solid', fgColor='EBF5FB'),
        PatternFill('solid', fgColor='FFFFFF'),
    ]
    for row_i, p in enumerate(PARTICIPANTS, 2):
        fill = fills[row_i % 2]
        for col_i, val in enumerate(p, 1):
            cell = ws.cell(row=row_i, column=col_i, value=val)
            cell.fill = fill
            cell.alignment = Alignment(vertical='center', wrap_text=(col_i == 19))
            cell.border = Border(left=Side(style='thin'), right=Side(style='thin'),
                                 top=Side(style='thin'), bottom=Side(style='thin'))
    ws.freeze_panes = 'A2'
    _auto_width(ws)
    return ws


# ─── Feuille README ──────────────────────────────────────────────────

def _build_readme(wb):
    ws = wb.create_sheet("README")
    info = [
        ("Feuille",        "Description",                              "Colonnes obligatoires"),
        ("Formations",     "Liste des modules (1 ligne = 1 module)",   "Formation (cycle), Module (titre), Date début, Date fin, Catégorie"),
        ("Formateurs",     "Formateurs à créer",                       "Nom, Prénoms"),
        ("Participants",   "Participants + auto-inscription",           "N\u00b0 d'inscription, Nom, Prénom, Catégorie, Grade, Groupe"),
        ("Séances",        "Séances matin/après-midi par module",       "module_titre, grade, groupe, vague, date_journee, numero"),
        ("",  "", ""),
        ("Notes", "", ""),
        ("", "• Catégorie : FAB A, FAB B ou FAB C (détermine le secrétariat)", ""),
        ("", "• module_titre doit correspondre EXACTEMENT à l'intitulé du module", ""),
        ("", "• groupe doit correspondre EXACTEMENT au groupe du module (ex: GROUPE 1)", ""),
        ("", "• date_journee format : JJ/MM/AAAA ou AAAA-MM-JJ", ""),
        ("", "• Import ordre : Formations → Participants → Séances", ""),
        ("", "• python manage.py import_excel import_test.xlsx", ""),
    ]
    hs = _header_style()
    for row_i, row in enumerate(info, 1):
        for col_i, val in enumerate(row, 1):
            cell = ws.cell(row=row_i, column=col_i, value=val)
            if row_i == 1:
                _apply(cell, hs)
            elif col_i == 1 and val:
                cell.font = Font(bold=True, color='1F4E79')
            cell.alignment = Alignment(wrap_text=True, vertical='top')
    ws.column_dimensions['A'].width = 18
    ws.column_dimensions['B'].width = 70
    ws.column_dimensions['C'].width = 45
    return ws


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    wb = openpyxl.Workbook()
    del wb['Sheet']

    _build_formations(wb)
    _build_formateurs(wb)
    _build_participants(wb)
    _build_seances(wb)
    _build_readme(wb)

    out = os.path.abspath(OUTPUT)
    wb.save(out)
    print(f"✅ Fichier généré : {out}")
    print(f"   → {len(FORMATIONS)} modules ({len(set(f[1] for f in FORMATIONS))} formations)")
    print(f"   → {len(FORMATEURS)} formateurs")
    print(f"   → {len(PARTICIPANTS)} participants")
    print(f"   → {len(SEANCES)} séances")
    print()
    print("Import : python manage.py import_excel test_import_formations_seances.xlsx")


if __name__ == '__main__':
    main()
