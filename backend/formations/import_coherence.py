"""
Vérification de cohérence entre feuilles d'un fichier Excel d'import.

Clés de rapprochement :
  - Cours (Formations) : (module_titre, grade, groupe, vague)
  - Auditeurs          : grade + groupe (+ vague optionnel pour auto-match)
  - Séances            : module_titre + grade + groupe + vague (obligatoires)
"""
from __future__ import annotations

from dataclasses import dataclass, field


def _norm(val) -> str:
    if val is None:
        return ''
    return str(val).strip()


def _row_dict(headers, row):
    d = {}
    for i, h in enumerate(headers):
        if h and i < len(row):
            d[h] = row[i]
    return d


@dataclass
class CoherenceReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors


def _module_key(module_titre, grade, groupe, vague) -> tuple[str, str, str, str]:
    return (_norm(module_titre), _norm(grade), _norm(groupe), _norm(vague))


def _combo_key(grade, groupe) -> tuple[str, str]:
    return (_norm(grade), _norm(groupe))


def check_workbook(wb) -> CoherenceReport:
    """Analyse un openpyxl Workbook déjà ouvert (read_only ou non)."""
    report = CoherenceReport()

    modules: set[tuple[str, str, str, str]] = set()
    combos_fg: set[tuple[str, str]] = set()
    cycles: set[str] = set()

    # ── Formations ───────────────────────────────────────────────────────
    if 'Formations' in wb.sheetnames:
        ws = wb['Formations']
        rows = list(ws.iter_rows(values_only=True))
        if rows:
            headers = [_norm(h) for h in rows[0]]
            hmap = {h.lower(): h for h in headers if h}

            def col(*names):
                for n in names:
                    key = n.lower()
                    if key in hmap:
                        return hmap[key]
                return None

            c_module = col('Module (titre)', 'module (titre)', 'module_titre', 'module')
            c_grade = col('Grade', 'grade')
            c_groupe = col('Groupe', 'groupe')
            c_vague = col('Vague', 'vague')
            c_cycle = col('Formation (cycle)', 'Formation', 'formation')
            c_debut = col('Date début', 'date_debut', 'date debut')
            c_fin = col('Date fin', 'date_fin', 'date fin')

            missing_cols = [
                label for label, c in (
                    ('Module (titre)', c_module),
                    ('Grade', c_grade),
                    ('Groupe', c_groupe),
                    ('Vague', c_vague),
                ) if not c
            ]
            for label in missing_cols:
                report.errors.append(f"Formations : colonne « {label} » manquante")

            n_formations = 0
            for row_idx, row in enumerate(rows[1:], 2):
                if not row or all(v is None or _norm(v) == '' for v in row):
                    break
                data = _row_dict(headers, row)
                module = _norm(data.get(c_module)) if c_module else ''
                grade = _norm(data.get(c_grade)) if c_grade else ''
                groupe = _norm(data.get(c_groupe)) if c_groupe else ''
                vague = _norm(data.get(c_vague)) if c_vague else ''
                if not module:
                    report.errors.append(f"Formations ligne {row_idx} : module (titre) manquant")
                    continue
                if not grade or not groupe or not vague:
                    report.errors.append(
                        f"Formations ligne {row_idx} : grade/groupe/vague incomplets "
                        f"({grade!r}/{groupe!r}/{vague!r})"
                    )
                if c_debut and c_fin and (not data.get(c_debut) or not data.get(c_fin)):
                    report.warnings.append(
                        f"Formations ligne {row_idx} : date début/fin manquante pour « {module} »"
                    )
                if c_cycle:
                    cycles.add(_norm(data.get(c_cycle)))
                key = _module_key(module, grade, groupe, vague)
                modules.add(key)
                if grade and groupe:
                    combos_fg.add(_combo_key(grade, groupe))
                n_formations += 1

            report.stats['formations_lignes'] = n_formations
            report.stats['modules_distincts'] = len(modules)
            report.stats['combos_grade_groupe'] = len(combos_fg)

            # ── Validation : groupes présents dans plusieurs formations ─────────
            # Un même groupe ne devrait apparaître que dans un seul cycle
            groupe_to_cycles: dict[str, set[str]] = {}
            for row_idx, row in enumerate(rows[1:], 2):
                if not row or all(v is None or _norm(v) == '' for v in row):
                    break
                data = _row_dict(headers, row)
                groupe = _norm(data.get(c_groupe)) if c_groupe else ''
                cycle = _norm(data.get(c_cycle)) if c_cycle else ''
                if groupe and cycle:
                    if groupe not in groupe_to_cycles:
                        groupe_to_cycles[groupe] = set()
                    groupe_to_cycles[groupe].add(cycle)

            for groupe, cycles_set in groupe_to_cycles.items():
                if len(cycles_set) > 1:
                    report.warnings.append(
                        f"Formations : groupe « {groupe} » présent dans {len(cycles_set)} formations différentes : "
                        f"{', '.join(sorted(cycles_set))}"
                    )

            # ── Validation : combos grade/groupe/vague avec plusieurs modules ──
            # Un même combo (grade, groupe, vague) ne devrait matcher qu'un seul module
            # dans un contexte donné (sinon auto-inscription ambiguë)
            combo_ggv_to_modules: dict[tuple[str, str, str], list[tuple[str, str]]] = {}
            for row_idx, row in enumerate(rows[1:], 2):
                if not row or all(v is None or _norm(v) == '' for v in row):
                    break
                data = _row_dict(headers, row)
                module = _norm(data.get(c_module)) if c_module else ''
                grade = _norm(data.get(c_grade)) if c_grade else ''
                groupe = _norm(data.get(c_groupe)) if c_groupe else ''
                vague = _norm(data.get(c_vague)) if c_vague else ''
                cycle = _norm(data.get(c_cycle)) if c_cycle else ''
                if grade and groupe and vague:
                    key = (grade, groupe, vague)
                    if key not in combo_ggv_to_modules:
                        combo_ggv_to_modules[key] = []
                    combo_ggv_to_modules[key].append((module, cycle))

            for (grade, groupe, vague), mods in combo_ggv_to_modules.items():
                unique_mods = set(mods)
                if len(unique_mods) > 1:
                    mod_list = ', '.join([f"« {m[0]} » ({m[1]})" for m in unique_mods])
                    report.warnings.append(
                        f"Formations : combo {grade}/{groupe}/{vague} matche {len(unique_mods)} modules différents : "
                        f"{mod_list} — risque d'auto-inscription multiple"
                    )

    else:
        report.errors.append('Feuille « Formations » absente')

    # ── Participants ─────────────────────────────────────────────────────
    part_sheet = None
    for name in ('Participants', 'Auditeurs'):
        if name in wb.sheetnames:
            part_sheet = name
            break

    if part_sheet:
        ws = wb[part_sheet]
        rows = list(ws.iter_rows(values_only=True))
        headers = [_norm(h) for h in rows[0]] if rows else []
        hmap = {h.lower(): h for h in headers if h}

        def pcol(*names):
            for n in names:
                if n.lower() in hmap:
                    return hmap[n.lower()]
            return None

        c_mat = pcol("N° d'inscription", 'matricule')
        c_nom = pcol('Nom', 'nom')
        c_grade = pcol('Grade', 'grade')
        c_groupe = pcol('Groupe', 'groupe')
        c_vague = pcol('Vague', 'vague')
        c_formations = pcol('Formation(s)', 'formations', 'formation(s)')

        matricules: list[str] = []
        n_participants = 0
        for row_idx, row in enumerate(rows[1:], 2):
            if not row or all(v is None or _norm(v) == '' for v in row):
                break
            data = _row_dict(headers, row)
            nom = _norm(data.get(c_nom)) if c_nom else ''
            grade = _norm(data.get(c_grade)) if c_grade else ''
            groupe = _norm(data.get(c_groupe)) if c_groupe else ''
            vague = _norm(data.get(c_vague)) if c_vague else ''
            formations_str = _norm(data.get(c_formations)) if c_formations else ''
            mat = _norm(data.get(c_mat)) if c_mat else ''
            if mat:
                matricules.append(mat)

            if not grade or not groupe:
                report.errors.append(
                    f"Participants ligne {row_idx} ({nom}) : grade et groupe obligatoires"
                )
            elif modules and not formations_str:
                combo = _combo_key(grade, groupe)
                if combo not in combos_fg:
                    report.warnings.append(
                        f"Participants ligne {row_idx} ({nom}) : combo {grade}/{groupe} "
                        f"sans cours correspondant (auto-match grade+groupe)"
                    )
                elif vague and modules:
                    has_module = any(
                        g == grade and gr == groupe and v == vague
                        for _, g, gr, v in modules
                    )
                    if not has_module:
                        report.warnings.append(
                            f"Participants ligne {row_idx} ({nom}) : aucun module "
                            f"avec vague={vague!r} pour {grade}/{groupe}"
                        )
            n_participants += 1

        dup = len(matricules) - len(set(matricules))
        if dup:
            report.errors.append(f"Participants : {dup} matricule(s) en doublon")
        report.stats['participants_lignes'] = n_participants
    else:
        report.warnings.append('Feuille « Participants » / « Auditeurs » absente')

    # ── Séances ──────────────────────────────────────────────────────────
    seance_sheet = None
    for name in ('Séances', 'Seances'):
        if name in wb.sheetnames:
            seance_sheet = name
            break

    if seance_sheet:
        ws = wb[seance_sheet]
        rows = list(ws.iter_rows(values_only=True))
        headers = [_norm(h) for h in rows[0]] if rows else []
        hmap = {h.lower(): h for h in headers if h}

        def scol(*names):
            for n in names:
                if n.lower() in hmap:
                    return hmap[n.lower()]
            return None

        c_module = scol('module_titre', 'module titre')
        c_grade = scol('grade', 'Grade')
        c_groupe = scol('groupe', 'Groupe')
        c_vague = scol('vague', 'Vague')
        c_date = scol('date_journee', 'date', 'date journée')
        c_num = scol('numero', 'numéro', 'n°')

        for label, c in (
            ('module_titre', c_module),
            ('grade', c_grade),
            ('groupe', c_groupe),
            ('vague', c_vague),
            ('date_journee', c_date),
            ('numero', c_num),
        ):
            if not c:
                report.errors.append(f"Séances : colonne « {label} » manquante")

        n_seances = 0
        orphan_seances = 0
        for row_idx, row in enumerate(rows[1:], 2):
            if not row or all(v is None or _norm(v) == '' for v in row):
                break
            data = _row_dict(headers, row)
            module = _norm(data.get(c_module)) if c_module else ''
            grade = _norm(data.get(c_grade)) if c_grade else ''
            groupe = _norm(data.get(c_groupe)) if c_groupe else ''
            vague = _norm(data.get(c_vague)) if c_vague else ''

            missing = [f for f, v in (
                ('grade', grade), ('groupe', groupe), ('vague', vague),
            ) if not v]
            if missing:
                report.errors.append(
                    f"Séances ligne {row_idx} : {', '.join(missing)} manquant(s)"
                )
            if modules:
                key = _module_key(module, grade, groupe, vague)
                if key not in modules:
                    orphan_seances += 1
                    report.errors.append(
                        f"Séances ligne {row_idx} : cours introuvable pour "
                        f"« {module} » ({grade}/{groupe}/{vague})"
                    )
            n_seances += 1

        report.stats['seances_lignes'] = n_seances
        report.stats['seances_orphelines'] = orphan_seances
    else:
        report.warnings.append('Feuille « Séances » absente')

    return report
