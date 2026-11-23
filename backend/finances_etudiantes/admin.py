"""Admin Finances Étudiantes (L6) — cohérent avec les champs réels des modèles."""
from django.contrib import admin

from .models import (
    Tarification, Echeancier, LigneEcheancier,
    Facture, Paiement, Quittance, Remboursement, Relance, RapprochementComptable,
)


@admin.register(Tarification)
class TarificationAdmin(admin.ModelAdmin):
    list_display = ['formation', 'parcours', 'niveau', 'annee_academique',
                    'nature', 'montant_base', 'devise', 'actif']
    list_filter = ['nature', 'actif', 'annee_academique']


@admin.register(Echeancier)
class EcheancierAdmin(admin.ModelAdmin):
    list_display = ['etudiant', 'annee_academique', 'lignes_count']
    readonly_fields = ['etudiant', 'annee_academique']

    def lignes_count(self, obj):
        return obj.lignes.count()
    lignes_count.short_description = "Lignes"


@admin.register(LigneEcheancier)
class LigneEcheancierAdmin(admin.ModelAdmin):
    list_display = ['echeancier', 'nature', 'montant', 'date_echeance', 'statut']
    readonly_fields = ['echeancier', 'nature', 'montant']


@admin.register(Facture)
class FactureAdmin(admin.ModelAdmin):
    list_display = ['numero', 'echeancier', 'total', 'statut', 'date_emission']
    readonly_fields = ['numero', 'echeancier', 'total', 'date_emission']


@admin.register(Paiement)
class PaiementAdmin(admin.ModelAdmin):
    list_display = ['id', 'etudiant', 'candidat', 'nature', 'montant',
                    'devise', 'statut', 'mode', 'date']
    readonly_fields = ['etudiant', 'candidat', 'nature', 'montant',
                       'date', 'transaction_externe', 'audit_trail']
    list_filter = ['statut', 'mode', 'nature']


@admin.register(Quittance)
class QuittanceAdmin(admin.ModelAdmin):
    list_display = ['paiement', 'numero', 'date_echeance']
    readonly_fields = ['paiement', 'numero', 'date_echeance']


@admin.register(Remboursement)
class RemboursementAdmin(admin.ModelAdmin):
    list_display = ['paiement_original', 'montant', 'devise', 'statut', 'date']
    readonly_fields = ['paiement_original', 'montant', 'devise', 'motif', 'date']


@admin.register(Relance)
class RelanceAdmin(admin.ModelAdmin):
    list_display = ['echeancier', 'type_relance', 'date_creation']
    readonly_fields = ['echeancier', 'type_relance', 'message', 'date_creation']


@admin.register(RapprochementComptable)
class RapprochementComptableAdmin(admin.ModelAdmin):
    list_display = ['date_periode', 'solde', 'transactions_count']
    readonly_fields = ['date_periode', 'solde', 'commentaire']

    def transactions_count(self, obj):
        return obj.transactions.count()
    transactions_count.short_description = "Transactions"
