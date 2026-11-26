from django.urls import path

from .views import (
    AuditeurCreateView,
    AuditeurDeleteView,
    AuditeurDetailView,
    AuditeurImportRapportView,
    AuditeurImportView,
    AuditeurListView,
    AuditeurUpdateView,
)

app_name = "auditeurs"

urlpatterns = [
    path("", AuditeurListView.as_view(), name="list"),
    path("create/", AuditeurCreateView.as_view(), name="create"),
    path("import/", AuditeurImportView.as_view(), name="import"),
    path("import/rapport/", AuditeurImportRapportView.as_view(), name="import_rapport"),
    path("<int:pk>/", AuditeurDetailView.as_view(), name="detail"),
    path("<int:pk>/update/", AuditeurUpdateView.as_view(), name="update"),
    path("<int:pk>/delete/", AuditeurDeleteView.as_view(), name="delete"),
]
