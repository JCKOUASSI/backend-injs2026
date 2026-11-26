"""
Vue de la page Simulation : un bloc de paramètres par formation, résultats individuels.
"""

from __future__ import annotations

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from apps.formations.models import Formation
from apps.parametrage.models import ParametreGeneral
from shared.formations_scope import (
    filter_formation_ids_pour_utilisateur,
    get_formation_pour_utilisateur,
    queryset_formations,
)
from shared.permissions import RoleProtectedMixin

from .forms import SimulationFormationFormSet
from .services import SimulationLigneResultat, extraire_chiffres_formation, synthese_simulations
from .models import ScenarioSimulation
from .scenario_storage import deserialize_formset_initial, serialize_formset_payload
from .view_helpers import (
    build_formset_initial,
    context_page,
    defaults_parametrage,
    initial_depuis_parametres,
    parse_formation_ids_from_request,
    simuler_ligne,
)

# Rétro-compatibilité tests
_calendrier_parametre = __import__(
    "apps.simulation.view_helpers", fromlist=["calendrier_parametre"]
).calendrier_parametre
_initial_depuis_parametres = initial_depuis_parametres
_initial_depuis_chiffres = __import__(
    "apps.simulation.view_helpers", fromlist=["initial_depuis_chiffres"]
).initial_depuis_chiffres
_build_formset_initial = build_formset_initial
_feries_pour_formation = __import__(
    "apps.simulation.view_helpers", fromlist=["feries_pour_formation"]
).feries_pour_formation
_overrides_pour_formation = __import__(
    "apps.simulation.view_helpers", fromlist=["overrides_pour_formation"]
).overrides_pour_formation
_simuler_ligne = simuler_ligne
_defaults_parametrage = defaults_parametrage
_context_page = context_page
_parse_formation_ids_from_request = parse_formation_ids_from_request


def _scenarios_utilisateur(user):
    return ScenarioSimulation.objects.filter(auteur=user).order_by("-updated_at")[:20]


def _charger_scenario_initial(request):
    raw = request.GET.get("scenario", "").strip()
    if not raw:
        return None
    try:
        scenario_id = int(raw)
    except (TypeError, ValueError):
        return None
    scenario = ScenarioSimulation.objects.filter(pk=scenario_id, auteur=request.user).first()
    if not scenario:
        messages.error(request, "Scénario introuvable.")
        return None
    messages.success(request, f"Scénario « {scenario.libelle} » chargé.")
    return deserialize_formset_initial(scenario.payload)


class FormationChiffresView(RoleProtectedMixin, View):
    """API JSON : chiffres d'une formation pour ajout dynamique sans rechargement."""

    permission_required = "formations.view_formation"

    def get(self, request, formation_id: int):
        from django.http import Http404

        try:
            formation = get_formation_pour_utilisateur(request.user, formation_id)
        except Http404:
            return JsonResponse({"error": "Formation introuvable."}, status=404)
        chiffres = extraire_chiffres_formation(formation_id)
        data = {k: v for k, v in chiffres.items() if not k.startswith("_")}
        data["formation_id"] = formation.pk
        data["intitule"] = formation.intitule
        if data.get("date_debut"):
            data["date_debut"] = data["date_debut"].isoformat()
        if data.get("date_fin"):
            data["date_fin"] = data["date_fin"].isoformat()
        data["jours_semaine"] = [str(j) for j in data.get("jours_semaine", [])]
        return JsonResponse(data)


class FormationSearchView(RoleProtectedMixin, View):
    """Recherche formations pour l'ajout dynamique (pas de liste complète)."""

    permission_required = "formations.view_formation"

    def get(self, request):
        q = request.GET.get("q", "").strip()
        base = queryset_formations(request.user).select_related("type_formation")
        if len(q) >= 2:
            rows = list(base.filter(intitule__icontains=q).order_by("-date_debut", "intitule")[:20])
        elif request.GET.get("recent"):
            rows = list(base.order_by("-date_debut", "intitule")[:50])
        else:
            return JsonResponse({"formations": []})
        return JsonResponse(
            {
                "formations": [
                    {
                        "id": f.pk,
                        "intitule": f.intitule,
                        "label": f"{f.intitule} ({f.type_formation.code})",
                    }
                    for f in rows
                ]
            }
        )


class SimulationView(RoleProtectedMixin, View):
    permission_required = "formations.view_formation"
    template_name = "simulation/index.html"

    def get(self, request):
        scenario_initial = _charger_scenario_initial(request)
        if scenario_initial is not None:
            formset = SimulationFormationFormSet(initial=scenario_initial, prefix="form")
            formation_ids = filter_formation_ids_pour_utilisateur(
                request.user,
                [row.get("formation_id") for row in scenario_initial if row.get("formation_id")],
            )
            formations_chargees = (
                list(queryset_formations(request.user).filter(pk__in=formation_ids).order_by("date_debut", "intitule"))
                if formation_ids
                else []
            )
            return render(
                request,
                self.template_name,
                context_page(
                    request,
                    formset=formset,
                    form=formset.forms[0] if formset.forms else None,
                    formations_chargees=formations_chargees,
                    marge_pct=int(getattr(ParametreGeneral.get(), "marge_simulation_pct", None) or 20),
                    chiffres_url_name="simulation:formation_chiffres",
                    formations_search_url_name="simulation:formations_search",
                    scenarios=_scenarios_utilisateur(request.user),
                ),
            )

        formation_ids = filter_formation_ids_pour_utilisateur(request.user, parse_formation_ids_from_request(request))
        ajouter_vide = request.GET.get("ajouter") == "1"
        initials = build_formset_initial(
            formation_ids, user=request.user, ajouter_vide=ajouter_vide and bool(formation_ids)
        )
        formset = SimulationFormationFormSet(initial=initials, prefix="form")

        formations_chargees: list[Formation] = []
        if formation_ids:
            formations_chargees = list(
                queryset_formations(request.user).filter(pk__in=formation_ids).order_by("date_debut", "intitule")
            )
            if len(formations_chargees) != len(formation_ids):
                messages.error(request, "Formation(s) introuvable(s).")
            elif len(formations_chargees) == 1:
                messages.success(
                    request,
                    f"Paramètres chargés pour « {formations_chargees[0].intitule} ».",
                )
            else:
                messages.success(
                    request,
                    f"{len(formations_chargees)} formations chargées — chacune avec ses propres paramètres.",
                )

        return render(
            request,
            self.template_name,
            context_page(
                request,
                formset=formset,
                form=formset.forms[0] if formset.forms else None,
                resultats=None,
                synthese=None,
                formations_chargees=formations_chargees,
                marge_pct=int(getattr(ParametreGeneral.get(), "marge_simulation_pct", None) or 20),
                chiffres_url_name="simulation:formation_chiffres",
                formations_search_url_name="simulation:formations_search",
                scenarios=_scenarios_utilisateur(request.user),
            ),
        )

    def post(self, request):
        if request.POST.get("action") == "save_scenario":
            return ScenarioSimulationSaveView.as_view()(request)

        formset = SimulationFormationFormSet(request.POST, prefix="form")
        marge_pct = int(getattr(ParametreGeneral.get(), "marge_simulation_pct", None) or 20)
        resultats: list[SimulationLigneResultat] | None = None
        synthese = None
        formations_chargees: list[Formation] = []

        if formset.is_valid() and not formset.forms:
            messages.error(
                request,
                "Ajoutez au moins une formation (liste déroulante + « Ajouter ») ou « Saisie manuelle ».",
            )
        elif formset.is_valid():
            resultats = [simuler_ligne(form.cleaned_data, marge_pct) for form in formset.forms]
            synthese = synthese_simulations(resultats)

            formation_ids = filter_formation_ids_pour_utilisateur(
                request.user,
                [form.cleaned_data["formation_id"] for form in formset.forms if form.cleaned_data.get("formation_id")],
            )
            if formation_ids:
                formations_chargees = list(
                    queryset_formations(request.user).filter(pk__in=formation_ids).order_by("date_debut", "intitule")
                )

        # Rétro-compatibilité tests mono-formation
        resultat = resultats[0].resultat if resultats and len(resultats) == 1 else None
        mode_auto = resultats[0].mode_auto if resultats and len(resultats) == 1 else False
        ctx_extra = {}
        if resultats and len(resultats) == 1:
            ligne = resultats[0]
            ctx_extra.update(
                {
                    "resultat": resultat,
                    "mode_auto": mode_auto,
                    "jours_ouvres_periode": ligne.jours_ouvres_periode,
                    "periode_suffisante": ligne.periode_suffisante,
                    "date_fin_proposee": ligne.date_fin_proposee,
                    "nb_jours_semaine": ligne.nb_jours_semaine,
                    "semaines_recommandees": ligne.semaines_recommandees,
                }
            )
        else:
            ctx_extra.update(
                {
                    "resultat": None,
                    "mode_auto": False,
                    "jours_ouvres_periode": None,
                    "periode_suffisante": None,
                    "date_fin_proposee": None,
                    "nb_jours_semaine": 5,
                    "semaines_recommandees": None,
                }
            )

        # Pour les tests qui lisent form.initial
        form_compat = formset.forms[0] if formset.forms else None

        return render(
            request,
            self.template_name,
            context_page(
                request,
                formset=formset,
                form=form_compat,
                resultats=resultats,
                synthese=synthese,
                formations_chargees=formations_chargees,
                marge_pct=marge_pct,
                chiffres_url_name="simulation:formation_chiffres",
                formations_search_url_name="simulation:formations_search",
                scenarios=_scenarios_utilisateur(request.user),
                **ctx_extra,
            ),
        )


class ScenarioSimulationSaveView(RoleProtectedMixin, View):
    """Enregistre les paramètres courants du formset comme scénario."""

    permission_required = "simulation.add_scenariosimulation"

    def post(self, request):
        formset = SimulationFormationFormSet(request.POST, prefix="form")
        libelle = (request.POST.get("scenario_libelle") or "").strip()
        if not libelle:
            messages.error(request, "Indiquez un libellé pour le scénario.")
            return redirect("simulation:index")
        if not formset.is_valid():
            messages.error(request, "Corrigez les paramètres avant d'enregistrer le scénario.")
            return redirect("simulation:index")
        if not formset.forms:
            messages.error(request, "Ajoutez au moins une formation avant d'enregistrer le scénario.")
            return redirect("simulation:index")
        marge_pct = int(getattr(ParametreGeneral.get(), "marge_simulation_pct", None) or 20)
        payload = serialize_formset_payload([f.cleaned_data for f in formset.forms])
        ScenarioSimulation.objects.create(
            auteur=request.user,
            libelle=libelle[:200],
            payload=payload,
            marge_pct=marge_pct,
        )
        messages.success(request, f"Scénario « {libelle} » enregistré.")
        return redirect("simulation:index")


class ScenarioSimulationDeleteView(RoleProtectedMixin, View):
    """Supprime un scénario enregistré."""

    permission_required = "simulation.delete_scenariosimulation"

    def post(self, request, pk: int):
        scenario = get_object_or_404(ScenarioSimulation, pk=pk, auteur=request.user)
        libelle = scenario.libelle
        scenario.delete()
        messages.success(request, f"Scénario « {libelle} » supprimé.")
        return redirect("simulation:index")
