from django.contrib import admin
from shared.admin import AdminModelAdmin

from .models import PlanningAuditLog, PlanningRun, Seance


@admin.register(Seance)
class SeanceAdmin(AdminModelAdmin):
    list_display = ["date", "heure_debut", "heure_fin", "module", "formateur_nom", "groupe"]
    list_filter = ["groupe__formation"]
    search_fields = [
        "groupe__nom",
        "groupe__formation__intitule",
        "module__titre",
        "formateur_nom",
        "formateur_prenom",
        "formateur_numero",
    ]
    date_hierarchy = "date"
    ordering = ["-date", "heure_debut"]
    raw_id_fields = ["groupe", "module", "salle"]
    list_select_related = ("module", "groupe", "groupe__formation", "salle")

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related(
                "module",
                "groupe",
                "groupe__formation",
                "salle",
            )
        )


@admin.register(PlanningAuditLog)
class PlanningAuditLogAdmin(AdminModelAdmin):
    list_display = ["created_at", "action", "actor", "groupe", "seance"]
    list_filter = ["action"]
    search_fields = ["actor__username", "groupe__nom", "seance__module__titre"]
    date_hierarchy = "created_at"
    ordering = ["-created_at"]
    raw_id_fields = ["groupe", "seance"]

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related(
                "actor",
                "groupe",
                "groupe__formation",
                "seance",
                "seance__module",
            )
        )


@admin.register(PlanningRun)
class PlanningRunAdmin(AdminModelAdmin):
    list_display = ["created_at", "formation", "statut", "actor", "mode"]
    list_filter = ["statut", "mode"]
    search_fields = ["formation__intitule", "actor__username"]
    date_hierarchy = "created_at"
    ordering = ["-created_at"]
    readonly_fields = ["created_at", "finished_at", "synthese", "groupes"]
    autocomplete_fields = ["formation"]
    raw_id_fields = ["actor"]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("formation", "actor")
