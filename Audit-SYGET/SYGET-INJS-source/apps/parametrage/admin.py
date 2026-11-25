from django.contrib import admin
from shared.admin import AdminModelAdmin

from .models import (
    Batiment,
    Grade,
    JourFerie,
    ModuleTypeFormation,
    ParametreFormation,
    ParametreGeneral,
    PeriodeDisponibiliteSite,
    Salle,
    Site,
    Vague,
)


@admin.register(Grade)
class GradeAdmin(AdminModelAdmin):
    list_display = ["libelle", "ordre", "actif"]
    list_filter = ["actif"]
    search_fields = ["libelle"]
    ordering = ["ordre", "libelle"]


@admin.register(Vague)
class VagueAdmin(AdminModelAdmin):
    list_display = ["libelle", "actif"]
    list_filter = ["actif"]
    search_fields = ["libelle"]


@admin.register(ParametreFormation)
class ParametreFormationAdmin(AdminModelAdmin):
    list_display = ["formation", "max_auditeurs_groupe_defaut", "duree_seance_defaut_minutes"]
    search_fields = ["formation__intitule"]
    autocomplete_fields = ["formation"]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("formation")


@admin.register(ParametreGeneral)
class ParametreGeneralAdmin(AdminModelAdmin):
    def has_add_permission(self, request) -> bool:
        return not ParametreGeneral.objects.exists()


@admin.register(ModuleTypeFormation)
class ModuleTypeFormationAdmin(AdminModelAdmin):
    list_display = ["module", "type_formation", "grade_cible", "volume_horaire_defaut"]
    list_filter = ["type_formation", "grade_cible"]
    search_fields = ["module__titre", "type_formation__code"]
    autocomplete_fields = ["module", "type_formation"]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("module", "type_formation")


@admin.register(Site)
class SiteAdmin(AdminModelAdmin):
    list_display = ["nom", "actif"]
    list_filter = ["actif"]
    search_fields = ["nom"]


@admin.register(PeriodeDisponibiliteSite)
class PeriodeDisponibiliteSiteAdmin(AdminModelAdmin):
    list_display = ["site", "date_debut", "date_fin"]
    list_filter = ["site"]
    search_fields = ["site__nom"]
    ordering = ["site__nom", "date_debut"]
    autocomplete_fields = ["site"]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("site")


@admin.register(Batiment)
class BatimentAdmin(AdminModelAdmin):
    list_display = ["nom", "site", "actif"]
    list_filter = ["actif", "site"]
    search_fields = ["nom", "site__nom"]
    autocomplete_fields = ["site"]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("site")


@admin.register(Salle)
class SalleAdmin(AdminModelAdmin):
    list_display = ["nom", "batiment", "capacite_max", "actif"]
    list_filter = ["actif", "batiment"]
    search_fields = ["nom", "batiment__nom"]
    autocomplete_fields = ["batiment"]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("batiment", "batiment__site")


@admin.register(JourFerie)
class JourFerieAdmin(AdminModelAdmin):
    list_display = ["date", "libelle", "actif"]
    list_filter = ["actif"]
    search_fields = ["libelle"]
    date_hierarchy = "date"
