"""Ajustements horaires sur séances réelles — workflow Direction/Finance."""

from datetime import datetime, timedelta

from django.db import transaction
from django.utils import timezone

from .models import FinanceAjustement, ModuleFormateur
from .volume_horaire import _session_realise_minutes


def _time_add_minutes(time_value, minutes):
    if not time_value:
        return None
    base = datetime(2000, 1, 1, time_value.hour, time_value.minute, time_value.second)
    result = base + timedelta(minutes=minutes)
    return result.time().replace(microsecond=0)


def _time_subtract_minutes(time_value, minutes):
    return _time_add_minutes(time_value, -minutes)


def preview_realise_after_adjustment(session, delta_minutes):
    """Estime le volume réalisé après ajustement sans modifier la séance."""
    from copy import copy

    clone = copy(session)
    apply_adjustment_to_session(clone, delta_minutes, save=False)
    return round(_session_realise_minutes(clone), 1)


def apply_adjustment_to_session(session, delta_minutes, save=True):
    """
    Modifie les horaires de la séance pour refléter l'ajustement validé.

    Ajout : prolonge terminee_le et heure_fin_prevue.
    Retrait : raccourcit terminee_le (plancher = demarree_le).
    """
    delta = int(delta_minutes)
    if delta == 0:
        return

    update_fields = []
    if delta > 0:
        if session.heure_fin_prevue:
            session.heure_fin_prevue = _time_add_minutes(session.heure_fin_prevue, delta)
            update_fields.append('heure_fin_prevue')
        if session.terminee_le:
            session.terminee_le = session.terminee_le + timedelta(minutes=delta)
            update_fields.append('terminee_le')
    else:
        remove = abs(delta)
        if session.terminee_le and session.demarree_le:
            new_end = session.terminee_le - timedelta(minutes=remove)
            if new_end < session.demarree_le:
                new_end = session.demarree_le
            session.terminee_le = new_end
            update_fields.append('terminee_le')
        if session.heure_fin_prevue and session.heure_debut_prevue:
            new_fin = _time_subtract_minutes(session.heure_fin_prevue, remove)
            if new_fin and new_fin > session.heure_debut_prevue:
                session.heure_fin_prevue = new_fin
                if 'heure_fin_prevue' not in update_fields:
                    update_fields.append('heure_fin_prevue')

    if save and update_fields:
        session.save(update_fields=update_fields)


def _validate_proposal_inputs(session, formateur, minutes_delta, motif):
    errors = []
    if not session:
        errors.append('Séance introuvable.')
        return errors
    if not formateur:
        errors.append('Formateur introuvable.')
        return errors
    if not session.terminee_le:
        errors.append('Seules les séances terminées peuvent être ajustées.')
    try:
        delta = int(minutes_delta)
    except (TypeError, ValueError):
        errors.append('minutes_delta invalide.')
        return errors
    if delta == 0:
        errors.append('minutes_delta ne peut pas être nul.')
    if abs(delta) > 8 * 60:
        errors.append('L\'ajustement ne peut pas dépasser 8 heures.')
    if not (motif or '').strip():
        errors.append('Le motif est obligatoire.')
    if not ModuleFormateur.objects.filter(module_id=session.module_id, formateur=formateur).exists():
        errors.append('Le formateur n\'est pas assigné au module de cette séance.')
    if FinanceAjustement.objects.filter(
        session=session,
        formateur=formateur,
        statut=FinanceAjustement.Statut.EN_ATTENTE,
    ).exists():
        errors.append('Un ajustement est déjà en attente pour cette séance et ce formateur.')
    return errors


def propose_ajustement(session, formateur, minutes_delta, motif, user):
    errors = _validate_proposal_inputs(session, formateur, minutes_delta, motif)
    if errors:
        return None, errors

    delta = int(minutes_delta)
    realise_avant = round(_session_realise_minutes(session), 1)
    realise_apres = preview_realise_after_adjustment(session, delta)

    ajustement = FinanceAjustement.objects.create(
        session=session,
        formateur=formateur,
        minutes_delta=delta,
        motif=(motif or '').strip(),
        realise_avant_minutes=realise_avant,
        realise_apres_minutes=realise_apres,
        proposed_by=user,
    )
    from .finance_notifications import notifier_ajustement_propose
    notifier_ajustement_propose(ajustement, user)
    return ajustement, []


def _log_finance_audit(action, request, ajustement, extra=None):
    from presences.models import _log_audit

    session = ajustement.session
    formateur = ajustement.formateur
    payload = {
        'ajustement_id': ajustement.id,
        'minutes_delta': ajustement.minutes_delta,
        'motif': ajustement.motif,
        'session_id': session.id,
        'formateur_id': formateur.id,
        'realise_avant_minutes': ajustement.realise_avant_minutes,
        'realise_apres_minutes': ajustement.realise_apres_minutes,
        'statut': ajustement.statut,
    }
    if extra:
        payload.update(extra)

    formation = session.module.formation if session.module_id else None
    _log_audit(
        action,
        request,
        cible_type='formateur',
        cible_numero=formateur.numerobadge or '',
        cible_nom=f'{formateur.nom} {formateur.prenom}'.strip(),
        formation=formation,
        extra=payload,
    )


@transaction.atomic
def valider_ajustement(ajustement, user, request=None):
    if ajustement.statut != FinanceAjustement.Statut.EN_ATTENTE:
        return None, ['Cet ajustement n\'est plus en attente.']

    session = ajustement.session
    apply_adjustment_to_session(session, ajustement.minutes_delta)
    realise_apres = round(_session_realise_minutes(session), 1)

    ajustement.statut = FinanceAjustement.Statut.VALIDE
    ajustement.validated_by = user
    ajustement.validated_at = timezone.now()
    ajustement.realise_apres_minutes = realise_apres
    ajustement.save(update_fields=[
        'statut', 'validated_by', 'validated_at', 'realise_apres_minutes',
    ])

    if request:
        _log_finance_audit(
            'FINANCE_AJUSTEMENT_VALIDE',
            request,
            ajustement,
            extra={'realise_effectif_minutes': realise_apres},
        )
    from .finance_notifications import notifier_ajustement_valide
    notifier_ajustement_valide(ajustement, user)
    return ajustement, []


@transaction.atomic
def rejeter_ajustement(ajustement, user, rejection_motif='', request=None):
    if ajustement.statut != FinanceAjustement.Statut.EN_ATTENTE:
        return None, ['Cet ajustement n\'est plus en attente.']

    motif = (rejection_motif or '').strip()
    if not motif:
        return None, ['Le motif de rejet est obligatoire.']

    ajustement.statut = FinanceAjustement.Statut.REJETE
    ajustement.rejected_by = user
    ajustement.rejected_at = timezone.now()
    ajustement.rejection_motif = motif
    ajustement.save(update_fields=[
        'statut', 'rejected_by', 'rejected_at', 'rejection_motif',
    ])

    if request:
        _log_finance_audit(
            'FINANCE_AJUSTEMENT_REJETE',
            request,
            ajustement,
            extra={'rejection_motif': motif},
        )
    from .finance_notifications import notifier_ajustement_rejete
    notifier_ajustement_rejete(ajustement, user, rejection_motif=motif)
    return ajustement, []


def serialize_ajustement(ajustement):
    session = ajustement.session
    module = session.module if session else None
    formateur = ajustement.formateur
    return {
        'id': ajustement.id,
        'statut': ajustement.statut,
        'statut_label': ajustement.get_statut_display(),
        'minutes_delta': ajustement.minutes_delta,
        'motif': ajustement.motif,
        'realise_avant_minutes': ajustement.realise_avant_minutes,
        'realise_apres_minutes': ajustement.realise_apres_minutes,
        'proposed_at': ajustement.proposed_at,
        'validated_at': ajustement.validated_at,
        'rejected_at': ajustement.rejected_at,
        'rejection_motif': ajustement.rejection_motif or '',
        'proposed_by': (
            ajustement.proposed_by.get_full_name() or ajustement.proposed_by.username
        ) if ajustement.proposed_by else None,
        'validated_by': (
            ajustement.validated_by.get_full_name() or ajustement.validated_by.username
        ) if ajustement.validated_by else None,
        'rejected_by': (
            ajustement.rejected_by.get_full_name() or ajustement.rejected_by.username
        ) if ajustement.rejected_by else None,
        'session': {
            'id': session.id,
            'date_journee': session.date_journee,
            'numero': session.numero,
            'intitule': session.intitule or f'Session {session.numero}',
            'module_id': session.module_id,
            'module_intitule': module.canonical_intitule() if module else '',
            'formation_intitule': (
                module.formation.formation if module and module.formation_id else ''
            ),
            'grade': module.grade if module else '',
            'groupe': module.groupe if module else '',
        },
        'formateur': {
            'id': formateur.id,
            'numerobadge': formateur.numerobadge,
            'nom': formateur.nom,
            'prenom': formateur.prenom,
            'label': f'{formateur.nom} {formateur.prenom}'.strip(),
        },
    }
