"""
Contrôle d'accès et périmètre des données — module Statistiques.

Centralise l'étanchéité par rôle (secrétariat, encadrant, direction).
"""
from dataclasses import dataclass
from typing import Optional

from django.db.models import Q

from formations.models import Formation, Module, Secretariat

from authentication.role_groups import (
    GLOBAL_STATS_ROLES,
    ROLE_HIERARCHY,
    SECRETARIAT_ROLES,
    STATS_ACCESS_ROLES,
    get_user_roles,
)

from .models import Rapport

ROLE_ALIASES = {
    'DFRC': 'INJS_ADMIN',
    'SUPERVISEUR': 'ENCADRANT',
    'SUPERVISOR': 'ENCADRANT',
}


def _normalize_stats_roles(roles):
    """Mappe les rôles legacy (DFRC, SUPERVISEUR…) vers les rôles actuels."""
    return frozenset(ROLE_ALIASES.get(role, role) for role in roles)


def effective_user_role(user) -> Optional[str]:
    return user_stats_role(user)


def user_stats_role(user) -> Optional[str]:
    """Rôle principal pour le périmètre stats (le plus élevé parmi les rôles autorisés)."""
    roles = _normalize_stats_roles(get_user_roles(user)) & STATS_ACCESS_ROLES
    if not roles:
        return None
    for candidate in ROLE_HIERARCHY:
        if candidate in roles:
            return candidate
    return next(iter(roles))


def user_has_stats_access(user) -> bool:
    return bool(_normalize_stats_roles(get_user_roles(user)) & STATS_ACCESS_ROLES)


def user_secretariat_scope_locked(user) -> bool:
    """Compte limité aux statistiques de son secrétariat."""
    roles = _normalize_stats_roles(get_user_roles(user))
    if roles & (GLOBAL_STATS_ROLES - SECRETARIAT_ROLES):
        return False
    return bool(roles & SECRETARIAT_ROLES)


@dataclass
class StatsScope:
    formation_id: Optional[int] = None
    secretariat_id: Optional[int] = None
    module_ids: Optional[list] = None  # None = pas de restriction module ; [] = périmètre vide


def encadrant_module_ids(user) -> list:
    return list(
        Module.objects.filter(superviseur=user).values_list('id', flat=True)
    )


def encadrant_secretariat_ids(user) -> list:
    return list(
        Module.objects.filter(superviseur=user)
        .exclude(secretariat_id__isnull=True)
        .values_list('secretariat_id', flat=True)
        .distinct()
    )


def resolve_stats_scope(
    user,
    *,
    formation_id=None,
    secretariat_id=None,
    module_id=None,
) -> tuple[StatsScope, Optional[str]]:
    """
    Calcule le périmètre autorisé pour un utilisateur.
    Retourne (StatsScope, message_d_erreur) — erreur non None → HTTP 403.
    """
    if not (user and user.is_authenticated):
        return StatsScope(), 'Authentification requise.'

    role = user_stats_role(user)
    scope = StatsScope(
        formation_id=int(formation_id) if formation_id else None,
        secretariat_id=int(secretariat_id) if secretariat_id else None,
    )

    if role in SECRETARIAT_ROLES:
        sec = getattr(user, 'secretariat', None)
        if not sec:
            return StatsScope(), 'Aucun secrétariat rattaché à votre compte.'
        if scope.secretariat_id and scope.secretariat_id != sec.id:
            return StatsScope(), 'Accès non autorisé à ce secrétariat.'
        scope.secretariat_id = sec.id

    elif role == 'ENCADRANT':
        mod_ids = encadrant_module_ids(user)
        scope.module_ids = mod_ids
        allowed_secs = set(encadrant_secretariat_ids(user))
        if scope.secretariat_id:
            if scope.secretariat_id not in allowed_secs:
                return StatsScope(), 'Accès non autorisé à ce secrétariat.'
        elif len(allowed_secs) == 1:
            scope.secretariat_id = next(iter(allowed_secs))

    if scope.formation_id:
        err = _validate_formation(user, scope.formation_id)
        if err:
            return StatsScope(), err

    if module_id:
        err = _validate_module(user, int(module_id), scope)
        if err:
            return StatsScope(), err

    return scope, None


def _validate_formation(user, formation_id: int) -> Optional[str]:
    role = user_stats_role(user)
    if role in GLOBAL_STATS_ROLES:
        return None
    if role in SECRETARIAT_ROLES:
        sec = getattr(user, 'secretariat', None)
        if not sec:
            return 'Aucun secrétariat rattaché.'
        if not Formation.objects.filter(pk=formation_id, modules__secretariat=sec).exists():
            return 'Formation non autorisée.'
        return None
    if role == 'ENCADRANT':
        if not Formation.objects.filter(pk=formation_id, modules__superviseur=user).exists():
            return 'Formation non autorisée.'
        return None
    return 'Accès non autorisé.'


def _validate_module(user, module_id: int, scope: StatsScope) -> Optional[str]:
    try:
        module = Module.objects.get(pk=module_id)
    except Module.DoesNotExist:
        return 'Module introuvable.'

    role = user_stats_role(user)
    if role in SECRETARIAT_ROLES:
        sec = getattr(user, 'secretariat', None)
        if not sec or module.secretariat_id != sec.id:
            return 'Module non autorisé.'
    elif role == 'ENCADRANT':
        if module.superviseur_id != user.id:
            return 'Module non autorisé.'
    if scope.secretariat_id and module.secretariat_id != scope.secretariat_id:
        return 'Module hors périmètre.'
    if scope.formation_id and module.formation_id != scope.formation_id:
        return 'Module hors périmètre.'
    return None


def formations_liste_for_user(user, limit=50) -> list:
    qs = Formation.objects.order_by('-id')
    role = user_stats_role(user)
    if role in SECRETARIAT_ROLES and getattr(user, 'secretariat_id', None):
        qs = qs.filter(modules__secretariat_id=user.secretariat_id).distinct()
    elif role == 'ENCADRANT':
        qs = qs.filter(modules__superviseur=user).distinct()
    return list(qs.values('id', 'formation')[:limit])


def secretariats_liste_for_user(user) -> list:
    qs = Secretariat.objects.order_by('nom')
    role = user_stats_role(user)
    if role in SECRETARIAT_ROLES and getattr(user, 'secretariat_id', None):
        qs = qs.filter(pk=user.secretariat_id)
    elif role == 'ENCADRANT':
        qs = qs.filter(pk__in=encadrant_secretariat_ids(user))
    return list(qs.values('id', 'nom', 'numero'))


def secretariats_stats_queryset(user):
    qs = Secretariat.objects.order_by('nom').prefetch_related('responsable')
    role = user_stats_role(user)
    if role in SECRETARIAT_ROLES and getattr(user, 'secretariat_id', None):
        return qs.filter(pk=user.secretariat_id)
    if role == 'ENCADRANT':
        sec_ids = encadrant_secretariat_ids(user)
        return qs.filter(pk__in=sec_ids) if sec_ids else qs.none()
    return qs


def module_filter_kwargs(scope: StatsScope) -> dict:
    """Filtres ORM Module à partir du périmètre."""
    kw = {}
    if scope.module_ids is not None:
        kw['id__in'] = scope.module_ids
    return kw


def rapports_queryset_for_user(user):
    qs = Rapport.objects.all()
    role = user_stats_role(user)
    if role in GLOBAL_STATS_ROLES:
        return qs
    if role in SECRETARIAT_ROLES and getattr(user, 'secretariat_id', None):
        return qs.filter(secretariat_id=user.secretariat_id)
    if role == 'ENCADRANT':
        sec_ids = encadrant_secretariat_ids(user)
        return qs.filter(
            Q(generateur=user) | Q(secretariat_id__in=sec_ids),
        ).distinct()
    return qs.none()


def rapport_accessible(user, rapport: Rapport) -> bool:
    role = user_stats_role(user)
    if role in GLOBAL_STATS_ROLES:
        return True
    if role in SECRETARIAT_ROLES:
        return (
            getattr(user, 'secretariat_id', None) is not None
            and rapport.secretariat_id == user.secretariat_id
        )
    if role == 'ENCADRANT':
        if rapport.generateur_id == user.id:
            return True
        return rapport.secretariat_id in encadrant_secretariat_ids(user)
    return False
