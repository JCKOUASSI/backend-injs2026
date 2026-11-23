"""Permissions du lot L4 (diplômation).

Lecture publique limitée au portail de vérification (token, aucune donnée
sensible). Toute autre opération nécessite un rôle de gestion
(SECRETARIAT/DIRECTION) ; la signature/validateur final est réservé à
DIRECTION/DFRC.
"""
from rest_framework.permissions import BasePermission, SAFE_METHODS

from authentication.role_groups import user_in_roles


class IsSecretariatOrAbove(BasePermission):
    """Secrétariat, Chef Secrétariat, DFRC, DIRECTION ou ADMIN : opérations courantes."""

    def has_permission(self, request, view):
        u = request.user
        if not (u and u.is_authenticated):
            return False
        return user_in_roles(u, ('SECRETARIAT', 'CHEF_SECRETARIAT', 'DFRC', 'DIRECTION', 'ADMIN'))


class IsDirectionOrAdmin(BasePermission):
    """DIRECTION, DFRC ou ADMIN uniquement : validation et révocation."""

    def has_permission(self, request, view):
        u = request.user
        if not (u and u.is_authenticated):
            return False
        return user_in_roles(u, ('DFRC', 'DIRECTION', 'ADMIN'))


class IsSecretariatOrReadOnly(BasePermission):
    """Lecture pour gestion, écriture réservée à SECRETARIAT et au-dessus."""

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return bool(request.user and request.user.is_authenticated)
        return IsSecretariatOrAbove().has_permission(request, view)

