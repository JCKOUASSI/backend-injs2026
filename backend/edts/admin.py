"""Admin du lot L8 — Emploi du temps.

Lecture/écriture pour planification (Secrétariat, Chef Secrétariat, DFRC, DIRECTION, ADMIN, ENCADRANT).
"""

from django.contrib import admin

from .models import AffectationCreneau, CreneauTemplate, ConflitCreneau, EmploiDuTemps

admin.site.register(CreneauTemplate)


@admin.register(EmploiDuTemps)
class EmploiDuTempsAdmin(admin.ModelAdmin):
    list_display = [
        'titre', 'annee_academique', 'population_type', 'population_id',
        'statut', 'created_at',
    ]
    list_filter = ['statut', 'annee_academique', 'population_type']
    search_fields = ['titre', 'population_denominateur']
    readonly_fields = ['created_at', 'updated_at']
    fieldsets = (
        ('Général', {
            'fields': ('titre', 'population_type', 'population_id', 'population_denominateur'),
        }),
        ('Période', {
            'fields': ('annee_academique',),
        }),
        ('État', {
            'fields': ('statut',),
        }),
    )


@admin.register(AffectationCreneau)
class AffectationCreneauAdmin(admin.ModelAdmin):
    list_display = [
        'emploi_du_temps', 'creneau_template', 'semaine_debut', 'semaine_fin',
        'nature', 'actif',
    ]
    list_filter = ['nature', 'actif', 'semaine_debut', 'semaine_fin']
    search_fields = ['intitule', 'enseignant_nom', 'commentaire']
    readonly_fields = ['created_at', 'updated_at']
    raw_id_fields = ['emploi_du_temps', 'creneau_template', 'formation', 'groupe']


@admin.register(ConflitCreneau)
class ConflitCreneauAdmin(admin.ModelAdmin):
    list_display = ['type_conflit', 'emploi_du_temps', 'actif', 'recalcule_le', 'created_at']
    list_filter = ['type_conflit', 'actif']
    readonly_fields = ['emploi_du_temps', 'recalcule_le', 'created_at']
    date_hierarchy = 'created_at'
