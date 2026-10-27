"""Reconstitution partielle depuis AuditLog (post-migration 0076, sans dump)."""

import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from django.db import transaction
from django.utils import timezone

from formations.models import Formateur, Module, ModuleParticipant, Participant, SessionModule
from presences.models import AuditLog, Pointage


def _parse_date(val):
    if not val:
        return None
    if hasattr(val, 'year'):
        return val
    try:
        return datetime.strptime(str(val)[:10], '%Y-%m-%d').date()
    except ValueError:
        return None


def _parse_numero(val):
    if val is None or val == '':
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def collect_orphan_session_events(audit_qs, existing_session_ids, existing_module_ids):
    """
    Regroupe les événements SEANCE_START/STOP dont session_id n'existe plus.

    Retourne (events_by_module, meta_by_module) où meta contient formation_id et intitulé.
    """
    by_module = defaultdict(lambda: defaultdict(dict))
    meta_by_module = {}

    for log in audit_qs.filter(action__in=(
        AuditLog.Action.SEANCE_START,
        AuditLog.Action.SEANCE_STOP,
    )).order_by('timestamp'):
        extra = log.extra or {}
        sid = extra.get('session_id')
        mid = extra.get('module_id')
        if not sid or sid in existing_session_ids:
            continue
        if not mid or mid in existing_module_ids:
            continue

        slot = by_module[mid][sid]
        slot['intitule'] = extra.get('module_intitule') or ''
        slot['date_journee'] = _parse_date(extra.get('date_journee'))
        slot['numero'] = _parse_numero(
            extra.get('session_numero') if extra.get('session_numero') is not None
            else extra.get('numero')
        )
        slot['formation_id'] = log.formation_id
        if log.action == AuditLog.Action.SEANCE_START:
            slot['start'] = log.timestamp
        else:
            slot['stop'] = log.timestamp

        if mid not in meta_by_module:
            meta_by_module[mid] = {
                'formation_id': log.formation_id,
                'intitule': (extra.get('module_intitule') or '').strip(),
            }

    return by_module, meta_by_module


def _session_slot_set(module):
    return frozenset(
        (s.date_journee, s.numero)
        for s in module.sessions.all()
    )


def _event_slot_set(events):
    return frozenset(
        (e['date_journee'], e['numero'])
        for e in events.values()
        if e.get('date_journee') and e.get('numero') is not None
    )


def _event_dates(events):
    return frozenset(
        e['date_journee'] for e in events.values() if e.get('date_journee')
    )


def _stop_time_fingerprint(events):
    """Empreinte date → heure de fin (UTC) pour distinguer les groupes parallèles."""
    fp = {}
    for event in events.values():
        day = event.get('date_journee')
        stop = event.get('stop')
        if day and stop:
            fp[day] = stop
    return fp


def _start_time_fingerprint(events):
    """Empreinte date → heure de début (UTC)."""
    fp = {}
    for event in events.values():
        day = event.get('date_journee')
        start = event.get('start')
        if day and start:
            fp[day] = start
    return fp


def _event_numeros(events):
    nums = {e.get('numero') for e in events.values() if e.get('numero') is not None}
    return nums or {2}


_SCAN_ACTIONS = (
    AuditLog.Action.SCAN_SECURE_ENTREE,
    AuditLog.Action.SCAN_SECURE_SORTIE,
    AuditLog.Action.FORCE_ENTREE,
    AuditLog.Action.FORCE_SORTIE,
)


def _session_windows(events):
    """Fenêtres (début, fin) par séance orpheline."""
    windows = []
    for event in events.values():
        start = event.get('start')
        stop = event.get('stop')
        if start and stop:
            windows.append((start, stop))
        elif start:
            windows.append((start, start + timedelta(hours=10)))
        elif stop:
            windows.append((stop - timedelta(hours=4), stop))
    return windows


def _inscriptions_by_matricule(survivor_ids, intitule):
    """Matricule participant → ids de modules survivants où il est inscrit."""
    by_matricule = defaultdict(set)
    if not survivor_ids:
        return by_matricule
    rows = ModuleParticipant.objects.filter(
        module_id__in=survivor_ids,
        module__intitule__iexact=intitule,
    ).values_list('participant__matricule', 'module_id')
    for matricule, module_id in rows:
        if matricule:
            by_matricule[matricule].add(module_id)
    return by_matricule


def _required_slot_count(events):
    slots = _event_slot_set(events)
    if slots:
        return len(slots)
    return len(_event_dates(events))


def _exit_scan_module_scores(formation_id, intitule, events, survivors, inscriptions=None):
    """
    Badgeages participants inscrits sur un seul module (ou groupe concordant),
    fenêtre autour de la dernière fin de séance audit.
    """
    if inscriptions is None:
        inscriptions = _inscriptions_by_matricule([m.id for m in survivors], intitule)

    stops = [e.get('stop') for e in events.values() if e.get('stop')]
    if not stops or not formation_id:
        return Counter()

    last_stop = max(stops)
    window_start = last_stop - timedelta(minutes=8)
    window_end = last_stop + timedelta(minutes=2)

    survivors_by_id = {m.id: m for m in survivors}
    scores = Counter()
    scans = AuditLog.objects.filter(
        formation_id=formation_id,
        action__in=_SCAN_ACTIONS,
        timestamp__gte=window_start,
        timestamp__lte=window_end,
        cible_type='participant',
    ).exclude(cible_numero='')

    for log in scans:
        mods = inscriptions.get(log.cible_numero, ())
        if len(mods) == 1:
            scores[next(iter(mods))] += 1
            continue
        if len(mods) < 2:
            continue
        participant = Participant.objects.filter(matricule=log.cible_numero).first()
        if not participant:
            continue
        pg = (participant.groupe or '').strip().upper()
        for module_id in mods:
            mod = survivors_by_id.get(module_id)
            if mod and (mod.groupe or '').strip().upper() == pg:
                scores[module_id] += 1
                break

    return scores


def _audit_slot_covered(module, day, numero):
    """Créneau audit couvert si (date, numéro) exact ou séance unique ce jour-là."""
    if SessionModule.objects.filter(
        module=module, date_journee=day, numero=numero,
    ).exists():
        return True
    return SessionModule.objects.filter(module=module, date_journee=day).count() == 1


def _edt_slot_score(events, module):
    """Nombre de créneaux audit présents dans l'EDT du survivant."""
    slots = _event_slot_set(events)
    if slots:
        return sum(1 for day, numero in slots if _audit_slot_covered(module, day, numero))
    dates = _event_dates(events)
    if not dates:
        return 0
    return sum(
        1 for day in dates
        if SessionModule.objects.filter(module=module, date_journee=day).exists()
    )


def _empty_slot_score(events, module):
    slots = _event_slot_set(events)
    count = 0
    for day, numero in slots:
        if SessionModule.objects.filter(
            module=module, date_journee=day, numero=numero, demarree_le__isnull=True,
        ).exists():
            count += 1
            continue
        day_sessions = list(
            SessionModule.objects.filter(module=module, date_journee=day)
        )
        if len(day_sessions) == 1 and not day_sessions[0].demarree_le:
            count += 1
    return count


def _session_for_audit_day(module, day, numeros):
    """Séance EDT pour un jour audit (numéro exact ou séance unique)."""
    for numero in numeros:
        try:
            return SessionModule.objects.get(
                module=module, date_journee=day, numero=numero,
            )
        except SessionModule.DoesNotExist:
            continue
    day_sessions = list(
        SessionModule.objects.filter(module=module, date_journee=day).order_by('numero')
    )
    if len(day_sessions) == 1:
        return day_sessions[0]
    return None


# Seuil d'écart terminee_le ↔ audit (secondes) pour l'appariement phase 1.
TERMINEE_MATCH_MAX_SECONDS = 120


def _best_terminee_delta(events, module):
    """Écart minimal en secondes entre un stop audit et terminee_le, ou None."""
    fp_stop = _stop_time_fingerprint(events)
    numeros = _event_numeros(events)
    best = None
    for day, stop_ts in fp_stop.items():
        session = _session_for_audit_day(module, day, numeros)
        if not session or not session.terminee_le:
            continue
        delta = abs((session.terminee_le - stop_ts).total_seconds())
        if best is None or delta < best:
            best = delta
    return best


def _edt_is_full(events, module):
    required = _required_slot_count(events)
    return required > 0 and _edt_slot_score(events, module) >= required


def _record_mapping(mapping, used_survivors, mid, mod, meta_by_module, sessions, method, **extra):
    mapping[mid] = mod
    used_survivors.add(mod.id)
    req = _required_slot_count(sessions)
    edt = _edt_slot_score(sessions, mod)
    meta = meta_by_module.setdefault(mid, {})
    meta['inferred_groupe'] = mod.groupe
    meta['edt_coverage'] = f'{edt}/{req}'
    meta['match_method'] = method
    meta.update(extra)


def _parse_explicit_mapping(raw):
    """Format : « 321:327,312:372 » ou JSON objet."""
    if not raw:
        return {}
    raw = raw.strip()
    if raw.startswith('{'):
        data = json.loads(raw)
        return {int(k): int(v) for k, v in data.items()}
    out = {}
    for part in raw.split(','):
        part = part.strip()
        if not part or ':' not in part:
            continue
        deleted, survivor = part.split(':', 1)
        out[int(deleted.strip())] = int(survivor.strip())
    return out


def match_deleted_modules_to_survivors(
    deleted_by_module, meta_by_module, *, explicit_mapping=None,
):
    """
    Appariement 1:1 déterministe (post-migration 0076).

    1. Mapping explicite (--mapping), validé contre l'EDT.
    2. terminee_le à ±120 s (données déjà en base sur le survivant).
    3. Règle 0076 : plus petit survivant.id > supprimé.id avec EDT complet.

    Les étapes 2 et 3 ne rivalisent plus via un score glouton global.
    """
    if not deleted_by_module:
        return {}

    explicit = explicit_mapping or {}

    by_scope = defaultdict(dict)
    for mid, sessions in deleted_by_module.items():
        meta = meta_by_module.get(mid, {})
        formation_id = meta.get('formation_id')
        intitule = (meta.get('intitule') or '').strip()
        if not intitule:
            continue
        by_scope[(formation_id, intitule.upper())][mid] = sessions

    mapping = {}
    for (formation_id, intitule_key), modules_dict in by_scope.items():
        survivors = list(
            Module.objects.filter(
                formation_id=formation_id,
                intitule__iexact=intitule_key,
            ).prefetch_related('sessions')
        )
        survivors_by_id = {m.id: m for m in survivors}
        if not survivors:
            continue

        pending = set(modules_dict.keys())
        used_survivors = set()

        # Étape 0 — mapping explicite (prioritaire, stable en prod).
        for mid in list(pending):
            survivor_id = explicit.get(mid)
            if not survivor_id:
                continue
            mod = survivors_by_id.get(survivor_id)
            sessions = modules_dict[mid]
            if not mod:
                meta_by_module.setdefault(mid, {})['match_error'] = (
                    f'survivant #{survivor_id} introuvable'
                )
                continue
            if not _edt_is_full(sessions, mod):
                meta_by_module.setdefault(mid, {})['match_warning'] = (
                    f'EDT incomplet sur #{survivor_id} '
                    f'({_edt_slot_score(sessions, mod)}/{_required_slot_count(sessions)})'
                )
            _record_mapping(
                mapping, used_survivors, mid, mod, meta_by_module, sessions,
                'explicit', match_score=0,
            )
            pending.discard(mid)

        # Étape 1 — terminee_le proche (survivant qui a déjà les horaires).
        terminee_edges = []
        for mid in pending:
            sessions = modules_dict[mid]
            for mod in survivors:
                if mod.id in used_survivors:
                    continue
                if _edt_slot_score(sessions, mod) == 0:
                    continue
                delta = _best_terminee_delta(sessions, mod)
                if delta is None or delta > TERMINEE_MATCH_MAX_SECONDS:
                    continue
                edt_full = 1 if _edt_is_full(sessions, mod) else 0
                id_gap = mod.id - mid if mod.id > mid else 99999
                terminee_edges.append((delta, -edt_full, id_gap, mid, mod))
        terminee_edges.sort()
        for delta, _neg_full, _gap, mid, mod in terminee_edges:
            if mid not in pending or mod.id in used_survivors:
                continue
            _record_mapping(
                mapping, used_survivors, mid, mod, meta_by_module,
                modules_dict[mid], 'terminee',
                match_score=round(delta, 1),
            )
            pending.discard(mid)

        # Étape 2 — migration 0076 : min(survivant.id - supprimé.id), EDT complet.
        for mid in sorted(pending):
            sessions = modules_dict[mid]
            best_mod = None
            best_gap = None
            for mod in survivors:
                if mod.id in used_survivors or mod.id <= mid:
                    continue
                if not _edt_is_full(sessions, mod):
                    continue
                gap = mod.id - mid
                if best_gap is None or gap < best_gap:
                    best_gap = gap
                    best_mod = mod
            if best_mod:
                _record_mapping(
                    mapping, used_survivors, mid, best_mod, meta_by_module,
                    sessions, 'dedup_0076', match_score=best_gap,
                )
                pending.discard(mid)

        # Étape 3 — secours : meilleure couverture EDT (affichage d'avertissement).
        for mid in sorted(pending):
            sessions = modules_dict[mid]
            best_mod = None
            best_rank = None
            for mod in survivors:
                if mod.id in used_survivors:
                    continue
                edt = _edt_slot_score(sessions, mod)
                if edt <= 0:
                    continue
                edt_full = 1 if _edt_is_full(sessions, mod) else 0
                id_gap = (mod.id - mid) if mod.id > mid else 99999
                rank = (edt_full, edt, -id_gap)
                if best_rank is None or rank > best_rank:
                    best_rank = rank
                    best_mod = mod
            if best_mod:
                _record_mapping(
                    mapping, used_survivors, mid, best_mod, meta_by_module,
                    sessions, 'edt_partial',
                    match_score=best_rank[1],
                    match_warning='EDT incomplet — vérifier manuellement',
                )
                pending.discard(mid)

    return mapping


def _resolve_session(module, date_j, numero, events_for_day):
    """Retrouve la séance EDT cible (numéro exact, sinon séance unique du jour)."""
    if date_j is None:
        return None

    if numero is not None:
        try:
            return SessionModule.objects.get(
                module=module,
                date_journee=date_j,
                numero=numero,
            )
        except SessionModule.DoesNotExist:
            pass

    day_sessions = list(
        SessionModule.objects.filter(module=module, date_journee=date_j).order_by('numero')
    )
    if len(day_sessions) == 1:
        return day_sessions[0]

    if numero is not None:
        for session in day_sessions:
            if session.numero == numero:
                return session

    return None


def _merge_session_events(sessions_by_id):
    """Fusionne les événements audit par (date_journee, numero)."""
    merged = defaultdict(dict)
    for event in sessions_by_id.values():
        date_j = event.get('date_journee')
        numero = event.get('numero')
        if not date_j:
            continue
        key = (date_j, numero)
        if event.get('start'):
            merged[key]['start'] = event['start']
        if event.get('stop'):
            merged[key]['stop'] = event['stop']
        merged[key]['date_journee'] = date_j
        merged[key]['numero'] = numero
    return dict(merged)


def ensure_audit_edt_slots(module, merged, *, dry_run=False):
    """
    Crée les créneaux EDT (date, numéro) absents du survivant mais présents dans l'audit.
    Copie horaires prévus depuis un module parallèle (#0b578e…) si disponible.
    """
    stats = {'created': 0}
    intitule = module.intitule
    formation_id = module.formation_id

    for (date_j, numero) in merged:
        if _resolve_session(module, date_j, numero, {}):
            continue

        template = SessionModule.objects.filter(
            module__formation_id=formation_id,
            module__intitule__iexact=intitule,
            date_journee=date_j,
            numero=numero,
        ).first()

        stats['created'] += 1
        if dry_run:
            continue

        SessionModule.objects.create(
            module=module,
            date_journee=date_j,
            numero=numero,
            intitule=(template.intitule if template else '') or f'Séance {numero}',
            heure_debut_prevue=template.heure_debut_prevue if template else None,
            heure_fin_prevue=template.heure_fin_prevue if template else None,
            auto_demarrage=template.auto_demarrage if template else True,
        )

    return stats


def apply_session_recovery(module, sessions_by_id, *, dry_run=False, create_missing_edt=True):
    """Repose demarree_le / terminee_le sur les séances EDT du module conservé."""
    stats = {
        'updated': 0,
        'skipped': 0,
        'missing': 0,
        'already_complete': 0,
        'no_slot': 0,
        'edt_created': 0,
    }

    merged = _merge_session_events(sessions_by_id)
    stats['no_slot'] = sum(
        1 for event in sessions_by_id.values() if not event.get('date_journee')
    )

    if create_missing_edt and merged:
        edt_stats = ensure_audit_edt_slots(module, merged, dry_run=dry_run)
        stats['edt_created'] = edt_stats['created']

    for key, event in merged.items():
        date_j, numero = key
        session = _resolve_session(module, date_j, numero, event)
        if not session:
            if create_missing_edt and dry_run:
                stats['updated'] += 1
            else:
                stats['missing'] += 1
            continue

        if session.demarree_le and session.terminee_le:
            stats['already_complete'] += 1
            continue

        updates = []
        if event.get('start') and not session.demarree_le:
            session.demarree_le = event['start']
            updates.append('demarree_le')
        if event.get('stop') and not session.terminee_le:
            session.terminee_le = event['stop']
            updates.append('terminee_le')

        if not updates:
            stats['skipped'] += 1
            continue

        if not dry_run:
            session.save(update_fields=updates)
        stats['updated'] += 1

    if not dry_run and stats['updated']:
        open_count = module.sessions.filter(
            demarree_le__isnull=False,
            terminee_le__isnull=True,
        ).count()
        if open_count:
            if module.statut != 'EN_COURS':
                module.statut = 'EN_COURS'
                module.save(update_fields=['statut'])
        elif module.sessions.filter(demarree_le__isnull=False).exists():
            if module.statut not in ('TERMINEE', 'EN_COURS'):
                module.statut = 'TERMINEE'
                module.save(update_fields=['statut'])

    return stats


def recover_sessions_from_audit(audit_qs, *, dry_run=False, explicit_mapping=None):
    existing_session_ids = set(SessionModule.objects.values_list('id', flat=True))
    existing_module_ids = set(Module.objects.values_list('id', flat=True))
    deleted_by_module, meta_by_module = collect_orphan_session_events(
        audit_qs, existing_session_ids, existing_module_ids,
    )
    mapping = match_deleted_modules_to_survivors(
        deleted_by_module, meta_by_module, explicit_mapping=explicit_mapping,
    )

    results = []
    totals = {
        'modules': 0,
        'sessions_updated': 0,
        'sessions_missing': 0,
        'edt_created': 0,
        'unmapped': 0,
    }

    for mid, sessions in deleted_by_module.items():
        survivor = mapping.get(mid)
        if not survivor:
            totals['unmapped'] += 1
            results.append({
                'deleted_module_id': mid,
                'survivor': None,
                'stats': None,
                'meta': meta_by_module.get(mid),
            })
            continue

        if dry_run:
            stats = apply_session_recovery(survivor, sessions, dry_run=True)
        else:
            with transaction.atomic():
                stats = apply_session_recovery(survivor, sessions, dry_run=False)

        totals['modules'] += 1
        totals['sessions_updated'] += stats['updated']
        totals['sessions_missing'] += stats['missing']
        totals['edt_created'] += stats.get('edt_created', 0)
        results.append({
            'deleted_module_id': mid,
            'survivor': survivor,
            'stats': stats,
            'meta': meta_by_module.get(mid),
        })

    return results, totals, mapping


def _resolve_personne(cible_type, cible_numero):
    if cible_type == 'formateur':
        return Formateur.objects.filter(numerobadge=cible_numero).first(), 'formateur'
    if cible_type == 'participant':
        return Participant.objects.filter(matricule=cible_numero).first(), 'participant'
    return None, cible_type


def _find_module_for_scan(log, personne, type_personne, *, intitule_hint='', module_mapping=None,
                          deleted_by_module=None, inscriptions_by_matricule=None):
    if not log.formation_id or not personne:
        return None

    if module_mapping and deleted_by_module:
        hit = _find_module_from_audit_windows(
            log, module_mapping, deleted_by_module, inscriptions_by_matricule,
        )
        if hit:
            return hit

    def _candidates(qs):
        modules = list(qs.prefetch_related('sessions'))
        day = timezone.localtime(log.timestamp).date()
        started = [m for m in modules if m.sessions.filter(
            date_journee=day, demarree_le__isnull=False,
        ).exists()]
        if len(started) == 1:
            return started[0]
        if len(modules) == 1:
            return modules[0]
        return None

    qs = Module.objects.filter(formation_id=log.formation_id)
    if intitule_hint:
        qs = qs.filter(intitule__iexact=intitule_hint)

    if type_personne == 'participant':
        insc_modules = list(
            Module.objects.filter(
                formation_id=log.formation_id,
                module_participants__participant=personne,
            ).distinct().prefetch_related('sessions')
        )
        if intitule_hint:
            insc_modules = [m for m in insc_modules if m.intitule.upper() == intitule_hint.upper()]
        if len(insc_modules) == 1:
            return insc_modules[0]
        if insc_modules:
            day = timezone.localtime(log.timestamp).date()
            started = [m for m in insc_modules if m.sessions.filter(
                date_journee=day, demarree_le__isnull=False,
            ).exists()]
            if len(started) == 1:
                return started[0]

        grade = getattr(personne, 'grade', '') or ''
        groupe = getattr(personne, 'groupe', '') or ''
        vague = getattr(personne, 'vague', '') or ''
        for filters in (
            {'grade__iexact': grade, 'groupe__iexact': groupe, 'vague__iexact': vague},
            {'grade__iexact': grade, 'groupe__iexact': groupe},
            {'grade__iexact': grade},
            {},
        ):
            filt = {k: v for k, v in filters.items() if v}
            hit = _candidates(qs.filter(**filt) if filt else qs)
            if hit:
                return hit
    return _candidates(qs)


def _find_scan_target(log, personne, type_personne, module_mapping, deleted_by_module):
    """
    Cible (module, séance) d'un badgeage via mapping explicite + groupe participant.
    Stable même quand plusieurs groupes ont des séances parallèles le même jour.
    """
    if not module_mapping or not deleted_by_module or not personne:
        return None, None

    ts = log.timestamp
    pg = ''
    if type_personne == 'participant':
        pg = (getattr(personne, 'groupe', None) or '').strip().upper()

    best = None
    for deleted_id, survivor in module_mapping.items():
        if pg and (survivor.groupe or '').strip().upper() != pg:
            continue
        events = deleted_by_module.get(deleted_id, {})
        for event in events.values():
            start = event.get('start')
            stop = event.get('stop')
            in_window = False
            if start and stop and start <= ts <= stop:
                in_window = True
            elif stop and abs((stop - ts).total_seconds()) <= 900:
                in_window = True
            elif start and not stop and abs((start - ts).total_seconds()) <= 900:
                in_window = True
            if not in_window:
                continue
            date_j = event.get('date_journee')
            numero = event.get('numero')
            session = _resolve_session(survivor, date_j, numero, event)
            if not session:
                continue
            dist = 0
            if start:
                dist = abs((start - ts).total_seconds())
            rank = (dist, deleted_id)
            if best is None or rank < best[0]:
                best = (rank, survivor, session)

    if not best:
        return None, None
    return best[1], best[2]


def _find_module_from_audit_windows(log, module_mapping, deleted_by_module, inscriptions=None):
    """Retrouve le module survivant via fenêtres séance audit + inscriptions."""
    ts = log.timestamp
    matricule = log.cible_numero if log.cible_type == 'participant' else ''
    hits = []

    for deleted_id, survivor in module_mapping.items():
        events = deleted_by_module.get(deleted_id, {})
        in_window = False
        for event in events.values():
            start = event.get('start')
            stop = event.get('stop')
            if start and stop and start <= ts <= stop:
                in_window = True
                break
            if stop and abs((stop - ts).total_seconds()) <= 1200:
                in_window = True
                break
        if not in_window:
            continue
        if matricule and inscriptions is not None:
            if survivor.id in inscriptions.get(matricule, ()):
                hits.append(survivor)
        else:
            hits.append(survivor)

    unique = {m.id: m for m in hits}
    if len(unique) == 1:
        return next(iter(unique.values()))
    return None


def _find_session_for_scan(module, ts):
    day = timezone.localtime(ts).date()
    sessions = list(
        module.sessions.filter(
            date_journee=day,
        ).order_by('numero')
    )
    started = [s for s in sessions if s.demarree_le]
    for s in started:
        start = s.demarree_le
        end = s.terminee_le or ts
        if start <= ts <= end:
            return s
    if len(started) == 1:
        return started[0]
    if len(sessions) == 1:
        return sessions[0]
    empty = [s for s in sessions if not s.demarree_le]
    if len(empty) == 1:
        return empty[0]
    return None


def relink_recovered_pointages(
    audit_qs, module_mapping, deleted_by_module, *, dry_run=False,
):
    """Rattache les pointages existants à la bonne séance (post-recover)."""
    entree_actions = (
        AuditLog.Action.SCAN_SECURE_ENTREE,
        AuditLog.Action.FORCE_ENTREE,
    )
    survivor_ids = {m.id for m in module_mapping.values()}
    stats = {'relinked': 0, 'unchanged': 0, 'no_target': 0, 'no_pointage': 0}

    for log in audit_qs.filter(action__in=entree_actions).exclude(cible_numero=''):
        personne, type_personne = _resolve_personne(log.cible_type, log.cible_numero)
        if not personne:
            stats['no_target'] += 1
            continue

        _module, session = _find_scan_target(
            log, personne, type_personne, module_mapping, deleted_by_module,
        )
        if not session:
            stats['no_target'] += 1
            continue

        lookup = {
            'date_journee': session.date_journee,
            'session__module_id__in': survivor_ids,
        }
        if type_personne == 'participant':
            lookup['participant'] = personne
        elif type_personne == 'formateur':
            lookup['formateur'] = personne
        else:
            stats['no_target'] += 1
            continue

        candidates = Pointage.objects.filter(**lookup)
        on_target = candidates.filter(session=session).exists()
        if on_target:
            stats['unchanged'] += 1
            continue

        wrong = list(candidates.exclude(session=session))
        if not wrong:
            stats['no_pointage'] += 1
            continue

        pt = min(
            wrong,
            key=lambda p: abs((p.timestamp_entree - log.timestamp).total_seconds()),
        )

        if not dry_run:
            pt.session = session
            pt.date_journee = session.date_journee
            pt.save(update_fields=['session', 'date_journee', 'updated_at'])
        stats['relinked'] += 1

    return stats


def recover_pointages_from_audit(
    audit_qs, *, dry_run=False, intitule_hint='',
    module_mapping=None, deleted_by_module=None,
):
    """
    Recrée les pointages dont l'audit existe mais le lien pointage_id est mort.
    """
    entree_actions = (
        AuditLog.Action.SCAN_SECURE_ENTREE,
        AuditLog.Action.FORCE_ENTREE,
    )
    sortie_actions = (
        AuditLog.Action.SCAN_SECURE_SORTIE,
        AuditLog.Action.FORCE_SORTIE,
    )

    entrees = list(
        audit_qs.filter(action__in=entree_actions, pointage__isnull=True)
        .exclude(cible_numero='')
        .order_by('timestamp')
    )
    sorties = list(
        audit_qs.filter(action__in=sortie_actions, pointage__isnull=True)
        .exclude(cible_numero='')
        .order_by('timestamp')
    )

    sorties_by_key = defaultdict(list)
    for log in sorties:
        key = (log.cible_numero, log.cible_type, log.formation_id)
        sorties_by_key[key].append(log)

    stats = {'created': 0, 'skipped': 0, 'no_module': 0, 'no_session': 0, 'relinked': 0}

    inscriptions = None
    if module_mapping:
        survivor_ids = [m.id for m in module_mapping.values()]
        inscriptions = _inscriptions_by_matricule(survivor_ids, intitule_hint)

    use_mapping = bool(module_mapping and deleted_by_module)

    for entree in entrees:
        personne, type_personne = _resolve_personne(entree.cible_type, entree.cible_numero)
        module = None
        session = None

        if use_mapping:
            module, session = _find_scan_target(
                entree, personne, type_personne, module_mapping, deleted_by_module,
            )

        if not module:
            module = _find_module_for_scan(
                entree, personne, type_personne,
                intitule_hint=intitule_hint,
                module_mapping=module_mapping,
                deleted_by_module=deleted_by_module,
                inscriptions_by_matricule=inscriptions,
            )
        if not module:
            stats['no_module'] += 1
            continue

        if not session:
            session = _find_session_for_scan(module, entree.timestamp)
        if not session:
            stats['no_session'] += 1
            continue

        key = (entree.cible_numero, entree.cible_type, entree.formation_id)
        sortie_log = None
        for candidate in sorties_by_key.get(key, []):
            if candidate.timestamp > entree.timestamp:
                sortie_log = candidate
                break

        lookup = {'session': session, 'date_journee': session.date_journee}
        if type_personne == 'participant':
            lookup['participant'] = personne
        elif type_personne == 'formateur':
            lookup['formateur'] = personne

        if Pointage.objects.filter(**lookup).exists():
            stats['skipped'] += 1
            continue

        if dry_run:
            stats['created'] += 1
            continue

        with transaction.atomic():
            pt = Pointage(
                session=session,
                date_journee=session.date_journee,
                timestamp_entree=entree.timestamp,
                timestamp_sortie=sortie_log.timestamp if sortie_log else None,
                device_id=entree.device_id or '',
                statut=Pointage.Statut.TERMINE if sortie_log else Pointage.Statut.EN_COURS,
            )
            if type_personne == 'participant':
                pt.participant = personne
            elif type_personne == 'formateur':
                pt.formateur = personne
            if sortie_log:
                pt.calculer_duree()
            pt.save()
            stats['created'] += 1

    if use_mapping:
        relink_stats = relink_recovered_pointages(
            audit_qs, module_mapping, deleted_by_module, dry_run=dry_run,
        )
        stats['relinked'] = relink_stats['relinked']
        stats['relink_unchanged'] = relink_stats['unchanged']
        stats['relink_no_target'] = relink_stats['no_target']

    return stats
