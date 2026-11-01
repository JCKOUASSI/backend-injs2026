"""Permissions du lot L7 — Patrimoine.

Gestion (équipements, maintenances, réservations) : Secrétariat, Chef
Secrétariat, INJS_ADMIN, DIRECTION, ADMIN. Validation des réservations :
DIRECTION / INJS_ADMIN / ADMIN. Lecture : tout utilisateur authentifié.
"""
from rest_framework.permissions import BasePermission, SAFE_METHODS

from authentication.role_groups import user_in_roles


GESTION_ROLES = ('SECRETARIAT', 'CHEF_SECRETARIAT', 'CHEF_INJS_ADMIN', 'INJS_ADMIN', 'DIRECTION', 'ADMIN')
VALIDATION_ROLES = ('CHEF_INJS_ADMIN', 'INJS_ADMIN', 'DIRECTION', 'ADMIN')


class IsGestionPatrimoine(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        if not (u and u.is_authenticated):
            return False
        return user_in_roles(u, GESTION_ROLES)


class IsValidationPatrimoine(BasePermission):
    """Validation des réservations et des maintenances sensibles."""

    def has_permission(self, request, view):
        u = request.user
        if not (u and u.is_authenticated):
            return False
        return user_in_roles(u, VALIDATION_ROLES)


class IsGestionPatrimoineOrReadOnly(BasePermission):
    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return bool(request.user and request.user.is_authenticated)
        return IsGestionPatrimoine().has_permission(request, view)