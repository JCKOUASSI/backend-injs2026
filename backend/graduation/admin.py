"""Admin du lot L4 — Diplômation et documents officiels.

Seuls les administrateurs habilités (DIRECTION/DFRC/ADMIN — géré via les
permissions Django) accèdent à ces interfaces. Les PDFs ne sont JAMAIS
modifiables dans l'admin (lecture seule stricte) ; les transitions de statut
passent par les services dédiés.
"""
from django.contrib import admin

from .models import Diplome, ModeleDocument, RegistreDiplomes, Reedition


class ReeditionInline(admin.TabularInline):
    model = Reedition
    extra = 0
    can_delete = False
    readonly_fields = ('motif', 'pdf_fichier', 'empreinte_pdf', 'par', 'date')
    verbose_name = "Réédition (lecture seule)"
    verbose_name_plural = "Rééditions (lecture seule)"


@admin.register(Diplome)
class DiplomeAdmin(admin.ModelAdmin):
    list_display = (
        'etudiant', 'ref_formation', 'niveau', 'annee_academique',
        'statut', 'mention', 'date_validation', 'numero_unique',
    )
    list_filter = ('statut', 'annee_academique', 'ref_formation', 'niveau')
    search_fields = (
        'etudiant__participant__matricule',
        'etudiant__participant__nom',
        'etudiant__participant__prenom',
        'mention',
    )
    readonly_fields = (
        'numero_unique', 'pdf_fichier', 'empreinte_pdf',
        'date_creation', 'date_validation', 'date_revocation',
        'cree_par', 'valide_par', 'revoque_par',
    )
    inlines = [ReeditionInline]
    actions = None  # pas de suppression groupée : convention L4 (append-only)


@admin.register(RegistreDiplomes)
class RegistreDiplomesAdmin(admin.ModelAdmin):
    list_display = ('annee_academique', 'cloture', 'date_cloture', 'cloture_par')
    list_filter = ('cloture', 'annee_academique')
    readonly_fields = ('cloture', 'date_cloture', 'cloture_par', 'created_at', 'updated_at')
    filter_horizontal = ('diplomes',)
    actions = None  # ajout via services uniquement — pas d'édition directe


@admin.register(ModeleDocument)
class ModeleDocumentAdmin(admin.ModelAdmin):
    list_display = ('type', 'formation', 'libelle', 'actif', 'date_modification', 'modifie_par')
    list_filter = ('type', 'formation', 'actif')
    search_fields = ('libelle',)
    readonly_fields = ('date_modification',)
