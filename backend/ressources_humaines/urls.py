"""URLs API Ressources Humaines (lot L7)."""
from django.urls import path

from . import api

urlpatterns = [
    # Services & fonctions
    path('services/', api.services_api, name='rh-services'),
    path('fonctions/', api.fonctions_api, name='rh-fonctions'),
    # Agents
    path('agents/', api.agents_api, name='rh-agents'),
    path('agents/<int:pk>/', api.agent_detail_api, name='rh-agent-detail'),
    path('agents/<int:pk>/affecter/', api.agent_affecter_api, name='rh-agent-affecter'),
    path('agents/<int:pk>/disponibilites/', api.agent_disponibilites_api, name='rh-agent-disponibilites'),
    # Documents RH
    path('documents/', api.documents_rh_api, name='rh-documents'),
]