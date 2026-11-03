"""URLs API Finances Étudiantes (L6)."""
from django.urls import path
from . import hub_api
from .api import (
    echeanciers_list_api, echeancier_detail_api,
    lignes_echeancier_api, facture_generer_api,
    paiements_list_api, paiement_detail_api, paiement_confirmer_api,
    quittances_list_api, remboursements_list_api, remboursement_creer_api,
    relances_list_api, rapprochements_list_api, rapprochement_creer_api,
)

urlpatterns = [
    # Hub premium (consultation consolidée — tâche 34)
    path('hub/stats/', hub_api.stats_api, name='fe-hub-stats'),
    path('hub/tarifications/', hub_api.tarifications_api, name='fe-hub-tarifications'),
    path('hub/echeanciers/', hub_api.echeanciers_api, name='fe-hub-echeanciers'),
    path('hub/factures/', hub_api.factures_api, name='fe-hub-factures'),
    path('hub/paiements/', hub_api.paiements_api, name='fe-hub-paiements'),
    path('hub/quittances/', hub_api.quittances_api, name='fe-hub-quittances'),
    path('hub/remboursements/', hub_api.remboursements_api, name='fe-hub-remboursements'),
    path('hub/relances/', hub_api.relances_api, name='fe-hub-relances'),
    # Échéanciers
    path('echeanciers/', echeanciers_list_api, name='echeanciers-list'),
    path('echeanciers/<int:pk>/', echeancier_detail_api, name='echeancier-detail'),
    path('echeanciers/<int:pk>/lignes/', lignes_echeancier_api, name='echeancier-lignes'),
    path('echeanciers/<int:pk>/facture/', facture_generer_api, name='echeancier-facture'),
    # Paiements
        path('paiements/', paiements_list_api, name='paiements-list'),
    path('paiements/<int:pk>/', paiement_detail_api, name='paiement-detail'),
    path('paiements/<int:pk>/confirmer/', paiement_confirmer_api, name='paiement-confirmer'),
    # Quittances
    path('quittances/', quittances_list_api, name='quittances-list'),
    # Remboursements
    path('remboursements/', remboursements_list_api, name='remboursements-list'),
    path('remboursements/creer/', remboursement_creer_api, name='remboursement-creer'),
    # Relances
    path('relances/', relances_list_api, name='relances-list'),
    # Rapprochements
    path('rapprochements/', rapprochements_list_api, name='rapprochements-list'),
    path('rapprochements/creer/', rapprochement_creer_api, name='rapprochement-creer'),
]
