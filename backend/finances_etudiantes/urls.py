"""URLs API Finances Étudiantes (L6)."""
from django.urls import path
from .api import (
    echeanciers_list_api, echeancier_detail_api,
    lignes_echeancier_api, facture_generer_api,
    paiements_list_api, paiement_detail_api, paiement_confirmer_api,
    quittances_list_api, remboursements_list_api, remboursement_creer_api,
    relances_list_api, rapprochements_list_api, rapprochement_creer_api,
)

urlpatterns = [
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
