from django.contrib import admin

from .models import (
    Admission,
    Candidat,
    Candidature,
    PieceCandidature,
    ReglePiece,
    TypeCandidature,
    TypePiece,
    VoieAcces,
)


@admin.register(TypeCandidature)
class TypeCandidatureAdmin(admin.ModelAdmin):
    list_display = ('code', 'libelle', 'actif')
    list_filter = ('actif',)


@admin.register(VoieAcces)
class VoieAccesAdmin(admin.ModelAdmin):
    list_display = ('code', 'libelle', 'actif')
    list_filter = ('actif',)


@admin.register(TypePiece)
class TypePieceAdmin(admin.ModelAdmin):
    list_display = ('code', 'libelle', 'obligatoire_par_defaut', 'avec_date_expiration', 'actif')
    list_filter = ('actif', 'obligatoire_par_defaut')


@admin.register(ReglePiece)
class ReglePieceAdmin(admin.ModelAdmin):
    list_display = ('type_piece', 'type_formation', 'ref_formation', 'obligatoire')
    list_filter = ('obligatoire', 'type_formation')
    autocomplete_fields = ('ref_formation',)


@admin.register(Candidat)
class CandidatAdmin(admin.ModelAdmin):
    list_display = ('nom', 'prenom', 'sexe', 'email', 'telephone', 'participant')
    search_fields = ('nom', 'prenom', 'email', 'telephone')


class PieceCandidatureInline(admin.TabularInline):
    model = PieceCandidature
    extra = 0
    readonly_fields = ('verifie_par', 'verifie_le')


@admin.register(Candidature)
class CandidatureAdmin(admin.ModelAdmin):
    list_display = (
        'numero', 'candidat', 'annee_academique', 'ref_formation', 'niveau',
        'statut', 'taux_completude',
    )
    list_filter = ('statut', 'annee_academique', 'niveau')
    search_fields = ('numero', 'candidat__nom', 'candidat__prenom')
    readonly_fields = ('numero', 'date_decision', 'decide_par')
    inlines = [PieceCandidatureInline]

    @admin.display(description='Complétude')
    def taux_completude(self, obj):
        return f'{obj.taux_completude} %'


@admin.register(Admission)
class AdmissionAdmin(admin.ModelAdmin):
    list_display = (
        'candidat', 'annee_academique', 'ref_formation', 'niveau',
        'decision', 'date_limite_inscription',
    )
    list_filter = ('decision', 'annee_academique', 'niveau')
    search_fields = ('candidat__nom', 'candidat__prenom', 'reference_decision')
    readonly_fields = ('date_decision', 'decide_par')
