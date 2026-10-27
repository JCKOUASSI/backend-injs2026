"""
API Views pour le module Paramètres.

Endpoints REST pour consulter et modifier les paramètres.
"""

from rest_framework import viewsets, status, serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.filters import SearchFilter, OrderingFilter
from drf_spectacular.utils import extend_schema, inline_serializer

from .models import Parametre, ParametreHistorique
from .serializers import (
    ParametreSerializer,
    ParametreUpdateSerializer,
    ParametreHistoriqueSerializer,
)
from .permissions import CanViewParametre, CanEditParametre


class ParametreViewSet(viewsets.ModelViewSet):
    """
    Consultation et modification des paramètres existants.

    Pas de création ni suppression via l'API (catalogue figé / seed).
    """

    http_method_names = ['get', 'patch', 'head', 'options']
    queryset = Parametre.objects.select_related('cree_par', 'modifie_par')
    serializer_class = ParametreSerializer
    permission_classes = [IsAuthenticated, CanViewParametre]
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ['cle', 'libelle', 'description']
    ordering_fields = ['categorie', 'ordre', 'libelle', 'modifie_le']
    ordering = ['categorie', 'ordre', 'libelle']
    pagination_class = None  # Pas de pagination (peu de paramètres)

    def get_queryset(self):
        """Filtre dynamique sur les query params."""
        queryset = super().get_queryset()

        # Par défaut, ne montrer que les paramètres actifs
        if self.request.query_params.get('actif') is None:
            queryset = queryset.filter(actif=True)

        # Filtrage sur categorie
        categorie = self.request.query_params.get('categorie', None)
        if categorie:
            queryset = queryset.filter(categorie=categorie)

        # Filtrage sur type
        param_type = self.request.query_params.get('type', None)
        if param_type:
            queryset = queryset.filter(type=param_type)

        # Filtrage explicite sur actif (écrase le défaut)
        actif = self.request.query_params.get('actif', None)
        if actif is not None:
            actif_bool = actif.lower() in ('true', '1', 'yes')
            queryset = queryset.filter(actif=actif_bool)

        # Filtrage sur modifiable
        modifiable = self.request.query_params.get('modifiable', None)
        if modifiable is not None:
            modifiable_bool = modifiable.lower() in ('true', '1', 'yes')
            queryset = queryset.filter(modifiable=modifiable_bool)

        return queryset

    def get_serializer_class(self):
        """Utilise ParametreUpdateSerializer pour les modifications."""
        if self.action in ['partial_update', 'update']:
            return ParametreUpdateSerializer
        return ParametreSerializer

    def get_permissions(self):
        """
        Permissions par action:
        - retrieve, list: CanViewParametre
        - partial_update, update: CanEditParametre
        """
        if self.action in ['partial_update', 'update']:
            self.permission_classes = [IsAuthenticated, CanEditParametre]
        else:
            self.permission_classes = [IsAuthenticated, CanViewParametre]
        return super().get_permissions()

    def list(self, request, *args, **kwargs):
        """Liste filtrée selon les droits de lecture de chaque paramètre."""
        queryset = self.filter_queryset(self.get_queryset())
        readable = [p for p in queryset if p.can_be_read_by(request.user)]
        serializer = self.get_serializer(readable, many=True)
        return Response(serializer.data)

    def partial_update(self, request, *args, **kwargs):
        """
        Modification partielle (PATCH) d'un paramètre.
        
        Corps attendu:
        {
            "valeur": "nouvelle valeur",
            "motif_modification": "raison optionnelle"
        }
        """
        instance = self.get_object()
        
        # Vérifier la permission
        self.check_object_permissions(request, instance)
        
        # Sérialiser avec contexte request
        serializer = self.get_serializer(
            instance,
            data=request.data,
            partial=True,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        
        # Retourner le paramètre mis à jour
        response_serializer = ParametreSerializer(
            instance,
            context={'request': request}
        )
        return Response(response_serializer.data, status=status.HTTP_200_OK)

    @action(
        detail=True,
        methods=['get'],
        permission_classes=[IsAuthenticated, CanViewParametre],
    )
    def historique(self, request, pk=None):
        """
        Récupère l'historique de modifications d'un paramètre.
        
        GET /api/parametres/{id}/historique/
        """
        parametre = self.get_object()
        historiques = parametre.historiques.all()
        serializer = ParametreHistoriqueSerializer(
            historiques,
            many=True,
            context={'request': request}
        )
        return Response(serializer.data)

    @extend_schema(
        tags=['Paramètres'],
        summary='Feature flags évalués pour l’utilisateur courant (P00-08)',
        responses=inline_serializer(
            name='FeatureFlagsResponse',
            fields={
                'flags': serializers.DictField(
                    child=serializers.BooleanField(),
                    help_text='Carte {clé du flag: état effectif pour l’utilisateur}',
                ),
            },
        ),
    )
    @action(
        detail=False,
        methods=['get'],
        permission_classes=[IsAuthenticated],
    )
    def flags(self, request):
        """
        Feature flags effectifs pour l'utilisateur connecté (lecture seule).

        GET /api/parametres/flags/ → ``{"flags": {"flag.xxx": true, …}}``

        Seules les valeurs booléennes sont exposées (jamais la liste interne
        des rôles habilités). Les flags sont livrés DÉSACTIVÉS et ne pilotent
        aucun comportement métier tant qu'un lot ne les consomme pas.
        """
        from .flags import flags_for_user
        return Response({'flags': flags_for_user(request.user)})

    @action(
        detail=False,
        methods=['get'],
        permission_classes=[IsAuthenticated],
    )
    def categories(self, request):
        """
        Retourne la liste des catégories disponibles.
        
        GET /api/parametres/categories/
        
        Returns:
            [
                {"value": "general", "label": "Général"},
                {"value": "finance", "label": "Finance"},
                ...
            ]
        """
        categories = [
            {'value': code, 'label': label}
            for code, label in Parametre.CATEGORIE_CHOICES
        ]
        return Response(categories)

    @action(
        detail=False,
        methods=['get'],
        permission_classes=[IsAuthenticated],
    )
    def types(self, request):
        """
        Retourne la liste des types disponibles.
        
        GET /api/parametres/types/
        """
        types = [
            {'value': code, 'label': label}
            for code, label in Parametre.TYPE_CHOICES
        ]
        return Response(types)

