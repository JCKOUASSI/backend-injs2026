"""
Helpers de contrôle d'accès aux formations, partagés entre les apps formations et presences.
Centraliser ici évite la duplication et garantit une logique cohérente dans tout le projet.
"""
from django.db.models import Q

from authentication.role_groups import (
    DASHBOARD_SECRETARIAT_FILTER_ROLES,
    GLOBAL_ACCESS_ROLES,
    MODULE_ARCHIVE_ROLES,
    SECRETARIAT_ROLES,
    get_user_roles,
    user_has_perm,
    user_in_roles,
)

from .models import Formation, Module, Participant, Formateur


def operational_modules_queryset(queryset=None):
    """Modules actifs (hors espace Archives)."""
    qs = queryset if queryset is not None else Module.objects.all()
    return qs.filter(archived=False)


def archived_modules_queryset(queryset=None):
    """Modules archivés (espace Archives uniquement)."""
    qs = queryset if queryset is not None else Module.objects.all()
    return qs.filter(archived=True)


def can_archive_module(user):
    """Indique si l'utilisateur peut archiver un module."""
    if not (user and user.is_authenticated):
        return False
    if getattr(user, 'is_superuser', False):
        return True
    return user_in_roles(user, MODULE_ARCHIVE_ROLES)


def can_unarchive_module(user):
    """Indique si l'utilisateur peut désarchiver un module (mêmes rôles que l'archivage)."""
    return can_archive_module(user)


def module_operational_accessible(user, module):
    """Module consultable dans les écrans opérationnels (non archivé)."""
    if module is None:
        return False
    if getattr(module, 'archived', False):
        return False
    return True


def _union_querysets(parts):
    if not parts:
        return None
    result = parts[0]
    for part in parts[1:]:
        result = result | part
    return result.distinct()


def formation_accessible(user, pk):
    """
    Retourne la Formation si l'utilisateur est autorisé à y accéder, None sinon.

    Règles :
    - AUDITEUR               : au moins un module de la formation doit contenir le participant lié à cet utilisateur.
    - ENCADRANT              : au moins un module de la formation doit être supervisé par cet utilisateur.
    - SECRETARIAT /
      CHEF_SECRETARIAT       : au moins un module de la formation doit appartenir au secrétariat de l'utilisateur.
                               Si l'utilisateur n'est rattaché à aucun secrétariat → accès refusé.
    - INJS_ADMIN /
      CHEF_INJS_ADMIN /
      DIRECTION / ARCHIVE / ADMIN      : accès complet à toutes les formations.
    - FINANCE                : accès refusé ici (module finance dédié).
    """
    if not (user and user.is_authenticated):
        return None

    roles = get_user_roles(user)

    if roles & GLOBAL_ACCESS_ROLES or user_has_perm(user, 'authentication.global_scope'):
        return Formation.objects.filter(pk=pk).first()

    parts = []
    if 'ENCADRANT' in roles:
        parts.append(
            Formation.objects.filter(pk=pk, modules__superviseur=user, modules__archived=False).distinct()
        )

    if roles & SECRETARIAT_ROLES:
        secretariat = getattr(user, 'secretariat', None)
        if secretariat:
            parts.append(
                Formation.objects.filter(
                    pk=pk, modules__secretariat=secretariat, modules__archived=False
                ).distinct()
            )

    if 'AUDITEUR' in roles:
        parts.append(
            Formation.objects.filter(
                pk=pk, modules__module_participants__participant__user=user, modules__archived=False
            ).distinct()
        )

    union = _union_querysets(parts)
    return union.first() if union is not None else None


def modules_queryset_for_user(user, queryset=None):
    """Modules visibles selon le périmètre opérationnel de l'utilisateur."""
    qs = operational_modules_queryset(queryset)
    if not (user and user.is_authenticated):
        return qs.none()

    roles = get_user_roles(user)
    if roles & GLOBAL_ACCESS_ROLES or user_has_perm(user, 'authentication.global_scope'):
        return qs

    parts = []
    if roles & SECRETARIAT_ROLES and user.secretariat:
        parts.append(qs.filter(secretariat=user.secretariat))
    if 'ENCADRANT' in roles:
        parts.append(qs.filter(superviseur=user))

    union = _union_querysets(parts)
    if union is not None:
        return union
    if roles & {'FINANCE'}:
        return qs.none()
    return qs


def participants_queryset_for_user(user, queryset=None):
    """Participants visibles selon le périmètre opérationnel de l'utilisateur."""
    qs = queryset if queryset is not None else Participant.objects.all()
    if not (user and user.is_authenticated):
        return qs.none()

    roles = get_user_roles(user)
    if roles & GLOBAL_ACCESS_ROLES or user_has_perm(user, 'authentication.global_scope'):
        return qs

    parts = []
    if roles & SECRETARIAT_ROLES:
        if user.secretariat:
            parts.append(
                qs.filter(
                    Q(secretariat=user.secretariat)
                    | Q(modules_inscrits__module__secretariat=user.secretariat)
                ).distinct()
            )
        else:
            parts.append(qs.filter(secretariat__isnull=True))
    if 'ENCADRANT' in roles:
        parts.append(qs.filter(modules_inscrits__module__superviseur=user).distinct())

    union = _union_querysets(parts)
    if union is not None:
        return union
    if roles & {'FINANCE'}:
        return qs.none()
    return qs


def participant_accessible(user, pk):
    """Retourne le Participant si l'utilisateur est autorisé à le consulter."""
    if not (user and user.is_authenticated):
        return None
    return participants_queryset_for_user(user).filter(pk=pk).first()


def participant_fiche_accessible(user, pk):
    """Participant consultable via fiche admin (historique badgeage, stats).

    FINANCE a un accès lecture globale (aligné sur participant_fiche_admin).
    """
    if not (user and user.is_authenticated):
        return None
    roles = get_user_roles(user)
    if roles & (GLOBAL_ACCESS_ROLES | {'FINANCE'}) or user_has_perm(user, 'authentication.global_scope'):
        return Participant.objects.filter(pk=pk).first()
    return participants_queryset_for_user(user).filter(pk=pk).first()


def formateurs_queryset_for_user(user, queryset=None):
    """Formateurs visibles selon le périmètre opérationnel de l'utilisateur.

    Secrétariat : pool global (tous les formateurs). Les règles d'assignation
    aux modules (conflits groupe/jour/horaire) restent appliquées à l'assignation.
    """
    qs = queryset if queryset is not None else Formateur.objects.all()
    if not (user and user.is_authenticated):
        return qs.none()

    roles = get_user_roles(user)
    if roles & GLOBAL_ACCESS_ROLES or user_has_perm(user, 'authentication.global_scope'):
        return qs

    if roles & SECRETARIAT_ROLES:
        return qs

    parts = []
    if 'ENCADRANT' in roles:
        parts.append(qs.filter(modules_assignes__module__superviseur=user).distinct())

    union = _union_querysets(parts)
    if union is not None:
        return union
    return qs.none()


def can_filter_modules_by_secretariat(user):
    """Indique si l'utilisateur peut appliquer un filtre secrétariat sur les listes modules."""
    return user_in_roles(user, DASHBOARD_SECRETARIAT_FILTER_ROLES) or user_has_perm(
        user, 'authentication.global_scope'
    )
