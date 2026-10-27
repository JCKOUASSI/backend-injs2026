"""URLs API Patrimoine (lot L7)."""
from django.urls import path

from . import api

urlpatterns = [
    # Équipements & véhicules
    path('equipements/', api.equipements_api, name='pat-equipements'),
    path('vehicules/', api.vehicules_api, name='pat-vehicules'),
    # Inventaires
    path('inventaires/', api.inventaires_api, name='pat-inventaires'),
    # Maintenances
    path('maintenances/', api.maintenances_api, name='pat-maintenances'),
    path('maintenances/<int:pk>/transition/', api.maintenance_transition_api, name='pat-maintenance-transition'),
    # Réservations d'espaces
    path('reservations/', api.reservations_api, name='pat-reservations'),
    path('reservations/<int:pk>/valider/', api.reservation_valider_api, name='pat-reservation-valider'),
    # Mouvements patrimoniaux
    path('mouvements/', api.mouvements_api, name='pat-mouvements'),
]