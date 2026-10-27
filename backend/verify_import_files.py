"""
Script manuel HORS RUNTIME Django (P00-05) : CLI opérateur
d'import/reprise — sorties print() de console volontaires ;
exclu du garde-fou check_repo_hygiene.
Vérifie la cohérence des 3 fichiers d'import avant import en base.
"""
import openpyxl, os, re
from datetime import datetime, date

OUT = 'donnees'

OK = '  ✅'
WARN = '  ⚠️ '
ERR = '  ❌'

errors = []
warnings = []

# ─────────────────────────────────────────────────────────
# Charger les 3 fichiers
# ─────────────────────────────────────────────────────────
def load(fname):
    wb = openpyxl.load_workbook(os.path.join(OUT, fname), read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    headers = [str(h).strip() if h else '' for h in rows[0]]
    data = []
    for row in rows[1:]:
        if any(v is not None and str(v).strip() for v in row):
            d = {headers[i]: row[i] for i in range(len(headers)) if i < len(row)}
            data.append(d)
    wb.close()
    return headers, data

f_headers, formations   = load('import_formations_FAB2026.xlsx')
p_headers, participants = load('import_participants_FAB2026.xlsx')
s_headers, seances      = load('import_seances_FAB2026.xlsx')

print(f"\n{'='*60}")
print("VÉRIFICATION DES FICHIERS D'IMPORT FAB 2026")
print(f"{'='*60}")

# ─────────────────────────────────────────────────────────
# 1. FORMATIONS
# ─────────────────────────────────────────────────────────
print(f"\n{'─'*60}")
print(f"1. FORMATIONS  ({len(formations)} lignes)")
print(f"{'─'*60}")

# Colonnes obligatoires
for col in ['Formation', 'Module (titre)', 'Grade', 'Groupe', 'Date début', 'Date fin']:
    if col not in f_headers:
        errors.append(f"Formations: colonne '{col}' manquante")
        print(f"{ERR} Colonne obligatoire manquante: '{col}'")
    else:
        print(f"{OK} Colonne '{col}' présente")

# Combien de (grade, groupe) distincts
combos = set()
modules_par_combo = {}
missing_date = 0
for f in formations:
    grade  = str(f.get('Grade') or '').strip()
    groupe = str(f.get('Groupe') or '').strip()
    module = str(f.get('Module (titre)') or '').strip()
    deb    = f.get('Date début')
    fin    = f.get('Date fin')
    if not grade or not groupe:
        errors.append(f"Formations: ligne sans grade/groupe: {f}")
    if not deb or not fin:
        missing_date += 1
    combos.add((grade, groupe))
    key = (grade, groupe)
    modules_par_combo.setdefault(key, set()).add(module)

print(f"{OK} {len(combos)} groupes distincts (grade+groupe)")
if missing_date:
    warnings.append(f"Formations: {missing_date} lignes sans date début/fin")
    print(f"{WARN}{missing_date} lignes sans date début/fin")
else:
    print(f"{OK} Toutes les dates présentes")

# Modules par combo
nb_modules = [len(v) for v in modules_par_combo.values()]
print(f"{OK} {min(nb_modules)}–{max(nb_modules)} modules par groupe (moy: {sum(nb_modules)/len(nb_modules):.1f})")

# Grades présents
grades_f = sorted(set(str(f.get('Grade','')).strip() for f in formations))
print(f"{OK} Grades: {grades_f}")

# ─────────────────────────────────────────────────────────
# 2. PARTICIPANTS
# ─────────────────────────────────────────────────────────
print(f"\n{'─'*60}")
print(f"2. PARTICIPANTS  ({len(participants)} lignes)")
print(f"{'─'*60}")

for col in ["N° d'inscription", 'Nom', 'Prénom', 'Grade', 'Groupe', 'Formation(s)']:
    if col not in p_headers:
        errors.append(f"Participants: colonne '{col}' manquante")
        print(f"{ERR} Colonne obligatoire manquante: '{col}'")
    else:
        print(f"{OK} Colonne '{col}' présente")

# Vérifier matricules uniques
matricules = [str(p.get("N° d'inscription") or '').strip() for p in participants]
matricules_non_vides = [m for m in matricules if m]
doublons = len(matricules_non_vides) - len(set(matricules_non_vides))
if doublons:
    errors.append(f"Participants: {doublons} matricules en doublon")
    print(f"{ERR} {doublons} matricules en doublon")
else:
    print(f"{OK} {len(matricules_non_vides)} matricules tous uniques")

# Vérifier cohérence grade/groupe avec formations
combos_p = set()
for p in participants:
    grade  = str(p.get('Grade') or '').strip()
    groupe = str(p.get('Groupe') or '').strip()
    if grade and groupe:
        combos_p.add((grade, groupe))

combos_manquants = combos_p - combos
combos_extra     = combos - combos_p
if combos_manquants:
    warnings.append(f"Participants: {len(combos_manquants)} combos grade/groupe sans formation correspondante: {sorted(combos_manquants)}")
    print(f"{WARN}{len(combos_manquants)} combos grade/groupe dans participants sans formation: {sorted(combos_manquants)}")
else:
    print(f"{OK} Tous les combos grade/groupe participants ont une formation")

if combos_extra:
    warnings.append(f"Formations: {len(combos_extra)} combos sans participants: {sorted(combos_extra)}")
    print(f"{WARN}{len(combos_extra)} formations sans participants: {sorted(combos_extra)}")

# Formation référencée
form_ref = set(str(p.get('Formation(s)') or '').strip() for p in participants if p.get('Formation(s)'))
print(f"{OK} Titre formation référencé: {list(form_ref)[:2]}")

# Grades participants
grades_p = sorted(set(str(p.get('Grade','')).strip() for p in participants))
print(f"{OK} Grades: {grades_p}")

# Sexe
sexes = set(str(p.get('Sexe') or '').strip().upper() for p in participants if p.get('Sexe'))
print(f"{OK} Valeurs Sexe: {sexes}")

# ─────────────────────────────────────────────────────────
# 3. SÉANCES
# ─────────────────────────────────────────────────────────
print(f"\n{'─'*60}")
print(f"3. SÉANCES  ({len(seances)} lignes)")
print(f"{'─'*60}")

for col in ['module_titre', 'date_journee', 'numero', 'groupe', 'grade', 'vague']:
    if col not in s_headers:
        errors.append(f"Séances: colonne '{col}' manquante")
        print(f"{ERR} Colonne obligatoire manquante: '{col}'")
    else:
        print(f"{OK} Colonne '{col}' présente")

# Modules dans séances vs formations
modules_seances   = set(str(s.get('module_titre') or '').strip() for s in seances if s.get('module_titre'))
modules_formations = set(str(f.get('Module (titre)') or '').strip() for f in formations if f.get('Module (titre)'))

modules_orphelins = modules_seances - modules_formations
modules_sans_seance = modules_formations - modules_seances

if modules_orphelins:
    warnings.append(f"Séances: modules sans formation correspondante: {sorted(modules_orphelins)}")
    print(f"{WARN}Modules dans séances sans formation: {sorted(modules_orphelins)}")
else:
    print(f"{OK} Tous les modules séances existent dans les formations")

if modules_sans_seance:
    warnings.append(f"Formations: modules sans séances: {sorted(modules_sans_seance)}")
    print(f"{WARN}Modules formations sans séances: {sorted(modules_sans_seance)}")
else:
    print(f"{OK} Tous les modules formations ont des séances")

# Combos grade/groupe dans séances vs formations
combos_s = set((str(s.get('grade','')).strip(), str(s.get('groupe','')).strip()) for s in seances)
combos_s.discard(('', ''))
combos_manquants_s = combos_s - combos
if combos_manquants_s:
    warnings.append(f"Séances: combos grade/groupe sans formation: {sorted(combos_manquants_s)}")
    print(f"{WARN}Combos grade/groupe dans séances sans formation: {sorted(combos_manquants_s)}")
else:
    print(f"{OK} Tous les combos grade/groupe séances ont une formation")

combos_sans_seance = combos - combos_s
if combos_sans_seance:
    warnings.append(f"Formations: {len(combos_sans_seance)} combos sans séances (fichiers EDT manquants): {sorted(combos_sans_seance)}")
    print(f"{WARN}{len(combos_sans_seance)} formations sans séances (EDT manquants): {sorted(combos_sans_seance)}")

# Stats séances
grades_s = sorted(set(str(s.get('grade','')).strip() for s in seances if s.get('grade')))
print(f"{OK} Grades couverts: {grades_s}")
nb_par_grade = {g: sum(1 for s in seances if str(s.get('grade','')).strip()==g) for g in grades_s}
for g, n in nb_par_grade.items():
    print(f"     Grade {g}: {n} séances")

# Numéros de séance
numeros = set(s.get('numero') for s in seances if s.get('numero'))
print(f"{OK} Numéros de séance utilisés: {sorted(numeros)}")

# ─────────────────────────────────────────────────────────
# BILAN
# ─────────────────────────────────────────────────────────
print(f"\n{'='*60}")
print("BILAN")
print(f"{'='*60}")
if errors:
    print(f"\n{ERR} {len(errors)} ERREUR(S) BLOQUANTE(S) :")
    for e in errors: print(f"   • {e}")
else:
    print(f"{OK} Aucune erreur bloquante")

if warnings:
    print(f"\n{WARN}{len(warnings)} AVERTISSEMENT(S) :")
    for w in warnings: print(f"   • {w}")
else:
    print(f"{OK} Aucun avertissement")

print(f"\n{'─'*60}")
print("RÉSUMÉ FINAL :")
print(f"  Formations  : {len(formations):4d} lignes  ({len(combos)} groupes × modules)")
print(f"  Participants: {len(participants):4d} lignes  (1246 attendus)")
print(f"  Séances     : {len(seances):4d} lignes  (grade+groupe+module+date)")
print(f"{'─'*60}")
if not errors:
    print("\n  ✅ Les fichiers sont PRÊTS à être importés.")
    print("  Ordre : formations → participants → séances (type=seances)")
else:
    print("\n  ❌ Corriger les erreurs avant import.")
