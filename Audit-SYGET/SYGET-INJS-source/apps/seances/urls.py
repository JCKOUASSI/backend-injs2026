from django.urls import path

from .views import (
    PlanningChevauchementsView,
    SeanceAuditListView,
    SeanceCreateView,
    SeanceDeleteView,
    SeanceExportView,
    SeanceFormationExportView,
    SeanceFormationModuleSyntheseDocxView,
    SeanceFormationPDFExportView,
    SeanceFormationPDFZipExportView,
    SeanceFormationZipExportView,
    SeanceGroupeModuleSyntheseDocxView,
    SeancePDFExportView,
    SeancePreviewView,
    SeancePreviewHtmxView,
    SeanceUpdateView,
)

app_name = "seances"

urlpatterns = [
    path("audit/", SeanceAuditListView.as_view(), name="audit_list"),
    path("chevauchements/", PlanningChevauchementsView.as_view(), name="chevauchements"),
    path("formation/<int:formation_pk>/export/", SeanceFormationExportView.as_view(), name="formation_export"),
    path(
        "formation/<int:formation_pk>/export-pdf/",
        SeanceFormationPDFExportView.as_view(),
        name="formation_export_pdf",
    ),
    path(
        "formation/<int:formation_pk>/export-pdf-zip/",
        SeanceFormationPDFZipExportView.as_view(),
        name="formation_export_pdf_zip",
    ),
    path(
        "formation/<int:formation_pk>/export-zip/",
        SeanceFormationZipExportView.as_view(),
        name="formation_export_zip",
    ),
    path(
        "formation/<int:formation_pk>/module/<int:module_pk>/synthese-docx/",
        SeanceFormationModuleSyntheseDocxView.as_view(),
        name="formation_module_synthese_docx",
    ),
    path("groupe/<int:groupe_pk>/", SeancePreviewView.as_view(), name="preview"),
    path("groupe/<int:groupe_pk>/preview-htmx/", SeancePreviewHtmxView.as_view(), name="preview_htmx"),
    path("groupe/<int:groupe_pk>/export/", SeanceExportView.as_view(), name="export"),
    path(
        "groupe/<int:groupe_pk>/export-pdf/",
        SeancePDFExportView.as_view(),
        name="export_pdf",
    ),
    path(
        "groupe/<int:groupe_pk>/module/<int:module_pk>/synthese-docx/",
        SeanceGroupeModuleSyntheseDocxView.as_view(),
        name="groupe_module_synthese_docx",
    ),
    path("groupe/<int:groupe_pk>/create/", SeanceCreateView.as_view(), name="create"),
    path("<int:pk>/update/", SeanceUpdateView.as_view(), name="update"),
    path("<int:pk>/delete/", SeanceDeleteView.as_view(), name="delete"),
]
