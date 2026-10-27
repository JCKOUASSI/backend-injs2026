"""Validation et effets de bord lors d'un changement de matricule auditeur."""

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import Q

from authentication.role_groups import user_in_roles


def normalize_matricule(value):
    return (value or '').strip()


def validate_participant_matricule(
    matricule,
    *,
    participant_id=None,
    linked_user_id=None,
):
    """Vérifie qu'un matricule est utilisable pour un auditeur."""
    matricule = normalize_matricule(matricule)
    if not matricule:
        raise ValidationError('Le matricule est obligatoire.')

    from formations.models import Participant

    participant_qs = Participant.objects.filter(matricule__iexact=matricule)
    if participant_id:
        participant_qs = participant_qs.exclude(pk=participant_id)
    if participant_qs.exists():
        raise ValidationError('Ce matricule est déjà utilisé par un autre auditeur.')

    User = get_user_model()
    user_qs = User.objects.filter(
        Q(username__iexact=matricule) | Q(matricule__iexact=matricule),
    )
    if linked_user_id:
        user_qs = user_qs.exclude(pk=linked_user_id)
    if user_qs.exists():
        raise ValidationError('Ce matricule est déjà utilisé par un compte utilisateur.')

    return matricule


def secretariat_from_matricule_for_actor(matricule, actor_user):
    """Réaffecte le secrétariat selon le préfixe matricule (hors rôles secrétariat)."""
    if actor_user and user_in_roles(actor_user, {'SECRETARIAT', 'CHEF_SECRETARIAT'}):
        return None
    from formations.views import _resolve_secretariat_from_matricule

    return _resolve_secretariat_from_matricule(matricule)


def sync_participant_user_after_matricule_change(participant):
    """Aligne le compte badge lié après modification du matricule."""
    if not participant.user_id:
        return
    from authentication.badge_accounts import ensure_auditeur_account

    ensure_auditeur_account(participant, send_email=False)
