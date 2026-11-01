"""Permissions du module Finances Étudiantes (L6).

Matrice **alignée sur l'interface** (`frontend/src/pages/scolarite/FinancesEtudiantes.jsx`) :

* lecture        : tout rôle admis sur la scolarité (écrans « Finances étudiantes »
  visibles dès `scolarite.voir` ou `finance.voir`) ;
* écriture       : saisie d'un paiement, génération d'un échéancier ou d'une facture ;
* actes sensibles : confirmation d'un paiement (qui crée une quittance), remboursement,
  rapprochement comptable.

Ces trois niveaux étaient décrits mais jamais branchés : les vues ne portaient que
``IsAuthenticated``, si bien qu'un compte étudiant (``AUDITEUR``) pouvait lire
l'intégralité des paiements de l'établissement par appel direct de l'API, alors que
l'interface lui masque le module. Les ensembles ci-dessous reprennent exactement les
rôles que l'interface utilise déjà (``peutConfirmer`` / ``peutEcrire``) : aucune
restriction nouvelle n'est inventée, elle est seulement appliquée côté serveur.

Le module respecte les rôles **multiples** (``get_user_roles``) et non le seul champ
dénormalisé ``User.role`` : un compte cumulant plusieurs rôles obtient l'union de
leurs droits, comme partout ailleurs dans le projet.
"""
from rest_framework import permissions

from authentication.role_groups import ADMIN_LEVEL_ROLES, SECRETARIAT_ROLES, user_in_roles

#: Rôles autorisés à consulter les données financières des étudiants.
#: Union de `scolarite.voir` (lecture) et `finance.voir`, définie dans
#: `authentication/capabilities.py`.
ROLES_LECTURE_FINANCES = frozenset({
    *ADMIN_LEVEL_ROLES,       # ADMIN, CHEF_INJS_ADMIN, INJS_ADMIN
    *SECRETARIAT_ROLES,       # CHEF_SECRETARIAT, SECRETARIAT
    'DIRECTION',
    'FINANCE',
    'ARCHIVE',
    'ENCADRANT',
})

#: Rôles autorisés à saisir un paiement / générer un échéancier ou une facture.
ROLES_ECRITURE_FINANCES = frozenset({
    *ADMIN_LEVEL_ROLES,
    *SECRETARIAT_ROLES,
    'DIRECTION',
    'FINANCE',
})

#: Rôles autorisés à confirmer un paiement, rembourser, rapprocher.
ROLES_VALIDATION_FINANCES = frozenset({
    *ADMIN_LEVEL_ROLES,
    'DIRECTION',
    'FINANCE',
})


class _BaseFinance(permissions.BasePermission):
    roles = frozenset()
    message = "Votre rôle ne permet pas cette opération sur les finances étudiantes."

    def has_permission(self, request, view):
        user = getattr(request, 'user', None)
        if not (user and getattr(user, 'is_authenticated', False)):
            return False
        return user_in_roles(user, self.roles)


class IsFinancesReadOnly(_BaseFinance):
    """Lecture des données financières (échéanciers, paiements, quittances…)."""

    roles = ROLES_LECTURE_FINANCES


class IsGestionFinanciere(_BaseFinance):
    """Écriture courante : saisie d'un paiement, génération d'échéancier/facture."""

    roles = ROLES_ECRITURE_FINANCES


class IsValidationFinanciere(_BaseFinance):
    """Actes sensibles : confirmation de paiement, remboursement, rapprochement."""

    roles = ROLES_VALIDATION_FINANCES


class _SelonMethode(permissions.BasePermission):
    """Applique une permission de lecture aux GET et une autre aux écritures."""

    lecture = IsFinancesReadOnly
    ecriture = IsGestionFinanciere

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return self.lecture().has_permission(request, view)
        return self.ecriture().has_permission(request, view)


class IsFinancesLectureOuGestion(_SelonMethode):
    """Listes mixtes : GET en lecture, POST en saisie courante."""

    lecture = IsFinancesReadOnly
    ecriture = IsGestionFinanciere


class IsFinancesLectureOuValidation(_SelonMethode):
    """Listes mixtes dont l'écriture est un acte sensible (remboursement, rapprochement)."""

    lecture = IsFinancesReadOnly
    ecriture = IsValidationFinanciere
