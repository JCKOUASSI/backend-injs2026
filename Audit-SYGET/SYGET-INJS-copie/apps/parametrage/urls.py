from django.urls import path

from .views import (
    BatimentCreateView,
    BatimentDeleteView,
    BatimentToggleActifView,
    BatimentUpdateView,
    GradeCreateView,
    GradeDeleteView,
    JourFerieCreateView,
    JourFerieDeleteView,
    ModuleAssocierView,
    ModuleCreateView,
    ModuleDissocierView,
    ParametrageIndexView,
    ParametreFormationUpdateView,
    ParametreGeneralUpdateView,
    PeriodeDisponibiliteSiteCreateView,
    PeriodeDisponibiliteSiteDeleteView,
    PeriodeDisponibiliteSiteUpdateView,
    SalleCreateView,
    SalleDeleteView,
    SalleToggleActifView,
    SalleUpdateView,
    SiteCreateView,
    SiteDeleteView,
    SiteToggleActifView,
    SiteUpdateView,
    TypeFormationCreateView,
    TypeFormationDeleteView,
    TypeFormationUpdateView,
    VagueCreateView,
    VagueDeleteView,
)

app_name = "parametrage"

urlpatterns = [
    path("", ParametrageIndexView.as_view(), name="index"),
    # Types de formation
    path("types/create/", TypeFormationCreateView.as_view(), name="type_create"),
    path("types/<int:pk>/update/", TypeFormationUpdateView.as_view(), name="type_update"),
    path("types/<int:pk>/delete/", TypeFormationDeleteView.as_view(), name="type_delete"),
    # Grades
    path("grades/create/", GradeCreateView.as_view(), name="grade_create"),
    path("grades/<int:pk>/delete/", GradeDeleteView.as_view(), name="grade_delete"),
    # Vagues
    path("vagues/create/", VagueCreateView.as_view(), name="vague_create"),
    path("vagues/<int:pk>/delete/", VagueDeleteView.as_view(), name="vague_delete"),
    # Sites / bâtiments / salles
    path("sites/create/", SiteCreateView.as_view(), name="site_create"),
    path("sites/<int:pk>/update/", SiteUpdateView.as_view(), name="site_update"),
    path("sites/<int:pk>/toggle-actif/", SiteToggleActifView.as_view(), name="site_toggle_actif"),
    path("sites/<int:pk>/delete/", SiteDeleteView.as_view(), name="site_delete"),
    path("batiments/create/", BatimentCreateView.as_view(), name="batiment_create"),
    path("batiments/<int:pk>/update/", BatimentUpdateView.as_view(), name="batiment_update"),
    path("batiments/<int:pk>/toggle-actif/", BatimentToggleActifView.as_view(), name="batiment_toggle_actif"),
    path("batiments/<int:pk>/delete/", BatimentDeleteView.as_view(), name="batiment_delete"),
    path("salles/create/", SalleCreateView.as_view(), name="salle_create"),
    path("salles/<int:pk>/update/", SalleUpdateView.as_view(), name="salle_update"),
    path("salles/<int:pk>/toggle-actif/", SalleToggleActifView.as_view(), name="salle_toggle_actif"),
    path("salles/<int:pk>/delete/", SalleDeleteView.as_view(), name="salle_delete"),
    path(
        "periodes-disponibilite-sites/create/",
        PeriodeDisponibiliteSiteCreateView.as_view(),
        name="periode_disponibilite_site_create",
    ),
    path(
        "periodes-disponibilite-sites/<int:pk>/update/",
        PeriodeDisponibiliteSiteUpdateView.as_view(),
        name="periode_disponibilite_site_update",
    ),
    path(
        "periodes-disponibilite-sites/<int:pk>/delete/",
        PeriodeDisponibiliteSiteDeleteView.as_view(),
        name="periode_disponibilite_site_delete",
    ),
    # Paramètres de planification
    path("parametres-formation/update/", ParametreFormationUpdateView.as_view(), name="parametres_formation_update"),
    path("parametres-defaut/update/", ParametreGeneralUpdateView.as_view(), name="parametres_defaut_update"),
    path("parametres/update/", ParametreGeneralUpdateView.as_view(), name="parametres_update"),
    # Jours fériés
    path("jours-feries/create/", JourFerieCreateView.as_view(), name="jour_ferie_create"),
    path("jours-feries/<int:pk>/delete/", JourFerieDeleteView.as_view(), name="jour_ferie_delete"),
    # Modules
    path("modules/create/", ModuleCreateView.as_view(), name="module_create"),
    path("modules/associer/", ModuleAssocierView.as_view(), name="module_associer"),
    path("modules/associations/<int:association_id>/delete/", ModuleDissocierView.as_view(), name="module_dissocier"),
]
