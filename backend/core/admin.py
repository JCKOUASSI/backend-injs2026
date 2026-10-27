"""Administration en lecture seule du journal d'audit unifié (P01-01).

Le registre est append-only : l'admin Django ne propose ni création, ni
édition, ni suppression. L'immmutabilité est par ailleurs défendue au niveau
du modèle (:class:`~core.models.JournalImmuableError`).
"""
from django.contrib import admin

from .models import CompteurCode, EvenementAudit


@admin.register(EvenementAudit)
class EvenementAuditAdmin(admin.ModelAdmin):
    list_display = (
        'code', 'source', 'action', 'acteur_label', 'objet_libelle',
        'horodatage',
    )
    list_filter = ('source', 'action')
    search_fields = (
        'code', 'action', 'acteur_label', 'objet_libelle', 'objet_id',
    )
    date_hierarchy = 'horodatage'
    readonly_fields = [f.name for f in EvenementAudit._meta.fields]
    list_select_related = ('acteur', 'content_type')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CompteurCode)
class CompteurCodeAdmin(admin.ModelAdmin):
    list_display = ('cle', 'dernier_numero')
    search_fields = ('cle',)
    readonly_fields = ('cle', 'dernier_numero')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
