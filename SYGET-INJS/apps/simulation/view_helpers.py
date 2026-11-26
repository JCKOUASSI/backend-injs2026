"""Helpers de calcul et contexte pour la page simulation."""

from __future__ import annotations

import math

from apps.formations.models import Formation
from apps.parametrage.models import ParametreGeneral
from shared.formations_scope import filter_formation_ids_pour_utilisateur, queryset_formations

from .forms import SimulationFormationFormSet
from .services import (
    SimulationInput,
    SimulationLigneResultat,
    calculer_besoins_formations,
    compter_jours_ouvres,
    estimer_date_fin,
    extraire_chiffres_formation,
    jours_ouvres_minimum_requis,
    simuler,
)


def calendrier_parametre() -> tuple[list[int], set]:
    from apps.parametrage.models import JourFerie

    params = ParametreGeneral.get()
    jours_indices = list(params.jours_defaut) if params.jours_defaut else [0, 1, 2, 3, 4]
    feries = set(JourFerie.objects.filter(actif=True).values_list("date", flat=True))
    return jours_indices, feries


def initial_depuis_parametres() -> dict:
    from apps.parametrage.models import Salle

    params = ParametreGeneral.get()
    duree_min = params.duree_seance_defaut_minutes or 240
    capacites_salles = list(Salle.objects.filter(actif=True).values_list("capacite_max", flat=True))
    nb_salles = len(capacites_salles) or 1
    capacite_salle_moyenne = max(1, round(sum(capacites_salles) / len(capacites_salles))) if capacites_salles else 25
    jours_semaine_defaut = [str(j) for j in (params.jours_defaut or [0, 1, 2, 3, 4])]

    return {
        "intitule": "Saisie manuelle",
        "capacite_groupe": params.max_auditeurs_groupe_defaut,
        "nb_salles": nb_salles,
        "capacite_salle_moyenne": capacite_salle_moyenne,
        "tolerance_capacite_pct": params.tolerance_capacite_salle or 0,
        "creneaux_par_jour": params.max_seances_par_jour_defaut or 2,
        "duree_creneau_heures": max(1, duree_min // 60),
        "max_salles_simultanees_module": params.max_salles_simultanees_module,
        "jours_semaine": jours_semaine_defaut,
        "nb_groupes": 1,
        "nb_modules": 1,
        "heures_par_module": 20,
    }


def parse_formation_ids_from_request(request) -> list[int]:
    raw = request.GET.getlist("formations")
    if not raw:
        single = request.GET.get("formation_id") or request.GET.get("formation")
        if single:
            raw = [single]
    ids: list[int] = []
    for value in raw:
        try:
            ids.append(int(value))
        except (TypeError, ValueError):
            continue
    return list(dict.fromkeys(ids))


def initial_depuis_chiffres(chiffres: dict, formation: Formation | None = None) -> dict:
    initial = {k: v for k, v in chiffres.items() if not k.startswith("_")}
    if formation:
        initial["formation_id"] = formation.pk
        initial["intitule"] = formation.intitule
    elif not initial.get("intitule"):
        initial["intitule"] = "Saisie manuelle"
    return initial


def build_formset_initial(formation_ids: list[int], *, user=None, ajouter_vide: bool = False) -> list[dict]:
    if not formation_ids and not ajouter_vide:
        return []

    if user is not None:
        formation_ids = filter_formation_ids_pour_utilisateur(user, formation_ids)

    initials: list[dict] = []
    if formation_ids:
        formations = {f.pk: f for f in queryset_formations(user).filter(pk__in=formation_ids)}
        for fid in formation_ids:
            formation = formations.get(fid)
            if not formation:
                continue
            chiffres = extraire_chiffres_formation(fid)
            initials.append(initial_depuis_chiffres(chiffres, formation))

    if ajouter_vide or not initials:
        initials.append(initial_depuis_parametres())

    return initials


def feries_pour_formation(
    formation_id: int | None,
    date_debut,
    date_fin,
) -> set:
    from apps.parametrage.models import JourFerie

    if date_debut and date_fin and date_fin >= date_debut:
        return set(
            JourFerie.objects.filter(
                actif=True,
                date__range=(date_debut, date_fin),
            ).values_list("date", flat=True)
        )

    if formation_id:
        formation = Formation.objects.filter(pk=formation_id).only("date_debut", "date_fin").first()
        if formation and formation.date_debut and formation.date_fin:
            return set(
                JourFerie.objects.filter(
                    actif=True,
                    date__range=(formation.date_debut, formation.date_fin),
                ).values_list("date", flat=True)
            )

    _, feries = calendrier_parametre()
    return feries


def overrides_pour_formation(
    formation_id: int | None,
    capacite_groupe: int,
    duree_creneau_heures: int,
) -> dict:
    if not formation_id:
        return {}
    details, creneaux_total, creneaux_module_max, nb_groupes_total = calculer_besoins_formations(
        [formation_id],
        capacite_groupe,
        duree_creneau_heures,
    )
    detail = details[0]
    return {
        "creneaux_demandes_total_override": creneaux_total,
        "creneaux_par_module_total_override": creneaux_module_max,
        "nb_groupes_requis_override": nb_groupes_total,
        "formations_detail": [detail],
        "nb_formations": 1,
    }


def simuler_ligne(cd: dict, marge_pct: int) -> SimulationLigneResultat:
    jours_indices_param, feries_default = calendrier_parametre()
    formation_id = cd.get("formation_id")
    simulation_extra = overrides_pour_formation(
        formation_id,
        cd["capacite_groupe"],
        cd["duree_creneau_heures"],
    )

    jours_indices_form = cd.get("jours_semaine") or []
    jours_indices = [int(j) for j in jours_indices_form] if jours_indices_form else jours_indices_param

    date_debut = cd.get("date_debut")
    date_fin = cd.get("date_fin")
    feries = feries_pour_formation(formation_id, date_debut, date_fin)

    mode_auto = False
    jours_ouvres_periode = None
    periode_suffisante = None
    date_fin_proposee = None

    if date_debut and date_fin and date_fin >= date_debut:
        jours_ouvres_periode = compter_jours_ouvres(date_debut, date_fin, jours_indices, feries)
        jours_ouvres_a_utiliser = max(1, jours_ouvres_periode)
    elif cd.get("jours_ouvres"):
        jours_ouvres_a_utiliser = cd["jours_ouvres"]
    else:
        strict_min = jours_ouvres_minimum_requis(
            nb_groupes=cd["nb_groupes"],
            nb_modules=cd["nb_modules"],
            heures_par_module=cd["heures_par_module"],
            nb_salles=cd["nb_salles"],
            creneaux_par_jour=cd["creneaux_par_jour"],
            duree_creneau_heures=cd["duree_creneau_heures"],
            max_salles_simultanees_module=cd["max_salles_simultanees_module"],
            creneaux_demandes_total=simulation_extra.get("creneaux_demandes_total_override"),
            creneaux_par_module_total=simulation_extra.get("creneaux_par_module_total_override"),
        )
        jours_ouvres_a_utiliser = math.ceil(strict_min * (1 + marge_pct / 100))
        mode_auto = True

    inputs = SimulationInput(
        nb_groupes=cd["nb_groupes"],
        capacite_groupe=cd["capacite_groupe"],
        nb_modules=cd["nb_modules"],
        heures_par_module=cd["heures_par_module"],
        nb_salles=cd["nb_salles"],
        capacite_salle_moyenne=cd["capacite_salle_moyenne"],
        tolerance_capacite_pct=cd["tolerance_capacite_pct"],
        jours_ouvres=jours_ouvres_a_utiliser,
        creneaux_par_jour=cd["creneaux_par_jour"],
        duree_creneau_heures=cd["duree_creneau_heures"],
        max_salles_simultanees_module=cd["max_salles_simultanees_module"],
    )
    resultat = simuler(
        inputs,
        date_debut=date_debut,
        jours_ouvres_indices=jours_indices,
        jours_feries=feries,
        mode_auto=mode_auto,
        marge_pct=marge_pct,
        **simulation_extra,
    )

    if date_debut:
        date_fin_proposee = estimer_date_fin(
            date_debut,
            resultat.jours_ouvres_recommandes,
            jours_indices,
            feries,
        )
    if jours_ouvres_periode is not None:
        periode_suffisante = jours_ouvres_periode >= resultat.jours_ouvres_recommandes

    nb_jours_semaine = len(jours_indices) if jours_indices else 5
    semaines_recommandees = round(resultat.jours_ouvres_recommandes / nb_jours_semaine, 1)

    return SimulationLigneResultat(
        intitule=cd.get("intitule") or "Formation",
        formation_id=formation_id,
        resultat=resultat,
        mode_auto=mode_auto,
        jours_ouvres_periode=jours_ouvres_periode,
        periode_suffisante=periode_suffisante,
        date_fin_proposee=date_fin_proposee,
        nb_jours_semaine=nb_jours_semaine,
        semaines_recommandees=semaines_recommandees,
    )


def defaults_parametrage() -> dict:
    """Valeurs par défaut pour un nouveau bloc (saisie manuelle)."""
    return initial_depuis_parametres()


def context_page(request, **extra):
    """Contexte commun GET/POST (defaults JSON, max formset)."""
    return {
        "defaults_parametrage": defaults_parametrage(),
        "formset_max_num": SimulationFormationFormSet.max_num,
        **extra,
    }
