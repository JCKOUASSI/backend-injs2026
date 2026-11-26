from django.contrib import admin
from shared.admin import AdminModelAdmin

from .models import Auditeur


@admin.register(Auditeur)
class AuditeurAdmin(AdminModelAdmin):
    list_display = ["matricule", "nom", "prenom", "genre", "grade", "categorie", "type_concours"]
    list_filter = ["grade", "genre", "categorie"]
    search_fields = ["matricule", "nom", "prenom", "libelle_concours"]
    ordering = ["nom", "prenom"]
