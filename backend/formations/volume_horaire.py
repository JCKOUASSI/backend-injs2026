"""Volume horaire : dashboard web et diagnostic admin (modules / séances).

Prévu période = Σ créneaux séances de la période (heure_fin_prevue − heure_debut_prevue).
Prévu contractuel (diagnostic fiche) = ``Module.duree_prevue_heures`` / référentiel.
Réalisé module = Σ min(durée réelle, durée prévue) par séance terminée.
La durée réelle (terminee_le − demarree_le) est plafonnée au créneau planifié de chaque séance.
Sans ``duree_prevue_heures``, repli sur le prévu EDT.
"""

from django.urls import reverse

from formations.models import Module, Secretariat, SessionModule

_MAX_DUREE_SESSION_MIN_DEFAUT = 8 * 60


def _minutes_entre_heures(h_debut, h_fin):
    if not h_debut or not h_fin:
        return None
    return (
        (h_fin.hour * 60 + h_fin.minute + h_fin.second / 60)
        - (h_debut.hour * 60 + h_debut.minute + h_debut.second / 60)
    )


def _session_prevu_minutes(session):
    """Durée planifiée d'une séance (créneau horaire)."""
    prevu = _minutes_entre_heures(
        session.heure_debut_prevue, session.heure_fin_prevue
    )
    if prevu is None or prevu <= 0:
        return 0.0
    return prevu


def _session_elapsed_brut_minutes(session):
    """Durée brute (terminee_le − demarree_le), sans plafond."""
    if not session.demarree_le or not session.terminee_le:
        return 0.0
    elapsed = (session.terminee_le - session.demarree_le).total_seconds() / 60
    return elapsed if elapsed > 0 else 0.0


def _session_realise_minutes(session):
    """Durée comptée : brute plafonnée au créneau planifié de la séance."""
    elapsed = _session_elapsed_brut_minutes(session)
    if elapsed <= 0:
        return 0.0
    plafond = _session_prevu_minutes(session)
    if plafond <= 0:
        plafond, _ = _session_plafond_minutes(session)
    return min(elapsed, plafond)


def _session_plafond_minutes(session):
    """Plafond horaire d'une séance (pour détecter les dépassements séance par séance)."""
    plafond = _minutes_entre_heures(
        session.heure_debut_prevue, session.heure_fin_prevue
    )
    if plafond is None or plafond <= 0:
        return _MAX_DUREE_SESSION_MIN_DEFAUT, True
    return plafond, False


def session_in_date_range(session, date_debut=None, date_fin=None):
    """Vrai si la séance tombe dans l'intervalle inclusif ``date_journee``."""
    if date_debut is None and date_fin is None:
        return True
    d = session.date_journee
    if not d:
        return False
    if date_debut and d < date_debut:
        return False
    if date_fin and d > date_fin:
        return False
    return True


def module_contractual_planned_minutes(module, categorie_code=None):
    """Volume horaire contractuel (minutes) : référentiel formation × catégorie, sinon fiche module."""
    if not module:
        return 0.0
    from .duree_prevue_resolve import _ref_module_volume_hours, _get_majoritaire_categorie, resolve_module_volume_contractuel_heures

    if not categorie_code:
        categorie_code = _get_majoritaire_categorie(module)

    heures = _ref_module_volume_hours(module, categorie_code)
    if heures <= 0:
        heures, _ = resolve_module_volume_contractuel_heures(module, categorie_code=categorie_code)
    return heures * 60 if heures > 0 else 0.0


def module_planned_minutes_for_period(
    module,
    sessions_in_period_count,
    total_sessions_count,
    sessions_in_period=None,
    categorie_code=None,
):
    """Planifié = volume contractuel référentiel (ou fiche) si connu, sinon Σ créneaux EDT.

    L'EDT peut être incomplet : le planifié affiche l'objectif (ex. 16 h), pas seulement
    la somme des séances déjà créées.
    """
    if not sessions_in_period:
        return 0.0
    contractual = module_contractual_planned_minutes(module, categorie_code)
    if contractual > 0:
        return contractual
    return sum(_session_prevu_minutes(s) for s in sessions_in_period)


def accumulate_sessions_volume(sessions, *, date_debut=None, date_fin=None):
    """Agrège prévu / réalisé sur un iterable de séances (règle commune SYGEP)."""
    prevu_min = 0.0
    realise_min = 0.0
    nb_sessions = 0
    nb_sessions_planifiees = 0
    nb_sessions_terminees = 0
    sessions_sans_horaires = 0

    for s in sessions:
        if not session_in_date_range(s, date_debut, date_fin):
            continue
        nb_sessions += 1
        prevu = _session_prevu_minutes(s)
        if prevu > 0:
            prevu_min += prevu
            nb_sessions_planifiees += 1
        elif not (s.heure_debut_prevue and s.heure_fin_prevue):
            sessions_sans_horaires += 1

        realise = _session_realise_minutes(s)
        if realise > 0:
            realise_min += realise
            nb_sessions_terminees += 1

    return {
        'prevu_min': prevu_min,
        'realise_min': realise_min,
        'nb_sessions': nb_sessions,
        'nb_sessions_planifiees': nb_sessions_planifiees,
        'nb_sessions_terminees': nb_sessions_terminees,
        'sessions_sans_horaires': sessions_sans_horaires,
    }


def finalize_volume_totals(prevu_min, realise_min, *, integer_hours=False):
    """Convertit des minutes agrégées en heures + taux (plafond réalisé ≤ prévu)."""
    if integer_hours:
        prevu_h = int(round(prevu_min / 60))
        realise_h = int(round(realise_min / 60))
        if prevu_h > 0:
            realise_h = min(realise_h, prevu_h)
            taux = min(100, int((realise_h / prevu_h) * 100))
        else:
            realise_h = 0
            taux = 0
        return {
            'prevu_heures': prevu_h,
            'realise_heures': realise_h,
            'taux_pct': taux,
            'prevu_minutes': round(prevu_min, 1),
            'realise_minutes': round(min(realise_min, prevu_min) if prevu_min > 0 else 0.0, 1),
        }

    prevu_h = round(prevu_min / 60, 1)
    realise_h = round(realise_min / 60, 1)
    if prevu_h > 0:
        realise_h = min(realise_h, prevu_h)
        taux = min(100.0, round((realise_h / prevu_h) * 100, 1))
    else:
        realise_h = 0.0
        taux = 0.0
    return {
        'prevu_heures': prevu_h,
        'realise_heures': realise_h,
        'taux_pct': taux,
        'prevu_minutes': round(prevu_min, 1),
        'realise_minutes': round(min(realise_min, prevu_min) if prevu_min > 0 else 0.0, 1),
    }


def compute_volume_horaire_from_module_ids(module_ids, date_debut=None, date_fin=None, *, integer_hours=False, group_by_categorie=False):
    """Volume horaire canonique : prévu = Σ créneaux EDT période ; réalisé plafonné.

    Si group_by_categorie=True, retourne un dict par catégorie {categorie: {prevu_heures, realise_heures, ...}}.
    Sinon, retourne les totaux agrégés en utilisant la catégorie majoritaire de chaque module."""
    from .duree_prevue_resolve import _get_module_participants_categories

    module_ids = list(module_ids or [])
    if not module_ids:
        if group_by_categorie:
            return {}
        totals = finalize_volume_totals(0.0, 0.0, integer_hours=integer_hours)
        totals['nb_sessions'] = 0
        return totals

    modules_by_id = {
        m.id: m
        for m in Module.objects.filter(id__in=module_ids).select_related('ref_module')
    }
    sessions = SessionModule.objects.filter(module_id__in=module_ids).only(
        'module_id',
        'heure_debut_prevue',
        'heure_fin_prevue',
        'demarree_le',
        'terminee_le',
        'date_journee',
    )
    sessions_by_module = {}
    for s in sessions:
        sessions_by_module.setdefault(s.module_id, []).append(s)

    if group_by_categorie:
        # Calculer par catégorie
        volumes_by_cat = {}
        for mid in module_ids:
            module = modules_by_id.get(mid)
            if not module:
                continue
            module_sessions = sessions_by_module.get(mid, [])
            in_period = [
                s for s in module_sessions
                if session_in_date_range(s, date_debut, date_fin)
            ]
            # Obtenir les catégories des participants de ce module
            cat_counts = _get_module_participants_categories(module)
            for cat, count in cat_counts.items():
                if cat not in volumes_by_cat:
                    volumes_by_cat[cat] = {'prevu_min': 0.0, 'realise_min': 0.0, 'nb_sessions': 0, 'participants': 0}
                prevu_min = module_planned_minutes_for_period(
                    module, len(in_period), len(module_sessions), in_period, cat
                )
                agg = accumulate_sessions_volume(in_period)
                volumes_by_cat[cat]['prevu_min'] += prevu_min
                volumes_by_cat[cat]['realise_min'] += agg['realise_min']
                volumes_by_cat[cat]['nb_sessions'] += agg['nb_sessions']
                volumes_by_cat[cat]['participants'] += count

        # Convertir en résultats finaux
        result = {}
        for cat, data in volumes_by_cat.items():
            totals = finalize_volume_totals(
                data['prevu_min'], data['realise_min'], integer_hours=integer_hours
            )
            totals['nb_sessions'] = data['nb_sessions']
            totals['participants'] = data['participants']
            result[cat] = totals
        return result

    # Calcul agrégé (comportement par défaut)
    prevu_min = 0.0
    realise_min = 0.0
    nb_sessions = 0
    for mid in module_ids:
        module_sessions = sessions_by_module.get(mid, [])
        in_period = [
            s for s in module_sessions
            if session_in_date_range(s, date_debut, date_fin)
        ]
        prevu_min += module_planned_minutes_for_period(
            modules_by_id.get(mid),
            len(in_period),
            len(module_sessions),
            in_period,
        )
        agg = accumulate_sessions_volume(in_period)
        realise_min += agg['realise_min']
        nb_sessions += agg['nb_sessions']

    totals = finalize_volume_totals(
        prevu_min,
        realise_min,
        integer_hours=integer_hours,
    )
    totals['nb_sessions'] = nb_sessions
    return totals


def compute_volume_horaire_per_module_ids(
    module_ids, date_debut=None, date_fin=None, *, integer_hours=False, include_categories=False,
):
    """VH prévu / réalisé par ``module_id`` (même logique que le dashboard).

    Si include_categories=True, ajoute les volumes par catégorie dans le résultat."""
    from .duree_prevue_resolve import _get_module_participants_categories

    module_ids = list(module_ids or [])
    if not module_ids:
        return {}

    modules_by_id = {
        m.id: m
        for m in Module.objects.filter(id__in=module_ids).select_related('ref_module')
    }
    sessions = SessionModule.objects.filter(module_id__in=module_ids).only(
        'module_id',
        'heure_debut_prevue',
        'heure_fin_prevue',
        'demarree_le',
        'terminee_le',
        'date_journee',
    )
    sessions_by_module = {}
    for s in sessions:
        sessions_by_module.setdefault(s.module_id, []).append(s)

    out = {}
    for mid in module_ids:
        module = modules_by_id.get(mid)
        module_sessions = sessions_by_module.get(mid, [])
        in_period = [
            s for s in module_sessions
            if session_in_date_range(s, date_debut, date_fin)
        ]
        prevu_min = module_planned_minutes_for_period(
            module,
            len(in_period),
            len(module_sessions),
            in_period,
        )
        agg = accumulate_sessions_volume(in_period)
        totals = finalize_volume_totals(
            prevu_min,
            agg['realise_min'],
            integer_hours=integer_hours,
        )
        totals['nb_sessions'] = agg['nb_sessions']

        # Si demandé, ajouter les volumes par catégorie
        if include_categories and module:
            cat_counts = _get_module_participants_categories(module)
            volumes_by_cat = {}
            for cat in cat_counts.keys():
                cat_prevu_min = module_planned_minutes_for_period(
                    module, len(in_period), len(module_sessions), in_period, cat
                )
                cat_totals = finalize_volume_totals(
                    cat_prevu_min, agg['realise_min'], integer_hours=integer_hours
                )
                cat_totals['participants'] = cat_counts[cat]
                volumes_by_cat[cat] = cat_totals
            totals['volumes_par_categorie'] = volumes_by_cat
            totals['categories'] = list(cat_counts.keys())

        out[mid] = totals
    return out


def compute_volume_horaire_from_modules(modules_qs, date_debut=None, date_fin=None, *, integer_hours=False, group_by_categorie=False):
    module_ids = list(modules_qs.values_list('pk', flat=True))
    return compute_volume_horaire_from_module_ids(
        module_ids,
        date_debut=date_debut,
        date_fin=date_fin,
        integer_hours=integer_hours,
        group_by_categorie=group_by_categorie,
    )


def _accumulate_module_session_volumes(module, *, date_debut=None, date_fin=None, categorie_code=None):
    """Agrège prévu (Σ créneaux EDT période) et réalisé (séances terminées) pour un module.

    Si categorie_code est fourni, utilise le volume horaire spécifique à cette catégorie.
    Sinon, utilise la catégorie majoritaire des participants."""
    from .duree_prevue_resolve import _get_majoritaire_categorie

    sessions = list(
        SessionModule.objects.filter(module=module).only(
            'heure_debut_prevue', 'heure_fin_prevue', 'demarree_le', 'terminee_le', 'date_journee',
        )
    )
    in_period = [
        s for s in sessions
        if session_in_date_range(s, date_debut, date_fin)
    ]
    agg_edt = accumulate_sessions_volume(sessions, date_debut=date_debut, date_fin=date_fin)
    agg = accumulate_sessions_volume(in_period)

    # Déterminer la catégorie à utiliser
    if not categorie_code:
        categorie_code = _get_majoritaire_categorie(module)

    prevu_min = module_planned_minutes_for_period(
        module,
        len(in_period),
        len(sessions),
        in_period,
        categorie_code,
    )
    prevu_edt_min = agg_edt['prevu_min']
    prevu_h = round(prevu_min / 60, 1)
    prevu_edt_h = round(prevu_edt_min / 60, 1)
    realise_h = round(agg['realise_min'] / 60, 1)
    if prevu_h > 0:
        realise_h = min(realise_h, prevu_h)

    return {
        'prevu_min': prevu_min,
        'prevu_edt_min': prevu_edt_min,
        'realise_min': agg['realise_min'],
        'prevu_h': prevu_h,
        'prevu_edt_h': prevu_edt_h,
        'realise_h': realise_h,
        'compte_h': realise_h,
        'ecart_h': round(realise_h - prevu_h, 1),
        'nb_sessions': agg['nb_sessions'],
        'nb_sessions_planifiees': agg['nb_sessions_planifiees'],
        'nb_sessions_terminees': agg['nb_sessions_terminees'],
        'sessions_sans_horaires': agg['sessions_sans_horaires'],
        'duree_fiche_h': round(float(module.duree_prevue_heures or 0), 1),
        'taux_realise_pct': (
            round(realise_h / prevu_h * 100, 1) if prevu_h > 0 else None
        ),
        'categorie_utilisee': categorie_code,
    }


def modules_qs_for_admin(request):
    """Modules visibles selon le rôle admin (aligné dashboard)."""
    from admin_mixins import admin_user_has_global_access

    qs = Module.objects.select_related('formation', 'secretariat', 'secretariat__type')
    if not request.user.is_staff:
        return qs.none()

    if admin_user_has_global_access(request.user):
        secretariat_id = (request.GET.get('secretariat') or '').strip()
        if secretariat_id.isdigit():
            qs = qs.filter(secretariat_id=int(secretariat_id))
        return qs

    role = getattr(request.user, 'role', None)
    secretariat = getattr(request.user, 'secretariat', None)
    if role in ('SECRETARIAT', 'CHEF_SECRETARIAT') and secretariat:
        return qs.filter(secretariat=secretariat)
    if role == 'ENCADRANT':
        return qs.filter(superviseur=request.user)
    return qs.none()


def secretariats_for_admin_filter(request):
    from admin_mixins import admin_user_has_global_access

    if not admin_user_has_global_access(request.user):
        return []
    return list(
        Secretariat.objects.select_related('type')
        .order_by('nom')
        .values('id', 'nom', 'type__libelle')
    )


def compute_dashboard_volume_horaire(modules_qs, date_debut=None, date_fin=None):
    """Volume agrégé dashboard web : prévu/réalisé par séances, taux ≤ 100 %."""
    totals = compute_volume_horaire_from_modules(
        modules_qs,
        date_debut=date_debut,
        date_fin=date_fin,
        integer_hours=True,
    )
    return totals['realise_heures'], totals['prevu_heures'], totals['taux_pct']


def _module_admin_url(module_id):
    try:
        return reverse('admin:formations_module_change', args=[module_id])
    except Exception:
        return None


def _session_admin_url(session_id):
    try:
        return reverse('admin:formations_sessionmodule_change', args=[session_id])
    except Exception:
        return None


def compute_modules_diagnostic(modules_qs):
    """Diagnostic par module : prévu (séances planifiées) vs réalisé (séances terminées)."""
    rows = []
    totaux = {
        'prevu_h': 0.0,
        'realise_h': 0.0,
        'compte_dashboard_h': 0.0,
        'duree_fiche_h': 0.0,
    }

    for module in modules_qs:
        vol = _accumulate_module_session_volumes(module)

        sec_label = ''
        if module.secretariat_id:
            sec_label = module.secretariat.nom or ''
            if module.secretariat.type_id:
                sec_label = f"{module.secretariat.type.libelle} — {sec_label}".strip(' —')

        rows.append({
            'module_id': module.pk,
            'module_label': module.intitule or '',
            'formation': module.formation.formation if module.formation_id else '',
            'secretariat': sec_label,
            'statut': module.statut or '',
            'prevu_h': vol['prevu_h'],
            'realise_h': vol['realise_h'],
            'compte_dashboard_h': vol['compte_h'],
            'duree_fiche_h': vol['duree_fiche_h'],
            'ecart_h': vol['ecart_h'],
            'nb_sessions': vol['nb_sessions'],
            'nb_sessions_planifiees': vol['nb_sessions_planifiees'],
            'nb_sessions_terminees': vol['nb_sessions_terminees'],
            'sessions_sans_horaires': vol['sessions_sans_horaires'],
            'depasse': vol['ecart_h'] > 0,
            'module_url': _module_admin_url(module.pk),
            'taux_realise_pct': vol['taux_realise_pct'],
        })

        totaux['prevu_h'] += vol['prevu_h']
        totaux['realise_h'] += vol['realise_h']
        totaux['compte_dashboard_h'] += vol['compte_h']
        totaux['duree_fiche_h'] += vol['duree_fiche_h']

    for key in totaux:
        totaux[key] = round(totaux[key], 1)
    totaux['ecart_h'] = round(totaux['realise_h'] - totaux['prevu_h'], 1)
    if totaux['prevu_h'] > 0:
        totaux['taux_realise_pct'] = round(
            totaux['realise_h'] / totaux['prevu_h'] * 100, 1
        )
    else:
        totaux['taux_realise_pct'] = None

    return rows, totaux


def compute_sessions_depassement(modules_qs):
    """Séances terminées dont la durée réelle dépasse l'horaire planifié."""
    rows = []
    module_ids = list(modules_qs.values_list('pk', flat=True))
    if not module_ids:
        return rows

    modules_by_id = {m.pk: m for m in modules_qs}
    sessions = (
        SessionModule.objects.filter(module_id__in=module_ids)
        .exclude(demarree_le__isnull=True)
        .exclude(terminee_le__isnull=True)
        .select_related('module__formation')
        .order_by('-date_journee', '-numero')
    )

    for s in sessions:
        elapsed = _session_elapsed_brut_minutes(s)
        if elapsed <= 0:
            continue
        plafond, sans_horaires = _session_plafond_minutes(s)
        depasse_min = elapsed - plafond
        if depasse_min <= 1:
            continue

        module = modules_by_id.get(s.module_id)
        rows.append({
            'session_id': s.pk,
            'date': s.date_journee,
            'numero': s.numero,
            'intitule': s.intitule or f"Séance {s.numero}",
            'module_id': s.module_id,
            'module_label': module.intitule if module else '',
            'formation': (
                module.formation.formation
                if module and module.formation_id else ''
            ),
            'prevu_seance_h': round(plafond / 60, 2),
            'realise_h': round(elapsed / 60, 2),
            'depasse_h': round(depasse_min / 60, 2),
            'sans_horaires_planifies': sans_horaires,
            'session_url': _session_admin_url(s.pk),
            'module_url': _module_admin_url(s.module_id),
        })

    rows.sort(key=lambda r: r['depasse_h'], reverse=True)
    return rows


def run_organisation_diagnostic(request, depassements_only=False):
    """Diagnostic global modules + séances (dashboard web)."""
    modules_qs = modules_qs_for_admin(request)
    module_rows, totaux = compute_modules_diagnostic(modules_qs)
    if depassements_only:
        module_rows = [r for r in module_rows if r['depasse']]
    module_rows.sort(key=lambda r: r['ecart_h'], reverse=True)

    session_rows = compute_sessions_depassement(modules_qs)
    effectue, total, taux = compute_dashboard_volume_horaire(modules_qs)

    return {
        'modules': module_rows,
        'sessions': session_rows,
        'totaux': totaux,
        'dashboard': {
            'effectue_h': effectue,
            'prevu_h': total,
            'taux_pct': taux,
        },
        'nb_modules': len(module_rows),
        'nb_sessions_depassement': len(session_rows),
        'secretariats': secretariats_for_admin_filter(request),
        'selected_secretariat': (request.GET.get('secretariat') or '').strip(),
        'depassements_only': depassements_only,
    }
