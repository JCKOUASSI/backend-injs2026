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
from rest_framework.pagination import PageNumberPagination
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from .models import (
    ReferentielJournal,
    RefModuleOfficiel,
    RefVolumeHoraireFormation,
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
    RefModuleOfficielSerializer,
    RefVolumeHoraireFormationSerializer,
    RefGradeEnseignantSerializer,
    RefModePaiementSerializer,
    RefTypeDecisionSerializer,
    RefTypeDocumentSerializer,
    RefTypeEspaceSportifSerializer,
    RefTypeEvaluationSerializer,
    RefTypeFraisSerializer,
    RefTypeNotificationSerializer,
)


class RefPagination(PageNumberPagination):
    """Pagination du module : tables courtes, taille réglable par le client."""

    page_size = 100
    page_size_query_param = 'page_size'
    max_page_size = 1000


class ReferentielSocleViewSet(viewsets.ModelViewSet):
    """ViewSet de base : CRUD sans suppression, archivage réversible, journal."""

    permission_classes = [ReferentielPermission]
    pagination_class = RefPagination
    http_method_names = ['get', 'post', 'patch', 'head', 'options']  # règle 2 : pas de DELETE

    def get_queryset(self):
        qs = self.queryset
        modele = qs.model
        # Règle 5 : les valeurs archivées sont masquées par défaut ; un
        # gestionnaire peut les consulter avec ?archives=1. Les modèles
        # hors socle sans colonne d'archivage (scolarité LMD) sont
        # simplement retournés tels quels.
        if _a_le_champ(modele, 'archive') \
                and self.request.query_params.get('archives') not in ('1', 'true'):
            qs = qs.filter(archive=False)
        actif = self.request.query_params.get('actif')
        if actif is not None and _a_le_champ(modele, 'actif'):
            qs = qs.filter(actif=actif.lower() in ('true', '1', 'yes'))
        return qs

    def _champ_libelle(self):
        """Champ d'intitulé réel du modèle servi (registre, défaut socle)."""
        if hasattr(self, '_entree'):
            return self._entree().get('champ_libelle', 'libelle')
        return 'libelle'

    def _journaliser(self, obj, action, detail=None):
        """Règle 6 : trace l'action, méthode du socle si le modèle en a une.

        Les modèles hors socle (scolarité) ne portent pas ``journaliser`` :
        l'entrée de journal est alors écrite directement via ContentType,
        de façon strictement équivalente.
        """
        if hasattr(obj, 'journaliser'):
            obj.journaliser(action, self.request.user, detail)
            return
        user = self.request.user
        ReferentielJournal.objects.create(
            content_type=ContentType.objects.get_for_model(obj),
            object_id=obj.pk,
            action=action,
            utilisateur=user if (user and user.is_authenticated) else None,
            detail=detail or {},
        )

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
        modele = self.queryset.model
        champ = self._champ_libelle()
        if libelle and _a_le_champ(modele, champ) and libelle_en_doublon(
                modele, libelle, pk_exclu, champ=champ):
            raise ValidationError(
                {'detail': 'Cette valeur existe déjà (code ou libellé en doublon).'}
            )

    def perform_create(self, serializer):
        self._controler_doublon_libelle(
            serializer.validated_data.get(self._champ_libelle()))
        obj = self._save_or_400(serializer)
        self._journaliser(obj, ReferentielJournal.Action.CREATION)

    def perform_update(self, serializer):
        self._controler_doublon_libelle(
            serializer.validated_data.get(self._champ_libelle()),
            pk_exclu=serializer.instance.pk,
        )
        concrets = {f.name for f in serializer.instance._meta.concrete_fields}
        suivis = [
            nom
            for nom in ('code', self._champ_libelle(), 'libelle', 'description', 'actif')
            if nom in concrets
        ]
        before = {f: getattr(serializer.instance, f) for f in suivis}
        obj = self._save_or_400(serializer)
        after = {f: getattr(obj, f) for f in before}
        changes = {k: {'avant': before[k], 'apres': after[k]} for k in before if before[k] != after[k]}
        self._journaliser(obj, ReferentielJournal.Action.MODIFICATION, changes or None)

    def _get_any_object(self, pk):
        """Récupère une valeur même archivée (pour archiver/reactiver)."""
        return get_object_or_404(self.queryset, pk=pk)

    # ── Règle 2 : archivage réversible, jamais de suppression physique ──
    @action(detail=True, methods=['post'])
    def archiver(self, request, pk=None):
        obj = self._get_any_object(pk)
        if not hasattr(obj, 'archive'):
            return Response(
                {'detail': (
                    'Ce référentiel ne gère pas l’archivage : '
                    'utilisez l’activation/désactivation.'
                )},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if obj.archive:
            return Response({'detail': 'Valeur déjà archivée.'}, status=status.HTTP_400_BAD_REQUEST)
        obj.archiver(request.user, motif=request.data.get('motif', ''))
        return Response({'detail': 'Valeur archivée.', 'archive': True})

    @action(detail=True, methods=['post'])
    def reactiver(self, request, pk=None):
        obj = self._get_any_object(pk)
        if not hasattr(obj, 'archive'):
            return Response(
                {'detail': (
                    'Ce référentiel ne gère pas l’archivage : '
                    'utilisez l’activation/désactivation.'
                )},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not obj.archive:
            return Response({'detail': 'Valeur non archivée.'}, status=status.HTTP_400_BAD_REQUEST)
        obj.reactiver(request.user, motif=request.data.get('motif', ''))
        return Response({'detail': 'Valeur réactivée.', 'archive': False, 'actif': True})


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


# ═══════════════════════════════════════════════════════════════════════════
# Refonte « Référentiels » : API générique pilotée par le registre
# ═══════════════════════════════════════════════════════════════════════════
from django.db.models import Count  # noqa: E402
from rest_framework.views import APIView  # noqa: E402

from .registre import (  # noqa: E402
    CATEGORIES,
    REGISTRE,
    entrees_par_categorie,
    modele_de,
)
from .serializers import serializer_pour_ref  # noqa: E402


class RefGeneriqueViewSet(ReferentielSocleViewSet):
    """CRUD d'un référentiel du registre, sélectionné par son slug d'URL.

    Réutilise intégralement le comportement du socle : pas de DELETE,
    archivage réversible, journalisation, anti-doublon de libellé.
    """

    #: Renseigné par le routeur DRF ; déclaré ici pour la lisibilité.
    slug = None

    def _entree(self):
        slug = self.kwargs.get('slug') or self.slug
        entree = REGISTRE.get(slug)
        if entree is None or not entree['editable']:
            from django.http import Http404

            raise Http404('Référentiel inconnu ou géré par un écran dédié.')
        return entree

    @property
    def queryset(self):  # noqa: D401 — propriété attendue par DRF
        return modele_de(self._entree()).objects.all()

    @queryset.setter
    def queryset(self, valeur):  # pragma: no cover — compatibilité DRF
        self._queryset_force = valeur

    def get_serializer_class(self):
        return serializer_pour_ref(self.kwargs.get('slug') or self.slug)

    def get_queryset(self):
        # La lecture des valeurs archivées reste possible (?archives=1) : la
        # base ne perd jamais une valeur utilisée par un dossier.
        return super().get_queryset().select_related(*self._entree()['selecteurs'])


class TableauDeBordReferentielsView(APIView):
    """Cartographie du module : un référentiel = une ligne, avec son état.

    Aucune donnée n'est calculée à partir d'une liste codée en dur : tout
    provient du registre et des modèles qu'il déclare.
    """

    permission_classes = [ReferentielPermission]

    def get(self, request):
        entrees = []
        total_valeurs = 0
        total_a_renseigner = 0
        total_sans_source = 0
        total_avec_provenance = 0

        for categorie in entrees_par_categorie():
            lignes = []
            for entree in categorie['entrees']:
                modele = modele_de(entree)
                qs = modele._default_manager.all()
                total = qs.count()
                actifs = qs.filter(actif=True).count() if _a_le_champ(modele, 'actif') else total
                archives = qs.filter(archive=True).count() if _a_le_champ(modele, 'archive') else 0

                a_renseigner = None
                sans_source = None
                if _a_le_champ(modele, 'fiabilite'):
                    a_renseigner = qs.filter(fiabilite='A_RENSEIGNER').count()
                    total_a_renseigner += a_renseigner
                if _a_le_champ(modele, 'source_document'):
                    sans_source = qs.filter(source_document='').count()
                    total_sans_source += sans_source
                    total_avec_provenance += total

                total_valeurs += total
                lignes.append({
                    **entree,
                    'modele': f'{modele._meta.app_label}.{modele._meta.model_name}',
                    'total': total,
                    'actifs': actifs,
                    'archives': archives,
                    'a_renseigner': a_renseigner,
                    'sans_source': sans_source,
                    'provenance_suivie': _a_le_champ(modele, 'source_document'),
                    # Capacités réelles du modèle, pour que l'écran générique
                    # adapte son formulaire sans rien coder en dur.
                    'archivage_supporte': _a_le_champ(modele, 'archive'),
                    'a_un_code': (
                        _a_le_champ(modele, entree.get('champ_code', 'code'))
                        and entree.get('champ_code', 'code')
                        != entree.get('champ_libelle', 'libelle')
                    ),
                    'champs_choix': _champs_choix(modele, entree),
                    'champs_numeriques': _champs_numeriques(modele, entree),
                    'route_api': entree.get('route_api') or f'/referentiels/{entree["slug"]}/',
                    'selecteurs_routes': _routes_selecteurs(entree),
                })
            entrees.append({**categorie, 'entrees': lignes})

        return Response({
            'categories': entrees,
            'catalogue': CATEGORIES,
            'synthese': {
                'nb_referentiels': len(REGISTRE),
                'nb_referentiels_editables': sum(1 for e in REGISTRE.values() if e['editable']),
                'nb_valeurs': total_valeurs,
                'nb_a_renseigner': total_a_renseigner,
                'nb_sans_source': total_sans_source,
                'nb_valeurs_tracees': total_avec_provenance,
                'taux_tracabilite': (
                    round((total_avec_provenance - total_sans_source) / total_avec_provenance, 4)
                    if total_avec_provenance else None
                ),
            },
        })


class RefModuleOfficielViewSet(viewsets.ReadOnlyModelViewSet):
    """Modules officiels des maquettes — lecture seule.

    Ces lignes proviennent de l'import du document « Formations et Modules
    INJS » : les modifier à la main romprait la traçabilité, elles ne sont
    donc jamais éditables par l'API. Les filtres `filiere`, `semestre` et
    `formation` alimentent les sélecteurs dépendants du front.
    """

    queryset = RefModuleOfficiel.objects.select_related('formation')
    serializer_class = RefModuleOfficielSerializer
    permission_classes = [ReferentielPermission]
    pagination_class = RefPagination

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if params.get('filiere'):
            qs = qs.filter(filiere_code=params['filiere'])
        if params.get('semestre'):
            qs = qs.filter(semestre=params['semestre'])
        if params.get('formation'):
            qs = qs.filter(formation_id=params['formation'])
        return qs.order_by('filiere_code', 'semestre', 'ordre')


class RefVolumeHoraireFormationViewSet(viewsets.ReadOnlyModelViewSet):
    """Volumes horaires de modélisation — lecture seule."""

    queryset = RefVolumeHoraireFormation.objects.select_related('formation')
    serializer_class = RefVolumeHoraireFormationSerializer
    permission_classes = [ReferentielPermission]
    pagination_class = RefPagination


def _routes_selecteurs(entree):
    """Associe chaque sélecteur à la route API du référentiel qu'il cible.

    La cible n'est pas devinée : elle est retrouvée par le modèle de la clé
    étrangère, puis par l'entrée de registre qui déclare ce modèle. Le front
    n'a donc aucune correspondance de noms à coder en dur.
    """
    modele = modele_de(entree)
    par_modele = {}
    for slug, item in REGISTRE.items():
        if item.get('modele') is None:
            continue
        cible = modele_de(item)
        par_modele[f'{cible._meta.app_label}.{cible._meta.model_name}'] = slug
    routes = {}
    for fk in entree['selecteurs']:
        champ = modele._meta.get_field(fk)
        cible = champ.related_model
        cle = f'{cible._meta.app_label}.{cible._meta.model_name}'
        slug = par_modele.get(cle)
        if slug:
            routes[fk] = {
                'slug': slug,
                # La cible peut être servie par son API historique
                # (route_api déclarée) plutôt que par le CRUD générique.
                'route': (
                    REGISTRE[slug].get('route_api') or f'/referentiels/{slug}/'
                ),
                'editable': bool(REGISTRE[slug]['editable']),
            }
    return routes


def _a_le_champ(modele, nom):
    return any(f.name == nom for f in modele._meta.get_fields())


def _champs_choix(modele, entree):
    """Listes de valeurs des champs métier à choix (ex. `cycle` du niveau)."""
    resultat = {}
    for nom in entree.get('champs', []):
        if not _a_le_champ(modele, nom):
            continue
        choix = modele._meta.get_field(nom).choices
        if choix:
            resultat[nom] = [
                {'value': str(valeur), 'label': str(libelle)}
                for valeur, libelle in choix
            ]
    return resultat


def _champs_numeriques(modele, entree):
    """Champs métier numériques (entiers/décimaux) déclarés par l'entrée."""
    from django.db import models as db_models

    types = (
        db_models.IntegerField, db_models.PositiveIntegerField,
        db_models.PositiveSmallIntegerField, db_models.SmallIntegerField,
        db_models.BigIntegerField, db_models.DecimalField,
        db_models.FloatField,
    )
    return [
        nom for nom in entree.get('champs', [])
        if _a_le_champ(modele, nom)
        and isinstance(modele._meta.get_field(nom), types)
    ]
