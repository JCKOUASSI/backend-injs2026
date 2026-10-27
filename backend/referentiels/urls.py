from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r'types-evaluation', views.RefTypeEvaluationViewSet, basename='ref-type-evaluation')
router.register(r'types-document', views.RefTypeDocumentViewSet, basename='ref-type-document')
router.register(r'grades-enseignant', views.RefGradeEnseignantViewSet, basename='ref-grade-enseignant')
router.register(r'types-frais', views.RefTypeFraisViewSet, basename='ref-type-frais')
router.register(r'modes-paiement', views.RefModePaiementViewSet, basename='ref-mode-paiement')
router.register(r'types-decision', views.RefTypeDecisionViewSet, basename='ref-type-decision')
router.register(r'types-notification', views.RefTypeNotificationViewSet, basename='ref-type-notification')
router.register(r'types-espace-sportif', views.RefTypeEspaceSportifViewSet, basename='ref-type-espace-sportif')
router.register(r'journal', views.ReferentielJournalViewSet, basename='ref-journal')

urlpatterns = [
    path('', include(router.urls)),
]
