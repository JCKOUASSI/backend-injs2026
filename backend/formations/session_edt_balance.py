"""Équilibrage automatique de l'EDT après modification d'une séance.

Lorsqu'une séance (autre que la dernière) voit sa durée planifiée changer,
la dernière séance du même module est compensée pour que le total EDT
(Σ durées réelles de chaque créneau, quelle que soit leur répartition)
corresponde à ``Module.duree_prevue_heures`` (référentiel ou fiche module).
"""

from datetime import datetime, timedelta

from django.db import transaction

from .duree_prevue_resolve import ensure_module_duree_prevue
from .models import SessionModule
from .volume_horaire import _minutes_entre_heures


class SessionEdtBalanceError(Exception):
    """Impossible d'ajuster automatiquement la dernière séance."""


def _time_add_minutes(time_value, minutes):
    if not time_value:
        return None
    base = datetime(2000, 1, 1, time_value.hour, time_value.minute, time_value.second)
    result = base + timedelta(minutes=minutes)
    return result.time().replace(microsecond=0)


def _session_planned_minutes(debut, fin):
    minutes = _minutes_entre_heures(debut, fin)
    if minutes is None or minutes <= 0:
        return 0.0
    return minutes


def _last_session_for_module(module, *, exclude_pk=None):
    qs = SessionModule.objects.filter(module=module).order_by(
        '-date_journee', '-heure_debut_prevue', '-numero',
    )
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    return qs.first()


def _format_duration_label(minutes):
    abs_min = abs(int(round(minutes)))
    h, m = divmod(abs_min, 60)
    if h and m:
        return f'{h}h{m:02d}'
    if h:
        return f'{h}h'
    return f'{m}min'


def _format_delta_message(
    delta_minutes,
    *,
    deleted=False,
    last_label='',
    edited_delta=0,
    target_hours=None,
):
    duree = _format_duration_label(delta_minutes)

    if deleted:
        return (
            f'Séance allongée de {_format_duration_label(edited_delta)} — '
            f'dernière séance ({last_label}) supprimée pour conserver '
            f'{target_hours:g}h au total.'
        )

    if edited_delta > 0:
        edit_desc = f'allongée de {_format_duration_label(edited_delta)}'
        last_sens = 'réduite'
    elif edited_delta < 0:
        edit_desc = f'raccourcie de {_format_duration_label(edited_delta)}'
        last_sens = 'prolongée'
    else:
        edit_desc = 'modifiée'
        last_sens = 'réduite' if delta_minutes < 0 else 'prolongée'

    target = f' ({target_hours:g}h au total)' if target_hours else ''
    return (
        f'Séance {edit_desc} — dernière séance ({last_label}) '
        f'{last_sens} de {duree}{target}.'
    )


def _apply_last_session_duration(
    last,
    new_last_duration,
    *,
    save=True,
    edited_delta=0,
    target_hours=None,
):
    """Applique une nouvelle durée planifiée sur la dernière séance."""
    last_label = last.intitule or f'Séance {last.numero}'
    old_duration = _session_planned_minutes(
        last.heure_debut_prevue, last.heure_fin_prevue,
    )
    compensation = new_last_duration - old_duration

    if new_last_duration <= 0:
        last_id = last.pk
        last.delete()
        return {
            'adjusted': True,
            'deleted_last': True,
            'last_session_id': last_id,
            'delta_minutes': compensation,
            'message': _format_delta_message(
                compensation,
                deleted=True,
                last_label=last_label,
                edited_delta=edited_delta,
                target_hours=target_hours,
            ),
        }

    if last.heure_fin_prevue:
        new_fin = _time_add_minutes(last.heure_fin_prevue, compensation)
    else:
        new_fin = _time_add_minutes(last.heure_debut_prevue, new_last_duration)

    if not new_fin or new_fin <= last.heure_debut_prevue:
        last_id = last.pk
        last.delete()
        return {
            'adjusted': True,
            'deleted_last': True,
            'last_session_id': last_id,
            'delta_minutes': compensation,
            'message': _format_delta_message(
                compensation,
                deleted=True,
                last_label=last_label,
                edited_delta=edited_delta,
                target_hours=target_hours,
            ),
        }

    last.heure_fin_prevue = new_fin
    if save:
        last.save(update_fields=['heure_fin_prevue'])

    if abs(compensation) < 0.5:
        return None

    return {
        'adjusted': True,
        'deleted_last': False,
        'last_session_id': last.pk,
        'delta_minutes': compensation,
        'message': _format_delta_message(
            compensation,
            last_label=last_label,
            edited_delta=edited_delta,
            target_hours=target_hours,
        ),
    }


def _sum_planned_minutes_except_last(module, session, *, edited_values=None):
    """Somme EDT des séances hors dernière ; ``edited_values`` pour la séance en cours."""
    last = _last_session_for_module(module)
    total = 0.0
    for s in SessionModule.objects.filter(module=module).only(
        'pk', 'heure_debut_prevue', 'heure_fin_prevue',
    ):
        if last and s.pk == last.pk:
            continue
        if edited_values and s.pk == session.pk:
            debut, fin = edited_values
        else:
            debut, fin = s.heure_debut_prevue, s.heure_fin_prevue
        total += _session_planned_minutes(debut, fin)
    return total


@transaction.atomic
def apply_session_edit_with_edt_balance(session, *, old_debut, old_fin, save=True):
    """
    Enregistre la séance modifiée et ajuste la dernière séance du module.

    Retourne un dict décrivant l'ajustement, ou ``None`` si aucune compensation.
    Lève ``SessionEdtBalanceError`` si la compensation est requise mais impossible.
    """
    module = session.module
    ensure_module_duree_prevue(module, save=save)

    delta = (
        _session_planned_minutes(session.heure_debut_prevue, session.heure_fin_prevue)
        - _session_planned_minutes(old_debut, old_fin)
    )
    if abs(delta) < 0.5:
        if save:
            session.save()
        return None

    last = _last_session_for_module(module)
    if not last or last.pk == session.pk:
        if save:
            session.save()
        return None

    if last.demarree_le:
        raise SessionEdtBalanceError(
            'Impossible de modifier cette séance : la dernière séance du module '
            'est déjà démarrée et ne peut pas être ajustée automatiquement.'
        )

    if not last.heure_debut_prevue:
        raise SessionEdtBalanceError(
            'Impossible d\'ajuster automatiquement : la dernière séance '
            'n\'a pas d\'horaire de début planifié.'
        )

    if save:
        session.save()

    target_hours = float(module.duree_prevue_heures or 0)
    target_minutes = target_hours * 60
    balance_kwargs = {
        'save': save,
        'edited_delta': delta,
        'target_hours': target_hours if target_hours > 0 else None,
    }

    if target_minutes > 0:
        others_minutes = _sum_planned_minutes_except_last(
            module,
            session,
            edited_values=(session.heure_debut_prevue, session.heure_fin_prevue),
        )
        new_last_duration = target_minutes - others_minutes
        return _apply_last_session_duration(
            last, new_last_duration, **balance_kwargs,
        )

    compensation = -delta
    last_duration = _session_planned_minutes(
        last.heure_debut_prevue, last.heure_fin_prevue,
    )
    new_last_duration = last_duration + compensation
    return _apply_last_session_duration(
        last, new_last_duration, **balance_kwargs,
    )
