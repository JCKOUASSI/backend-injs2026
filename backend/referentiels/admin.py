from django.contrib import admin

from .models import (
    ReferentielJournal,
    RefGradeEnseignant,
    RefModePaiement,
    RefTypeDecision,
    RefTypeDocument,
    RefTypeEspaceSportif,
    RefTypeEvaluation,
    RefTypeFrais,
    RefTypeNotification,
)


@admin.register(RefTypeEvaluation)
class RefTypeEvaluationAdmin(admin.ModelAdmin):
    list_display = ('code', 'libelle', 'actif', 'archive', 'modifie_le')
    list_filter = ('actif', 'archive')
    search_fields = ('code', 'libelle')


@admin.register(RefTypeDocument)
class RefTypeDocumentAdmin(admin.ModelAdmin):
    list_display = ('code', 'libelle', 'actif', 'archive', 'modifie_le')
    list_filter = ('actif', 'archive')
    search_fields = ('code', 'libelle')


@admin.register(RefGradeEnseignant)
class RefGradeEnseignantAdmin(admin.ModelAdmin):
    list_display = ('code', 'libelle', 'actif', 'archive', 'modifie_le')
    list_filter = ('actif', 'archive')
    search_fields = ('code', 'libelle')


@admin.register(RefTypeFrais)
class RefTypeFraisAdmin(admin.ModelAdmin):
    list_display = ('code', 'libelle', 'actif', 'archive', 'modifie_le')
    list_filter = ('actif', 'archive')
    search_fields = ('code', 'libelle')


@admin.register(RefModePaiement)
class RefModePaiementAdmin(admin.ModelAdmin):
    list_display = ('code', 'libelle', 'actif', 'archive', 'modifie_le')
    list_filter = ('actif', 'archive')
    search_fields = ('code', 'libelle')


@admin.register(RefTypeDecision)
class RefTypeDecisionAdmin(admin.ModelAdmin):
    list_display = ('code', 'libelle', 'actif', 'archive', 'modifie_le')
    list_filter = ('actif', 'archive')
    search_fields = ('code', 'libelle')


@admin.register(RefTypeNotification)
class RefTypeNotificationAdmin(admin.ModelAdmin):
    list_display = ('code', 'libelle', 'actif', 'archive', 'modifie_le')
    list_filter = ('actif', 'archive')
    search_fields = ('code', 'libelle')


@admin.register(RefTypeEspaceSportif)
class RefTypeEspaceSportifAdmin(admin.ModelAdmin):
    list_display = ('code', 'libelle', 'actif', 'archive', 'modifie_le')
    list_filter = ('actif', 'archive')
    search_fields = ('code', 'libelle')


@admin.register(ReferentielJournal)
class ReferentielJournalAdmin(admin.ModelAdmin):
    """Journal en lecture seule (règle 6 — append-only)."""

    list_display = ('action', 'cible', 'utilisateur', 'horodatage')
    list_filter = ('action',)
    readonly_fields = ('content_type', 'object_id', 'cible', 'action', 'utilisateur', 'horodatage', 'detail')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
