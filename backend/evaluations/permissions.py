"""C1 — RBAC des évaluations académiques.

Choix d'implémentation (conformément au contrat B.1 §23) :

* Les **rôles** sont ceux déjà canoniques du projet (12 rôles). Aucun rôle
  n'est créé, et ``CPFAE_ADMIN`` / ``CHEF_CPFAE_ADMIN`` restent proscrits.
* C1 n'ajoute **aucune** entrée au catalogue global
  ``habilitations.referentiel.catalogue_modules`` : modifier ce catalogue
  affecte la matrice de permissions de toutes les applications et relève
  d'une vague dédiée (C1.1) avec tests spécifiques. Les permissions sont
  donc portées ici, par rôle, sur le modèle déjà utilisé par
  ``suiviEvaluation.permissions``.
* Les points d'entrée qui doivent s'appuyer sur des ``code_permission``
  CURP (par exemple ``evaluations.note.*``) seront câblés en C2 via
  ``habilitations.permissions.ExigePermission``.

Isolation ENCADRANT : un encadrant ne voit et ne modifie que les
évaluations rattachées à **ses** affectations pédagogiques. Le filtre est
appliqué dans les querysets (jamais seulement dans l'IHM).
"""
from rest_framework.permissions import BasePermission

from authentication.role_groups import get_user_role

#: Rôles de gestion structurelle (scolarité, encadrement, direction).
ROLES_GESTION = {
    'ADMIN', 'DIRECTION', 'CHEF_INJS_ADMIN', 'INJS_ADMIN',
    'CHEF_SECRETARIAT', 'SECRETARIAT', 'ENCADRANT', 'SUPERVISEUR',
}

#: Rôles de lecture seule de la consultation (hors gestion).
ROLES_CONSULTATION = ROLES_GESTION | {'FINANCE', 'ARCHIVE'}

#: Rôles non Students : l'étudiant n'accède pas au socle d'évaluation.
ROLES_EXCLUS = {'AUDITEUR', 'FORMATEUR'}


def role(user):
    """Rôle canonique de l'utilisateur ('' si absent)."""
    try:
        return get_user_role(user) or ''
    except Exception:      # pragma: no cover - garde-fou de robustesse
        return ''


def peut_consulter(user):
    if not user or not user.is_authenticated:
        return False
    if role(user) in ROLES_EXCLUS:
        return False
    return role(user) in ROLES_CONSULTATION


def peut_gerer(user):
    """Gestion structurelle (création/modification)."""
    if not user or not user.is_authenticated:
        return False
    return role(user) in ROLES_GESTION


def peut_saisir_notes(user):
    """Saisie des notes : encadrant et rôles supérieurs.

    Le périmètre ENCADRANT est appliqué **en plus** dans les vues.
    """
    return peut_gerer(user)


def formateur_de(user):
    """Formateur rattaché au compte (None si le compte n'est pas encadrant)."""
    if not user or not user.is_authenticated:
        return None
    return getattr(user, 'formateur_profile', None)


def perimetre_affectations(user):
    """Affectations pédagogiques visibles pour l'utilisateur.

    * Rôles de gestion non encadrants : toutes les affectations.
    * ENCADRANT : uniquement ses propres affectations.
    * Rôles non autorisés : queryset vide (defense in depth).
    """
    from evaluations.models import AffectationPedagogique

    if not peut_gerer(user):
        return AffectationPedagogique.objects.none()
    formateur = formateur_de(user)
    if formateur is not None:
        return AffectationPedagogique.objects.filter(enseignant=formateur)
    return AffectationPedagogique.objects.all()


class EstConsultantEvaluations(BasePermission):
    """Lecture des données d'évaluation (hors étudiants)."""

    message = "Accès à la consultation des évaluations refusé."

    def has_permission(self, request, view):
        return peut_consulter(request.user)


class EstGestionEvaluations(BasePermission):
    """Création / modification de la structure d'évaluation."""

    message = "Gestion des évaluations réservée à la scolarité, l'encadrement ou la direction."

    def has_permission(self, request, view):
        return peut_gerer(request.user)


class EstEncadrantOuScolarite(EstGestionEvaluations):
    """Alias explicite : même contrôle que :class:`EstGestionEvaluations`.

    Nommé pour la lisibilité des vues ; le filtrage de périmètre reste
    effectué par ``views._perimetre_evaluations``.
    """