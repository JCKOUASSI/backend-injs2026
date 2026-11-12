from django.urls import include, path, re_path
from rest_framework.routers import DefaultRouter

from . import views
from .registre import REGISTRE

router = DefaultRouter()
router.register(r'types-evaluation', views.RefTypeEvaluationViewSet, basename='ref-type-evaluation')
router.register(r'types-document', views.RefTypeDocumentViewSet, basename='ref-type-document')
router.register(r'grades-enseignant', views.RefGradeEnseignantViewSet, basename='ref-grade-enseignant')
router.register(r'types-frais', views.RefTypeFraisViewSet, basename='ref-type-frais')
router.register(r'modes-paiement', views.RefModePaiementViewSet, basename='ref-mode-paiement')
router.register(r'types-decision', views.RefTypeDecisionViewSet, basename='ref-type-decision')
router.register(r'types-notification', views.RefTypeNotificationViewSet, basename='ref-type-notification')
router.register(r'types-espace-sportif', views.RefTypeEspaceSportifViewSet, basename='ref-type-espace-sportif')
router.register(r'modules-officiels', views.RefModuleOfficielViewSet, basename='ref-module-officiel')
router.register(r'volumes-horaires', views.RefVolumeHoraireFormationViewSet, basename='ref-volume-horaire')
router.register(r'journal', views.ReferentielJournalViewSet, basename='ref-journal')

# Référentiels métier de la refonte : une route par slug éditable du registre.
# Le ViewSet est partagé, seul le slug du registre sélectionne le modèle — il
# n'existe donc qu'un seul point de vérité pour la liste des référentiels.
urlpatterns = [
    path(
        'tableau-de-bord/',
        views.TableauDeBordReferentielsView.as_view(),
        name='ref-tableau-de-bord',
    ),
]

for _slug, _entree in REGISTRE.items():
    # Les entrées qui déclarent déjà leur route API sont servies par un ViewSet
    # dédié : on n'ajoute pas une seconde route qui ferait doublon.
    if not _entree['editable'] or _entree.get('route_api'):
        continue
    urlpatterns.append(re_path(
        rf'^{_slug}/$',
        views.RefGeneriqueViewSet.as_view({'get': 'list', 'post': 'create'}, slug=_slug),
        name=f'ref-{_slug}-list',
    ))
    urlpatterns.append(re_path(
        rf'^{_slug}/(?P<pk>[0-9]+)/$',
        views.RefGeneriqueViewSet.as_view({
            'get': 'retrieve', 'patch': 'partial_update', 'put': 'update',
        }, slug=_slug),
        name=f'ref-{_slug}-detail',
    ))
    for _action in ('archiver', 'reactiver', 'activer', 'desactiver', 'supprimer'):
        urlpatterns.append(re_path(
            rf'^{_slug}/(?P<pk>[0-9]+)/{_action}/$',
            views.RefGeneriqueViewSet.as_view({'post': _action}, slug=_slug),
            name=f'ref-{_slug}-{_action}',
        ))
    # Mission « Référentiels » : exports (4 formats) et imports (5 étapes)
    # servis par le moteur commun, une seule route par référentiel.
    urlpatterns.append(re_path(
        rf'^{_slug}/exporter/$',
        views.RefGeneriqueViewSet.as_view({'get': 'exporter'}, slug=_slug),
        name=f'ref-{_slug}-exporter',
    ))
    urlpatterns.append(re_path(
        rf'^{_slug}/importer/$',
        views.RefGeneriqueViewSet.as_view({'post': 'importer'}, slug=_slug),
        name=f'ref-{_slug}-importer',
    ))
    urlpatterns.append(re_path(
        rf'^{_slug}/importer/analyse/$',
        views.RefGeneriqueViewSet.as_view({'post': 'importer_analyse'}, slug=_slug),
        name=f'ref-{_slug}-importer-analyse',
    ))

# Référentiels non éditables : le caractère « lecture seule » interdit la
# création, la modification et la suppression — jamais la consultation ni
# l'export. Une route d'export **et** une route de consultation en lecture
# seule leur sont ouvertes, servies par une vue qui n'expose aucun verbe
# d'écriture et résout le modèle depuis le registre.
#
# Sans la route de consultation, un écran du Hub qui pointe sur un référentiel
# historisé (``route_ui``) appellerait une API inexistante : la page
# s'afficherait vide ou en erreur, ce qui reviendrait à empêcher la lecture —
# précisément ce que le caractère lecture seule n'a pas le droit de faire.
_routes_reservees = {prefix for prefix, _viewset, _basename in router.registry}

for _slug, _entree in REGISTRE.items():
    if _entree['editable']:
        continue
    # La route d'export est ouverte à **tous** les référentiels non éditables,
    # y compris ceux qui disposent par ailleurs de leur propre API métier
    # (``route_api``) : le routeur ne génère pas de route d'export, et le
    # caractère lecture seule n'a jamais le droit de bloquer une lecture.
    urlpatterns.append(re_path(
        rf'^{_slug}/exporter/$',
        views.ReferentielLectureSeuleViewSet.as_view({'get': 'exporter'}, slug=_slug),
        name=f'ref-{_slug}-exporter',
    ))
    # Consultation : ajoutée quand aucune route ne la sert déjà **sous ce
    # chemin**. Un référentiel servi par le routeur (``modules-officiels``)
    # l'aurait en double ; un référentiel dont la route métier est ailleurs
    # (``route_api``) garde la sienne, mais l'écran du Hub qui référence le
    # slug du registre doit pouvoir lire sans dépendre d'un autre chemin.
    if _slug in _routes_reservees:
        continue
    urlpatterns.append(re_path(
        rf'^{_slug}/$',
        views.ReferentielLectureSeuleViewSet.as_view({'get': 'list'}, slug=_slug),
        name=f'ref-{_slug}-list',
    ))
    urlpatterns.append(re_path(
        rf'^{_slug}/(?P<pk>[0-9]+)/$',
        views.ReferentielLectureSeuleViewSet.as_view({'get': 'retrieve'}, slug=_slug),
        name=f'ref-{_slug}-detail',
    ))

urlpatterns.append(path('', include(router.urls)))
