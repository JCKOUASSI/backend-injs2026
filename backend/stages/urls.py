"""URLs API Stages (lot L5)."""
from django.urls import path

from . import api

urlpatterns = [
    # Organismes d'accueil
    path('organismes/', api.organismes_list_api, name='stages-organismes-list'),
    path('organismes/creer/', api.organisme_creer_api, name='stages-organisme-creer'),
    path('organismes/<int:pk>/', api.organisme_detail_api, name='stages-organisme-detail'),
    # Tuteurs externes
    path('tuteurs/', api.tuteurs_list_api, name='stages-tuteurs-list'),
    path('tuteurs/creer/', api.tuteur_creer_api, name='stages-tuteur-creer'),
    # Conventions de stage
    path('conventions/', api.conventions_list_api, name='stages-conventions-list'),
    path('conventions/creer/', api.convention_creer_api, name='stages-convention-creer'),
    path('conventions/<int:pk>/', api.convention_detail_api, name='stages-convention-detail'),
    path('conventions/<int:pk>/transition/', api.convention_transition_api, name='stages-convention-transition'),
    path('conventions/<int:pk>/pdf/', api.convention_pdf_api, name='stages-convention-pdf'),
    # Évaluations
    path('evaluations/', api.evaluations_list_api, name='stages-evaluations-list'),
    path('conventions/<int:convention_id>/evaluation/', api.evaluation_creer_api, name='stages-evaluation-creer'),
    path('evaluations/<int:pk>/', api.evaluation_detail_api, name='stages-evaluation-detail'),
]
