"""URLs API Graduation (lot L4)."""
from django.urls import path

from . import api

urlpatterns = [
    # Gestion des diplômes
    path('diplomes/', api.diplomes_list_api, name='graduation-diplomes-list'),
    path('diplomes/creer/', api.diplome_creer_api, name='graduation-diplome-creer'),
    path('diplomes/<int:pk>/', api.diplome_detail_api, name='graduation-diplome-detail'),
    path('diplomes/<int:pk>/valider/', api.diplome_valider_api, name='graduation-diplome-valider'),
    path('diplomes/<int:pk>/revoquer/', api.diplome_revoquer_api, name='graduation-diplome-revoquer'),
    path('diplomes/<int:pk>/reedition/', api.diplome_reedition_api, name='graduation-diplome-reedition'),
    path('diplomes/<int:pk>/pdf/', api.diplome_pdf_api, name='graduation-diplome-pdf'),
    # Registre (annuel, conservation longue durée)
    path('registres/', api.registres_list_api, name='graduation-registres-list'),
    path('registres/<int:pk>/', api.registre_detail_api, name='graduation-registre-detail'),
    # Gabarits
    path('modeles/', api.modeles_list_api, name='graduation-modeles-list'),
    path('modeles/creer/', api.modele_creer_api, name='graduation-modele-creer'),
    # Portail public de vérification (lecture seule, token, aucune donnée sensible)
    path('verifier/<str:token>/', api.verifier_diplome_api, name='graduation-verifier'),
]
