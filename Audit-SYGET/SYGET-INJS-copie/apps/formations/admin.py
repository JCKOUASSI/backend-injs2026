from django.contrib import admin
from django.db.models import Count
from unfold.contrib.inlines.admin import StackedInline
from shared.admin import AdminModelAdmin

from .models import (
    AffectationFormateurGroupe,
    Formateur,
    Formation,
    FormationModule,
    FormationPeriode,
    Inscription,
    ResponsableUnitePedagogique,
)


@admin.register(FormationPeriode)
class FormationPeriodeAdmin(AdminModelAdmin):
    list_display = ["formation", "libelle", "date_debut", "date_fin", "rythme_mensuel", "ordre"]
    list_filter = ["formation"]
    search_fields = ["formation__intitule", "libelle"]
    autocomplete_fields = ["formation"]


@admin.register(FormationModule)
class FormationModuleAdmin(AdminModelAdmin):
    """Programme pédagogique (édition hors fiche Formation)."""

    list_display = [
        "formation",
        "periode",
        "module",
        "grade_cible",
        "volume_horaire",
        "date_debut",
        "date_fin",
    ]
    list_filter = ["formation", "periode", "creneau_mode"]
    search_fields = ["formation__intitule", "module__titre"]
    autocomplete_fields = ["formation", "module", "periode"]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("formation", "module")


@admin.register(Inscription)
class InscriptionAdmin(AdminModelAdmin):
    """Inscriptions : volume élevé, pas d'inline sur Formation."""

    list_display = ["formation", "formation_module", "auditeur", "date_inscription"]
    list_filter = ["formation", "formation__type_formation"]
    search_fields = [
        "formation__intitule",
        "auditeur__matricule",
        "auditeur__nom",
        "auditeur__prenom",
        "formation_module__module__titre",
    ]
    raw_id_fields = ["auditeur", "formation_module"]
    autocomplete_fields = ["formation"]
    date_hierarchy = "date_inscription"

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related(
                "formation",
                "formation_module__module",
                "auditeur",
            )
        )


@admin.register(Formation)
class FormationAdmin(AdminModelAdmin):
    """Fiche formation allégée (modules et inscriptions via leurs admins dédiés)."""

    list_display = [
        "intitule",
        "type_formation",
        "vague",
        "date_debut",
        "date_fin",
        "planning_union_sites_programme",
        "nb_inscrits_display",
    ]
    list_filter = ["type_formation", "vague"]
    search_fields = ["intitule"]
    autocomplete_fields = ["type_formation", "responsable"]

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("type_formation", "responsable")
            .annotate(_nb_inscrits=Count("inscriptions__auditeur", distinct=True))
        )

    @admin.display(description="Inscrits", ordering="_nb_inscrits")
    def nb_inscrits_display(self, obj: Formation) -> int:
        if hasattr(obj, "_nb_inscrits"):
            return obj._nb_inscrits
        return obj.nb_inscrits


@admin.register(Formateur)
class FormateurAdmin(AdminModelAdmin):
    list_display = ["nom", "prenom", "numero", "organisation", "created_at"]
    search_fields = ["nom", "prenom", "numero", "email", "telephone"]
    autocomplete_fields = ["specialites"]


@admin.register(ResponsableUnitePedagogique)
class ResponsableUnitePedagogiqueAdmin(AdminModelAdmin):
    """RUP : un module du référentiel par utilisateur (liste déroulante)."""

    list_display = ["user", "module", "created_at"]
    list_filter = ["module"]
    search_fields = ["user__username", "user__email", "module__titre"]
    raw_id_fields = ["user"]
    fields = ("user", "module")

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user", "module")

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "module":
            from apps.referentiels.models import Module

            kwargs["queryset"] = Module.objects.filter(actif=True).select_related("specialite").order_by("titre")
            kwargs["empty_label"] = "— Choisir un module (matière) —"
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if "module" in form.base_fields:
            form.base_fields["module"].help_text = (
                "Module du référentiel (matière plateforme) dont cet utilisateur est responsable. "
                "Il gère les formateurs de ce module dans toutes les formations où il figure au programme."
            )
        return form


class ResponsabiliteUpInline(StackedInline):
    """Permet de définir le module RUP depuis la fiche utilisateur."""

    model = ResponsableUnitePedagogique
    fk_name = "user"
    max_num = 1
    extra = 0
    can_delete = True
    fields = ("module",)
    verbose_name = "Module RUP"
    verbose_name_plural = "Module RUP (responsable d'unité pédagogique)"

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "module":
            from apps.referentiels.models import Module

            kwargs["queryset"] = Module.objects.filter(actif=True).select_related("specialite").order_by("titre")
            kwargs["empty_label"] = "— Choisir un module (matière) —"
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(AffectationFormateurGroupe)
class AffectationFormateurGroupeAdmin(AdminModelAdmin):
    list_display = ["groupe", "module", "formateur", "created_at"]
    list_filter = ["groupe__formation", "groupe", "module"]
    search_fields = [
        "groupe__nom",
        "module__titre",
        "formateur__nom",
        "formateur__prenom",
        "formateur__numero",
    ]
    autocomplete_fields = ["groupe", "module", "formateur"]

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related(
                "groupe",
                "groupe__formation",
                "module",
                "formateur",
            )
        )
