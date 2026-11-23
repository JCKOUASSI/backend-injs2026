"""Contrôle d'accès des endpoints React (formations/api_views.py)."""
from rest_framework.permissions import BasePermission
from rest_framework.response import Response

from authentication.role_groups import (
    ALLOWED_WEB_ROLES,
    GLOBAL_ACCESS_ROLES,
    OPERATIONAL_WEB_ROLES,
    PARTICIPANT_LIST_ROLES,
    SECRETARIAT_ROLES,
    get_user_role,
    get_user_roles,
    user_has_perm,
    user_in_roles,
)
from authentication.permissions import IsDFRC, IsSecretariatOrDFRC, IsSecretariatOrEncadrantOrDFRC

from .access import formation_accessible, module_operational_accessible
from .models import Formation, Module


def _module_in_user_scope(user, module):
    """Vérifie que l'utilisateur peut accéder à ce module précis (pas seulement la formation)."""
    if not (user and user.is_authenticated):
        return False
    roles = get_user_roles(user)
    if roles & GLOBAL_ACCESS_ROLES or user_has_perm(user, 'authentication.global_scope'):
        return True
    if roles & SECRETARIAT_ROLES:
        return bool(user.secretariat and module.secretariat_id == user.secretariat_id)
    if 'ENCADRANT' in roles:
        return module.superviseur_id == user.id
    return False

# Réexport des classes DRF déjà utilisées ailleurs dans le projet.
__all__ = [
    'IsWebStaff',
    'IsOperationalWebStaff',
    'CanListParticipants',
    'IsDFRC',
    'IsSecretariatOrDFRC',
    'IsSecretariatOrEncadrantOrDFRC',
    'formation_or_response',
    'module_or_response',
    'archived_module_or_response',
    'module_for_notes_or_response',
    'module_unarchive_or_response',
    'deny_if_not_formation_accessible',
    'deny_finance_operational_response',
]


class IsWebStaff(BasePermission):
    """Tout rôle autorisé sur la plateforme web (y compris FINANCE pour les endpoints finance)."""

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        return user_has_perm(user, 'authentication.access_web') or user_in_roles(user, ALLOWED_WEB_ROLES)


class IsOperationalWebStaff(BasePermission):
    """Personnel opérationnel web — exclut FINANCE (réservé au module finance dédié)."""

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        return user_has_perm(user, 'authentication.operational_web') or user_in_roles(user, OPERATIONAL_WEB_ROLES)


class CanListParticipants(BasePermission):
    """Liste auditeurs : pas FINANCE / FORMATEUR / AUDITEUR."""

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        return user_has_perm(user, 'authentication.list_participants') or user_in_roles(user, PARTICIPANT_LIST_ROLES)


def formation_or_response(user, pk):
    """Retourne (formation, None) ou (None, Response 404)."""
    formation = formation_accessible(user, pk)
    if formation:
        return formation, None
    return None, Response({'detail': 'Formation introuvable ou non autorisée.'}, status=404)


def module_or_response(user, formation_pk, module_pk):
    """Retourne (formation, module, None) ou (None, None, Response)."""
    formation, err = formation_or_response(user, formation_pk)
    if err:
        return None, None, err
    try:
        module = Module.objects.get(pk=module_pk, formation=formation)
    except Module.DoesNotExist:
        return formation, None, Response({'detail': 'Module introuvable.'}, status=404)
    if not module_operational_accessible(user, module):
        return formation, None, Response({'detail': 'Module archivé ou non autorisé.'}, status=404)
    if not _module_in_user_scope(user, module):
        return formation, None, Response({'detail': 'Module introuvable ou non autorisé.'}, status=404)
    return formation, module, None


def module_for_notes_or_response(user, formation_pk, module_pk):
    """Module consultable en lecture pour les notes, archivé ou non.

    Les listes de notes restent consultables après archivage (espace Archives),
    contrairement aux écrans opérationnels servis par `module_or_response`.
    """
    formation = Formation.objects.filter(pk=formation_pk).first()
    if not formation:
        return None, None, Response({'detail': 'Formation introuvable.'}, status=404)
    try:
        module = Module.objects.get(pk=module_pk, formation=formation)
    except Module.DoesNotExist:
        return formation, None, Response({'detail': 'Module introuvable.'}, status=404)
    if not _module_in_user_scope(user, module):
        return formation, None, Response({'detail': 'Module introuvable ou non autorisé.'}, status=404)
    return formation, module, None


def deny_if_not_formation_accessible(user, pk):
    """Alias court pour les vues qui n'ont besoin que du garde-fou."""
    return formation_or_response(user, pk)


def archived_module_or_response(user, formation_pk, module_pk):
    """Retourne (formation, module_archivé, None) ou (None, None, Response 404)."""
    formation = Formation.objects.filter(pk=formation_pk).first()
    if not formation:
        return None, None, Response({'detail': 'Formation introuvable.'}, status=404)
    try:
        module = Module.objects.get(pk=module_pk, formation=formation, archived=True)
    except Module.DoesNotExist:
        return formation, None, Response({'detail': 'Module archivé introuvable.'}, status=404)

    if not (user and user.is_authenticated):
        return formation, None, Response({'detail': 'Module archivé introuvable.'}, status=404)

    roles = get_user_roles(user)
    if roles & GLOBAL_ACCESS_ROLES or user_has_perm(user, 'authentication.global_scope'):
        return formation, module, None
    if roles & SECRETARIAT_ROLES and user.secretariat and module.secretariat_id == user.secretariat_id:
        return formation, module, None
    if 'ENCADRANT' in roles and module.superviseur_id == user.id:
        return formation, module, None
    return formation, None, Response({'detail': 'Module archivé introuvable ou non autorisé.'}, status=404)


def _archived_module_accessible(user, module):
    if not (user and user.is_authenticated):
        return False
    roles = get_user_roles(user)
    if roles & GLOBAL_ACCESS_ROLES or user_has_perm(user, 'authentication.global_scope'):
        return True
    if roles & SECRETARIAT_ROLES and user.secretariat and module.secretariat_id == user.secretariat_id:
        return True
    if 'ENCADRANT' in roles and module.superviseur_id == user.id:
        return True
    return False


def module_unarchive_or_response(user, formation_pk, module_pk):
    """Retourne (formation, module_archivé, None) ou (None, None, Response erreur)."""
    formation = Formation.objects.filter(pk=formation_pk).first()
    if not formation:
        return None, None, Response({'detail': 'Formation introuvable.'}, status=404)
    try:
        module = Module.objects.get(pk=module_pk, formation=formation)
    except Module.DoesNotExist:
        return formation, None, Response({'detail': 'Module introuvable.'}, status=404)

    if not module.archived:
        return formation, None, Response({'detail': 'Ce module n\'est pas archivé.'}, status=400)

    if not _archived_module_accessible(user, module):
        return formation, None, Response({'detail': 'Module archivé introuvable ou non autorisé.'}, status=404)

    return formation, module, None


def deny_finance_operational_response(request):
    """Bloque FINANCE sur les endpoints opérationnels du dashboard formations."""
    user = getattr(request, 'user', None)
    role = get_user_role(user) if user and user.is_authenticated else None
    if role == 'FINANCE' and not user_has_perm(user, 'authentication.operational_web'):
        return Response(
            {
                'detail': (
                    'Accès réservé au personnel opérationnel. '
                    'Utilisez le module Finance.'
                ),
            },
            status=403,
        )
    return None
