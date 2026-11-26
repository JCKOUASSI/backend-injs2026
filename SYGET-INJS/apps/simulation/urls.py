from django.urls import path

from .views import (
    FormationChiffresView,
    FormationSearchView,
    ScenarioSimulationDeleteView,
    ScenarioSimulationSaveView,
    SimulationView,
)

app_name = "simulation"

urlpatterns = [
    path("", SimulationView.as_view(), name="index"),
    path("formation/<int:formation_id>/chiffres/", FormationChiffresView.as_view(), name="formation_chiffres"),
    path("formations/search/", FormationSearchView.as_view(), name="formations_search"),
    path("scenarios/save/", ScenarioSimulationSaveView.as_view(), name="scenario_save"),
    path("scenarios/<int:pk>/delete/", ScenarioSimulationDeleteView.as_view(), name="scenario_delete"),
]
