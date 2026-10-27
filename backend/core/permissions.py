"""Permissions du journal d'audit unifié (P01-01, décision validée).

L'accès en lecture au journal transverse est réservé aux rôles d'audit et de
direction globales, validés au cadrage P01-01 :

* N4 — ADMIN, DIRECTION, CHEF_INJS_ADMIN, INJS_ADMIN ;
* N1 — AUDITEUR (conformité) et ARCHIVE.

Les autres rôles conservent l'accès aux journaux métriers ciblés existants
(``/api/presences/audit-logs/``, ``/api/referentiels/journal/``). L'accès est
par ailleurs fermé tant que le feature flag LOT 1 est désactivé.
"""
from rest_framework.permissions import BasePermission

from authentication.role_groups import (
    ADMIN_LEVEL_ROLES,
    get_user_roles,
)
from authentication.models import User

#: Rôles autorisés à consulter le journal unifié.
AUDIT_CORE_ROLES = frozenset({
    *ADMIN_LEVEL_ROLES,          # ADMIN, CHEF_INJS_ADMIN, INJS_ADMIN
    User.Role.DIRECTION,
    User.Role.AUDITEUR,
    User.Role.ARCHIVE,
})


class PeutConsulterAuditCore(BasePermission):
    """Lecture du journal unifié réservée aux rôles d'audit validés."""

    message = "Votre rôle ne permet pas de consulter le journal d'audit unifié."

    def has_permission(self, request, view):
        user = getattr(request, 'user', None)
        if not user or not getattr(user, 'is_authenticated', False):
            return False
        return bool(get_user_roles(user) & AUDIT_CORE_ROLES)
