"""Admin du lot L7 — Ressources Humaines."""
from django.contrib import admin

from .models import AffectationRH, Agent, DisponibiliteAgent, DocumentRH, Fonction, Service


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ['nom', 'actif']
    search_fields = ['nom']


@admin.register(Fonction)
class FonctionAdmin(admin.ModelAdmin):
    list_display = ['intitule', 'service', 'grade', 'actif']
    list_filter = ['service', 'actif']
    search_fields = ['intitule']


@admin.register(Agent)
class AgentAdmin(admin.ModelAdmin):
    list_display = ['matricule', 'nom', 'prenom', 'type_contrat', 'statut']
    list_filter = ['type_contrat', 'statut']
    search_fields = ['matricule', 'nom', 'prenom', 'email']


@admin.register(AffectationRH)
class AffectationRHAdmin(admin.ModelAdmin):
    list_display = ['agent', 'fonction', 'date_debut', 'date_fin']
    list_filter = ['fonction']
    search_fields = ['agent__nom', 'agent__matricule']


@admin.register(DisponibiliteAgent)
class DisponibiliteAgentAdmin(admin.ModelAdmin):
    list_display = ['agent', 'type_indispo', 'date_debut', 'date_fin']
    list_filter = ['type_indispo']
    search_fields = ['agent__nom']


@admin.register(DocumentRH)
class DocumentRHAdmin(admin.ModelAdmin):
    list_display = ['agent', 'type_document', 'intitule', 'created_at']
    list_filter = ['type_document']
    search_fields = ['agent__nom', 'intitule']