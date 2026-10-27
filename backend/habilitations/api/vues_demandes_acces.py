"""Workflow générique de demandes d'accès (Lot C, additif).

Garde identique à la console CURP : drapeau ``flag.curp_ui_admin`` +
administration de l'habilitation. Les transitions passent EXCLUSIVEMENT par
le service (machine d'états), jamais par écriture directe du modèle.
"""
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from habilitations.models import DemandeAcces
from habilitations.permissions import ExigeDrapeauAdmin
from habilitations.services import demandes_acces as svc

GARDE = [IsAuthenticated, ExigeDrapeauAdmin]

#: Actions exposées → états d'arrivée.
ACTIONS = {
    'soumettre': DemandeAcces.Statut.SOUMISE,
    'revue': DemandeAcces.Statut.EN_REVUE,
    'approuver': DemandeAcces.Statut.APPROUVEE,
    'refuser': DemandeAcces.Statut.REFUSEE,
    'annuler': DemandeAcces.Statut.ANNULEE,
}


def _serialiser(demande):
    return {
        'id': demande.pk,
        'type_demande': demande.type_demande,
        'type_libelle': demande.get_type_demande_display(),
        'statut': demande.statut,
        'statut_libelle': demande.get_statut_display(),
        'compte_cible': demande.compte_cible_id,
        'username_cible': (
            demande.compte_cible.user.get_username()
            if demande.compte_cible_id else ''
        ),
        'role': demande.role.code if demande.role_id else '',
        'permission': demande.permission.code if demande.permission_id else '',
        'justification': demande.justification,
        'demandeur': (
            demande.demandeur.get_username() if demande.demandeur_id else ''
        ),
        'approbateur': (
            demande.approbateur.get_username()
            if demande.approbateur_id else ''
        ),
        'motif_decision': demande.motif_decision,
        'date_soumission': (
            demande.date_soumission.isoformat() if demande.date_soumission
            else None
        ),
        'date_decision': (
            demande.date_decision.isoformat() if demande.date_decision
            else None
        ),
        'date_creation': demande.date_creation.isoformat(),
        'provisionnement': demande.proposition_id,
    }


class DemandeListCreateView(APIView):
    """GET (liste filtrable) / POST (création) /api/habilitations/demandes/"""

    permission_classes = GARDE

    def get(self, request):
        qs = DemandeAcces.objects.select_related(
            'compte_cible__user', 'role', 'permission',
            'demandeur', 'approbateur',
        ).order_by('-date_creation')
        if request.query_params.get('statut'):
            qs = qs.filter(statut=request.query_params['statut'])
        if request.query_params.get('type'):
            qs = qs.filter(type_demande=request.query_params['type'])
        paginator = PageNumberPagination()
        paginator.page_size = int(request.query_params.get('page_size', 50))
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response(
            [_serialiser(d) for d in page]
        )

    def post(self, request):
        donnees = request.data or {}

        def _resoudre(modele, cle):
            valeur = donnees.get(cle)
            if not valeur:
                return None
            objet = modele.objects.filter(pk=valeur).first()
            if objet is None:
                raise ValueError(f'{cle} introuvable.')
            return objet

        from habilitations.models import CompteUtilisateur, PermissionMetier, RoleMetier
        try:
            demande = svc.creer_demande(
                request.user,
                type_demande=donnees.get('type_demande', ''),
                justification=donnees.get('justification', ''),
                compte_cible=_resoudre(CompteUtilisateur, 'compte_cible'),
                role=_resoudre(RoleMetier, 'role'),
                permission=_resoudre(PermissionMetier, 'permission'),
            )
        except ValueError as erreur:
            return Response({'detail': str(erreur)}, status=400)
        return Response(_serialiser(demande), status=201)


class DemandeDetailView(APIView):
    """GET /api/habilitations/demandes/<pk>/"""

    permission_classes = GARDE

    def get(self, request, pk):
        demande = DemandeAcces.objects.filter(pk=pk).select_related(
            'compte_cible__user', 'role', 'permission',
            'demandeur', 'approbateur',
        ).first()
        if demande is None:
            return Response({'detail': 'Demande introuvable.'}, status=404)
        return Response(_serialiser(demande))


class DemandeActionView(APIView):
    """POST /api/habilitations/demandes/<pk>/action/

    Corps : {action: soumettre|revue|approuver|refuser|annuler,
             motif_decision?: str}
    """

    permission_classes = GARDE

    def post(self, request, pk):
        demande = DemandeAcces.objects.filter(pk=pk).first()
        if demande is None:
            return Response({'detail': 'Demande introuvable.'}, status=404)
        donnees = request.data or {}
        action = donnees.get('action', '')
        if action not in ACTIONS:
            return Response(
                {'detail': f'Action inconnue : {action!r}.'}, status=400,
            )
        try:
            demande = svc.appliquer_transition(
                demande, ACTIONS[action],
                acteur=request.user,
                motif_decision=donnees.get('motif_decision', ''),
            )
        except svc.TransitionIllegale as erreur:
            return Response({'detail': str(erreur)}, status=409)
        except ValueError as erreur:
            return Response({'detail': str(erreur)}, status=400)
        return Response(_serialiser(demande))
