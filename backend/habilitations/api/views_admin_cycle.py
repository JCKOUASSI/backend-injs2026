"""Vues U5 (prompt C3) : file de provisionnement, imports écrits/réversibles,
notifications, activation de délégation et journalisation des actions
déléguées. Toutes gardées par :class:`ExigeDrapeauAdmin` (console U4) ; les
automatismes sont en outre protégés par leurs propres drapeaux côté
services, donc éteints par défaut.
"""
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from habilitations.models import (
    DelegationHabilitation,
    ExecutionImport,
    NotificationHabilitation,
    PropositionProvisionnement,
)
from habilitations.permissions import ExigeDrapeauAdmin
from habilitations.services import drapeaux
from habilitations.services.comptes_admin import ErreurConsole
from habilitations.services.delegations_u5 import (
    activer_delegation,
    controler_delegation,
    journaliser_action_deleguee,
)
from habilitations.services.imports_masse import (
    annuler_import,
    executer_import,
    serialiser_execution,
)
from habilitations.services.notifications import serialiser_notification
from habilitations.services.provisionnement import approbation, file as file_service

from .serializers_admin import (
    ActionDelegueeSerializer,
    AnnulationImportSerializer,
    DelegationActiverSerializer,
    ImportExecuterSerializer,
    PropositionDecisionSerializer,
)

GARDE = [ExigeDrapeauAdmin]


def _meta(request):
    return {
        'ip': request.META.get('REMOTE_ADDR', ''),
        'ua': request.META.get('HTTP_USER_AGENT', '')[:250],
    }


def _erreur(erreur):
    return Response(
        {'detail': str(erreur), 'code': erreur.code},
        status=getattr(erreur, 'statut', 400),
    )


def _serialiser_proposition(p):
    return {
        'id': p.pk,
        'declencheur': p.declencheur,
        'declencheur_libelle': p.get_declencheur_display(),
        'action_proposee': p.action_proposee,
        'action_libelle': p.get_action_proposee_display(),
        'source': f'{p.source_app}.{p.source_modele}#{p.source_objet_id}',
        'source_libelle': p.source_libelle,
        'statut': p.statut,
        'statut_libelle': p.get_statut_display(),
        'proposition': p.proposition,
        'resultat': p.resultat,
        'motif': p.motif,
        'motif_rejet': p.motif_rejet,
        'compte': p.compte_cible_id,
        'cree_le': p.cree_le.isoformat(),
        'traite_le': p.traite_le.isoformat() if p.traite_le else None,
    }


# ---------------------------------------------------------------------------
# File de validation humaine
# ---------------------------------------------------------------------------
class PropositionListView(APIView):
    permission_classes = GARDE

    def get(self, request):
        qs = PropositionProvisionnement.objects.select_related('compte_cible__user')
        if request.query_params.get('statut'):
            qs = qs.filter(statut=request.query_params['statut'])
        else:
            qs = qs.filter(statut=PropositionProvisionnement.Statut.EN_ATTENTE)
        if request.query_params.get('declencheur'):
            qs = qs.filter(declencheur=request.query_params['declencheur'])
        paginator = PageNumberPagination()
        paginator.page_size = int(request.query_params.get('page_size', 50))
        page = paginator.paginate_queryset(qs, request, view=self)
        reponse = paginator.get_paginated_response(
            [_serialiser_proposition(p) for p in page])
        reponse.data['compteurs'] = {
            s: PropositionProvisionnement.objects.filter(statut=s).count()
            for s, _ in PropositionProvisionnement.Statut.choices
        }
        return reponse


class PropositionApprouverView(APIView):
    permission_classes = GARDE

    def post(self, request, pk):
        proposition = PropositionProvisionnement.objects.filter(pk=pk).first()
        if proposition is None:
            return Response({'detail': 'Proposition introuvable.'}, status=404)
        serializer = PropositionDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            proposition = approbation.approuver(
                proposition, request.user,
                serializer.validated_data['motif'],
                ajustements=serializer.validated_data.get('ajustements'),
                meta=_meta(request),
            )
        except ErreurConsole as erreur:
            return _erreur(erreur)
        return Response(_serialiser_proposition(proposition))


class PropositionRejeterView(APIView):
    permission_classes = GARDE

    def post(self, request, pk):
        proposition = PropositionProvisionnement.objects.filter(pk=pk).first()
        if proposition is None:
            return Response({'detail': 'Proposition introuvable.'}, status=404)
        serializer = PropositionDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            proposition = approbation.rejeter(
                proposition, request.user,
                serializer.validated_data['motif'], meta=_meta(request),
            )
        except ErreurConsole as erreur:
            return _erreur(erreur)
        return Response(_serialiser_proposition(proposition))


class ProvisionScanView(APIView):
    """Déclenche manuellement les sondes (pour la démo et la supervision)."""

    permission_classes = GARDE

    def post(self, request):
        declencheurs = request.data.get('declencheurs')
        try:
            bilan = file_service.scanner(
                declencheurs=declencheurs, acteur=request.user,
            )
        except ErreurConsole as erreur:
            return _erreur(erreur)
        # Les sondes éteintes sont simplement absentes du bilan.
        return Response({
            'bilan': bilan,
            'total': sum(bilan.values()),
            'maitre_actif': drapeaux.is_enabled(drapeaux.MAITRE_PROVISIONNEMENT),
        })


# ---------------------------------------------------------------------------
# Imports en masse : exécution transactionnelle et annulation
# ---------------------------------------------------------------------------
class ImportExecuterView(APIView):
    permission_classes = GARDE

    def post(self, request):
        if not drapeaux.import_masse_actif():
            return Response(
                {'detail': "L'écriture des imports est désactivée "
                           "(flag.curp_import_masse fermé) ; l'aperçu reste disponible.",
                 'code': 'IMPORT_DESACTIVE'},
                status=403,
            )
        serializer = ImportExecuterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        donnees = serializer.validated_data
        try:
            execution = executer_import(
                request.user, donnees['lignes'], meta=_meta(request),
                nom_fichier=donnees.get('nom_fichier', ''),
            )
        except ErreurConsole as erreur:
            return _erreur(erreur)
        return Response(
            serialiser_execution(execution), status=status.HTTP_201_CREATED,
        )


class ImportDetailView(APIView):
    permission_classes = GARDE

    def get(self, request, reference):
        execution = ExecutionImport.objects.filter(reference=reference).first()
        if execution is None:
            return Response({'detail': 'Exécution introuvable.'}, status=404)
        return Response(serialiser_execution(execution))


class ImportAnnulerView(APIView):
    permission_classes = GARDE

    def post(self, request, reference):
        execution = ExecutionImport.objects.filter(reference=reference).first()
        if execution is None:
            return Response({'detail': 'Exécution introuvable.'}, status=404)
        serializer = AnnulationImportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            execution = annuler_import(
                execution, request.user,
                serializer.validated_data['motif'], meta=_meta(request),
            )
        except ErreurConsole as erreur:
            return _erreur(erreur)
        return Response(serialiser_execution(execution))


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------
class NotificationListView(APIView):
    permission_classes = GARDE

    def get(self, request):
        qs = NotificationHabilitation.objects.filter(destinataire=request.user)
        if request.query_params.get('lu') in ('true', 'false'):
            qs = qs.filter(lu=request.query_params['lu'] == 'true')
        paginator = PageNumberPagination()
        paginator.page_size = int(request.query_params.get('page_size', 50))
        page = paginator.paginate_queryset(qs.order_by('-date_creation'), request, view=self)
        return paginator.get_paginated_response([
            serialiser_notification(n) for n in page
        ])


class NotificationLireView(APIView):
    permission_classes = GARDE

    def post(self, request, pk):
        from django.utils import timezone
        notification = NotificationHabilitation.objects.filter(
            pk=pk, destinataire=request.user,
        ).first()
        if notification is None:
            return Response({'detail': 'Notification introuvable.'}, status=404)
        if not notification.lu:
            notification.lu = True
            notification.date_lecture = timezone.now()
            notification.save(update_fields=['lu', 'date_lecture'])
        return Response(serialiser_notification(notification))


class NotificationToutLireView(APIView):
    permission_classes = GARDE

    def post(self, request):
        from django.utils import timezone
        nombre = NotificationHabilitation.objects.filter(
            destinataire=request.user, lu=False,
        ).update(lu=True, date_lecture=timezone.now())
        return Response({'marquees_lues': nombre})


# ---------------------------------------------------------------------------
# Délégation : activation et traçabilité des actions déléguées
# ---------------------------------------------------------------------------
class DelegationActiverView(APIView):
    permission_classes = GARDE

    def post(self, request, pk):
        delegation = DelegationHabilitation.objects.filter(pk=pk).first()
        if delegation is None:
            return Response({'detail': 'Délégation introuvable.'}, status=404)
        serializer = DelegationActiverSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            delegation = activer_delegation(
                delegation, request.user,
                serializer.validated_data.get('motif')
                or "Activation après vérification des droits délégués.",
                meta=_meta(request),
            )
        except ErreurConsole as erreur:
            return _erreur(erreur)
        from .serializers import serialiser_delegation
        return Response(serialiser_delegation(delegation))


class DelegationActionView(APIView):
    """Journalise une action exercée EN VERTU d'une délégation active.

    Accessible à tout utilisateur authentifié : le vrai contrôle est celui
    du service (cet utilisateur est-il LE délégataire d'une délégation
    active ?), conforme à l'exigence « chaque action faite par délégation est
    journalisée avec la mention du délégant ».
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        delegation = DelegationHabilitation.objects.filter(pk=pk).first()
        if delegation is None:
            return Response({'detail': 'Délégation introuvable.'}, status=404)
        serializer = ActionDelegueeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            entree = journaliser_action_deleguee(
                delegation, request.user,
                serializer.validated_data['action'],
                detail=serializer.validated_data.get('detail'),
                motif=serializer.validated_data.get('motif', ''),
            )
        except ErreurConsole as erreur:
            return _erreur(erreur)
        return Response({
            'numero': entree.numero,
            'delegation': delegation.pk,
            'delegant': delegation.delegant.user.get_username(),
        }, status=status.HTTP_201_CREATED)


# Réexporté pour les contrôles de création côté vue workflow.
controler_delegation = controler_delegation
