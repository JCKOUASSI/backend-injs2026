from django.contrib import admin

from .models import (
    ReferentielJournal,
    RefEcole,
    RefFiliere,
    RefMention,
    RefModuleOfficiel,
    RefStatutVague,
    RefTypeCursus,
    RefTypeEnseignement,
    RefVolumeHoraireFormation,
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


@admin.register(RefModuleOfficiel)
class RefModuleOfficielAdmin(admin.ModelAdmin):
    """Modules officiels : issus de l'import documentaire, non éditables ici."""

    list_display = ('libelle', 'filiere_code', 'semestre', 'formation', 'etat_ventilation')
    list_filter = ('filiere_code', 'semestre', 'etat_ventilation', 'fiabilite')
    search_fields = ('libelle', 'filiere_code')
    list_select_related = ('formation',)
    ordering = ('filiere_code', 'semestre', 'ordre')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(RefVolumeHoraireFormation)
class RefVolumeHoraireFormationAdmin(admin.ModelAdmin):
    """Volumes horaires de modélisation : lecture seule (réimportables)."""

    list_display = ('intitule_module', 'formation', 'heures_cm', 'heures_td', 'heures_tp', 'heures_total')
    list_filter = ('formation', 'fiabilite')
    search_fields = ('intitule_module',)
    list_select_related = ('formation',)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# ── Référentiels métier de la refonte (mêmes règles de gestion) ──────────────
class RefMetierAdmin(admin.ModelAdmin):
    """Administration commune aux référentiels issus des documents INJS."""

    list_display = ('code', 'libelle', 'actif', 'archive', 'fiabilite', 'modifie_le')
    list_filter = ('actif', 'archive', 'fiabilite')
    search_fields = ('code', 'libelle', 'description')
    readonly_fields = ('archive', 'cree_le', 'modifie_le')


@admin.register(RefEcole)
class RefEcoleAdmin(RefMetierAdmin):
    list_display = ('code', 'libelle', 'nom_complet', 'actif', 'archive', 'fiabilite')
    search_fields = ('code', 'libelle', 'nom_complet')


@admin.register(RefMention)
class RefMentionAdmin(RefMetierAdmin):
    list_display = ('code', 'libelle', 'ecole', 'actif', 'archive', 'fiabilite')
    list_filter = ('ecole', 'actif', 'archive', 'fiabilite')
    list_select_related = ('ecole',)


@admin.register(RefTypeCursus)
class RefTypeCursusAdmin(RefMetierAdmin):
    pass


@admin.register(RefFiliere)
class RefFiliereAdmin(RefMetierAdmin):
    list_display = ('code', 'code_dossier', 'libelle', 'ecole', 'mention', 'type_cursus', 'ordre')
    list_filter = ('ecole', 'mention', 'type_cursus', 'actif', 'archive', 'fiabilite')
    list_select_related = ('ecole', 'mention', 'type_cursus')
    search_fields = ('code', 'code_dossier', 'libelle')
    ordering = ('code_dossier',)


@admin.register(RefStatutVague)
class RefStatutVagueAdmin(RefMetierAdmin):
    list_display = ('code', 'libelle', 'est_ouvert', 'actif', 'archive', 'fiabilite')


@admin.register(RefTypeEnseignement)
class RefTypeEnseignementAdmin(RefMetierAdmin):
    list_display = ('code', 'libelle', 'abrege', 'est_stage', 'actif', 'archive', 'fiabilite')
