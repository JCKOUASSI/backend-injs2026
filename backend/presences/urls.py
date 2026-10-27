from django.urls import path
from . import views
from . import rattrapage_api
from . import stats_api
from . import seances_edt_api

urlpatterns = [
    # Lot C refonte — présence par QR sur les séances LMD (EDT), émargement
    # manuel à motif et clôture automatique (modèle fonctionnel MODULE 08).
    path('presences/seances-edt/du-jour/', seances_edt_api.seances_du_jour, name='presences-edt-du-jour'),
    # Bloc « Séances en direct » du dashboard administrateur : supervision
    # consultative des séances LMD d'une journée (statut, contexte LMD,
    # présences rattachées). Lecture seule — ne déclenche aucune écriture.
    path('presences/seances-edt/supervision/', seances_edt_api.supervision_api,
         name='presences-edt-supervision'),
    path('presences/seances-edt/scan/', seances_edt_api.scan_seance, name='presences-edt-scan'),
    path('presences/seances-edt/<int:pk>/qr/', seances_edt_api.qr_seance, name='presences-edt-qr'),
    path('presences/seances-edt/<int:pk>/presences/', seances_edt_api.presences_seance,
         name='presences-edt-liste'),
    path('presences/seances-edt/<int:pk>/emargement/', seances_edt_api.emargement_seance,
         name='presences-edt-emargement'),
    path('presences/seances-edt/<int:pk>/autoclore/', seances_edt_api.autoclore_seance,
         name='presences-edt-autoclore'),

    # Lot L1 — statistiques de présence et alertes d'absence
    path('stats/taux/', stats_api.taux, name='presences-stats-taux'),
    path('stats/alertes/', stats_api.alertes, name='presences-stats-alertes'),
    path('stats/notifications/', stats_api.notifications, name='presences-stats-notifications'),
    path('stats/notifications/recues/', stats_api.notifications_recues,
         name='presences-stats-notifications-recues'),

    # Rattrapages inter-cohorte (DFRC / Encadrant / Secrétariat)
    path('rattrapages/', rattrapage_api.rattrapage_list_create, name='rattrapage-list-create'),
    path('rattrapages/participants/', rattrapage_api.rattrapage_participants_search, name='rattrapage-participants'),
    path('rattrapages/seances/', rattrapage_api.rattrapage_seances_search, name='rattrapage-seances'),
    path('rattrapages/modules/', rattrapage_api.rattrapage_modules_search, name='rattrapage-modules'),
    path('rattrapages/<int:pk>/generer-presence/', rattrapage_api.rattrapage_generer_presence, name='rattrapage-generer'),
    path('rattrapages/<int:pk>/annuler/', rattrapage_api.rattrapage_annuler, name='rattrapage-annuler'),

    # Scan QR (participant — pas besoin d'auth)
    path('scan/', views.scan_view, name='scan'),
    path('scan/offline-data/', views.scan_offline_data, name='scan-offline-data'),

    # Scan sécurisé (app mobile — anti-fraude, auth requise)
    path('scan/secure/', views.secure_scan_view, name='secure-scan'),
    path('scan/secure/heartbeat/', views.secure_scan_heartbeat, name='secure-scan-heartbeat'),
    path('scan/secure/check-status/', views.secure_check_badge_status, name='secure-check-badge-status'),

    # Config runtime (app mobile)
    path('mobile/config/', views.mobile_config, name='mobile-config'),

    # Historique personnel (app mobile)
    path('me/historique/', views.my_historique, name='my-historique'),
    path('me/fiche/', views.my_fiche, name='my-fiche'),

    # Dashboard & présences (DFRC / Superviseur)
    path('formations/<int:pk>/dashboard/', views.formation_dashboard, name='formation-dashboard'),
    path('formations/<int:pk>/presences/', views.formation_presences, name='formation-presences'),
    path('formations/<int:pk>/force-pointage/', views.force_pointage, name='force-pointage'),
    path(
        'formations/<int:pk>/force-badgeage-auditeurs-bulk/',
        views.force_badgeage_auditeurs_bulk,
        name='force-badgeage-auditeurs-bulk',
    ),
    path('formations/<int:pk>/close-session/', views.close_session, name='close-session'),

    # Offline badging data
    path('formations/<uuid:token>/offline-data/', views.formation_offline_data, name='formation-offline-data'),

    # Participant
    path('participant/<int:pk>/historique/', views.participant_historique, name='participant-historique'),
    path('participant/<int:pk>/fiche-admin/', views.participant_fiche_admin, name='participant-fiche-admin'),
    path('participant/<int:pk>/notes-fiche/', views.participant_notes_fiche, name='participant-notes-fiche'),
    path('participant/<int:pk>/notes-fiche/export/<str:fmt>/', views.participant_notes_fiche_export, name='participant-notes-fiche-export'),
    path('participant/lookup/', views.participant_lookup, name='participant-lookup'),

    # Gestion liaisons appareils (superviseur / DFRC)
    path('devices/', views.list_device_bindings, name='device-bindings'),
    path('devices/<str:device_id>/unbind/', views.unbind_device, name='unbind-device'),

    # Journal d'audit (DFRC / Encadrant)
    path('audit-logs/', views.audit_log_list, name='audit-log-list'),

    # Vérification statut badgeage avant confirmation (public)
    path('scan/check-status/', views.check_badge_status, name='check-badge-status'),
]
