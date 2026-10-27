"""Provisionnement des comptes badge (auditeurs / formateurs) sans compte User."""

from formations.models import Formateur, ModuleFormateur, ModuleParticipant, Participant

from .badge_accounts import (
    _empty_stats,
    ensure_auditeur_account,
    ensure_formateur_account,
)


def _inscribed_participant_ids(formation_id=None):
    qs = ModuleParticipant.objects.values_list('participant_id', flat=True).distinct()
    if formation_id is not None:
        qs = qs.filter(module__formation_id=formation_id)
    return qs


def _assigned_formateur_ids(formation_id=None):
    qs = ModuleFormateur.objects.values_list('formateur_id', flat=True).distinct()
    if formation_id is not None:
        qs = qs.filter(module__formation_id=formation_id)
    return qs


def participants_sans_compte(formation_id=None):
    """Auditeurs inscrits à au moins un module, sans compte User lié."""
    return (
        Participant.objects.filter(
            pk__in=_inscribed_participant_ids(formation_id),
            user__isnull=True,
        )
        .select_related('secretariat')
        .order_by('nom', 'prenom', 'matricule')
    )


def formateurs_sans_compte(formation_id=None):
    """Formateurs assignés à au moins un module, sans compte User lié."""
    return (
        Formateur.objects.filter(
            pk__in=_assigned_formateur_ids(formation_id),
            user__isnull=True,
        )
        .order_by('nom', 'prenom', 'numerobadge')
    )


def preview_missing_badge_accounts(formation_id=None, limit=50):
    auditeurs_qs = participants_sans_compte(formation_id)
    formateurs_qs = formateurs_sans_compte(formation_id)
    return {
        'auditeurs_count': auditeurs_qs.count(),
        'formateurs_count': formateurs_qs.count(),
        'auditeurs': list(auditeurs_qs[:limit]),
        'formateurs': list(formateurs_qs[:limit]),
        'preview_limit': limit,
        'password_mode': 'random_per_account',
    }


def provision_missing_badge_accounts(
    *,
    formation_id=None,
    include_auditeurs=True,
    include_formateurs=True,
    password=None,
    send_email=True,
):
    """Crée les comptes User manquants (sans modifier les comptes déjà liés).

    Chaque compte reçoit un mot de passe aléatoire unique (sauf si ``password``
    est fourni explicitement, ex. commande d'admin).
    """
    stats = {
        'auditeurs': _empty_stats(),
        'formateurs': _empty_stats(),
    }

    if include_auditeurs:
        for participant in participants_sans_compte(formation_id):
            try:
                action = ensure_auditeur_account(
                    participant,
                    password=password,
                    send_email=send_email,
                    skip_existing=True,
                    reset_password=False,
                )
                stats['auditeurs'][action] += 1
                if action == 'created' and send_email and participant.email:
                    stats['auditeurs']['emails_sent'] += 1
            except Exception:
                stats['auditeurs']['errors'] += 1

    if include_formateurs:
        for formateur in formateurs_sans_compte(formation_id):
            try:
                action = ensure_formateur_account(
                    formateur,
                    password=password,
                    send_email=send_email,
                    skip_existing=True,
                    reset_password=False,
                )
                stats['formateurs'][action] += 1
                if action == 'created' and send_email and formateur.email:
                    stats['formateurs']['emails_sent'] += 1
            except Exception:
                stats['formateurs']['errors'] += 1

    return stats
