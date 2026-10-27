from rest_framework.permissions import BasePermission

from authentication.permissions import _has_role
from authentication.role_groups import get_user_role, user_has_perm


ROLES_SUPERVISEUR = {'SUPERVISEUR', 'ADMIN', 'INJS_ADMIN', 'CHEF_INJS_ADMIN'}

# Aligné sur frontend EVALUATION_ALLOWED_ROLES
ROLES_GESTION_QUESTIONNAIRES = ROLES_SUPERVISEUR | {
    'CHEF_SECRETARIAT', 'SECRETARIAT', 'ENCADRANT',
}

# Rôles autorisés à saisir/gérer les notes et épreuves
ROLES_GESTION_NOTES = {
    'ADMIN', 'DIRECTION', 'CHEF_INJS_ADMIN', 'INJS_ADMIN',
    'CHEF_SECRETARIAT', 'SECRETARIAT', 'ENCADRANT', 'SUPERVISEUR',
}

# Rôles autorisés à valider les décisions pédagogiques
ROLES_DECISION = {
    'ADMIN', 'DIRECTION', 'CHEF_INJS_ADMIN', 'INJS_ADMIN', 'ENCADRANT', 'SUPERVISEUR',
}

# Rôles ayant accès en lecture aux fiches/tableaux de bord
ROLES_CONSULTATION = ROLES_GESTION_NOTES | {'FINANCE', 'ARCHIVE'}

# Export des fiches et relevés (archiviste : export global)
ROLES_FICHE_EXPORT = ROLES_GESTION_NOTES | {'ARCHIVE'}


def _can_manage_questionnaires(user):
    return user_has_perm(user, 'authentication.manage_questionnaires') or _has_role(
        user, *ROLES_GESTION_QUESTIONNAIRES
    )


def _can_manage_notes(user):
    return user_has_perm(user, 'authentication.manage_notes') or get_user_role(user) in ROLES_GESTION_NOTES


def _can_consult_evaluation(user):
    return user_has_perm(user, 'authentication.consult_evaluation') or get_user_role(user) in ROLES_CONSULTATION


def _can_validate_decisions(user):
    return user_has_perm(user, 'authentication.validate_decisions') or get_user_role(user) in ROLES_DECISION


class IsSuperviseur(BasePermission):
    """Secrétariat, encadrants, superviseurs et admins peuvent gérer les questionnaires."""
    def has_permission(self, request, view):
        return request.user.is_authenticated and _can_manage_questionnaires(request.user)


class IsAuditeur(BasePermission):
    """Seuls les auditeurs peuvent soumettre des réponses."""
    def has_permission(self, request, view):
        return request.user.is_authenticated and _has_role(request.user, 'AUDITEUR')


class IsSuperviseurOrReadOnly(BasePermission):
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.method in ('GET', 'HEAD', 'OPTIONS'):
            return True
        return _can_manage_questionnaires(request.user)


class IsGestionNotes(BasePermission):
    """Secrétariat, encadrants et au-dessus peuvent saisir/gérer les notes."""
    def has_permission(self, request, view):
        return request.user.is_authenticated and _can_manage_notes(request.user)


class IsGestionNotesOrReadOnly(BasePermission):
    """Lecture pour tous les rôles de consultation, écriture pour gestion notes."""
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.method in ('GET', 'HEAD', 'OPTIONS'):
            return _can_consult_evaluation(request.user)
        return _can_manage_notes(request.user)


class IsDecisionValidator(BasePermission):
    """Direction/encadrants peuvent valider les décisions pédagogiques."""
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.method in ('GET', 'HEAD', 'OPTIONS'):
            return _can_consult_evaluation(request.user)
        return _can_validate_decisions(request.user)
