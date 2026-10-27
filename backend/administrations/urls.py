"""URLs API Administrations (lot L7)."""
from django.urls import path

from . import api, organigramme_api as organigramme

urlpatterns = [
    # Courriers
    path('courriers/', api.courriers_list_api, name='adm-courriers-list'),
    path('courriers/creer/', api.courrier_creer_api, name='adm-courrier-creer'),
    path('courriers/<int:pk>/transition/', api.courrier_transition_api, name='adm-courrier-transition'),
    # Documents officiels
    path('documents/', api.documents_list_api, name='adm-documents-list'),
    path('documents/creer/', api.document_creer_api, name='adm-document-creer'),
    path('documents/<int:pk>/transition/', api.document_transition_api, name='adm-document-transition'),
    # Réunions / commissions
    path('reunions/', api.reunions_api, name='adm-reunions'),
    path('reunions/<int:pk>/transition/', api.reunion_transition_api, name='adm-reunion-transition'),
    # Missions
    path('missions/', api.missions_api, name='adm-missions'),
    path('missions/<int:pk>/transition/', api.mission_transition_api, name='adm-mission-transition'),
    # Organigramme unifié (modèle fonctionnel 13 — Directions / Départements /
    # Services, secrétariats rattachés). Lot A de la refonte.
    path('organigramme/arbre/', organigramme.arbre, name='adm-organigramme-arbre'),
    path('organigramme/types-secretariat/', organigramme.types_secretariat,
         name='adm-organigramme-types-secretariat'),
    path('organigramme/responsables/', organigramme.responsables, name='adm-organigramme-responsables'),
    path('organigramme/directions/', organigramme.directions, name='adm-organigramme-directions'),
    path('organigramme/directions/<int:pk>/', organigramme.direction_detail,
         name='adm-organigramme-direction-detail'),
    path('organigramme/departements/', organigramme.departements, name='adm-organigramme-departements'),
    path('organigramme/departements/<int:pk>/', organigramme.departement_detail,
         name='adm-organigramme-departement-detail'),
    path('organigramme/services/', organigramme.services, name='adm-organigramme-services'),
    path('organigramme/services/<int:pk>/', organigramme.service_detail,
         name='adm-organigramme-service-detail'),
    path('organigramme/secretariats/', organigramme.secretariats, name='adm-organigramme-secretariats'),
    path('organigramme/secretariats/<int:pk>/', organigramme.secretariat_detail,
         name='adm-organigramme-secretariat-detail'),
]