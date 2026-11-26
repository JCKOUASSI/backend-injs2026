from django.urls import path

from .views import (
    ConfigGroupesView,
    GroupeAssurerHomologuesView,
    GroupeAuditeursExportView,
    GroupeAutoGenerateView,
    GroupeCreateView,
    GroupeDeleteView,
    GroupeListView,
    GroupeNormaliserNomsView,
    GroupeRegenererPlanningFormationView,
    GroupeReporterDepuisSourceView,
    MembreAddView,
    MembreDeleteView,
)

app_name = "groupes"

urlpatterns = [
    path("formation/<int:formation_pk>/", GroupeListView.as_view(), name="list"),
    path("formation/<int:formation_pk>/creer/", GroupeCreateView.as_view(), name="create"),
    path("formation/<int:formation_pk>/auto/", GroupeAutoGenerateView.as_view(), name="auto_generate"),
    path(
        "formation/<int:formation_pk>/normaliser-noms/",
        GroupeNormaliserNomsView.as_view(),
        name="normaliser_noms",
    ),
    path(
        "formation/<int:formation_pk>/planning/",
        GroupeRegenererPlanningFormationView.as_view(),
        name="regenerer_planning",
    ),
    path(
        "formation/<int:formation_pk>/assurer-homologues/",
        GroupeAssurerHomologuesView.as_view(),
        name="assurer_homologues",
    ),
    path(
        "formation/<int:formation_pk>/reporter-depuis-source/",
        GroupeReporterDepuisSourceView.as_view(),
        name="reporter_depuis_source",
    ),
    path("<int:groupe_pk>/export/auditeurs/", GroupeAuditeursExportView.as_view(), name="export_auditeurs"),
    path("<int:groupe_pk>/config/", ConfigGroupesView.as_view(), name="config"),
    path("<int:groupe_pk>/delete/", GroupeDeleteView.as_view(), name="groupe_delete"),
    # Membres
    path("<int:groupe_pk>/membres/", MembreAddView.as_view(), name="membre_add"),
    path("<int:groupe_pk>/membres/<int:auditeur_pk>/delete/", MembreDeleteView.as_view(), name="membre_delete"),
]
