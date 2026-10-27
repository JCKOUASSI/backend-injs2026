from django.urls import path

from . import api

urlpatterns = [
    path('demandes/',                        api.demande_list,               name='equiv-demande-list'),
    path('demandes/<int:pk>/',               api.demande_detail,             name='equiv-demande-detail'),
    path('demandes/<int:pk>/transition/',    api.demande_transition,         name='equiv-demande-transition'),
    path('demandes/<int:pk>/decision/',      api.demande_decision,           name='equiv-demande-decision'),
    path('demandes/<int:pk>/appliquer/',     api.demande_appliquer,          name='equiv-demande-appliquer'),
    path('demandes/<int:pk>/rectifier/',     api.demande_rectifier,          name='equiv-demande-rectifier'),
    path('demandes/<int:pk>/historique/',    api.demande_historique,         name='equiv-demande-historique'),
    path('demandes/<int:pk>/pieces/',        api.demande_piece_add,          name='equiv-demande-piece-add'),
    path('pieces/<int:piece_id>/verifier/',  api.demande_piece_verifier,     name='equiv-piece-verifier'),
]
