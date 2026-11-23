"""Permissions des référentiels (lot L0/L7).

Consultation : tout utilisateur authentifié (les référentiels alimentent
les écrans web et mobile — règle 9).
Édition : rôles de gestion uniquement, via get_user_roles (pattern parametres).
"""
from rest_framework.permissions import BasePermission, SAFE_METHODS

from authentication.role_groups import get_user_roles

ROLES_EDITION_REFERENTIEL = frozenset({
    'ADMIN',
    'DIRECTION',
    'CHEF_INJS_ADMIN',
    'INJS_ADMIN',
    'CHEF_SECRETARIAT',
    'SECRETARIAT',
})


class ReferentielPermission(BasePermission):
    """Lecture pour tout authentifié ; écriture pour les rôles de gestion."""

    message = "Vous n'avez pas la permission de gérer les référentiels."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            return True
        return bool(get_user_roles(request.user) & ROLES_EDITION_REFERENTIEL)
