from django.contrib import admin

from .models import (
    DemandeEquivalenceDispense,
    HistoriqueEquivalence,
    PieceEquivalence,
)


@admin.register(DemandeEquivalenceDispense)
class DemandeEquivalenceAdmin(admin.ModelAdmin):
    list_display = ('type_demande', 'etudiant', 'ref_formation', 'statut', 'decision', 'credits_reconnus')
    list_filter = ('type_demande', 'statut', 'decision')
    search_fields = ('etudiant__participant__matricule', 'etudiant__participant__nom', 'libelle')


@admin.register(PieceEquivalence)
class PieceEquivalenceAdmin(admin.ModelAdmin):
    list_display = ('demande', 'libelle', 'obligatoire', 'statut')
    list_filter = ('statut',)


@admin.register(HistoriqueEquivalence)
class HistoriqueEquivalenceAdmin(admin.ModelAdmin):
    list_display = ('demande', 'statut', 'decision', 'utilisateur', 'horodatage')
    list_filter = ('statut',)
    readonly_fields = ('demande', 'statut', 'decision', 'utilisateur', 'horodatage', 'commentaire')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
