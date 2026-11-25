from django.contrib import admin
from django.db.models import Count
from shared.admin import AdminModelAdmin

from .models import Groupe, GroupeAuditeur


@admin.register(GroupeAuditeur)
class GroupeAuditeurAdmin(AdminModelAdmin):
    """Membres de groupe : hors inline (volume important)."""

    list_display = ["groupe", "auditeur"]
    list_filter = ["groupe__formation", "groupe"]
    search_fields = [
        "groupe__nom",
        "groupe__formation__intitule",
        "auditeur__matricule",
        "auditeur__nom",
        "auditeur__prenom",
    ]
    raw_id_fields = ["auditeur", "groupe"]
    autocomplete_fields = ["groupe"]

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related(
                "groupe",
                "groupe__formation",
                "auditeur",
            )
        )


@admin.register(Groupe)
class GroupeAdmin(AdminModelAdmin):
    list_display = ["nom", "formation", "max_auditeurs", "nb_auditeurs_display"]
    list_filter = ["formation__type_formation", "formation"]
    search_fields = ["nom", "formation__intitule"]
    autocomplete_fields = ["formation"]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("formation").annotate(_nb_auditeurs=Count("membres"))

    @admin.display(description="Auditeurs", ordering="_nb_auditeurs")
    def nb_auditeurs_display(self, obj: Groupe) -> int:
        if hasattr(obj, "_nb_auditeurs"):
            return obj._nb_auditeurs
        return obj.nb_auditeurs
