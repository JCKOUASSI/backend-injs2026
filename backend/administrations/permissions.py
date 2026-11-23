"""Permissions du lot L7 — Administration générale.

Gestion : Secrétariat, Chef Secrétariat, DFRC, DIRECTION, ADMIN.
Validation finale (signature document, mission) : DIRECTION/ADMIN.
"""
from rest_framework.permissions import BasePermission, SAFE_METHODS

from authentication.role_groups import user_in_roles


GESTION_ROLES = ('SECRETARIAT', 'CHEF_SECRETARIAT', 'DFRC', 'DIRECTION', 'ADMIN')
VALIDATION_ROLES = ('DIRECTION', 'ADMIN')


class IsGestionAdministration(BasePermission):
    """Écriture réservée aux rôles de gestion de l'administration."""

    def has_permission(self, request, view):
        u = request.user
        if not (u and u.is_authenticated):
            return False
        return user_in_roles(u, GESTION_ROLES)


class IsDirectionOrAdminAdministration(BasePermission):
    """Rôles de validation finale."""

    def has_permission(self, request, view):
        u = request.user
        if not (u and u.is_authenticated):
            return False
        return user_in_roles(u, VALIDATION_ROLES)


class IsGestionOrReadOnly(BasePermission):
    """Lecture pour tout utilisateur authentifié, écriture pour la gestion."""

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return bool(request.user and request.user.is_authenticated)
        return IsGestionAdministration().has_permission(request, view)