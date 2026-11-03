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
    for _action in ('archiver', 'reactiver'):
        urlpatterns.append(re_path(
            rf'^{_slug}/(?P<pk>[0-9]+)/{_action}/$',
            views.RefGeneriqueViewSet.as_view({'post': _action}, slug=_slug),
            name=f'ref-{_slug}-{_action}',
        ))

urlpatterns.append(path('', include(router.urls)))
