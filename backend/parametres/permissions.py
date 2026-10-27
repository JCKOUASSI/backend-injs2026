"""
Permissions Django Rest Framework pour le module Paramètres.

Contrôle d'accès granulaire par rôle.
"""

from rest_framework.permissions import BasePermission


class CanViewParametre(BasePermission):
    """
    Permission de consultation d'un paramètre.
    
    Vérifie:
    - Utilisateur authentifié
    - Paramètre actif
    - Rôle utilisateur dans lecturable_par_roles du paramètre
    """

    message = "Vous n'avez pas la permission de consulter ce paramètre."

    def has_permission(self, request, view):
        """Authentification obligatoire."""
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        """Vérifier lecturable_par_roles."""
        if not obj.actif:
            return False
        return obj.can_be_read_by(request.user)


class CanEditParametre(BasePermission):
    """
    Permission de modification d'un paramètre.
    
    Vérifie:
    - Utilisateur authentifié
    - Paramètre modifiable=True et actif
    - Rôle utilisateur dans modifiable_par_roles du paramètre
    """

    message = "Vous n'avez pas la permission de modifier ce paramètre."

    def has_permission(self, request, view):
        """Authentification obligatoire."""
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        """Vérifier modifiable + modifiable_par_roles."""
        if not obj.modifiable or not obj.actif:
            return False
        return obj.can_be_modified_by(request.user)
