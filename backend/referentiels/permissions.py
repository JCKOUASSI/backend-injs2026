"""Permissions des référentiels (lot L0/L7 + mission « Référentiels »).

Consultation : tout utilisateur authentifié (les référentiels alimentent
les écrans web et mobile — règle 9).
Édition : rôles de gestion uniquement, via get_user_roles (pattern parametres).

Mission « Référentiels » — exigence sécurité : chaque opération est protégée
**individuellement** côté backend. Masquer un bouton dans React n'est jamais
une protection ; c'est bien le serveur qui décide.

Aucun système RBAC parallèle n'est créé : on réutilise ``get_user_roles``
(module ``authentication``) et les permissions du module ``habilitations``
lorsqu'elles sont disponibles.
"""

from rest_framework.permissions import SAFE_METHODS, BasePermission

from authentication.role_groups import get_user_roles

ROLES_EDITION_REFERENTIEL = frozenset({
    'ADMIN',
    'DIRECTION',
    'CHEF_INJS_ADMIN',
    'INJS_ADMIN',
    'CHEF_SECRETARIAT',
    'SECRETARIAT',
})

# Opération de référentiel → rôles autorisés.
# Une opération non listée suit la règle d'édition générale.
ROLES_PAR_OPERATION = {
    'exporter': ROLES_EDITION_REFERENTIEL,          # export de données : édition
    'importer': ROLES_EDITION_REFERENTIEL,          # écriture en masse
    'importer_analyse': ROLES_EDITION_REFERENTIEL,  # révèle des données du référentiel
    'activer': ROLES_EDITION_REFERENTIEL,
    'desactiver': ROLES_EDITION_REFERENTIEL,
    'archiver': ROLES_EDITION_REFERENTIEL,
    'reactiver': ROLES_EDITION_REFERENTIEL,
    'supprimer': frozenset({'ADMIN', 'DIRECTION'}),  # destruction logique : restreinte
}


class ReferentielPermission(BasePermission):
    """Lecture pour tout authentifié ; écriture pour les rôles de gestion.

    Les opérations sensibles (import, export, suppression) sont en plus
    filtrées par :attr:`ROLES_PAR_OPERATION`.
    """

    message = "Vous n'avez pas la permission de gérer les référentiels."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        roles = get_user_roles(request.user)

        # Opérations sensibles : protégées **individuellement**, même en
        # méthode sûre. Un export est une lecture, mais il extrait des
        # données du référentiel : il n'est donc pas ouvert à tous.
        operation = getattr(view, 'action', None)
        if operation in ROLES_PAR_OPERATION:
            if not (roles & ROLES_PAR_OPERATION[operation]):
                return False
            return bool(roles & ROLES_EDITION_REFERENTIEL)

        if request.method in SAFE_METHODS:
            return True
        return bool(roles & ROLES_EDITION_REFERENTIEL)

    @staticmethod
    def _operation_autorisee(view, roles):
        operation = getattr(view, 'action', None)
        attendus = ROLES_PAR_OPERATION.get(operation)
        if attendus is None:
            return True
        if roles & attendus:
            return True
        return False


class GererReferentielPermission(ReferentielPermission):
    """Alias explicite pour les vues d'administration du référentiel."""

    message = "Vous n'avez pas la permission de gérer ce référentiel."


class PeutExporterReferentiel(BasePermission):
    """Export : réservé aux rôles de gestion (les exports contiennent des données)."""

    message = "Vous n'avez pas la permission d'exporter les référentiels."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return bool(get_user_roles(request.user) & ROLES_EDITION_REFERENTIEL)


class PeutImporterReferentiel(BasePermission):
    """Import : réservé aux rôles de gestion (écriture en masse)."""

    message = "Vous n'avez pas la permission d'importer des données dans les référentiels."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return bool(get_user_roles(request.user) & ROLES_EDITION_REFERENTIEL)


class PeutSupprimerReferentiel(BasePermission):
    """Suppression (archivage) : restreinte à l'administration."""

    message = ("Vous n'avez pas la permission de supprimer une valeur de référentiel. "
               "Cette opération est réservée à l'administration.")

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return bool(get_user_roles(request.user) & ROLES_PAR_OPERATION['supprimer'])
