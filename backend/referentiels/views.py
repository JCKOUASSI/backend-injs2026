"""Vues API des référentiels (lot L0/L7).

Pattern retenu : ViewSet + DefaultRouter (comme l'app parametres).
- GET   : tout utilisateur authentifié (alimente React/Flutter — règle 9).
- POST/PATCH : rôles de gestion (ReferentielPermission).
- DELETE : jamais exposé (règle 2 — archivage via action dédiée).
"""
from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.db import models
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.filters import OrderingFilter, SearchFilter
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
from .permissions import (
    GererReferentielPermission,
    ReferentielPermission,
)
from .moteur.mixins import ExportReferentielMixin, ImportReferentielMixin
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


class _AnnulationAnalyse(Exception):
    """Annulation interne de l'exploration de dépendances (jamais une erreur)."""


class RefPagination(PageNumberPagination):
    """Pagination du module : tables courtes, taille réglable par le client."""

    page_size = 100
    page_size_query_param = 'page_size'
    max_page_size = 1000


class ReferentielSocleViewSet(ExportReferentielMixin,
                              ImportReferentielMixin,
                              viewsets.ModelViewSet):
    """ViewSet de base : CRUD, statuts, archivage, exports et imports.

    Mission « Référentiels » : les comportements communs (export Word/Excel/
    CSV/PDF, import Excel/CSV en 5 étapes, activation/désactivation,
    archivage/désarchivage, suppression sécurisée) sont fournis par les mixins
    du moteur, donc identiques pour les 27 référentiels du registre — chaque
    référentiel ne code que ses règles métier propres.
    """

    permission_classes = [ReferentielPermission]
    pagination_class = RefPagination
    http_method_names = ['get', 'post', 'patch', 'head', 'options']  # règle 2 : pas de DELETE

    # Recherche multicritère, filtres et tri (exigence « liste » du Hub) :
    # ``?search=`` cherche dans les champs texte, ``?ordering=`` trie, et les
    # filtres métier (``?actif=``, ``?archives=``) sont appliqués par
    # ``get_queryset``. Les champs sont déduits du modèle : aucune liste en dur.
    filter_backends = [SearchFilter, OrderingFilter]
    ordering_fields = '__all__'

    @property
    def search_fields(self):
        """Champs texte du modèle : la recherche suit le référentiel servi."""
        modele = getattr(getattr(self, 'queryset', None), 'model', None)
        if modele is None:
            return ('libelle',)
        champs = [
            f.name for f in modele._meta.concrete_fields
            if isinstance(f, (models.CharField, models.TextField))
            and not f.choices
        ]
        return tuple(champs) or ('libelle',)

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
            # Point de sauvegarde : une IntegrityError attrapée hors
            # savepoint laisserait la transaction de la requête (ou du
            # test) inutilisable alors même que l'erreur est traduite.
            with transaction.atomic():
                return serializer.save()
        except IntegrityError:
            # Règle 4 — anti-doublons : la contrainte DB (code unique,
            # Lower(libelle)) est traduite en 400 propre pour les clients.
            raise ValidationError(
                {'detail': 'Cette valeur existe déjà (code ou libellé en doublon).'}
            )

    def _controler_doublon_libelle(self, libelle, pk_exclu=None, serializer=None):
        # ADR-006 — défense de profondeur au niveau application : la
        # comparaison normalisée (casse + accents) est portable sur
        # SQLite/PostgreSQL, là où la contrainte Lower() de base ne l'est
        # pas. La contrainte DB reste en garde-fou.
        modele = self.queryset.model
        champ = self._champ_libelle()
        filtres = None
        if hasattr(self, '_entree'):
            # Certains référentiels bornent l'unicité du nom à un
            # rattachement (nom de bâtiment/salle unique PAR SITE) :
            # le contrôle suit alors le même périmètre que la contrainte.
            unicite_par = self._entree().get('unicite_par')
            if unicite_par and serializer is not None:
                portee = serializer.validated_data.get(unicite_par)
                if portee is None and serializer.instance is not None:
                    portee = getattr(serializer.instance, unicite_par, None)
                if portee is not None:
                    filtres = {unicite_par: portee}
        if libelle and _a_le_champ(modele, champ) and libelle_en_doublon(
                modele, libelle, pk_exclu, champ=champ, filtres=filtres):
            raise ValidationError(
                {'detail': 'Cette valeur existe déjà (code ou libellé en doublon).'}
            )

    def _preparer_bascule_unique(self, serializer):
        """Bascule un drapeau « un seul vrai » avant l'écriture.

        Certains référentiels portent un booléen qui ne peut être vrai
        que sur une ligne (année académique courante). Le processus
        métier bascule alors l'ancienne ligne à faux plutôt que de
        refuser l'opération : l'écran générique applique la même règle,
        la contrainte d'unicité de la base restant le garde-fou.
        """
        if not hasattr(self, '_entree'):
            return
        champ = self._entree().get('bascule_unique')
        if not champ or not serializer.validated_data.get(champ):
            return
        autres = self.queryset.model._default_manager.filter(**{champ: True})
        if serializer.instance is not None:
            autres = autres.exclude(pk=serializer.instance.pk)
        autres.update(**{champ: False})

    def perform_create(self, serializer):
        self._controler_doublon_libelle(
            serializer.validated_data.get(self._champ_libelle()),
            serializer=serializer)
        self._preparer_bascule_unique(serializer)
        obj = self._save_or_400(serializer)
        self._journaliser(obj, ReferentielJournal.Action.CREATION)

    def perform_update(self, serializer):
        self._controler_doublon_libelle(
            serializer.validated_data.get(self._champ_libelle()),
            pk_exclu=serializer.instance.pk,
            serializer=serializer,
        )
        concrets = {f.name for f in serializer.instance._meta.concrete_fields}
        suivis = [
            nom
            for nom in ('code', self._champ_libelle(), 'libelle', 'description', 'actif')
            if nom in concrets
        ]
        before = {f: getattr(serializer.instance, f) for f in suivis}
        self._preparer_bascule_unique(serializer)
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
        if not _a_le_champ(type(obj), 'archive'):
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
        if not _a_le_champ(type(obj), 'archive'):
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

    # ── Règle 1 : activer ≠ archiver ≠ supprimer (trois actions distinctes) ──
    def _bascule_activation(self, obj, activer, request):
        """Active ou désactive une valeur, modèle socle ou non.

        Les modèles du socle portent ``activer()`` / ``desactiver()`` ; les
        modèles hors socle (scolarité, formations) portent seulement le champ
        ``actif``. Le comportement est identique dans les deux cas : la valeur
        reste présente, consultable et archivable, et l'action est tracée.
        """
        if not hasattr(obj, 'actif'):
            return None
        motif = request.data.get('motif', '')
        if activer:
            obj.actif = True
            if hasattr(obj, 'date_activation'):
                obj.date_activation = timezone.now()
            if hasattr(obj, 'date_desactivation'):
                obj.date_desactivation = None
            action = ReferentielJournal.Action.ACTIVATION
        else:
            obj.actif = False
            if hasattr(obj, 'date_desactivation'):
                obj.date_desactivation = timezone.now()
            action = ReferentielJournal.Action.DESACTIVATION
        champs = [c for c in ('actif', 'date_activation', 'date_desactivation')
                  if hasattr(obj, c)]
        obj.save(update_fields=champs)
        self._journaliser(obj, action, {'motif': motif})
        return obj

    @action(detail=True, methods=['post'])
    def activer(self, request, pk=None):
        """Active la valeur sans toucher à son archivage ni la supprimer."""
        obj = self._get_any_object(pk)
        if _a_le_champ(type(obj), 'archive') and getattr(obj, 'archive', False):
            return Response(
                {'detail': 'Valeur archivée : désarchivez-la avant de l’activer.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if getattr(obj, 'actif', False):
            return Response({'detail': 'Valeur déjà active.'}, status=status.HTTP_400_BAD_REQUEST)
        if self._bascule_activation(obj, True, request) is None:
            return Response(
                {'detail': 'Ce référentiel ne gère pas l’activation.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({
            'detail': 'Valeur activée.',
            'actif': True,
            'archive': getattr(obj, 'archive', False),
        })

    @action(detail=True, methods=['post'])
    def desactiver(self, request, pk=None):
        """Désactive la valeur : elle reste présente, consultable et archivable."""
        obj = self._get_any_object(pk)
        if not _a_le_champ(type(obj), 'actif'):
            return Response(
                {'detail': 'Ce référentiel ne gère pas l’activation.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not obj.actif:
            return Response({'detail': 'Valeur déjà inactive.'}, status=status.HTTP_400_BAD_REQUEST)
        self._bascule_activation(obj, False, request)
        return Response({
            'detail': 'Valeur désactivée.',
            'actif': False,
            'archive': getattr(obj, 'archive', False),
        })

    @action(detail=True, methods=['post'])
    def supprimer(self, request, pk=None):
        """Suppression sécurisée : vérifie les dépendances, puis **archive**.

        Conformément à la règle 2, rien n'est détruit physiquement : la valeur
        est archivée de façon réversible, sauf blocage par une dépendance
        académique (auquel cas rien n'est modifié).
        """
        obj = self._get_any_object(pk)
        confirmation = str(request.data.get('confirmation', '')).strip().lower()
        if confirmation not in {'confirmer', 'supprimer', 'oui'}:
            return Response({
                'detail': 'Confirmation requise : renvoyez « confirmer ».',
                'confirmation_attendue': 'confirmer',
            }, status=status.HTTP_400_BAD_REQUEST)

        dependances = self._dependances(obj)
        if dependances:
            return Response({
                'detail': (
                    'Suppression refusée : cette valeur est utilisée par '
                    f'{len(dependances)} enregistrement(s) du système. '
                    'Archivez-la plutôt, ou réaffectez ces enregistrements.'
                ),
                'dependances': dependances[:20],
                'solution': 'archiver',
            }, status=status.HTTP_409_CONFLICT)

        # Rien n'est jamais détruit : la valeur est archivée. Un modèle sans
        # colonne d'archivage ne peut pas être « supprimé » sans destruction :
        # l'opération est refusée et la désactivation est proposée à la place.
        if not _a_le_champ(type(obj), 'archive'):
            return Response({
                'detail': (
                    'Ce référentiel ne gère pas l’archivage : la suppression y '
                    'entraînerait une destruction de données. Désactivez plutôt '
                    'la valeur, qui reste ainsi consultable et traçable.'
                ),
                'solution': 'desactiver',
            }, status=status.HTTP_409_CONFLICT)

        with transaction.atomic():
            self._journaliser(obj, ReferentielJournal.Action.ARCHIVAGE, {
                'origine': 'suppression_securisee',
                'motif': request.data.get('motif', ''),
            })
            obj.archiver(request.user, motif=request.data.get('motif', ''))
        return Response({
            'detail': 'Valeur supprimée (archivage réversible) : aucune donnée détruite.',
            'archive': True,
        })

    def _dependances(self, obj):
        """Objets référençant cette valeur — **sans jamais rien supprimer**.

        Le contrôle s'appuie sur un ``delete()`` exploratoire exécuté dans une
        transaction immédiatement annulée : si des enregistrements protègent la
        valeur (``on_delete=PROTECT``), ``ProtectedError`` les liste.
        """
        from django.db.models.deletion import ProtectedError

        dependances = []

        # ``delete()`` met ``pk`` à None en mémoire ; l'exploration étant
        # annulée, la valeur existe toujours en base : on restaure son pk.
        identifiant = obj.pk
        try:
            with transaction.atomic():
                try:
                    obj.delete()
                except ProtectedError as exc:
                    dependances = [
                        {'modele': str(type(lie)._meta.verbose_name), 'identifiant': str(lie)}
                        for lie in exc.protected_objects
                    ]
                except Exception:
                    # Toute autre erreur : la suppression n'est pas autorisée.
                    dependances = [{'modele': 'inconnu', 'identifiant': str(obj)}]
                # Annulation garantie de l'exploration, y compris delete() réussi.
                raise _AnnulationAnalyse
        except _AnnulationAnalyse:
            pass
        except Exception:
            obj.pk = identifiant
            return [{'modele': 'inconnu', 'identifiant': str(obj)}]
        obj.pk = identifiant
        return dependances


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
                    'a_une_description': _a_le_champ(modele, 'description'),
                    'champs_choix': _champs_choix(modele, entree),
                    'champs_numeriques': _champs_numeriques(modele, entree),
                    'champs_dates': _champs_dates(modele, entree),
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


def _champs_dates(modele, entree):
    """Champs métier de type date déclarés par l'entrée (périodes…)."""
    from django.db import models as db_models

    return [
        nom for nom in entree.get('champs', [])
        if _a_le_champ(modele, nom)
        and isinstance(modele._meta.get_field(nom), db_models.DateField)
    ]


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


class ReferentielLectureSeuleViewSet(ExportReferentielMixin, viewsets.ReadOnlyModelViewSet):
    """Export d'un référentiel **non éditable** (données historisées ou importées).

    Ces référentiels ne doivent pas pouvoir être créés, modifiés ni supprimés
    depuis le Hub : leurs valeurs proviennent de documents officiels ou
    d'écrans métier existants. Le caractère « lecture seule » ne doit en
    revanche jamais empêcher la **consultation** ni l'**exportation**, qui
    sont deux opérations de lecture encadrées par les mêmes permissions que
    les autres référentiels du registre.

    Le modèle est résolu à partir du slug du registre : une seule source de
    vérité, aucune liste codée en dur.
    """

    permission_classes = [ReferentielPermission]
    pagination_class = RefPagination
    filter_backends = [SearchFilter, OrderingFilter]
    ordering_fields = '__all__'
    slug = None

    def get_queryset(self):
        from referentiels.registre import REGISTRE, modele_de

        entree = REGISTRE.get(self.slug)
        if entree is None:
            from rest_framework.exceptions import NotFound
            raise NotFound(f"Référentiel inconnu : {self.slug}.")
        return modele_de(entree)._default_manager.all()

    @property
    def search_fields(self):
        modele = self.get_queryset().model
        return self._champs_texte(modele)

    @staticmethod
    def _champs_texte(modele):
        champs = [
            f.name for f in modele._meta.concrete_fields
            if isinstance(f, (models.CharField, models.TextField)) and not f.choices
        ]
        return tuple(champs) or ('libelle',)

    def _entree_registre(self):
        from referentiels.registre import REGISTRE

        entree = REGISTRE.get(self.slug)
        return {**entree, 'slug': self.slug} if entree else None

    def _slug_referentiel(self):
        return self.slug or 'referentiel'

    def get_serializer_class(self):
        from rest_framework import serializers

        modele = self.get_queryset().model

        class _Serializer(serializers.ModelSerializer):
            class Meta:
                model = modele
                fields = '__all__'

        return _Serializer
