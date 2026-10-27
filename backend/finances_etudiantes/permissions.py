"""Permissions pour le module Finances Étudiantes (L6).
    
Lecture : ADMIN, DIRECTION, CHEF_SECRETARIAT, SECRETARIAT, FINANCE
Écriture/validation : FINANCE, DIRECTION
Audit : ADMIN, AUDITEUR
"""
from rest_framework import permissions


class IsGestionFinanciere(permissions.BasePermission):
    """FINANCE / DIRECTION : accès en écriture complète."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.role in ['FINANCE', 'DIRECTION', 'ADMIN']


class IsFinancesReadOnly(permissions.BasePermission):
    """Secrétariat/Direction/Finance : lecture + actions autorisées."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.role in ['FINANCE', 'DIRECTION', 'CHEF_SE   TARIAT', 'SECRETARIAT', 'ADMIN']
