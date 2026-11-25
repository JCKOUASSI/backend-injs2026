from django.urls import path

from .views import (
    FormationAuditeursExportView,
    FormationCreateView,
    FormationDeleteView,
    FormationDetailView,
    FormationRupView,
    FormateursImportPageView,
    FormateursListView,
    FormationListView,
    FormationModuleAddView,
    FormationModuleDeleteView,
    FormationModuleUpdateView,
    FormationPeriodeAddView,
    FormationPeriodeDeleteView,
    FormationPeriodeUpdateView,
    FormationUpdateView,
    InscriptionAddView,
    InscriptionCopierView,
    InscriptionDeleteView,
    RupAffectationFormateurView,
)

app_name = "formations"

urlpatterns = [
    path("", FormationListView.as_view(), name="list"),
    path("formateurs/import/", FormateursImportPageView.as_view(), name="formateurs_import_page"),
    path("formateurs/", FormateursListView.as_view(), name="formateurs_list"),
    path("create/", FormationCreateView.as_view(), name="create"),
    path("<int:pk>/", FormationDetailView.as_view(), name="detail"),
    path("<int:pk>/up/", FormationRupView.as_view(), name="rup_unite"),
    path(
        "<int:formation_pk>/up/groupe/<int:groupe_pk>/module/<int:module_pk>/affectation/",
        RupAffectationFormateurView.as_view(),
        name="rup_affectation",
    ),
    path("<int:pk>/export/auditeurs/", FormationAuditeursExportView.as_view(), name="export_auditeurs"),
    path("<int:pk>/edit/", FormationUpdateView.as_view(), name="edit"),
    path("<int:pk>/delete/", FormationDeleteView.as_view(), name="delete"),
    path("<int:pk>/periodes/add/", FormationPeriodeAddView.as_view(), name="periode_add"),
    path("<int:pk>/periodes/<int:periode_pk>/edit/", FormationPeriodeUpdateView.as_view(), name="periode_edit"),
    path("<int:pk>/periodes/<int:periode_pk>/delete/", FormationPeriodeDeleteView.as_view(), name="periode_delete"),
    path("<int:pk>/modules/add/", FormationModuleAddView.as_view(), name="module_add"),
    path("<int:pk>/modules/<int:module_pk>/edit/", FormationModuleUpdateView.as_view(), name="module_edit"),
    path("<int:pk>/modules/<int:module_pk>/delete/", FormationModuleDeleteView.as_view(), name="module_delete"),
    path("<int:pk>/inscriptions/add/", InscriptionAddView.as_view(), name="inscription_add"),
    path("<int:pk>/inscriptions/copier/", InscriptionCopierView.as_view(), name="inscription_copier"),
    path("<int:pk>/inscriptions/<int:auditeur_pk>/delete/", InscriptionDeleteView.as_view(), name="inscription_delete"),
]
