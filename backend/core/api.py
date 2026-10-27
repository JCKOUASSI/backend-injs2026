"""API du journal d'audit unifié (P01-01), lecture seule.

``GET /api/core/audit/``      liste paginée et filtrable
``GET /api/core/audit/<code>/`` détail d'un événement

L'accès exige :
1. un utilisateur authentifié ;
2. un rôle d'audit (:class:`~core.permissions.PeutConsulterAuditCore`) ;
3. le feature flag LOT 1 activé (``require_flag``) — hors activation, l'API
   répond 403, y compris pour les administrateurs (kill switch de P00-08).
"""
from django.utils.dateparse import parse_date
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAuthenticated

from parametres.flags import require_flag

from .audit_services import FLAG_LOT1
from .models import EvenementAudit
from .permissions import PeutConsulterAuditCore
from .serializers import EvenementAuditSerializer

_FILTRES_DATE = [
    OpenApiParameter(
        'date_debut', description='Date minimale (AAAA-MM-JJ, inclusive).', type=str),
    OpenApiParameter(
        'date_fin', description='Date maximale (AAAA-MM-JJ, inclusive).', type=str),
    OpenApiParameter('source', description='Source : presences | scolarite | referentiels | core.'),
    OpenApiParameter('action', description='Code d’action (ex. JURY_DECISION).'),
    OpenApiParameter('acteur', description='Identifiant de l’acteur (entier).'),
    OpenApiParameter('objet', description='Recherche dans le libellé de l’objet (icontains).'),
]


@extend_schema(tags=['Noyau – audit'])
class EvenementAuditViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Liste et détail du journal d'audit unifié (aucune écriture exposée)."""

    serializer_class = EvenementAuditSerializer
    permission_classes = [
        IsAuthenticated,
        require_flag(FLAG_LOT1),
        PeutConsulterAuditCore,
    ]
    lookup_field = 'code'

    def get_queryset(self):
        qs = EvenementAudit.objects.select_related('acteur', 'content_type')
        params = self.request.query_params

        source = params.get('source')
        if source:
            qs = qs.filter(source=source)
        action = params.get('action')
        if action:
            qs = qs.filter(action=action)
        acteur = params.get('acteur')
        if acteur:
            qs = qs.filter(acteur_id=acteur)
        objet = params.get('objet')
        if objet:
            qs = qs.filter(objet_libelle__icontains=objet)
        date_debut = params.get('date_debut')
        if date_debut:
            jour = parse_date(date_debut)
            if jour:
                qs = qs.filter(horodatage__date__gte=jour)
        date_fin = params.get('date_fin')
        if date_fin:
            jour = parse_date(date_fin)
            if jour:
                qs = qs.filter(horodatage__date__lte=jour)
        return qs

    @extend_schema(parameters=_FILTRES_DATE, summary='Journal d’audit unifié (liste)')
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(summary='Détail d’un événement d’audit par code')
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)
