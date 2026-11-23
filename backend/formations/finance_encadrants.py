"""Rapport finance — volumes horaires par encadrant (Module.superviseur)."""

from formations.models import Module
from formations.volume_horaire import (
    accumulate_sessions_volume,
    module_planned_minutes_for_period,
    session_in_date_range,
)


def _encadrant_label(user):
    if not user:
        return ''
    return (user.get_full_name() or '').strip() or user.username


def _groupe_sort_key(groupe, grade):
    return (grade or '', groupe or '')


def finance_encadrants_report(*, date_debut=None, date_fin=None, secretariat_id=None):
    """
    Liste des encadrants avec volumes par groupe (module supervisé).

    Colonnes métier : Groupe, volume planifié, volume réalisé.
    """
    qs = Module.objects.filter(
        superviseur__isnull=False,
    ).select_related(
        'superviseur', 'formation', 'secretariat', 'ref_module',
    ).prefetch_related('sessions').order_by(
        'superviseur__last_name', 'superviseur__first_name', 'grade', 'groupe', 'intitule',
    )
    if secretariat_id:
        qs = qs.filter(secretariat_id=secretariat_id)

    by_encadrant = {}
    totals = {'planned_minutes': 0.0, 'realized_minutes': 0.0, 'lignes_count': 0}

    for module in qs:
        all_sessions = list(module.sessions.all())
        sessions_in_period = [
            s for s in all_sessions
            if session_in_date_range(s, date_debut, date_fin)
        ]
        if not sessions_in_period:
            continue

        planned = round(module_planned_minutes_for_period(
            module,
            len(sessions_in_period),
            len(all_sessions),
            sessions_in_period,
        ), 1)
        vol = accumulate_sessions_volume(
            sessions_in_period,
            date_debut=date_debut,
            date_fin=date_fin,
        )
        realized = round(float(vol['realise_min'] or 0), 1)
        if planned > 0:
            realized = round(min(realized, planned), 1)

        enc = module.superviseur
        enc_key = enc.id
        block = by_encadrant.setdefault(enc_key, {
            'encadrant_id': enc.id,
            'encadrant_label': _encadrant_label(enc),
            'encadrant_username': enc.username,
            'lignes': [],
            'sous_total': {'planned_minutes': 0.0, 'realized_minutes': 0.0},
        })
        ligne = {
            'module_id': module.id,
            'groupe': (module.groupe or '').strip() or '—',
            'grade': (module.grade or '').strip(),
            'module_intitule': module.canonical_intitule(),
            'formation_intitule': (
                module.formation.formation if module.formation_id else ''
            ),
            'planned_minutes': planned,
            'realized_minutes': realized,
            'sessions_count': len(sessions_in_period),
        }
        block['lignes'].append(ligne)
        block['sous_total']['planned_minutes'] = round(
            block['sous_total']['planned_minutes'] + planned, 1,
        )
        block['sous_total']['realized_minutes'] = round(
            block['sous_total']['realized_minutes'] + realized, 1,
        )
        totals['planned_minutes'] = round(totals['planned_minutes'] + planned, 1)
        totals['realized_minutes'] = round(totals['realized_minutes'] + realized, 1)
        totals['lignes_count'] += 1

    encadrants = []
    for block in by_encadrant.values():
        block['lignes'].sort(key=lambda l: _groupe_sort_key(l['groupe'], l['grade']))
        block['sous_total']['planned_minutes'] = round(block['sous_total']['planned_minutes'], 1)
        block['sous_total']['realized_minutes'] = round(block['sous_total']['realized_minutes'], 1)
        encadrants.append(block)

    encadrants.sort(key=lambda b: (b['encadrant_label'] or b['encadrant_username']).lower())
    totals['encadrants_count'] = len(encadrants)
    totals['planned_minutes'] = round(totals['planned_minutes'], 1)
    totals['realized_minutes'] = round(totals['realized_minutes'], 1)

    return {
        'encadrants': encadrants,
        'totaux': totals,
    }
