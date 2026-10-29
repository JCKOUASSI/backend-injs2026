"""Admin du lot L8 — Emploi du temps.

Lecture/écriture pour planification (Secrétariat, Chef Secrétariat, DFRC, DIRECTION, ADMIN, ENCADRANT).
"""

from django.contrib import admin

from .models import (
    AffectationCreneau,
    CreneauTemplate,
    ConflitCreneau,
    EmploiDuTemps,
    InscriptionImportee,
)

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


@admin.register(InscriptionImportee)
class InscriptionImporteeAdmin(admin.ModelAdmin):
    """Consultation des inscrits lus dans un fichier externe (GET-INJS).

    L'import se fait par l'écran « Génération annuelle » ou par l'API : l'admin
    est **en lecture seule**. Une inscription importée est la trace d'un
    fichier source ; la corriger à la main romprait la traçabilité
    (``fichier``, ``empreinte``, ``ligne_source``) et fausserait l'effectif
    réel utilisé comme contrainte de capacité. Pour corriger : réimporter un
    fichier rectifié (l'import est idempotent sur année + matricule).
    """

    list_display = [
        'matricule', 'nom', 'prenoms', 'annee_academique', 'ref_formation',
        'niveau', 'groupe', 'vague', 'statut',
    ]
    list_filter = ['statut', 'annee_academique', 'ref_formation', 'niveau', 'groupe']
    search_fields = ['matricule', 'nom', 'prenoms']
    date_hierarchy = 'created_at'
    ordering = ['annee_academique__libelle', 'nom', 'prenoms']
    list_select_related = ['annee_academique', 'ref_formation', 'niveau', 'groupe', 'vague']
    readonly_fields = [
        'annee_academique', 'matricule', 'nom', 'prenoms', 'sexe', 'date_naissance',
        'filiere_code', 'ref_formation', 'parcours', 'niveau', 'semestre', 'groupe',
        'vague', 'statut', 'fichier', 'empreinte', 'ligne_source',
        'created_at', 'updated_at',
    ]
    fieldsets = (
        ('Identité', {'fields': ('matricule', 'nom', 'prenoms', 'sexe', 'date_naissance')}),
        ('Cohorte', {
            'fields': ('annee_academique', 'filiere_code', 'ref_formation', 'parcours',
                       'niveau', 'semestre', 'groupe', 'vague'),
        }),
        ('Traçabilité du fichier', {
            'fields': ('statut', 'fichier', 'empreinte', 'ligne_source',
                       'created_at', 'updated_at'),
        }),
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
