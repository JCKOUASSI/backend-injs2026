"""Permissions du lot L7 — Patrimoine.

Gestion (équipements, maintenances, réservations) : Secrétariat, Chef
Secrétariat, DFRC, DIRECTION, ADMIN. Validation des réservations :
DIRECTION/ADMIN (ou DFRC). Lecture : tout utilisateur authentifié.
"""
from rest_framework.permissions import BasePermission, SAFE_METHODS

from authentication.role_groups import user_in_roles


GESTION_ROLES = ('SECRETARIAT', 'CHEF_SECRETARIAT', 'DFRC', 'DIRECTION', 'ADMIN')
VALIDATION_ROLES = ('DFRC', 'DIRECTION', 'ADMIN')


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