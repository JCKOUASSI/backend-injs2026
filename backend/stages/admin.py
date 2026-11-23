"""Admin du lot L5 — Stages et conventions.

Lecture stricte des conventions VALIDEE_JURY et ARCHIVEE via
``readonly_fields`` étendus ; les transitions passent par les services.
"""
from django.contrib import admin

from .models import ConventionStage, EvaluationStage, OrganismeAccueil, TuteurExterne


@admin.register(OrganismeAccueil)
class OrganismeAccueilAdmin(admin.ModelAdmin):
    list_display = ['nom', 'ville', 'pays', 'contact_nom', 'actif']
    list_filter = ['actif', 'pays']
    search_fields = ['nom', 'raison_sociale']


@admin.register(TuteurExterne)
class TuteurExterneAdmin(admin.ModelAdmin):
    list_display = ['nom', 'prenom', 'organisme', 'fonction', 'actif']
    list_filter = ['actif', 'organisme']
    search_fields = ['nom', 'prenom', 'email']


@admin.register(ConventionStage)
class ConventionStageAdmin(admin.ModelAdmin):
    list_display = ['etudiant', 'intitule', 'organisme', 'annee_academique', 'statut', 'date_debut', 'date_fin']
    list_filter = ['statut', 'annee_academique', 'organisme']
    search_fields = ['etudiant__participant__matricule', 'intitule', 'sujet']
    readonly_fields = [
        'statut', 'date_soumission', 'date_validation_admin', 'valide_par',
        'date_signature', 'date_debut_effectif', 'date_fin_effective',
        'date_soutenance', 'note_rapport', 'note_soutenance', 'mention',
        'rapport_fichier', 'convention_pdf', 'cree_par', 'archive_par',
        'date_archivage', 'motif_refus', 'created_at', 'updated_at',
    ]
    actions = None  # pas de mutation groupée — transitions via services uniquement


@admin.register(EvaluationStage)
class EvaluationStageAdmin(admin.ModelAdmin):
    list_display = ['convention', 'note_finale', 'mention', 'date_evaluation', 'valide_par']
    list_filter = ['mention']
    readonly_fields = [
        'note_finale', 'mention', 'evalue_par', 'valide_par',
        'date_evaluation', 'date_validation',
    ]
    actions = None
