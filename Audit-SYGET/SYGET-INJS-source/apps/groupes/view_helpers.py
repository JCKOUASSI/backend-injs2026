"""Helpers HTTP pour les vues groupes (contexte liste, config, redirections)."""

from __future__ import annotations

import logging
from typing import Optional

from django.contrib import messages
from django.http import HttpResponseRedirect
from django.urls import reverse

from apps.groupes.models import ConfigGroupe, Groupe, GroupeAuditeur
from apps.groupes.repositories import ConfigGroupeRepository, GroupeRepository, JourCoursRepository
from apps.groupes.services import GroupeService
from apps.groupes.forms import ConfigHorairesForm, JoursCoursForm, RythmeMensuelGroupeForm

logger = logging.getLogger(__name__)

# Liste des groupes : évite des dizaines de modales + listes d'inscriptions dans une seule page HTML.
GROUPES_LIST_PAGE_SIZE = 12
# Par modal « Membres », évite des milliers de lignes <tr> (le reste reste en base, à affiner plus tard si besoin).
GROUPES_MAX_INSCRITS_DISPONIBLES_MODAL = 300


def config_form_prefix(groupe_pk: int) -> str:
    """Préfixe unique pour les formulaires config sur la liste (plusieurs modales)."""
    return f"g{groupe_pk}"


def config_for_groupe(groupe: Groupe) -> Optional[ConfigGroupe]:
    """Retourne la config du groupe, ou None si absente."""
    try:
        return groupe.config
    except ConfigGroupe.DoesNotExist:
        return None


def config_forms_for_groupe(
    groupe: Groupe, params
) -> tuple[ConfigHorairesForm, JoursCoursForm, RythmeMensuelGroupeForm]:
    """Construit les formulaires horaires + jours + rythme pour un groupe (liste ou page config)."""
    pfx = config_form_prefix(groupe.pk)
    config = config_for_groupe(groupe)
    horaires_form = ConfigHorairesForm(
        instance=config,
        prefix=pfx,
        initial=(
            {
                "matin_actif": True,
                "soir_actif": True,
                "matin_heure_debut": params.matin_heure_debut_defaut,
                "matin_heure_fin": params.matin_heure_fin_defaut,
                "soir_heure_debut": params.soir_heure_debut_defaut,
                "soir_heure_fin": params.soir_heure_fin_defaut,
            }
            if config is None
            else {}
        ),
    )
    jours_db = [str(jc.jour) for jc in groupe.jours_cours.all()]
    jours_actifs = jours_db or [str(j) for j in (params.jours_defaut or [])]
    jours_form = JoursCoursForm(prefix=pfx, initial={"jours": jours_actifs})
    rythme_form = RythmeMensuelGroupeForm(
        prefix=pfx,
        initial=({"rythme_mensuel": [groupe.rythme_mensuel]} if groupe.rythme_mensuel else {}),
    )
    return horaires_form, jours_form, rythme_form


def redirect_liste_groupes(
    formation_pk: int,
    fragment_groupe_pk: Optional[int] = None,
    source_formation_id: Optional[int] = None,
) -> HttpResponseRedirect:
    url = reverse("groupes:list", kwargs={"formation_pk": formation_pk})
    if source_formation_id:
        url = f"{url}?source_formation={source_formation_id}"
    if fragment_groupe_pk is not None:
        url = f"{url}#groupe-{fragment_groupe_pk}"
    return HttpResponseRedirect(url)


def parse_source_formation_id(raw: Optional[str]) -> Optional[int]:
    if not raw or not str(raw).strip():
        return None
    try:
        return int(str(raw).strip())
    except (ValueError, TypeError):
        return None


def groupe_actuel_par_auditeur(formation_pk: int) -> dict[int, str]:
    """Retourne auditeur_id → nom du groupe actuel dans la formation."""
    return dict(
        GroupeAuditeur.objects.filter(groupe__formation_id=formation_pk).values_list("auditeur_id", "groupe__nom")
    )


def make_groupe_service() -> GroupeService:
    """Factory pour GroupeService."""
    return GroupeService(
        repo=GroupeRepository(),
        config_repo=ConfigGroupeRepository(),
        jours_repo=JourCoursRepository(),
    )


def messages_rapport_planning_formation(
    request,
    rapport_groupes: list[dict],
    synthese: dict,
    planning_run_id: Optional[int] = None,
) -> None:
    """Affiche les retours utilisateur après une génération de planning multi-groupes."""
    echecs = [g for g in rapport_groupes if g.get("status") in ("partiel", "erreur")]
    if planning_run_id:
        messages.info(
            request,
            f"Rapport complet enregistré (n° {planning_run_id}). "
            f"Consultez l'administration ou les logs pour le détail de tous les groupes.",
        )
    if echecs:
        MAX_DETAILS = 10
        for grp in echecs[:MAX_DETAILS]:
            status = grp.get("status", "erreur")
            nom = grp.get("nom") or f"#{grp.get('groupe_id')}"
            if status == "partiel":
                modules_ko = grp.get("echecs_modules", [])
                titres = ", ".join((m.get("module_titre", "") for m in modules_ko[:3]))
                suffix = "" if len(modules_ko) <= 3 else f" (+{len(modules_ko) - 3} autres)"
                messages.warning(
                    request,
                    f"Groupe « {nom} » : planning partiel — {len(modules_ko)} module(s) "
                    f"non entièrement planifié(s) : {titres}{suffix}.",
                )
            else:
                err = grp.get("error") or "planning impossible"
                messages.error(request, f"Groupe « {nom} » : {err}")
        reste = len(echecs) - MAX_DETAILS
        if reste > 0:
            messages.warning(
                request,
                f"… et {reste} autre(s) groupe(s) avec un planning partiel ou en erreur "
                "(voir les logs pour le détail).",
            )

    nb_seances = int(synthese.get("nb_seances_total") or 0)
    nb_ok = int(synthese.get("nb_groupes_ok") or 0)
    nb_total = int(synthese.get("nb_groupes") or 0)
    if nb_total and nb_ok == nb_total and not echecs:
        messages.success(
            request,
            f"Planning régénéré pour {nb_total} groupe(s) — {nb_seances} séance(s) au total. "
            "Les affectations d'auditeurs aux groupes sont inchangées.",
        )
    elif nb_seances:
        messages.success(
            request,
            f"Planning régénéré : {nb_seances} séance(s) créée(s) pour "
            f"{nb_ok}/{nb_total} groupe(s) sans erreur bloquante. "
            "Les affectations d'auditeurs aux groupes sont inchangées.",
        )
    elif nb_total:
        messages.warning(
            request,
            "Aucune séance n'a pu être générée (vérifiez la configuration des groupes et les dates).",
        )


def build_groupe_list_context(request, formation_pk: int) -> dict:
    """Construit le contexte template pour la liste des groupes."""
    from collections import defaultdict

    from django.core.paginator import Paginator

    from apps.parametrage.repositories import ParametreFormationRepository
    from shared.formations_scope import (
        get_formation_pour_utilisateur,
        module_rup_id_pour_utilisateur,
        modules_up_formation_pour_utilisateur,
        queryset_formations,
        queryset_formateurs_pour_utilisateur,
        utilisateur_est_rup,
        utilisateur_voit_formation_entierement,
    )
    from shared.services.pool_inscriptions import filtrer_disponibles_groupe, pool_inscrits_pour_affectation

    from .forms import GroupeForm
    from .models import Groupe, GroupeAuditeur

    formation = get_formation_pour_utilisateur(request.user, formation_pk)
    service = make_groupe_service()
    groupes = service.list_par_formation(formation_pk)

    membres_par_groupe: dict[int, set[int]] = defaultdict(set)
    for gid, aid in GroupeAuditeur.objects.filter(groupe__formation_id=formation_pk).values_list(
        "groupe_id", "auditeur_id"
    ):
        membres_par_groupe[gid].add(aid)

    auditeurs_en_groupe_formation: set[int] = set()
    for ids in membres_par_groupe.values():
        auditeurs_en_groupe_formation.update(ids)

    source_formation_id: Optional[int] = None
    source_formation = None
    raw = request.GET.get("source_formation", "").strip()
    if raw:
        try:
            source_formation_id = int(raw)
        except (ValueError, TypeError):
            source_formation_id = None

    if source_formation_id and source_formation_id != formation_pk:
        source_formation = queryset_formations(request.user).filter(pk=source_formation_id).first()
        if not source_formation:
            source_formation_id = None

    auditeurs_par_nom_source: dict[str, set[int]] = {}
    homologues_manquants: list[str] = []
    if source_formation_id and source_formation:
        noms_cible = set(Groupe.objects.filter(formation_id=formation_pk).values_list("nom", flat=True))
        noms_source = set(Groupe.objects.filter(formation_id=source_formation_id).values_list("nom", flat=True))
        homologues_manquants = sorted(noms_source - noms_cible)

    inscrits_pool, auditeurs_par_nom_source = pool_inscrits_pour_affectation(
        formation_pk,
        source_formation_id if source_formation else None,
        auditeurs_en_groupe_formation,
    )

    toutes_formations = list(
        queryset_formations(request.user).exclude(pk=formation_pk).order_by("-date_debut", "intitule")
    )

    params = ParametreFormationRepository().get_for_formation(formation_pk)
    groupes_auto_mixage_grades = bool(getattr(params, "groupes_auto_mixage_grades", False))
    groupe_create_form = GroupeForm(initial={"max_auditeurs": params.max_auditeurs_groupe_defaut or 25})
    paginator = Paginator(groupes, GROUPES_LIST_PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get("page") or 1)

    modules_up_rup = list(modules_up_formation_pour_utilisateur(request.user, formation_pk))
    perimetre_partiel = not utilisateur_voit_formation_entierement(request.user, formation)

    formateurs_rup: list = []
    module_rup = None
    affectations_rup: dict[int, object] = {}
    peut_affecter_formateur = False
    if perimetre_partiel and modules_up_rup:
        from apps.formations.models import AffectationFormateurGroupe
        from apps.referentiels.models import Module

        module_rup_id = module_rup_id_pour_utilisateur(request.user)
        if module_rup_id:
            module_rup = Module.objects.filter(pk=module_rup_id).select_related("specialite").first()
            formateurs_qs = queryset_formateurs_pour_utilisateur(request.user)
            affectations_rup = {
                a.groupe_id: a
                for a in AffectationFormateurGroupe.objects.filter(
                    groupe__formation_id=formation_pk,
                    module_id=module_rup_id,
                ).select_related("formateur")
            }
            assigned_ids = {a.formateur_id for a in affectations_rup.values() if a.formateur_id}
            if assigned_ids:
                from apps.formations.models import Formateur

                formateurs_qs = (
                    Formateur.objects.filter(pk__in=formateurs_qs.values("pk"))
                    | Formateur.objects.filter(pk__in=assigned_ids)
                ).distinct().order_by("nom", "prenom")
            formateurs_rup = list(formateurs_qs.prefetch_related("specialites"))
        peut_affecter_formateur = request.user.has_perm(
            "formations.change_affectationformateurgroupe"
        ) or request.user.has_perm("formations.add_affectationformateurgroupe")

    groupes_cards: list[dict] = []
    for groupe in page_obj.object_list:
        horaires_form, jours_form, rythme_form = config_forms_for_groupe(groupe, params)
        membres_ids = membres_par_groupe.get(groupe.pk, set())
        inscrits_disponibles, nb_disponibles_total = filtrer_disponibles_groupe(
            inscrits_pool,
            groupe.nom,
            membres_ids,
            auditeurs_par_nom_source,
            source_formation_id if source_formation else None,
            limit=GROUPES_MAX_INSCRITS_DISPONIBLES_MODAL,
            filtrer_homologue=True,
        )
        groupes_cards.append(
            {
                "groupe": groupe,
                "horaires_form": horaires_form,
                "jours_form": jours_form,
                "rythme_form": rythme_form,
                "inscrits_disponibles": inscrits_disponibles,
                "inscrits_disponibles_total": nb_disponibles_total,
                "affectation_formateur": affectations_rup.get(groupe.pk) if affectations_rup else None,
            }
        )

    modules_formation = list(formation.modules.select_related("module").order_by("date_debut", "module__titre"))

    return {
        "formation": formation,
        "groupes_cards": groupes_cards,
        "page_obj": page_obj,
        "toutes_formations": toutes_formations,
        "source_formation_id": source_formation_id,
        "source_formation": source_formation,
        "modules_formation": modules_formation,
        "groupes_auto_mixage_grades": groupes_auto_mixage_grades,
        "groupe_create_form": groupe_create_form,
        "homologues_manquants": homologues_manquants,
        "est_rup": utilisateur_est_rup(request.user),
        "perimetre_partiel": perimetre_partiel,
        "modules_up_rup": modules_up_rup,
        "module_rup": module_rup,
        "formateurs_rup": formateurs_rup,
        "affectations_rup": affectations_rup,
        "peut_affecter_formateur": peut_affecter_formateur,
    }
