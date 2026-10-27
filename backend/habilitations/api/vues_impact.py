"""Vues API de la couche IMPACT (additive — ne remplace aucune vue CURP).

Trois familles, gardées exactement comme la console U4
(:class:`ExigeDrapeauAdmin` : drapeau ``flag.curp_ui_admin`` ouvert ET trio
d'administration) : ces endpoints révèlent la cartographie des habilitations
(rôles porteurs, comptes impactés, accès effectifs) et ne doivent donc jamais
être exposés au-delà de la console.

Le calcul est entièrement délégué à ``habilitations.services.impact`` :
aucune logique d'autorisation ici, uniquement la mise en forme HTTP et les
cas d'erreur (404 objet inexistant) aux conventions du projet
(``{'detail': ..., 'code': ...}``).
"""
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from habilitations.permissions import ExigeDrapeauAdmin
from habilitations.services import impact

GARDE = [ExigeDrapeauAdmin]

CODES_INCONNU = {
    'permission': 'PERMISSION_INCONNUE',
    'role': 'ROLE_INCONNU',
    'utilisateur': 'COMPTE_INCONNU',
    'module': 'MODULE_INCONNU',
}


class ImpactModuleView(APIView):
    """GET /api/habilitations/impact/module/<code>/ — impact d'un module.

    Chaînon §28 : MODULE → PERMISSIONS → RÔLES → COMPTES. Lecture pure,
    dérivée de la base ; garde identique à la console U4.
    """

    permission_classes = GARDE

    def get(self, request, code=None):
        code = (code or '').strip()
        if not code:
            return Response(
                {'detail': 'Code de module requis.', 'code': 'CODE_ABSENT'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        donnees = impact.impact_module(code)
        if donnees is None:
            return Response(
                {
                    'detail': f'Module inconnu : {code}.',
                    'code': CODES_INCONNU['module'],
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(donnees)


class ImpactPermissionView(APIView):
    """GET /api/habilitations/impact/permission/<code>/ — impact d'une permission."""

    permission_classes = GARDE

    def get(self, request, code=None):
        code = (code or '').strip()
        if not code:
            return Response(
                {'detail': 'Code de permission requis.', 'code': 'CODE_ABSENT'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        donnees = impact.impact_permission(code)
        if donnees is None:
            return Response(
                {
                    'detail': f'Permission inconnue : {code}.',
                    'code': CODES_INCONNU['permission'],
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(donnees)


class ImpactRoleView(APIView):
    """GET /api/habilitations/impact/role/<code>/ — impact d'un rôle."""

    permission_classes = GARDE

    def get(self, request, code=None):
        code = (code or '').strip()
        if not code:
            return Response(
                {'detail': 'Code de rôle requis.', 'code': 'CODE_ABSENT'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        donnees = impact.impact_role(code)
        if donnees is None:
            return Response(
                {
                    'detail': f'Rôle inconnu : {code}.',
                    'code': CODES_INCONNU['role'],
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(donnees)


class ImpactUtilisateurView(APIView):
    """GET /api/habilitations/impact/utilisateur/<user_id>/ — impact d'un compte.

    L'identifiant est celui du ``User`` Django ; le compte CURP est résolu par
    ``profil_habilitation`` (source de vérité de l'identité).
    """

    permission_classes = GARDE

    def get(self, request, user_id=None):
        try:
            identifiant = int(user_id)
        except (TypeError, ValueError):
            return Response(
                {
                    'detail': 'Identifiant utilisateur invalide.',
                    'code': 'IDENTIFIANT_INVALIDE',
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        donnees = impact.impact_utilisateur(identifiant)
        if donnees is None:
            return Response(
                {
                    'detail': f"Aucun compte CURP pour l'utilisateur {identifiant}.",
                    'code': CODES_INCONNU['utilisateur'],
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(donnees)
