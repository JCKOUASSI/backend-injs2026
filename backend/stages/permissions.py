"""Permissions du lot L5 — Stages et conventions.

Gestion (CRUD, transitions) : Secrétariat, Chef Secrétariat, Encadrant interne,
INJS_ADMIN, DIRECTION, ADMIN. Validation finale (VALIDEE_JURY) réservée à DIRECTION/ADMIN.
"""
from rest_framework.permissions import BasePermission, SAFE_METHODS

from authentication.role_groups import user_in_roles

# Rôles de gestion des stages et conventions.
GESTION_ROLES = (
    'SECRETARIAT', 'CHEF_SECRETARIAT', 'ENCADRANT',
    'CHEF_INJS_ADMIN', 'INJS_ADMIN', 'DIRECTION', 'ADMIN',
)
# Validation finale (convention VALIDEE_JURY) et archivage.
VALIDATION_ROLES = ('CHEF_INJS_ADMIN', 'INJS_ADMIN', 'DIRECTION', 'ADMIN')


class IsSecretariatOrEncadrant(BasePermission):
    """Secrétariat, Chef Secrétariat, Encadrant interne, INJS_ADMIN, DIRECTION, ADMIN."""

    def has_permission(self, request, view):
        u = request.user
        if not (u and u.is_authenticated):
            return False
        return user_in_roles(u, GESTION_ROLES)


class IsDirectionOrAdmin(BasePermission):
    """DIRECTION / INJS_ADMIN / ADMIN : validation finale et archivage."""

    def has_permission(self, request, view):
        u = request.user
        if not (u and u.is_authenticated):
            return False
        return user_in_roles(u, VALIDATION_ROLES)


class IsSecretariatOrEncadrantOrReadOnly(BasePermission):
    """Lecture pour authentifié, écriture pour Secrétariat/Encadrant et au-dessus."""

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return bool(request.user and request.user.is_authenticated)
        return IsSecretariatOrEncadrant().has_permission(request, view)
