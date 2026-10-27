"""Vues API des référentiels (lot L0/L7).

Pattern retenu : ViewSet + DefaultRouter (comme l'app parametres).
- GET   : tout utilisateur authentifié (alimente React/Flutter — règle 9).
- POST/PATCH : rôles de gestion (ReferentielPermission).
- DELETE : jamais exposé (règle 2 — archivage via action dédiée).
"""
from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from .models import (
    ReferentielJournal,
    RefGradeEnseignant,
    RefModePaiement,
    RefTypeDecision,
    RefTypeDocument,
    RefTypeEspaceSportif,
    RefTypeEvaluation,
    RefTypeFrais,
    RefTypeNotification,
)
from .permissions import ReferentielPermission
from .utils import libelle_en_doublon
from .serializers import (
    ReferentielJournalSerializer,
    RefGradeEnseignantSerializer,
    RefModePaiementSerializer,
    RefTypeDecisionSerializer,
    RefTypeDocumentSerializer,
    RefTypeEspaceSportifSerializer,
    RefTypeEvaluationSerializer,
    RefTypeFraisSerializer,
    RefTypeNotificationSerializer,
)


class ReferentielSocleViewSet(viewsets.ModelViewSet):
    """ViewSet de base : CRUD sans suppression, archivage réversible, journal."""

    permission_classes = [ReferentielPermission]
    http_method_names = ['get', 'post', 'patch', 'head', 'options']  # règle 2 : pas de DELETE

    def get_queryset(self):
        qs = self.queryset
        # Règle 5 : les valeurs archivées sont masquées par défaut ; un
        # gestionnaire peut les consulter avec ?archives=1.
        if self.request.query_params.get('archives') not in ('1', 'true'):
            qs = qs.filter(archive=False)
        actif = self.request.query_params.get('actif')
        if actif is not None:
            qs = qs.filter(actif=actif.lower() in ('true', '1', 'yes'))
        return qs

    def _save_or_400(self, serializer):
        try:
            return serializer.save()
        except IntegrityError:
            # Règle 4 — anti-doublons : la contrainte DB (code unique,
            # Lower(libelle)) est traduite en 400 propre pour les clients.
            raise ValidationError(
                {'detail': 'Cette valeur existe déjà (code ou libellé en doublon).'}
            )

    def _controler_doublon_libelle(self, libelle, pk_exclu=None):
        # ADR-006 — défense de profondeur au niveau application : la
        # comparaison normalisée (casse + accents) est portable sur
        # SQLite/PostgreSQL, là où la contrainte Lower() de base ne l'est
        # pas. La contrainte DB reste en garde-fou.
        if libelle and libelle_en_doublon(self.queryset.model, libelle, pk_exclu):
            raise ValidationError(
                {'detail': 'Cette valeur existe déjà (code ou libellé en doublon).'}
            )

    def perform_create(self, serializer):
        self._controler_doublon_libelle(
            serializer.validated_data.get('libelle'))
        obj = self._save_or_400(serializer)
        obj.journaliser(ReferentielJournal.Action.CREATION, self.request.user)

    def perform_update(self, serializer):
        self._controler_doublon_libelle(
            serializer.validated_data.get('libelle'),
            pk_exclu=serializer.instance.pk,
        )
        before = {f: getattr(serializer.instance, f) for f in ('code', 'libelle', 'description', 'actif')}
        obj = self._save_or_400(serializer)
        after = {f: getattr(obj, f) for f in before}
        changes = {k: {'avant': before[k], 'apres': after[k]} for k in before if before[k] != after[k]}
        obj.journaliser(ReferentielJournal.Action.MODIFICATION, self.request.user, changes or None)

    def _get_any_object(self, pk):
        """Récupère une valeur même archivée (pour archiver/reactiver)."""
        return get_object_or_404(self.queryset, pk=pk)

    # ── Règle 2 : archivage réversible, jamais de suppression physique ──
    @action(detail=True, methods=['post'])
    def archiver(self, request, pk=None):
        obj = self._get_any_object(pk)
        if obj.archive:
            return Response({'detail': 'Valeur déjà archivée.'}, status=status.HTTP_400_BAD_REQUEST)
        obj.archiver(request.user, motif=request.data.get('motif', ''))
        return Response({'detail': 'Valeur archivée.', 'archive': True})

    @action(detail=True, methods=['post'])
    def reactiver(self, request, pk=None):
        obj = self._get_any_object(pk)
        if not obj.archive:
            return Response({'detail': 'Valeur non archivée.'}, status=status.HTTP_400_BAD_REQUEST)
        obj.archive = False
        obj.save(update_fields=['archive', 'modifie_le'])
        obj.journaliser(ReferentielJournal.Action.MODIFICATION, request.user, {'desarchivage': True})
        return Response({'detail': 'Valeur réactivée.', 'archive': False})


# ── ViewSets concrets (8 référentiels) ───────────────────────────────────────

class RefTypeEvaluationViewSet(ReferentielSocleViewSet):
    queryset = RefTypeEvaluation.objects.all()
    serializer_class = RefTypeEvaluationSerializer


class RefTypeDocumentViewSet(ReferentielSocleViewSet):
    queryset = RefTypeDocument.objects.all()
    serializer_class = RefTypeDocumentSerializer


class RefGradeEnseignantViewSet(ReferentielSocleViewSet):
    queryset = RefGradeEnseignant.objects.all()
    serializer_class = RefGradeEnseignantSerializer


class RefTypeFraisViewSet(ReferentielSocleViewSet):
    queryset = RefTypeFrais.objects.all()
    serializer_class = RefTypeFraisSerializer


class RefModePaiementViewSet(ReferentielSocleViewSet):
    queryset = RefModePaiement.objects.all()
    serializer_class = RefModePaiementSerializer


class RefTypeDecisionViewSet(ReferentielSocleViewSet):
    queryset = RefTypeDecision.objects.all()
    serializer_class = RefTypeDecisionSerializer


class RefTypeNotificationViewSet(ReferentielSocleViewSet):
    queryset = RefTypeNotification.objects.all()
    serializer_class = RefTypeNotificationSerializer


class RefTypeEspaceSportifViewSet(ReferentielSocleViewSet):
    queryset = RefTypeEspaceSportif.objects.all()
    serializer_class = RefTypeEspaceSportifSerializer


class ReferentielJournalViewSet(viewsets.ReadOnlyModelViewSet):
    """Règle 6 — consultation de l'historique (filtres : ?app=…&model=…&object_id=…)."""

    queryset = ReferentielJournal.objects.select_related('content_type', 'utilisateur')
    serializer_class = ReferentielJournalSerializer
    permission_classes = [ReferentielPermission]

    def get_queryset(self):
        qs = super().get_queryset()
        app = self.request.query_params.get('app')
        model = self.request.query_params.get('model')
        object_id = self.request.query_params.get('object_id')
        if app and model:
            try:
                ct = ContentType.objects.get_by_natural_key(app, model)
            except ContentType.DoesNotExist:
                return qs.none()
            qs = qs.filter(content_type=ct)
        if object_id:
            qs = qs.filter(object_id=object_id)
        return qs
