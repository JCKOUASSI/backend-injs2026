from django.urls import path
from . import views
from . import academic_views

urlpatterns = [
    # ── Questionnaires (superviseurs) ────────────────────────────────
    path('questionnaires/', views.questionnaire_list_create, name='eval-questionnaire-list'),
    path('questionnaires/<int:pk>/', views.questionnaire_detail, name='eval-questionnaire-detail'),
    path('questionnaires/<int:pk>/statut/', views.questionnaire_publier, name='eval-questionnaire-statut'),
    path('questionnaires/<int:pk>/resultats/', views.resultats_questionnaire, name='eval-questionnaire-resultats'),
    path('questionnaires/<int:pk>/analyse/', views.analyse_qualitative, name='eval-questionnaire-analyse'),
    path('questionnaires/<int:pk>/export/<str:fmt>/', views.export_questionnaire_analyse, name='eval-questionnaire-export'),

    # ── Questions (superviseurs) ──────────────────────────────────────
    path('questionnaires/<int:questionnaire_pk>/questions/', views.question_create, name='eval-question-create'),
    path('questionnaires/<int:questionnaire_pk>/questions/<int:pk>/', views.question_detail, name='eval-question-detail'),

    # ── Résultats par module (superviseurs) ──────────────────────────
    path('modules/<int:module_pk>/resultats/', views.resultats_par_module, name='eval-module-resultats'),

    # ── Auditeurs ─────────────────────────────────────────────────────
    path('mes-questionnaires/', views.questionnaires_disponibles, name='eval-mes-questionnaires'),
    path('soumettre/', views.soumettre_evaluation, name='eval-soumettre'),

    # ── Moyennes & décisions (notes + temps de cours) ─────────────────
    path('modules/<int:module_pk>/moyennes/', academic_views.module_moyennes_list, name='eval-module-moyennes'),
    path('modules/<int:module_pk>/moyennes/recalculer/', academic_views.module_moyennes_recalc, name='eval-module-moyennes-recalc'),
    path('formations/<int:formation_pk>/decisions/', academic_views.formation_decisions_list, name='eval-formation-decisions'),
    path('formations/<int:formation_pk>/decisions/recalculer/', academic_views.formation_decisions_recalc, name='eval-formation-decisions-recalc'),
    path('decisions/<int:pk>/', academic_views.decision_detail, name='eval-decision-detail'),
]

