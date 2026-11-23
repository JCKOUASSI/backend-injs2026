"""Admin du lot L7 — Administration générale.

Lecture stricte des documents publiés (jamais supprimés). Transitions via
services uniquement (pas de mutation groupée).
"""
from django.contrib import admin

from .models import Courrier, DocumentOfficiel, Mission, ReunionCommission, VersionDocument


@admin.register(Courrier)
class CourrierAdmin(admin.ModelAdmin):
    list_display = ['reference', 'objet', 'sens', 'statut', 'created_at']
    list_filter = ['sens', 'statut']
    search_fields = ['reference', 'objet', 'expediteur', 'destinataire']
    readonly_fields = ['statut', 'created_at', 'updated_at']


@admin.register(DocumentOfficiel)
class DocumentOfficielAdmin(admin.ModelAdmin):
    list_display = ['titre', 'type_document', 'reference', 'statut', 'date_signature']
    list_filter = ['type_document', 'statut']
    search_fields = ['titre', 'reference']
    readonly_fields = ['statut', 'signe_par', 'date_signature', 'created_at', 'updated_at']
    actions = None


@admin.register(VersionDocument)
class VersionDocumentAdmin(admin.ModelAdmin):
    list_display = ['document', 'numero_version', 'created_at']
    readonly_fields = ['document', 'numero_version', 'contenu', 'fichier', 'cree_par', 'created_at']


@admin.register(ReunionCommission)
class ReunionCommissionAdmin(admin.ModelAdmin):
    list_display = ['titre', 'type_reunion', 'date_reunion', 'statut']
    list_filter = ['type_reunion', 'statut']
    search_fields = ['titre', 'type_reunion']


@admin.register(Mission)
class MissionAdmin(admin.ModelAdmin):
    list_display = ['objet', 'lieu', 'date_debut', 'date_fin', 'statut', 'budget']
    list_filter = ['statut']
    search_fields = ['objet', 'lieu']