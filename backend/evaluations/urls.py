"""C1 — Routes des évaluations académiques.

Montage unique (B.1 §12) : ``/api/evaluations-academiques/``.
Aucun double chemin n'est créé — contrairement au doublon historique
``/api/juries/`` + ``/api/jurys/``, qui n'est pas reproduit ici.
"""
from django.urls import path

from . import views

app_name = 'evaluations'

urlpatterns = [
    # ── Sessions ──────────────────────────────────────────────────────
    path('sessions/', views.sessions_list, name='eval-sessions-list'),
    path('sessions/create/', views.sessions_create, name='eval-sessions-create'),
    path('sessions/<int:pk>/', views.session_detail, name='eval-session-detail'),

    # ── Évaluations et composants ─────────────────────────────────────
    path('evaluations/', views.evaluations_list, name='eval-evaluations-list'),
    path('evaluations/create/', views.evaluations_create, name='eval-evaluations-create'),
    path('evaluations/<int:pk>/', views.evaluation_detail, name='eval-evaluation-detail'),
    path('evaluations/<int:pk>/composants/', views.composants_list,
         name='eval-evaluation-composants'),

    # ── Participants ──────────────────────────────────────────────────
    path('evaluations/<int:pk>/participants/', views.participants_list,
         name='eval-evaluation-participants'),

    # ── Moteur C2 : préparation (projection, lecture seule) ───────────
    path('evaluations/<int:pk>/participants/<int:participant_pk>/preparation/',
         views.preparation_participant, name='eval-participant-preparation'),

    # ── Épreuves et émargement ────────────────────────────────────────
    path('evaluations/<int:pk>/epreuves/', views.epreuves_list,
         name='eval-evaluation-epreuves'),
    path('epreuves/<int:pk>/presences/', views.presences_list,
         name='eval-epreuve-presences'),

    # ── Notes (saisie brute C1 ; workflow de validation en C2) ────────
    path('composants/<int:pk>/notes/', views.notes_saisie, name='eval-composant-notes'),
    path('notes/historique/', views.notes_historique, name='eval-notes-historique'),

    # ── Résultats (lecture seule en C1) ───────────────────────────────
    path('resultats/ecue/', views.resultats_ecue_list, name='eval-resultats-ecue'),
    path('resultats/ue/', views.resultats_ue_list, name='eval-resultats-ue'),
    path('resultats/semestre/', views.resultats_semestre_list,
         name='eval-resultats-semestre'),

    # ── Passage de niveau (calcul technique, lecture seule) ──────────
    path('resultats/passage/', views.passage_niveau_calcul,
         name='eval-resultats-passage'),

    # ── Relevés de notes (versionnés, SHA-256) ───────────────────────
    path('releves/', views.releves_list, name='eval-releves-list'),
    path('releves/generer/', views.releves_generer, name='eval-releves-generer'),
    path('releves/<int:pk>/', views.releves_detail, name='eval-releve-detail'),

    # ── Référentiels et règles (aucun seed en C1) ────────────────────
    path('regles/', views.regles_list, name='eval-regles-list'),
    path('regles/versions/', views.regles_versions_list, name='eval-regles-versions'),
    path('types-evaluation/', views.types_evaluation_list, name='eval-types-list'),
]