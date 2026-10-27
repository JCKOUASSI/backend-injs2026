"""Permissions du module GET-INJS (lot L8) — Emploi du temps.

Répartition conforme à la matrice CURP du socle :
- lecture pour tout compte authentifié ;
- planification (créneaux, affectations, brouillons, détection) : Secrétariat,
  Chef Secrétariat, DFRC, DIRECTION, ADMIN, ENCADRANT ;
- validation / publication / dépublication / archivage : DIRECTION et ADMIN
  (les rôles « chef d'établissement » super-utilisateurs héritent d'ADMIN).

Historique : deux classes « enseignant lecture seule » étaient définies sans
jamais être branchées (code mort, docstring trompeuse) — supprimées par
l'audit du 2026-09-15 ; le filtrage « mon EDT » est désormais porté par
`GET /api/edts/emplois/?selon_role=1`.
"""

from rest_framework.permissions import BasePermission, SAFE_METHODS

from authentication.permissions import _has_role


# Correction audit 2026-09-15 : le littéral « DFRC » ne correspond à aucun rôle
# de User.Role (le socle mappe DFRC sur {ADMIN, INJS_ADMIN, CHEF_INJS_ADMIN}
# via authentication.permissions.IsDFRC). Les comptes INJS-Admin étaient donc
# silencieusement exclus de la planification. La liste reprend la matrice CURP.
PLANIFICATION_ROLES = (
    'ADMIN',
    'CHEF_INJS_ADMIN',
    'INJS_ADMIN',
    'SECRETARIAT',
    'CHEF_SECRETARIAT',
    'DIRECTION',
    'ENCADRANT',
)

VALIDATION_ROLES = ('DIRECTION', 'ADMIN')


def _peut_planifier(user):
    return bool(user and user.is_authenticated and _has_role(user, *PLANIFICATION_ROLES))


def _peut_valider(user):
    return bool(user and user.is_authenticated and _has_role(user, *VALIDATION_ROLES))


class IsEdtPlanification(BasePermission):
    """Écriture de planification (brouillon, affectations, référentiels)."""

    message = 'Seuls les rôles de planification (Secrétariat, DFRC, Encadrant, Direction, Admin) ' \
              'peuvent modifier les emplois du temps.'

    def has_permission(self, request, view):
        return _peut_planifier(request.user)


class IsEdtValidation(BasePermission):
    """Validation et publication réservées à la Direction / Admin."""

    message = 'La validation et la publication des emplois du temps sont réservées à la Direction.'

    def has_permission(self, request, view):
        return _peut_valider(request.user)


class IsEdtReadOnlyOrPlanification(BasePermission):
    """Lecture pour tout authentifié ; écriture pour la planification."""

    message = 'Droits insuffisants pour modifier les emplois du temps.'

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return bool(request.user and request.user.is_authenticated)
        return _peut_planifier(request.user)
