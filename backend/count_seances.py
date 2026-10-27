# Script manuel HORS RUNTIME Django (P00-05) : CLI opérateur d'import/reprise.
# Sorties print() de console volontaires ; exclu du garde-fou check_repo_hygiene.
import openpyxl, os, re

SRC = 'donnees'

JOURS = ('LUNDI','MARDI','MERCREDI','JEUDI','VENDREDI','SAMEDI','DIMANCHE')
MOIS  = ('JANVIER','FEVRIER','MARS','AVRIL','MAI','JUIN','JUILLET',
          'AOUT','SEPTEMBRE','OCTOBRE','NOVEMBRE','DECEMBRE')
MONTHS_FR = {'JANVIER':1,'FEVRIER':2,'MARS':3,'AVRIL':4,'MAI':5,'JUIN':6,
             'JUILLET':7,'AOUT':8,'SEPTEMBRE':9,'OCTOBRE':10,'NOVEMBRE':11,'DECEMBRE':12}

def clean(v):
    if v is None: return ''
    return str(v).strip().replace('\xa0', ' ').strip()

def parse_date_fr(s):
    if not s: return None
    s = re.sub(r'^(LUNDI|MARDI|MERCREDI|JEUDI|VENDREDI|SAMEDI|DIMANCHE)\s*', '', s.upper()).strip()
    m = re.match(r'(\d{1,2})\s+(\w+)\s+(\d{4})', s)
    if m:
        from datetime import date
        day, mon, year = int(m.group(1)), MONTHS_FR.get(m.group(2)), int(m.group(3))
        if mon:
            try: return date(year, mon, day)
            except: pass
    return None

def is_noise(v):
    v = str(v).upper().strip().replace('\xa0','')
    if not v or len(v) < 3: return True
    if any(j in v for j in JOURS): return True
    if any(m in v for m in MOIS): return True
    if re.match(r'^\d+\s*H', v): return True
    if any(k in v for k in ('MINISTERE','DIRECTION','CENTRE','REPUBLIQUE','UNION',
                             'FORMATION EN','EMPLOI','MATIERES','DU MODULE',
                             'RESTANT','FORMATEUR','SITE','GROUPE','CPFAE',
                             'BATIMENT','SALLE','PERIODE','HORAIRE','VOLUME',
                             'FONCTION PUBLIQUE','RENFORCEMENT','MODERNISATION',
                             'AGC','AMADOU','----------')): return True
    return False

edt_files = [f for f in os.listdir(SRC) if 'Emploi' in f and f.endswith('.xlsx')]

# stats globales
stats = {}  # fichier -> feuille -> {grade, groupe, modules:{module->[dates]}}
total_seances = 0
total_seances_uniq = 0

for fname in sorted(edt_files):
    path = os.path.join(SRC, fname)
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    stats[fname] = {}

    for shname in wb.sheetnames:
        ws = wb[shname]
        all_rows = list(ws.iter_rows(values_only=True))

        grade = groupe = ''
        header_idx = None
        for i, row in enumerate(all_rows):
            vals = [clean(v) for v in row]
            full = ' '.join(vals).upper()
            if 'GRADE' in full and 'EMPLOI' in full:
                m = re.search(r'GRADE\s+([A-Z]\d)', full)
                if m: grade = m.group(1)
            if 'GROUPE' in full and not groupe:
                m2 = re.search(r'GROUPE\s*[:\s]*0*(\d+)', full)
                if m2: groupe = f'GROUPE {int(m2.group(1))}'
            if 'MATIERES' in full:
                header_idx = i
                break

        if header_idx is None:
            continue

        data_start = header_idx + 1
        if data_start < len(all_rows):
            nv = [clean(v).upper() for v in all_rows[data_start]]
            if any('DU MODULE' in v or 'RESTANT' in v for v in nv):
                data_start += 1

        modules_found = {}  # module -> [dates]
        current = ''
        for row in all_rows[data_start:]:
            first = clean(row[0]) if row[0] else ''
            # Nouveau module ?
            if first and not is_noise(first) and not re.match(r'^\d+\s*H?\s*$', first.upper()):
                current = first.strip()

            # Chercher date dans la ligne
            for v in row:
                d = parse_date_fr(clean(v))
                if d and current:
                    modules_found.setdefault(current, set()).add(d)

        stats[fname][shname] = {
            'grade': grade, 'groupe': groupe,
            'modules': modules_found,
        }

    wb.close()

# Affichage
print(f"\n{'='*65}")
print("DÉTAIL DES SÉANCES PAR FICHIER / FEUILLE / MODULE")
print(f"{'='*65}")

all_seances = set()  # (grade, groupe, module, date) pour dédupliquer global

for fname in sorted(stats.keys()):
    print(f"\n📄 {fname}")
    for shname, info in stats[fname].items():
        grade  = info['grade']
        groupe = info['groupe']
        mods   = info['modules']
        nb_seances = sum(len(dates)*2 for dates in mods.values())  # ×2 matin+aprèm
        print(f"  Feuille '{shname:12s}' Grade:{grade:4s} {groupe:12s} — {len(mods)} modules, {sum(len(d) for d in mods.values())} jours")
        for mod, dates in sorted(mods.items()):
            print(f"    {mod:<50s}: {len(dates)} jour(s) → {sorted(dates)}")
            for d in dates:
                all_seances.add((grade, groupe, mod, str(d)))

print(f"\n{'='*65}")
print(f"TOTAL séances uniques (grade+groupe+module+date) : {len(all_seances)}")

# Résumé par fichier EDT
print(f"\nRÉSUMÉ PAR FICHIER :")
for fname in sorted(stats.keys()):
    nb_feuilles = len(stats[fname])
    nb_mods = sum(len(i['modules']) for i in stats[fname].values())
    nb_jours = sum(len(d) for i in stats[fname].values() for d in i['modules'].values())
    print(f"  {fname[:55]:<55s} : {nb_feuilles} feuilles, {nb_mods} modules-feuille, {nb_jours} jours")
