"""
Point journalier — format CPFAE (fichiers « POINT JOURNALIER CAT … »).

Optimisé : pré-chargement bulk des séances, inscriptions et pointages
pour éviter les requêtes N+1 sur les filtres larges (année entière, etc.).
"""
import re
from collections import defaultdict
from datetime import date

from django.db.models import Q

from formations.categorie_referentiel import categories_from_raw_values, resolve_categorie_ref
from formations.models import Formation, Module, ModuleParticipant, SessionModule, Participant
from presences.models import Pointage

from .effectifs import (
    filter_sessions,
    presents_par_session,
    rattrapages_par_session,
    stats_creneau_module,
    categories_for_scope,
)

MOIS_FR = [
    '', 'JANVIER', 'FÉVRIER', 'MARS', 'AVRIL', 'MAI', 'JUIN',
    'JUILLET', 'AOÛT', 'SEPTEMBRE', 'OCTOBRE', 'NOVEMBRE', 'DÉCEMBRE',
]

MAX_GROUP_COLS = 17
ORGANISME_DEFAULT = 'CPFAE'
DEFAULT_HORAIRES = {'MATIN': '08H00-12H00', 'SOIR': '13H00-17H00'}


def _organisme_label(categorie, grade=None):
    """Libellé ligne DATE — ex. CATÉGORIE A_GRADE A3 (modèle CPFAE)."""
    cat = (categorie or '').strip()
    gr = (grade or '').strip()
    if cat and gr:
        return f'CATÉGORIE {cat}_GRADE {gr}'
    if gr:
        return f'CATÉGORIE _GRADE {gr}'
    if cat:
        return f'CATÉGORIE {cat}'
    return ORGANISME_DEFAULT


def _vague_sidebar_label(modules):
    for mod in modules:
        v = (mod.vague or '').strip()
        if v:
            return v.upper()
    return 'SECONDE VAGUE'


def _creneau(session):
    label = (session.intitule or '').lower()
    if any(k in label for k in ('matin', 'mat ', 'mat.')):
        return 'MATIN'
    if any(k in label for k in ('soir', 'après-midi', 'apres-midi', 'après midi', 'apres midi', 'pm')):
        return 'SOIR'
    if session.heure_debut_prevue:
        return 'MATIN' if session.heure_debut_prevue.hour < 13 else 'SOIR'
    return 'MATIN' if (session.numero or 1) <= 1 else 'SOIR'


def _fmt_heure(t):
    if not t:
        return None
    return f"{t.hour:02d}H{t.minute:02d}"


def _horaire_creneau(sessions, creneau):
    filtered = [s for s in sessions if _creneau(s) == creneau]
    if not filtered:
        return DEFAULT_HORAIRES.get(creneau, '—')
    starts = [s.heure_debut_prevue for s in filtered if s.heure_debut_prevue]
    ends = [s.heure_fin_prevue for s in filtered if s.heure_fin_prevue]
    if starts and ends:
        return f"{_fmt_heure(min(starts))}-{_fmt_heure(max(ends))}"
    if starts:
        h = _fmt_heure(starts[0])
        default_end = DEFAULT_HORAIRES.get(creneau, '').split('-')[-1]
        return f"{h}-{default_end}" if default_end else h
    return DEFAULT_HORAIRES.get(creneau, creneau)


def _group_label(module, multi_grade):
    g = (module.groupe or '').strip()
    gr = (module.grade or '').strip()
    if multi_grade and gr and g:
        g_short = g.replace('GROUPE ', 'G').replace('Groupe ', 'G')
        return f"{gr}-{g_short}" if not g.startswith(gr) else g_short or f"{gr}-{g}"
    if g:
        return g.replace('GROUPE ', 'G').replace('Groupe ', 'G')
    if gr:
        return gr
    return module.intitule[:20] if module.intitule else f"Module {module.id}"


def _salle_label(module):
    return (module.salle or module.batiment or '').strip() or '—'


def _titre_ligne1(formation, categorie=None):
    """Ligne 1 du modèle CPFAE (ex. FAC CAT A)."""
    name = (formation.formation or '').strip().upper()
    cat = (categorie or '').strip().upper()
    if cat == '—':
        cat = ''
    if 'FAC' in name or ('ACCOMPAGNEMENT' in name and 'CARRIER' in name):
        cat_part = f' CAT {cat}' if cat else ''
        return f"FORMATION D'ACCOMPAGNEMENT DE CARRIER{cat_part} _POINT DES PRÉSENCES_CPFAE"
    if 'ADMINISTRATION DE BASE' in name or 'FAB' in name:
        return 'FORMATION EN ADMINISTRATION DE BASE_POINT DES PRÉSENCES_CPFAE'
    return f"{name}_POINT DES PRÉSENCES_CPFAE"


def _sessions_pj_queryset(
    *,
    module_ids=None,
    annee=None,
    mois=None,
    formation_id=None,
    secretariat_id=None,
    allowed_module_ids=None,
    jours=None,
):
    """
    Séances éligibles au point journalier CPFAE.

    Utilise ``filter_sessions`` (même règle que assiduité / bilans / KPI).
    Les présences restent calculées à partir des pointages (0 si aucun badge).
    """
    scope_ids = module_ids
    if allowed_module_ids is not None:
        if scope_ids is not None:
            scope_ids = list(set(scope_ids) & set(allowed_module_ids))
        else:
            scope_ids = list(allowed_module_ids)

    qs = filter_sessions(module_ids=scope_ids, annee=annee, mois=mois)
    if formation_id:
        qs = qs.filter(module__formation_id=formation_id)
    if secretariat_id:
        qs = qs.filter(module__secretariat_id=secretariat_id)
    if jours:
        qs = qs.filter(date_journee__in=jours)
    return qs


def _jours_activite(annee, mois=None, formation_id=None, secretariat_id=None, allowed_module_ids=None):
    sm_q = _sessions_pj_queryset(
        annee=annee,
        mois=mois,
        formation_id=formation_id,
        secretariat_id=secretariat_id,
        allowed_module_ids=allowed_module_ids,
    )
    dates = sorted(set(sm_q.values_list('date_journee', flat=True)))
    return dates


def _liste_categories(formation_id=None, secretariat_id=None, allowed_module_ids=None):
    return categories_for_scope(
        formation_id=formation_id,
        secretariat_id=secretariat_id,
        module_ids=allowed_module_ids,
    )


def _categories_pour_formation(formation_id, secretariat_id=None, cache=None, allowed_module_ids=None):
    if cache and formation_id in cache['cats_by_formation']:
        return cache['cats_by_formation'][formation_id]
    mq = {'module__formation_id': formation_id}
    if secretariat_id:
        mq['module__secretariat_id'] = secretariat_id
    if allowed_module_ids is not None:
        mq['module_id__in'] = allowed_module_ids
    cats = categories_from_raw_values(
        ModuleParticipant.objects.filter(**mq)
        .exclude(participant__categorie='')
        .values_list('participant__categorie', flat=True)
    )
    return cats


def _formation_ids_for_scope(annee, mois, formation_id, secretariat_id, allowed_module_ids=None):
    if formation_id:
        return [formation_id]
    fq = Formation.objects.filter(
        modules__sessions__date_journee__year=annee,
    )
    if mois:
        fq = fq.filter(modules__sessions__date_journee__month=mois)
    if secretariat_id:
        fq = fq.filter(modules__secretariat_id=secretariat_id)
    if allowed_module_ids is not None:
        fq = fq.filter(modules__id__in=allowed_module_ids)
    return list(fq.distinct().values_list('id', flat=True))


def _build_pj_cache(annee, mois, formation_ids, jours, secretariat_id=None, allowed_module_ids=None):
    """Pré-charge modules, séances, inscriptions et pointages pour la période."""
    cache = {
        'formations': {},
        'modules_by_formation': defaultdict(list),
        'modules': {},
        'sessions_by_mod_day': defaultdict(list),
        'all_sessions_by_mod_day': defaultdict(list),
        'participants_by_mod': defaultdict(set),
        'participants_by_mod_cat': defaultdict(set),
        'participant_cat': {},
        'presents_by_session': defaultdict(set),
        'rattrapage_by_session': defaultdict(set),
        'cats_by_formation': defaultdict(list),
    }

    if not formation_ids or not jours:
        return cache

    formations = Formation.objects.filter(id__in=formation_ids)
    cache['formations'] = {f.id: f for f in formations}

    mq = Q(formation_id__in=formation_ids)
    if secretariat_id:
        mq &= Q(secretariat_id=secretariat_id)
    if allowed_module_ids is not None:
        mq &= Q(id__in=allowed_module_ids)

    modules = list(Module.objects.filter(mq).order_by('formation_id', 'grade', 'groupe', 'ordre', 'intitule'))
    module_ids = []
    for mod in modules:
        cache['modules'][mod.id] = mod
        cache['modules_by_formation'][mod.formation_id].append(mod)
        module_ids.append(mod.id)

    if not module_ids:
        return cache

    mp_rows = ModuleParticipant.objects.filter(module_id__in=module_ids).values_list(
        'module_id', 'participant_id', 'participant__categorie',
    )
    for mod_id, pid, cat in mp_rows:
        cache['participants_by_mod'][mod_id].add(pid)
        raw = (cat or '').strip()
        resolved = resolve_categorie_ref(raw) or raw
        cache['participant_cat'][pid] = resolved
        if resolved:
            cache['participants_by_mod_cat'][(mod_id, resolved.upper())].add(pid)

    sessions = list(
        _sessions_pj_queryset(module_ids=module_ids, jours=jours)
    )
    session_ids = []
    for sess in sessions:
        key = (sess.module_id, sess.date_journee)
        cache['all_sessions_by_mod_day'][key].append(sess)
        session_ids.append(sess.id)

    for sid, pids in presents_par_session(session_ids).items():
        cache['presents_by_session'][sid] = pids

    for sid, pids in rattrapages_par_session(session_ids).items():
        cache['rattrapage_by_session'][sid] = pids

    for fid in formation_ids:
        mod_ids = [m.id for m in cache['modules_by_formation'][fid]]
        cats = set()
        for mid in mod_ids:
            for pid in cache['participants_by_mod'][mid]:
                c = cache['participant_cat'].get(pid, '')
                if c:
                    cats.add(c)
        cache['cats_by_formation'][fid] = sorted(cats, key=lambda c: (len(c), c))

    return cache


def _participant_ids_for_module(module, categorie, cache):
    if categorie and categorie != '—':
        participant_ids = cache['participants_by_mod_cat'].get(
            (module.id, categorie.upper()), set(),
        )
        if not participant_ids:
            participant_ids = {
                pid for pid in cache['participants_by_mod'][module.id]
                if cache['participant_cat'].get(pid, '').upper() == categorie.upper()
            }
        return participant_ids
    return cache['participants_by_mod'][module.id]


def _groupe_bucket_key(module):
    """Clé d'agrégation : grade + groupe physique (pas le module / matière)."""
    gr = (module.grade or '').strip().upper()
    g = (module.groupe or '').strip().upper()
    if not g:
        return (gr, f'__MOD_{module.id}')
    return (gr, g)


def _groupe_num_sort(value):
    m = re.search(r'(\d+)', (value or ''))
    return int(m.group(1)) if m else 9999


def _groupe_bucket_sort_key(key):
    gr, g = key
    return (_groupe_num_sort(gr), gr, _groupe_num_sort(g), g)


def _sessions_creneau(modules, jour, creneau, cache):
    sessions = []
    for mod in modules:
        for sess in cache['all_sessions_by_mod_day'].get((mod.id, jour), []):
            if _creneau(sess) == creneau:
                sessions.append(sess)
    return sessions


def _stats_groupe_cached(module, jour, creneau, categorie, cache):
    participant_ids = _participant_ids_for_module(module, categorie, cache)
    sessions = _sessions_creneau([module], jour, creneau, cache)
    return stats_creneau_module(
        participant_ids,
        sessions,
        cache['presents_by_session'],
        cache['rattrapage_by_session'],
    )


def _stats_groupe_modules(modules, jour, creneau, categorie, cache):
    """Stats agrégées pour un groupe physique (union auditeurs + séances du créneau)."""
    participant_ids = set()
    for mod in modules:
        participant_ids |= _participant_ids_for_module(mod, categorie, cache)
    sessions = _sessions_creneau(modules, jour, creneau, cache)
    return stats_creneau_module(
        participant_ids,
        sessions,
        cache['presents_by_session'],
        cache['rattrapage_by_session'],
    )


def _aggregate_total(groupes):
    effectif = sum(g['effectif'] for g in groupes)
    presents = sum(g['presents'] for g in groupes)
    absents = sum(g['absents'] for g in groupes)
    return {
        'effectif': effectif,
        'presents': presents,
        'absents': absents,
        'taux_presence': round(presents / effectif, 4) if effectif else 0.0,
        'taux_absence': round(absents / effectif, 4) if effectif else 0.0,
    }


def _modules_avec_cours_jour(modules, jour, cache):
    """Modules ayant au moins une séance planifiée le jour donné."""
    return [
        m for m in modules
        if cache['all_sessions_by_mod_day'].get((m.id, jour), [])
    ]


def _bloc_creneau_cached(modules, jour, creneau, categorie, multi_grade, all_sessions, cache):
    """Une colonne par groupe physique (G10, G11…), uniquement si cours ce créneau."""
    buckets = defaultdict(list)
    for mod in modules:
        buckets[_groupe_bucket_key(mod)].append(mod)

    groupes = []
    for key in sorted(buckets.keys(), key=_groupe_bucket_sort_key):
        mods = sorted(buckets[key], key=lambda m: m.id)
        sessions = _sessions_creneau(mods, jour, creneau, cache)
        if not sessions:
            continue
        rep = mods[0]
        stats = _stats_groupe_modules(mods, jour, creneau, categorie, cache)
        groupes.append({
            'module_id': rep.id,
            'module_ids': [m.id for m in mods],
            'label': _group_label(rep, multi_grade),
            'salle': _salle_label(rep),
            **stats,
        })
    return {
        'horaire': _horaire_creneau(all_sessions, creneau),
        'groupes': groupes[:MAX_GROUP_COLS],
        'total': _aggregate_total(groupes),
    }


def _modules_for_tableau(formation, categorie, cache, secretariat_id=None, grade=None):
    modules = list(cache['modules_by_formation'].get(formation.id, []))
    if not modules:
        return [], False

    if categorie and categorie != '—':
        mod_ids = {
            mid for (mid, cat), pids in cache['participants_by_mod_cat'].items()
            if cat.upper() == categorie.upper() and pids
        }
        modules = [m for m in modules if m.id in mod_ids]
    else:
        mod_ids = {m.id for m in modules if cache['participants_by_mod'][m.id]}
        modules = [m for m in modules if m.id in mod_ids]

    if grade:
        grade_up = grade.strip().upper()
        modules = [m for m in modules if (m.grade or '').strip().upper() == grade_up]

    if not modules:
        return [], False

    grades = {m.grade for m in modules if (m.grade or '').strip()}
    return modules, len(grades) > 1


def _compute_tableau_cached(formation, categorie, jour, cache, secretariat_id=None,
                            full_detail=True, grade=None):
    modules, multi_grade = _modules_for_tableau(
        formation, categorie, cache, secretariat_id, grade=grade,
    )
    if not modules:
        return None

    modules = _modules_avec_cours_jour(modules, jour, cache)
    if not modules:
        return None

    grade_val = (grade or '').strip() or next(
        ((m.grade or '').strip() for m in modules if (m.grade or '').strip()), ''
    )

    all_sessions = []
    for mod in modules:
        all_sessions.extend(cache['all_sessions_by_mod_day'].get((mod.id, jour), []))
    if not all_sessions:
        return None

    matin = _bloc_creneau_cached(modules, jour, 'MATIN', categorie, multi_grade, all_sessions, cache)
    soir = _bloc_creneau_cached(modules, jour, 'SOIR', categorie, multi_grade, all_sessions, cache)

    if not modules:
        return None

    taux_presence_jour = round(
        (matin['total']['taux_presence'] + soir['total']['taux_presence']) / 2, 4
    ) if (matin['total']['effectif'] or soir['total']['effectif']) else 0.0
    taux_absence_jour = round(
        (matin['total']['taux_absence'] + soir['total']['taux_absence']) / 2, 4
    ) if (matin['total']['effectif'] or soir['total']['effectif']) else 0.0

    suffix = f"-{grade_val}" if grade_val else ''
    base = {
        'id': f"{formation.id}-{categorie}-{jour.isoformat()}{suffix}",
        'categorie': categorie,
        'grade': grade_val,
        'formation_id': formation.id,
        'formation': str(formation),
        'date': jour.isoformat(),
        'date_fr': jour.strftime('%d/%m/%Y'),
        'jour': jour.day,
        'mois': jour.month,
        'mois_libelle': MOIS_FR[jour.month],
        'annee': jour.year,
        'organisme': _organisme_label(categorie, grade_val),
        'vague_sidebar': _vague_sidebar_label(modules),
        'titre_ligne1': _titre_ligne1(formation, categorie),
        'titre': f"POINT JOURNALIER CAT {categorie} — {formation.formation} — {jour.strftime('%d/%m/%Y')}",
        'taux_presence_jour': taux_presence_jour,
        'taux_absence_jour': taux_absence_jour,
        'matin_horaire': matin['horaire'],
        'soir_horaire': soir['horaire'],
    }

    if not full_detail:
        return base

    base['matin'] = matin
    base['soir'] = soir
    return base


def compute_tableau_jour(formation, categorie, jour, secretariat_id=None, grade=None):
    """Construit un point journalier complet pour UNE journée (exports / détail)."""
    cache = _build_pj_cache(
        jour.year, jour.month, [formation.id], [jour], secretariat_id=secretariat_id,
    )
    if isinstance(formation, int):
        formation = cache['formations'].get(formation) or Formation.objects.get(pk=formation)
    return _compute_tableau_cached(
        formation, categorie, jour, cache,
        secretariat_id=secretariat_id, full_detail=True, grade=grade,
    )


def get_tableau_detail(annee, formation_id, categorie, jour, secretariat_id=None, module_ids=None, grade=None):
    """Retourne un seul tableau complet (lazy load côté frontend)."""
    if isinstance(jour, str):
        jour = date.fromisoformat(jour)
    cache = _build_pj_cache(
        annee, jour.month, [formation_id], [jour],
        secretariat_id=secretariat_id, allowed_module_ids=module_ids,
    )
    formation = cache['formations'].get(formation_id)
    if not formation:
        try:
            formation = Formation.objects.get(pk=formation_id)
        except Formation.DoesNotExist:
            return None
    return _compute_tableau_cached(
        formation, categorie, jour, cache,
        secretariat_id=secretariat_id, full_detail=True, grade=grade,
    )


def compute_point_journalier(
    annee=None,
    mois=None,
    categorie=None,
    formation_id=None,
    secretariat_id=None,
    module_ids=None,
    jour=None,
    index_only=False,
):
    """
    Retourne les tableaux journaliers (1 par jour × catégorie × formation).
    index_only=True : métadonnées légères pour la liste (sans blocs MATIN/SOIR).

    Seuls les groupes ayant au moins une séance le jour J apparaissent dans le tableau.
    """
    annee = annee or date.today().year

    if jour:
        try:
            if isinstance(jour, str):
                jour = date.fromisoformat(jour)
        except ValueError:
            jour = None

    jours = [jour] if jour else _jours_activite(annee, mois, formation_id, secretariat_id, module_ids)
    formation_ids = _formation_ids_for_scope(annee, mois, formation_id, secretariat_id, module_ids)

    cache = _build_pj_cache(annee, mois, formation_ids, jours, secretariat_id=secretariat_id, allowed_module_ids=module_ids)

    tableaux = []
    for fid in formation_ids:
        formation = cache['formations'].get(fid)
        if not formation:
            continue

        cats = [categorie] if categorie else _categories_pour_formation(fid, secretariat_id, cache, module_ids)
        if not cats:
            cats = ['—']

        for cat in cats:
            for j in jours:
                modules, multi_grade = _modules_for_tableau(
                    formation, cat, cache, secretariat_id,
                )
                if not modules:
                    continue
                grade_list = sorted({
                    (m.grade or '').strip()
                    for m in modules if (m.grade or '').strip()
                })
                if not grade_list or not multi_grade:
                    grade_list = [None]
                for gr in grade_list:
                    tb = _compute_tableau_cached(
                        formation, cat, j, cache, secretariat_id=secretariat_id,
                        full_detail=not index_only, grade=gr,
                    )
                    if tb:
                        tableaux.append(tb)

    tableaux.sort(key=lambda t: (t['date'], t['categorie'], t['formation_id']))

    categories_avec_donnees = sorted({t['categorie'] for t in tableaux})
    categories = _liste_categories(formation_id, secretariat_id, module_ids)
    formations_idx = {t['formation_id']: t['formation'] for t in tableaux}

    sm_q = _sessions_pj_queryset(
        annee=annee,
        formation_id=formation_id,
        secretariat_id=secretariat_id,
        allowed_module_ids=module_ids,
    )
    mois_avec_donnees = sorted(set(sm_q.values_list('date_journee__month', flat=True)))

    return {
        'annee': annee,
        'mois': mois,
        'tableaux': tableaux,
        'total_tableaux': len(tableaux),
        'categories': categories,
        'categories_avec_donnees': categories_avec_donnees,
        'mois_avec_donnees': mois_avec_donnees,
        'formations': [{'id': k, 'formation': v} for k, v in sorted(formations_idx.items())],
    }


PJ_META_KEYS = (
    'id', 'categorie', 'grade', 'formation_id', 'formation', 'date', 'date_fr', 'jour', 'mois',
    'mois_libelle', 'annee', 'organisme', 'vague_sidebar', 'titre_ligne1', 'titre',
    'taux_presence_jour', 'taux_absence_jour', 'matin_horaire', 'soir_horaire',
)


def compute_point_journalier_avec_tableaux(
    annee=None,
    mois=None,
    categorie=None,
    formation_id=None,
    secretariat_id=None,
    module_ids=None,
):
    """Index léger + tous les tableaux complets (vue d'ensemble Point Journalier)."""
    data = compute_point_journalier(
        annee=annee,
        mois=mois,
        categorie=categorie,
        formation_id=formation_id,
        secretariat_id=secretariat_id,
        module_ids=module_ids,
        index_only=False,
    )
    tableaux_complets = []
    tableaux_index = []
    for tb in data['tableaux']:
        meta = {k: tb[k] for k in PJ_META_KEYS if k in tb}
        tableaux_complets.append({
            'tableau_id': tb['id'],
            'meta': meta,
            'tableau': tb,
        })
        tableaux_index.append(meta)
    data['tableaux'] = tableaux_index
    data['tableaux_complets'] = tableaux_complets
    return data
