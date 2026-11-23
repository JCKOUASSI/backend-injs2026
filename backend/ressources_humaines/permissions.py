"""Permissions du lot L7 — Ressources Humaines.

Consultation : Secrétariat, Chef Secrétariat, DFRC, DIRECTION, ADMIN.
Gestion (agents, affectations, documents) : rôles de gestion.
Opérations RH sensibles : DIRECTION/ADMIN.
"""
from rest_framework.permissions import BasePermission, SAFE_METHODS

from authentication.role_groups import user_in_roles


CONSULTATION_ROLES = ('SECRETARIAT', 'CHEF_SECRETARIAT', 'DFRC', 'DIRECTION', 'ADMIN')
GESTION_ROLES = ('CHEF_SECRETARIAT', 'DFRC', 'DIRECTION', 'ADMIN')


class IsConsultationRH(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        if not (u and u.is_authenticated):
            return False
        return user_in_roles(u, CONSULTATION_ROLES)


class IsGestionRH(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        if not (u and u.is_authenticated):
            return False
        return user_in_roles(u, GESTION_ROLES)


class IsGestionRHOrReadOnly(BasePermission):
    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return bool(request.user and request.user.is_authenticated)
        return IsGestionRH().has_permission(request, view)