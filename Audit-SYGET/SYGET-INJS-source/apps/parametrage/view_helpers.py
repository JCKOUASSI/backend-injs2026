"""Helpers HTTP pour les vues parametrage."""

from __future__ import annotations

from django.http import HttpResponseRedirect
from django.urls import reverse

from apps.referentiels.repositories import ModuleRepository, TypeFormationRepository
from apps.parametrage.repositories import GradeRepository, ParametreGeneralRepository, VagueRepository
from apps.parametrage.services import ParametrageService
from apps.parametrage.forms import (
    BatimentForm,
    GradeForm,
    JourFerieForm,
    ModuleForm,
    ModuleTypeFormationForm,
    ParametreFormationForm,
    ParametreGeneralForm,
    PeriodeDisponibiliteSiteForm,
    SalleForm,
    SiteForm,
    TypeFormationForm,
    VagueForm,
)


def make_parametrage_service() -> ParametrageService:
    """Factory pour instancier ParametrageService avec ses dépendances."""
    return ParametrageService(
        grade_repo=GradeRepository(),
        vague_repo=VagueRepository(),
        parametre_repo=ParametreGeneralRepository(),
        type_form_repo=TypeFormationRepository(),
        module_repo=ModuleRepository(),
    )


def parse_formation_id(raw) -> int | None:
    if raw in (None, ""):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def redirect_parametrage(*, anchor: str | None = None) -> HttpResponseRedirect:
    """Redirige vers la page paramétrage, avec ancre optionnelle."""
    url = reverse("parametrage:index")
    if anchor:
        url = f"{url}#{anchor}"
    return HttpResponseRedirect(url)


def build_parametrage_index_forms(ctx) -> dict:
    """Instancie les formulaires vides de la page paramétrage index."""
    parametres_formation = ctx.parametres_formation
    return {
        "type_form_form": TypeFormationForm(),
        "grade_form": GradeForm(),
        "vague_form": VagueForm(),
        "site_form": SiteForm(),
        "batiment_form": BatimentForm(),
        "salle_form": SalleForm(),
        "parametre_formation_form": (
            ParametreFormationForm(instance=parametres_formation) if parametres_formation else None
        ),
        "parametre_defaut_form": ParametreGeneralForm(instance=ctx.parametres_defaut),
        "module_form": ModuleForm(),
        "module_type_form": ModuleTypeFormationForm(),
        "jour_ferie_form": JourFerieForm(),
        "periode_disponibilite_site_form": PeriodeDisponibiliteSiteForm(),
    }
