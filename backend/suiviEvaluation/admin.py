from django.contrib import admin

from .models import (
    Questionnaire, Question, ChoixQuestion,
    ReponseQuestionnaire, ReponseQuestion,
)


class ChoixQuestionInline(admin.TabularInline):
    model = ChoixQuestion
    extra = 2
    fields = ['ordre', 'libelle']


class QuestionInline(admin.TabularInline):
    model = Question
    extra = 1
    fields = ['ordre', 'intitule', 'type_question', 'obligatoire']
    show_change_link = True


@admin.register(Questionnaire)
class QuestionnaireAdmin(admin.ModelAdmin):
    list_display = ['get_titres', 'cible', 'statut', 'get_categories', 'module', 'createur', 'created_at']
    list_filter = ['cible', 'statut']
    search_fields = ['titres', 'module__intitule']
    inlines = [QuestionInline]
    autocomplete_fields = ['module']

    @admin.display(description='Titres')
    def get_titres(self, obj):
        return ', '.join(obj.titres) if obj.titres else '—'

    @admin.display(description='Catégories')
    def get_categories(self, obj):
        return ', '.join(obj.categories) if obj.categories else '—'


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ['questionnaire', 'ordre', 'intitule', 'type_question', 'obligatoire']
    list_filter = ['type_question', 'obligatoire']
    search_fields = ['intitule']
    inlines = [ChoixQuestionInline]


@admin.register(ReponseQuestionnaire)
class ReponseQuestionnaireAdmin(admin.ModelAdmin):
    list_display = ['participant', 'questionnaire', 'soumis_le']
    list_filter = ['questionnaire__cible', 'questionnaire__statut']
    search_fields = ['participant__nom', 'participant__prenom']
    readonly_fields = ['soumis_le']

