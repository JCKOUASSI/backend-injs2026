import logging

from rest_framework.permissions import BasePermission

from authentication.role_groups import (
    ROLE_GROUP_NAMES,
    ROLE_HIERARCHY,
    USER_MUTATION_ROLES,
    get_subordinate_roles,
    get_creatable_roles,
    get_user_role,
    user_has_perm,
    user_in_roles,
    _cached_user_groups,
)

logger = logging.getLogger(__name__)

__all__ = [
    'ROLE_HIERARCHY',
    'get_subordinate_roles',
    'get_creatable_roles',
    'ROLE_GROUP_NAMES',
    '_has_role',
    '_in_groups',
    '_model_perm',
    'HasFormationsPerm',
    'CanManageParticipant',
    'CanManageModuleParticipant',
    'IsDFRC',
    'IsDFRCOrEncadrant',
    'IsParticipantOrReadOnly',
    'IsSecretariat',
    'IsEncadrant',
    'IsSecretariatOrEncadrant',
    'IsSecretariatOrDFRC',
    'IsSecretariatOrEncadrantOrDFRC',
    'IsUserMutationAllowed',
    'get_user_role',
    'user_in_roles',
    'user_has_perm',
]

# Hiérarchie et helpers de création : source canonique authentication.role_groups


def _in_groups(user, *roles):
    """Vérifie si l'utilisateur appartient au groupe de rôle d'au moins un des rôles donnés."""
    target = {ROLE_GROUP_NAMES[r] for r in roles if r in ROLE_GROUP_NAMES}
    return bool(_cached_user_groups(user) & target)


def _has_role(user, *roles):
    """Vérifie le rôle effectif via les groupes Django ROLE_*.

    Les groupes Django sont la source de vérité pour les rôles et permissions.
    Le champ ``User.role`` est une dénormalisation synchronisée automatiquement.
    """
    return _in_groups(user, *roles) or get_user_role(user) in roles


def _model_perm(request, app_label, model_name):
    """Vérifie la permission Django correspondant à la méthode HTTP et au modèle donné.

    Utilise has_perm() qui consulte les permissions des groupes de l'utilisateur.
    Les permissions sont mises en cache par Django après le premier appel.
    """
    if request.method in ('GET', 'HEAD', 'OPTIONS'):
        codename = f'{app_label}.view_{model_name}'
    elif request.method == 'POST':
        codename = f'{app_label}.add_{model_name}'
    elif request.method in ('PUT', 'PATCH'):
        codename = f'{app_label}.change_{model_name}'
    elif request.method == 'DELETE':
        codename = f'{app_label}.delete_{model_name}'
    else:
        return False
    return request.user.has_perm(codename)


class HasFormationsPerm(BasePermission):
    """Classe de base : vérifie la permission Django sur un modèle de l'app formations.

    Utilise has_perm() qui consulte les permissions réelles du groupe de l'utilisateur,
    respectant ainsi les changements effectués dans l'admin Django ou via ROLE_POLICY.
    Les sous-classes définissent `model_name` pour cibler un modèle précis.
    """
    model_name = None  # À surcharger dans les sous-classes

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        return _model_perm(request, 'formations', self.model_name)


class CanManageParticipant(HasFormationsPerm):
    """Permission basée sur les droits réels du groupe pour le modèle Participant."""
    model_name = 'participant'


class CanManageModuleParticipant(HasFormationsPerm):
    """Permission basée sur les droits réels du groupe pour l'inscription d'un participant à un module."""
    model_name = 'moduleparticipant'


class IsDFRC(BasePermission):
    """ADMIN/CHEF_INJS_ADMIN/INJS_ADMIN : accès complet. Direction : lecture seule."""
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if _has_role(request.user, 'ADMIN', 'INJS_ADMIN', 'CHEF_INJS_ADMIN'):
            return True
        if _has_role(request.user, 'DIRECTION', 'ARCHIVE') and request.method in ('GET', 'HEAD', 'OPTIONS'):
            return True
        return False


class IsDFRCOrEncadrant(BasePermission):
    """ADMIN/CHEF_INJS_ADMIN/INJS_ADMIN/Encadrant : accès complet. Direction/Archiviste : lecture seule."""
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if _has_role(request.user, 'ADMIN', 'INJS_ADMIN', 'CHEF_INJS_ADMIN', 'ENCADRANT'):
            return True
        if _has_role(request.user, 'DIRECTION', 'ARCHIVE') and request.method in ('GET', 'HEAD', 'OPTIONS'):
            return True
        return False


class IsParticipantOrReadOnly(BasePermission):
    """Participant peut lire ses propres données."""
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated


class IsSecretariat(BasePermission):
    """Accès réservé aux secrétariats et chef secrétariat."""
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and _has_role(request.user, 'SECRETARIAT', 'CHEF_SECRETARIAT')
        )


class IsEncadrant(BasePermission):
    """Accès réservé aux encadrants."""
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and _has_role(request.user, 'ENCADRANT')
        )


class IsSecretariatOrEncadrant(BasePermission):
    """Secrétariat, Chef Secrétariat et Encadrant."""
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and _has_role(request.user, 'SECRETARIAT', 'CHEF_SECRETARIAT', 'ENCADRANT')
        )


class IsSecretariatOrDFRC(BasePermission):
    """ADMIN/Secrétariat/DFRC : accès complet. Direction et Finance : lecture seule."""
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if _has_role(
            request.user,
            'ADMIN', 'SECRETARIAT', 'CHEF_SECRETARIAT', 'INJS_ADMIN', 'CHEF_INJS_ADMIN',
        ):
            return True
        if _has_role(
            request.user, 'DIRECTION', 'FINANCE', 'ENCADRANT', 'ARCHIVE',
        ) and request.method in ('GET', 'HEAD', 'OPTIONS'):
            return True
        return False


class IsUserMutationAllowed(BasePermission):
    """Création / modification / suppression de comptes utilisateurs."""

    message = (
        "Vous n'avez pas les droits pour créer ou modifier des comptes utilisateurs. "
        "Réservé aux rôles : Administrateur, Chef CPFAE Admin, CPFAE Admin, "
        "Chef Secrétariat et Secrétariat."
    )

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if user_has_perm(request.user, 'authentication.mutate_users'):
            return True
        role = get_user_role(request.user)
        if role in USER_MUTATION_ROLES:
            return True
        logger.warning(
            'user_mutation_denied user=%s role=%s method=%s path=%s',
            request.user.username,
            role,
            request.method,
            getattr(request, 'path', ''),
        )
        return False


class IsSecretariatOrEncadrantOrDFRC(BasePermission):
    """ADMIN, Secrétariat, Chef Secrétariat, Encadrant, INJS_ADMIN, Chef INJS_ADMIN : accès complet. Direction : lecture seule."""
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if _has_role(request.user, 'ADMIN', 'SECRETARIAT', 'CHEF_SECRETARIAT', 'ENCADRANT', 'INJS_ADMIN', 'CHEF_INJS_ADMIN'):
            return True
        if _has_role(request.user, 'DIRECTION', 'ARCHIVE') and request.method in ('GET', 'HEAD', 'OPTIONS'):
            return True
        return False
