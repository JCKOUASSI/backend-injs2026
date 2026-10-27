from django.urls import path
from . import views
from . import api_views
from . import archives_api
from . import notes_fiche_api
from . import session_views
from . import api_lmd
from .api_views import (
    module_list_api, module_detail_api, module_full_detail_api, module_archive_api, module_unarchive_api, module_presences_api,
    module_add_participant, module_remove_participant,
    module_add_formateur, module_remove_formateur,
    module_assign_superviseur,
    module_notes_list_api, module_notes_bulk_api,
    module_notes_colonnes_api, module_notes_colonne_delete_api,
    module_notes_workflow_api, module_notes_historique_api,
    note_modifications_notifications_api,
    finance_ajustements_notifications_api,
    ref_type_secretariat_list, ref_type_secretariat_detail,
)

urlpatterns = [
    # QR images (public) - available under both /formations/ and /api/formations/
    path('<int:pk>/qr-image/', views.qr_image, name='qr-image'),
    path('<int:pk>/sessions/<int:session_pk>/qr-image/', views.session_qr_image, name='session-qr-image'),
    
    # DFRC — Formations CRUD
    path('', views.FormationListCreateView.as_view(), name='formation-list'),
    path('<int:pk>/', views.FormationDetailView.as_view(), name='formation-detail'),
    path('<int:pk>/assign-superviseur/', views.assign_superviseur, name='assign-superviseur'),
    path('<int:pk>/participants/add/', views.add_participant_to_formation, name='add-participant'),
    path('<int:pk>/participants/<int:participant_id>/remove/', views.remove_participant_from_formation, name='remove-participant'),
    path('<int:pk>/formateurs/', views.list_formateurs_of_formation, name='formation-formateurs'),
    path('<int:pk>/formateurs/add/', views.add_formateur_to_formation, name='add-formateur'),
    path('<int:pk>/formateurs/<int:formateur_id>/remove/', views.remove_formateur_from_formation, name='remove-formateur'),

    # DFRC — Participants CRUD
    path('participants/', views.ParticipantListCreateView.as_view(), name='participant-list'),
    path('participants/<int:pk>/', views.ParticipantDetailView.as_view(), name='participant-detail'),

    # DFRC — Secretariats CRUD
    path('secretariats/', views.SecretariatListCreateView.as_view(), name='secretariat-list'),
    path('secretariats/<int:pk>/', views.SecretariatDetailView.as_view(), name='secretariat-detail'),
    path('secretariats/<int:pk>/participants/', views.secretariat_participants, name='secretariat-participants'),

    # SECRETARIAT — Formateurs CRUD
    path('formateurs/', views.FormateurListCreateView.as_view(), name='formateur-list'),
    path('formateurs/<int:pk>/', views.FormateurDetailView.as_view(), name='formateur-detail'),

    # SUPERVISEUR — Mes formations
    path('superviseur/', views.superviseur_formations, name='superviseur-formations'),
    path('superviseur/<int:pk>/', views.superviseur_formation_detail, name='superviseur-formation-detail'),
    path('superviseur/<int:pk>/generate-qr/', views.generate_qr, name='generate-qr'),
    path('superviseur/<int:pk>/qr/', views.get_active_qr, name='get-active-qr'),

    # ── Frontend API endpoints ──────────────────────────────────────────────
    # Stats for dashboard
    path('stats/', api_views.dashboard_stats, name='api-stats'),
    
    # List/filter formations (for React frontend)
    path('list/', api_views.formation_list_api, name='api-formation-list'),
    path('archives/stats/', archives_api.archives_stats_api, name='api-archives-stats'),
    path('archives/modules/', archives_api.archives_modules_list_api, name='api-archives-modules'),
    path('<int:pk>/detail/', api_views.formation_detail_api, name='api-formation-detail'),
    
    # QR code generation (simplified for frontend)
    path('<int:formation_pk>/generate-qr/', api_views.api_generate_qr, name='api-generate-qr'),
    path('<int:formation_pk>/sessions/<int:session_pk>/generate-qr/', api_views.api_generate_qr, name='api-session-generate-qr'),
    
    # Participants list
    path('participants/list/', api_views.participant_list_api, name='api-participant-list'),
    path('participants/<int:pk>/formations/', api_views.participant_formations_api, name='api-participant-formations'),
    
    # Formateurs list
    path('formateurs/list/', api_views.formateur_list_api, name='api-formateur-list'),
    path('formateurs/finance-report/', api_views.formateur_finance_report_api, name='api-formateur-finance-report'),
    path('formateurs/<int:pk>/donnees-sensibles/', api_views.formateur_donnees_sensibles_api, name='api-formateur-donnees-sensibles'),
    path('finance/dashboard/', api_views.finance_dashboard_api, name='api-finance-dashboard'),
    path('finance/settings/', api_views.finance_settings_api, name='api-finance-settings'),
    path('finance/encadrants/', api_views.finance_encadrants_api, name='api-finance-encadrants'),
    path('finance/ajustements/', api_views.finance_ajustements_api, name='api-finance-ajustements'),
    path('finance/ajustements/<int:pk>/valider/', api_views.finance_ajustement_valider_api, name='api-finance-ajustement-valider'),
    path('finance/ajustements/<int:pk>/rejeter/', api_views.finance_ajustement_rejeter_api, name='api-finance-ajustement-rejeter'),
    path('finance/notifications/', finance_ajustements_notifications_api, name='api-finance-ajustements-notifications'),
    
    # Référentiels (listes déroulantes)
    path('referentiels/', api_views.referentiels_api, name='api-referentiels'),
    path('referentiels/gestion/', api_views.referentiels_gestion_api, name='api-referentiels-gestion'),
    path('ref/excel/<str:kind>/', api_views.referentiel_excel_api, name='api-referentiel-excel'),

    # Référentiels CRUD
    path('ref/formations/', api_views.ref_formation_list, name='api-ref-formation-list'),
    path('ref/formations/<int:pk>/', api_views.ref_formation_detail, name='api-ref-formation-detail'),
    path('lmd/formations/', api_lmd.formations_lmd_api, name='api-lmd-formations'),
    path('ref/modules/', api_views.ref_module_list, name='api-ref-module-list'),
    path('ref/modules/<int:pk>/', api_views.ref_module_detail, name='api-ref-module-detail'),
    path('ref/sites/', api_views.ref_site_list, name='api-ref-site-list'),
    path('ref/sites/<int:pk>/', api_views.ref_site_detail, name='api-ref-site-detail'),
    path('ref/batiments/', api_views.ref_batiment_list, name='api-ref-batiment-list'),
    path('ref/batiments/<int:pk>/', api_views.ref_batiment_detail, name='api-ref-batiment-detail'),
    path('ref/salles/', api_views.ref_salle_list, name='api-ref-salle-list'),
    path('ref/salles/<int:pk>/', api_views.ref_salle_detail, name='api-ref-salle-detail'),
    path('ref/categories/', api_views.ref_categorie_list, name='api-ref-categorie-list'),
    path('ref/categories/<int:pk>/', api_views.ref_categorie_detail, name='api-ref-categorie-detail'),
    path('ref/grades/', api_views.ref_grade_list, name='api-ref-grade-list'),
    path('ref/grades/<int:pk>/', api_views.ref_grade_detail, name='api-ref-grade-detail'),
    path('ref/types-secretariat/', ref_type_secretariat_list, name='api-ref-type-secretariat-list'),
    path('ref/types-secretariat/<int:pk>/', ref_type_secretariat_detail, name='api-ref-type-secretariat-detail'),
    path('ref/vagues/', api_views.refvague_list_api, name='api-ref-vague-list'),
    path('ref/vagues/<int:pk>/', api_views.refvague_detail_api, name='api-ref-vague-detail'),

    # Excel import (JWT-authenticated API endpoint)
    path('import-excel/', api_views.api_import_excel, name='api-import-excel'),
    
    # Module management
    path('<int:formation_pk>/modules/', module_list_api, name='api-module-list'),
    path('<int:formation_pk>/modules/<int:module_pk>/', module_detail_api, name='api-module-detail'),
    path('<int:formation_pk>/modules/<int:module_pk>/full/', module_full_detail_api, name='api-module-full-detail'),
    path('<int:formation_pk>/modules/<int:module_pk>/archive/', module_archive_api, name='api-module-archive'),
    path('<int:formation_pk>/modules/<int:module_pk>/unarchive/', module_unarchive_api, name='api-module-unarchive'),
    path('<int:formation_pk>/modules/<int:module_pk>/archives/cahier/', archives_api.archives_cahier_appel_api, name='api-archives-cahier'),
    path('<int:formation_pk>/modules/<int:module_pk>/presences/', module_presences_api, name='api-module-presences'),
    path('<int:formation_pk>/modules/<int:module_pk>/participants/add/', module_add_participant, name='api-module-add-participant'),
    path('<int:formation_pk>/modules/<int:module_pk>/participants/<int:participant_id>/remove/', module_remove_participant, name='api-module-remove-participant'),
    path('<int:formation_pk>/modules/<int:module_pk>/formateurs/add/', module_add_formateur, name='api-module-add-formateur'),
    path('<int:formation_pk>/modules/<int:module_pk>/formateurs/<int:formateur_id>/remove/', module_remove_formateur, name='api-module-remove-formateur'),
    path('<int:formation_pk>/modules/<int:module_pk>/assign-superviseur/', module_assign_superviseur, name='api-module-assign-superviseur'),
    path('<int:formation_pk>/modules/<int:module_pk>/notes/', module_notes_list_api, name='api-module-notes-list'),
    path('<int:formation_pk>/modules/<int:module_pk>/notes/bulk/', module_notes_bulk_api, name='api-module-notes-bulk'),
    path('<int:formation_pk>/modules/<int:module_pk>/notes/workflow/', module_notes_workflow_api, name='api-module-notes-workflow'),
    path('<int:formation_pk>/modules/<int:module_pk>/notes/historique/', module_notes_historique_api, name='api-module-notes-historique'),
    path('<int:formation_pk>/modules/<int:module_pk>/notes/colonnes/', module_notes_colonnes_api, name='api-module-notes-colonnes'),
    path('<int:formation_pk>/modules/<int:module_pk>/notes/colonnes/<int:colonne_pk>/', module_notes_colonne_delete_api, name='api-module-notes-colonne-delete'),
    path('<int:formation_pk>/modules/<int:module_pk>/notes/fiche/pdf/', notes_fiche_api.module_notes_fiche_pdf_api, name='api-module-notes-fiche-pdf'),
    path('<int:formation_pk>/modules/<int:module_pk>/notes/fiche/<int:participant_pk>/pdf/', notes_fiche_api.module_notes_fiche_auditeur_pdf_api, name='api-module-notes-fiche-auditeur-pdf'),
    path('notes/notifications/', note_modifications_notifications_api, name='api-note-modifications-notifications'),

    # Session management (via module)
    path('<int:formation_pk>/sessions/', session_views.session_list, name='api-session-list'),
    path('<int:formation_pk>/modules/<int:module_pk>/sessions/new/', session_views.session_create, name='api-session-create'),
    path('<int:formation_pk>/sessions/<int:session_pk>/start/', session_views.session_start, name='api-session-start'),
    path('<int:formation_pk>/sessions/<int:session_pk>/stop/', session_views.session_stop, name='api-session-stop'),
    path('<int:formation_pk>/sessions/<int:session_pk>/delete/', session_views.session_delete, name='api-session-delete'),
    path('<int:formation_pk>/sessions/<int:session_pk>/update/', session_views.session_update, name='api-session-update'),
]
