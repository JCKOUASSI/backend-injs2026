"""Permissions du lot L4 (diplômation).

Lecture publique limitée au portail de vérification (token, aucune donnée
sensible). Toute autre opération nécessite un rôle de gestion
(SECRETARIAT/DIRECTION) ; la signature/validateur final est réservé à
DIRECTION / INJS_ADMIN.
"""
from rest_framework.permissions import BasePermission, SAFE_METHODS

from authentication.role_groups import user_in_roles

# Rôles de gestion courante (création, édition, consultation) des diplômes.
GESTION_ROLES = (
    'SECRETARIAT', 'CHEF_SECRETARIAT', 'CHEF_INJS_ADMIN', 'INJS_ADMIN',
    'DIRECTION', 'ADMIN',
)
# Actes de signature : validation et révocation d'un diplôme.
VALIDATION_ROLES = ('CHEF_INJS_ADMIN', 'INJS_ADMIN', 'DIRECTION', 'ADMIN')


class IsSecretariatOrAbove(BasePermission):
    """Secrétariat, Chef Secrétariat, INJS_ADMIN, DIRECTION ou ADMIN : opérations courantes."""

    def has_permission(self, request, view):
        u = request.user
        if not (u and u.is_authenticated):
            return False
        return user_in_roles(u, GESTION_ROLES)


class IsDirectionOrAdmin(BasePermission):
    """DIRECTION, INJS_ADMIN ou ADMIN uniquement : validation et révocation."""

    def has_permission(self, request, view):
        u = request.user
        if not (u and u.is_authenticated):
            return False
        return user_in_roles(u, VALIDATION_ROLES)


class IsSecretariatOrReadOnly(BasePermission):
    """Lecture pour gestion, écriture réservée à SECRETARIAT et au-dessus."""

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return bool(request.user and request.user.is_authenticated)
        return IsSecretariatOrAbove().has_permission(request, view)

