from django.contrib import admin
from shared.admin import AdminModelAdmin

from .models import Module, Specialite, TypeFormation


@admin.register(Specialite)
class SpecialiteAdmin(AdminModelAdmin):
    list_display = ["code", "libelle"]
    search_fields = ["code", "libelle"]


@admin.register(TypeFormation)
class TypeFormationAdmin(AdminModelAdmin):
    list_display = ["code", "libelle"]
    search_fields = ["code", "libelle"]


@admin.register(Module)
class ModuleAdmin(AdminModelAdmin):
    list_display = ["titre", "specialite", "actif"]
    list_filter = ["actif", "specialite"]
    search_fields = ["titre", "specialite__code"]
    autocomplete_fields = ["specialite"]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("specialite")
