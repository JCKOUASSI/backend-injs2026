"""C1 — Administration Django des évaluations académiques.

L'admin est un accès technique : il ne contourne pas les invariants
modèles (unicité, ``PROTECT``, immuabilité des versions de règles).
"""
from django.contrib import admin

from .models import (
    ConvocationEvaluation,
    ECUEResult,
    Epreuve,
    EpreuveSurveillant,
    Evaluation,
    EvaluationAttendance,
    EvaluationComponent,
    EvaluationGrade,
    EvaluationGradeHistory,
    EvaluationParticipant,
    RegleCalcul,
    RegleCalculVersion,
    ReleveNotes,
    SemesterResult,
    SessionEvaluation,
    TypeEvaluation,
    UEResult,
)


@admin.register(SessionEvaluation)
class SessionEvaluationAdmin(admin.ModelAdmin):
    list_display = ('annee_academique', 'ref_formation', 'niveau', 'type_session',
                    'statut', 'verrouillee')
    list_filter = ('type_session', 'statut', 'annee_academique', 'niveau')
    search_fields = ('libelle',)
    raw_id_fields = ('maquette', 'session_origine', 'regle_version', 'creee_par',
                     'verrouillee_par')


@admin.register(Evaluation)
class EvaluationAdmin(admin.ModelAdmin):
    list_display = ('libelle', 'session', 'ecue', 'type_evaluation', 'poids',
                    'statut', 'composition_verrouillee')
    list_filter = ('statut', 'type_evaluation', 'composition_verrouillee')
    search_fields = ('libelle', 'ecue__code')
    raw_id_fields = ('session', 'ecue', 'affectation_pedagogique', 'regle_version')


@admin.register(EvaluationComponent)
class EvaluationComponentAdmin(admin.ModelAdmin):
    list_display = ('code', 'libelle', 'evaluation', 'poids', 'bareme', 'ordre',
                    'obligatoire', 'actif')
    list_filter = ('obligatoire', 'actif')


class EpreuveSurveillantInline(admin.TabularInline):
    model = EpreuveSurveillant
    extra = 0
    raw_id_fields = ('formateur',)


@admin.register(Epreuve)
class EpreuveAdmin(admin.ModelAdmin):
    list_display = ('date', 'heure_debut', 'evaluation', 'salle', 'statut')
    list_filter = ('statut', 'date', 'salle')
    raw_id_fields = ('evaluation', 'groupe', 'salle', 'enseignant_responsable')
    inlines = [EpreuveSurveillantInline]


@admin.register(EvaluationParticipant)
class EvaluationParticipantAdmin(admin.ModelAdmin):
    list_display = ('inscription_pedagogique', 'evaluation', 'statut_participation',
                    'source', 'eligible_rattrapage')
    list_filter = ('statut_participation', 'source', 'eligible_rattrapage')
    raw_id_fields = ('evaluation', 'inscription_pedagogique', 'groupe')


@admin.register(EvaluationAttendance)
class EvaluationAttendanceAdmin(admin.ModelAdmin):
    list_display = ('epreuve', 'evaluation_participant', 'statut', 'saisi_par',
                    'saisi_le')
    list_filter = ('statut',)
    raw_id_fields = ('evaluation_participant', 'epreuve', 'saisi_par')


@admin.register(EvaluationGrade)
class EvaluationGradeAdmin(admin.ModelAdmin):
    list_display = ('component', 'evaluation_participant', 'valeur', 'bareme',
                    'statut', 'verrouillee')
    list_filter = ('statut', 'verrouillee', 'component__evaluation')
    raw_id_fields = ('evaluation_participant', 'component', 'saisie_par')
    readonly_fields = ('valeur', 'bareme', 'statut', 'verrouillee')


@admin.register(EvaluationGradeHistory)
class EvaluationGradeHistoryAdmin(admin.ModelAdmin):
    """Historique append-only : lecture seule dans l'admin."""

    list_display = ('grade', 'action', 'ancienne_valeur', 'nouvelle_valeur',
                    'auteur', 'created_at')
    list_filter = ('action',)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ConvocationEvaluation)
class ConvocationEvaluationAdmin(admin.ModelAdmin):
    list_display = ('reference', 'epreuve', 'evaluation_participant', 'statut',
                    'date_envoi')
    list_filter = ('statut', 'support')
    raw_id_fields = ('evaluation_participant', 'epreuve')


class RegleCalculVersionInline(admin.TabularInline):
    model = RegleCalculVersion
    extra = 0
    readonly_fields = ('verrouillee', 'publiee_le', 'publiee_par')


@admin.register(RegleCalcul)
class RegleCalculAdmin(admin.ModelAdmin):
    list_display = ('code', 'libelle', 'categorie', 'actif')
    list_filter = ('categorie', 'actif')
    search_fields = ('code', 'libelle')
    inlines = [RegleCalculVersionInline]


@admin.register(TypeEvaluation)
class TypeEvaluationAdmin(admin.ModelAdmin):
    list_display = ('code', 'libelle', 'categorie', 'actif')
    list_filter = ('actif', 'categorie')
    search_fields = ('code', 'libelle')


class _ResultatAdmin(admin.ModelAdmin):
    """Résultats : lecture seule tant que le moteur C2 n'existe pas.

    Aucun résultat ne peut être créé ou modifié manuellement : un résultat
    sans règle appliquée n'est pas une traçabilité (B.1 §9 et §10).
    """

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(ECUEResult)
class ECUEResultAdmin(_ResultatAdmin):
    list_display = ('ecue', 'inscription_pedagogique', 'session', 'moyenne',
                    'statut', 'source', 'migration_status', 'verrouillee')
    list_filter = ('statut', 'source', 'migration_status', 'verrouillee')
    raw_id_fields = ('inscription_pedagogique', 'session', 'ecue', 'regle_version')


@admin.register(UEResult)
class UEResultAdmin(_ResultatAdmin):
    list_display = ('ue', 'inscription', 'session', 'moyenne', 'statut_ue',
                    'source', 'migration_status', 'verrouillee')
    list_filter = ('statut_ue', 'source', 'migration_status', 'verrouillee')
    raw_id_fields = ('inscription', 'session', 'ue', 'regle_version')


@admin.register(SemesterResult)
class SemesterResultAdmin(_ResultatAdmin):
    list_display = ('semestre', 'inscription', 'session', 'moyenne',
                    'statut_semestre', 'credits_acquis', 'verrouillee')
    list_filter = ('statut_semestre', 'source', 'migration_status', 'verrouillee')
    raw_id_fields = ('inscription', 'session', 'semestre', 'regle_version')


@admin.register(ReleveNotes)
class ReleveNotesAdmin(admin.ModelAdmin):
    list_display = ('inscription', 'session', 'version', 'genere_le', 'verrouillee')

    def has_add_permission(self, request):
        return False