"""Permissions du lot L7 — Administration générale.

Consultation : rôles du personnel web opérationnel — le même ensemble que la
capacité d'interface ``web.operationnel`` (`authentication.capabilities`) qui
conditionne la section « Administration générale » du menu.
Gestion : Secrétariat, Chef Secrétariat, INJS_ADMIN, DIRECTION, ADMIN.
Validation finale (signature document, mission) : DIRECTION/ADMIN.

Le registre du courrier et les documents officiels sont des données internes :
ils étaient lisibles par **tout compte authentifié**, y compris un compte
étudiant, alors que l'interface en réserve l'accès au personnel. La classe
``IsConsultationAdministration`` aligne l'API sur l'interface.
"""
from rest_framework.permissions import BasePermission, SAFE_METHODS

from authentication.role_groups import OPERATIONAL_WEB_ROLES, user_in_roles


GESTION_ROLES = ('SECRETARIAT', 'CHEF_SECRETARIAT', 'CHEF_INJS_ADMIN', 'INJS_ADMIN', 'DIRECTION', 'ADMIN')
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


class IsConsultationAdministration(BasePermission):
    """Lecture réservée au personnel web opérationnel (hors comptes étudiants/formateurs)."""

    message = "Votre rôle ne permet pas de consulter les données de l'administration générale."

    def has_permission(self, request, view):
        u = request.user
        if not (u and u.is_authenticated):
            return False
        return user_in_roles(u, OPERATIONAL_WEB_ROLES)


class IsGestionOrReadOnly(BasePermission):
    """Lecture pour le personnel opérationnel, écriture pour la gestion."""

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return IsConsultationAdministration().has_permission(request, view)
        return IsGestionAdministration().has_permission(request, view)