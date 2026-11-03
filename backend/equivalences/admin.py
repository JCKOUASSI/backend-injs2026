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
    # `libelle` n'existe pas sur DemandeEquivalenceDispense : Django levait un
    # FieldError dès qu'on utilisait la recherche de l'admin (500). On cherche
    # dans les champs texte réellement présents.
    search_fields = (
        'etudiant__participant__matricule', 'etudiant__participant__nom',
        'diplome_origine', 'etablissement_origine', 'motif',
    )


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
