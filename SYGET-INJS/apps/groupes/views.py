"""
Vues de l'app groupes.
"""

import logging
from typing import Optional

from django.contrib import messages
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View

from apps.formations.services import exporter_auditeurs_groupe_xlsx

from apps.formations.models import Inscription
from apps.parametrage.repositories import ParametreFormationRepository
from shared.formations_scope import (
    get_formation_pour_utilisateur,
    get_groupe_pour_utilisateur,
    queryset_formations,
    queryset_groupes,
)
from shared.permissions import RoleProtectedMixin
from shared.services.pool_inscriptions import (
    filtrer_disponibles_groupe,
    pool_inscrits_pour_affectation,
)

from .forms import ConfigHorairesForm, GroupeForm, JoursCoursForm, RythmeMensuelGroupeForm
from .models import Groupe, GroupeAuditeur
from .services import GroupeService
from .view_helpers import (
    build_groupe_list_context,
    config_form_prefix,
    config_forms_for_groupe,
    config_for_groupe,
    groupe_actuel_par_auditeur,
    make_groupe_service,
    messages_rapport_planning_formation,
    parse_source_formation_id,
    redirect_liste_groupes,
)

logger = logging.getLogger(__name__)

# Rétro-compatibilité tests / imports historiques
_config_form_prefix = config_form_prefix
_config_for_groupe = config_for_groupe
_config_forms_for_groupe = config_forms_for_groupe
_redirect_liste_groupes = redirect_liste_groupes
_parse_source_formation_id = parse_source_formation_id
_groupe_actuel_par_auditeur = groupe_actuel_par_auditeur
_make_service = make_groupe_service
_messages_rapport_planning_formation = messages_rapport_planning_formation


class GroupeListView(RoleProtectedMixin, View):
    """Affiche la liste des groupes d'une formation."""

    permission_required = "groupes.view_groupe"
    template_name = "groupes/list.html"

    def get(self, request, formation_pk: int):
        """Retourne la liste des groupes."""
        return render(
            request,
            self.template_name,
            build_groupe_list_context(request, formation_pk),
        )


class GroupeAuditeursExportView(RoleProtectedMixin, View):
    """Export Excel des auditeurs affectés à un groupe."""

    permission_required = "groupes.view_groupe"

    def get(self, request, groupe_pk: int):
        groupe = get_groupe_pour_utilisateur(
            request.user, groupe_pk, queryset=queryset_groupes(request.user).select_related("formation")
        )
        try:
            contenu = exporter_auditeurs_groupe_xlsx(groupe_pk)
        except ValueError:
            raise Http404()
        base_g = "".join(c if c.isalnum() else "_" for c in groupe.nom).strip("_")[:40] or "groupe"
        base_f = "".join(c if c.isalnum() else "_" for c in groupe.formation.intitule).strip("_")[:40] or "formation"
        fname = f"auditeurs_{base_g}_{base_f}_{groupe_pk}.xlsx"
        response = HttpResponse(
            contenu,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="{fname}"'
        return response


class GroupeCreateView(RoleProtectedMixin, View):
    """Crée manuellement un groupe vide sur une formation."""

    permission_required = "groupes.add_groupe"

    def post(self, request, formation_pk: int):
        get_formation_pour_utilisateur(request.user, formation_pk)
        form = GroupeForm(request.POST)
        source_formation_id = _parse_source_formation_id(request.POST.get("source_formation"))
        if not form.is_valid():
            for err in form.errors.get("nom", []):
                messages.error(request, err)
            for err in form.errors.get("max_auditeurs", []):
                messages.error(request, err)
            return _redirect_liste_groupes(formation_pk, source_formation_id=source_formation_id)

        cd = form.cleaned_data
        try:
            _make_service().creer(
                formation_id=formation_pk,
                nom=cd["nom"],
                max_auditeurs=cd["max_auditeurs"],
            )
        except ValueError as exc:
            messages.error(request, str(exc))
            return _redirect_liste_groupes(formation_pk, source_formation_id=source_formation_id)

        messages.success(request, f"Groupe « {cd['nom']} » créé.")
        return _redirect_liste_groupes(formation_pk, source_formation_id=source_formation_id)


class GroupeDeleteView(RoleProtectedMixin, View):
    """Supprime un groupe de la formation."""

    permission_required = "groupes.delete_groupe"

    def post(self, request, groupe_pk: int):
        groupe = get_groupe_pour_utilisateur(
            request.user, groupe_pk, queryset=queryset_groupes(request.user).only("formation_id", "nom")
        )
        source_formation_id = _parse_source_formation_id(request.POST.get("source_formation"))
        try:
            nom = _make_service().supprimer(groupe_pk)
        except ValueError as exc:
            messages.error(request, str(exc))
            return _redirect_liste_groupes(groupe.formation_id, source_formation_id=source_formation_id)

        messages.success(request, f"Groupe « {nom} » supprimé.")
        return _redirect_liste_groupes(groupe.formation_id, source_formation_id=source_formation_id)


class GroupeAutoGenerateView(RoleProtectedMixin, View):
    """Régénère les groupes automatiquement par grade."""

    permission_required = ("groupes.add_groupe", "groupes.delete_groupe")

    def post(self, request, formation_pk: int):
        """Supprime et régénère les groupes d'une formation."""
        get_formation_pour_utilisateur(request.user, formation_pk)
        logger.info(
            "GROUPES_AUTO_HTTP_POST formation_id=%s user_id=%s username=%s",
            formation_pk,
            getattr(request.user, "id", None),
            getattr(request.user, "username", ""),
        )
        mixage_grades = request.POST.get("mixage_grades") == "on"
        service = _make_service()
        try:
            nb_crees = service.generer_automatiquement_par_grade(
                formation_pk,
                reset=True,
                mixage_grades=mixage_grades,
                actor=request.user if request.user.is_authenticated else None,
            )
        except ValueError as e:
            messages.error(request, str(e))
            logger.warning(
                "GROUPES_AUTO_HTTP_RESULT formation_id=%s created=0 error=%s",
                formation_pk,
                e,
            )
            return redirect("groupes:list", formation_pk=formation_pk)

        echecs = list(getattr(service, "derniers_echecs_planning", []) or [])
        rapport = getattr(service, "dernier_rapport_planning", None) or {}
        if echecs or rapport:
            _messages_rapport_planning_formation(
                request,
                rapport_groupes=rapport.get("groupes", echecs),
                synthese=rapport.get("synthese", {}),
            )

        if nb_crees:
            mode = "avec mixage des grades par catégorie" if mixage_grades else "par grade (sans mixage inter-grades)"
            messages.success(
                request,
                f"{nb_crees} groupe(s) régénéré(s) automatiquement ({mode}).",
            )
            logger.warning(
                "GROUPES_AUTO_HTTP_RESULT formation_id=%s created=%s",
                formation_pk,
                nb_crees,
            )
        else:
            messages.warning(
                request,
                "Aucun groupe généré (vérifiez les inscriptions et les grades des auditeurs).",
            )
            logger.warning(
                "GROUPES_AUTO_HTTP_RESULT formation_id=%s created=0",
                formation_pk,
            )
        return redirect("groupes:list", formation_pk=formation_pk)


class GroupeNormaliserNomsView(RoleProtectedMixin, View):
    """Renomme les groupes existants au format A4_GROUPE1."""

    permission_required = "groupes.change_groupe"

    def post(self, request, formation_pk: int):
        get_formation_pour_utilisateur(request.user, formation_pk)
        nb = _make_service().normaliser_noms_groupes_formation(formation_pk)
        if nb:
            messages.success(request, f"{nb} groupe(s) renommé(s) au format A4_GROUPE1.")
        else:
            messages.info(request, "Aucun nom à modifier (déjà au bon format ou conflit de doublon).")
        source_formation_id = _parse_source_formation_id(request.POST.get("source_formation"))
        return _redirect_liste_groupes(formation_pk, source_formation_id=source_formation_id)


class GroupeAssurerHomologuesView(RoleProtectedMixin, View):
    """Crée les groupes homologues manquants depuis une formation source (POST explicite)."""

    permission_required = "groupes.add_groupe"

    def post(self, request, formation_pk: int):
        source_formation_id = _parse_source_formation_id(request.POST.get("source_formation"))
        if not source_formation_id or source_formation_id == formation_pk:
            messages.error(request, "Formation source invalide.")
            return redirect("groupes:list", formation_pk=formation_pk)

        crees = _make_service().assurer_groupes_homologues_depuis_source(formation_pk, source_formation_id)
        if crees:
            messages.success(
                request,
                f"{crees} groupe(s) créé(s) (mêmes noms que la formation source).",
            )
        else:
            messages.info(request, "Tous les groupes homologues existent déjà.")
        return _redirect_liste_groupes(formation_pk, source_formation_id=source_formation_id)


class GroupeReporterDepuisSourceView(RoleProtectedMixin, View):
    """Reporte les affectations groupe depuis une formation source (même noms de groupes)."""

    permission_required = ("groupes.add_groupe", "groupes.add_groupeauditeur")

    def post(self, request, formation_pk: int):
        get_formation_pour_utilisateur(request.user, formation_pk)
        source_formation_id = _parse_source_formation_id(request.POST.get("source_formation"))
        if not source_formation_id or source_formation_id == formation_pk:
            messages.error(request, "Formation source invalide.")
            return redirect("groupes:list", formation_pk=formation_pk)

        if not queryset_formations(request.user).filter(pk=source_formation_id).exists():
            messages.error(request, "Formation source introuvable.")
            return redirect("groupes:list", formation_pk=formation_pk)

        stats = _make_service().reporter_membres_depuis_formation_source(formation_pk, source_formation_id)
        if stats.get("groupes_crees"):
            messages.success(
                request,
                f"{stats['groupes_crees']} groupe(s) créé(s) (mêmes noms que la formation source).",
            )
        if stats["ajoutes"]:
            messages.success(
                request,
                f"{stats['ajoutes']} auditeur(s) affecté(s) selon les groupes de la formation source.",
            )
        if stats["ignores"]:
            messages.warning(
                request,
                f"{stats['ignores']} affectation(s) ignorée(s) (déjà affecté, sans groupe source ou groupe plein).",
            )
        if not stats["ajoutes"] and not stats["ignores"]:
            messages.info(request, "Aucun auditeur à reporter depuis la formation source.")
        return _redirect_liste_groupes(formation_pk, source_formation_id=source_formation_id)


class GroupeRegenererPlanningFormationView(RoleProtectedMixin, View):
    """Régénère l'emploi du temps de tous les groupes sans modifier leurs membres."""

    permission_required = "seances.change_seance"

    def post(self, request, formation_pk: int):
        from apps.seances.repositories import SeanceRepository
        from apps.seances.services import PlanningService

        formation = get_formation_pour_utilisateur(request.user, formation_pk)
        if not formation.groupes.exists():
            messages.warning(
                request,
                "Aucun groupe sur cette formation : créez d'abord les groupes avant de régénérer le planning.",
            )
            return redirect("groupes:list", formation_pk=formation_pk)

        actor = request.user if request.user.is_authenticated else None
        logger.info(
            "GROUPES_PLANNING_REGEN_HTTP_POST formation_id=%s user_id=%s",
            formation_pk,
            getattr(request.user, "id", None),
        )
        try:
            rapport = PlanningService(SeanceRepository()).generer_pour_formation(
                formation_pk,
                mode="best_effort",
                actor=actor,
            )
        except Exception as exc:
            logger.exception("GROUPES_PLANNING_REGEN_FAILED formation_id=%s", formation_pk)
            messages.error(request, f"Échec de la régénération du planning : {exc}")
            return redirect("groupes:list", formation_pk=formation_pk)

        _messages_rapport_planning_formation(
            request,
            rapport_groupes=rapport.get("groupes", []),
            synthese=rapport.get("synthese", {}),
            planning_run_id=rapport.get("planning_run_id"),
        )
        return redirect("groupes:list", formation_pk=formation_pk)


class ConfigGroupesView(RoleProtectedMixin, View):
    """Configure les horaires d'un groupe."""

    permission_required = "groupes.change_configgroupe"
    template_name = "groupes/config.html"

    def get(self, request, groupe_pk: int):
        """Affiche le formulaire de configuration."""
        groupe = get_groupe_pour_utilisateur(
            request.user,
            groupe_pk,
            queryset=queryset_groupes(request.user)
            .select_related("formation", "config")
            .prefetch_related("jours_cours"),
        )
        params = ParametreFormationRepository().get_for_formation(groupe.formation_id)
        horaires_form, jours_form, rythme_form = _config_forms_for_groupe(groupe, params)

        return render(
            request,
            self.template_name,
            {
                "groupe": groupe,
                "horaires_form": horaires_form,
                "jours_form": jours_form,
                "rythme_form": rythme_form,
            },
        )

    def post(self, request, groupe_pk: int):
        """Traite la soumission des formulaires de configuration."""
        groupe = get_groupe_pour_utilisateur(
            request.user, groupe_pk, queryset=queryset_groupes(request.user).select_related("config")
        )
        config = _config_for_groupe(groupe)
        pfx = _config_form_prefix(groupe_pk)
        horaires_form = ConfigHorairesForm(request.POST, instance=config, prefix=pfx)
        jours_form = JoursCoursForm(request.POST, prefix=pfx)
        rythme_form = RythmeMensuelGroupeForm(request.POST, prefix=pfx)

        if horaires_form.is_valid() and jours_form.is_valid() and rythme_form.is_valid():
            cd = horaires_form.cleaned_data
            service = _make_service()
            service.configurer_horaires(
                groupe_id=groupe_pk,
                matin_actif=cd["matin_actif"],
                matin_heure_debut=cd["matin_heure_debut"],
                matin_heure_fin=cd["matin_heure_fin"],
                soir_actif=cd["soir_actif"],
                soir_heure_debut=cd["soir_heure_debut"],
                soir_heure_fin=cd["soir_heure_fin"],
            )
            service.configurer_jours(groupe_pk, jours_form.cleaned_data["jours"])
            service.configurer_rythme_mensuel(groupe_pk, rythme_form.cleaned_data["rythme_mensuel"])
            messages.success(request, "Configuration enregistrée.")
            return _redirect_liste_groupes(groupe.formation_id, fragment_groupe_pk=groupe_pk)
        return render(
            request,
            "groupes/config.html",
            {
                "groupe": groupe,
                "horaires_form": horaires_form,
                "jours_form": jours_form,
                "rythme_form": rythme_form,
            },
        )


# ── Membres du groupe ─────────────────────────────────────────────────────────


class MembreAddView(RoleProtectedMixin, View):
    """
    Gestion manuelle des membres d'un groupe (page dédiée + POST d'affectation).
    """

    permission_required = "groupes.view_groupe"
    template_name = "groupes/membres.html"

    def _get_groupe(self, request, groupe_pk: int) -> Groupe:
        return get_groupe_pour_utilisateur(
            request.user,
            groupe_pk,
            queryset=queryset_groupes(request.user)
            .select_related("formation", "formation__type_formation")
            .prefetch_related("membres__auditeur"),
        )

    def _context_membres(
        self,
        request,
        groupe: Groupe,
        source_formation_id: Optional[int] = None,
    ) -> dict:
        q = (request.GET.get("q") or "").strip()
        source_formation_id = _parse_source_formation_id(request.GET.get("source_formation"))
        filtrer_homologue = request.GET.get("homologue") == "1" and bool(source_formation_id)
        auditeurs_en_groupe = set(
            GroupeAuditeur.objects.filter(groupe__formation_id=groupe.formation_id).values_list(
                "auditeur_id", flat=True
            )
        )
        pool, auditeurs_par_nom_source = pool_inscrits_pour_affectation(
            groupe.formation_id,
            source_formation_id,
            auditeurs_en_groupe,
            exclure_deja_en_groupe=False,
        )
        membres_ids = set(groupe.membres.values_list("auditeur_id", flat=True))
        inscrits_disponibles, nb_disponibles_total = filtrer_disponibles_groupe(
            pool,
            groupe.nom,
            membres_ids,
            auditeurs_par_nom_source,
            source_formation_id,
            q=q,
            filtrer_homologue=filtrer_homologue,
        )
        groupe_par_auditeur = _groupe_actuel_par_auditeur(groupe.formation_id)
        for ins in inscrits_disponibles:
            ins.groupe_actuel = groupe_par_auditeur.get(ins.auditeur_id)
        source_formation = None
        if source_formation_id and source_formation_id != groupe.formation_id:
            source_formation = queryset_formations(request.user).filter(pk=source_formation_id).first()
        nb_inscrits_formation = (
            Inscription.objects.filter(formation_id=groupe.formation_id).values("auditeur_id").distinct().count()
        )
        return {
            "groupe": groupe,
            "inscrits_disponibles": inscrits_disponibles,
            "nb_disponibles_total": nb_disponibles_total,
            "nb_inscrits_formation": nb_inscrits_formation,
            "groupe_par_auditeur": groupe_par_auditeur,
            "source_formation_id": source_formation_id,
            "source_formation": source_formation,
            "filtrer_homologue": filtrer_homologue,
            "q": q,
            "can_add": request.user.has_perm("groupes.add_groupeauditeur"),
            "can_remove": request.user.has_perm("groupes.delete_groupeauditeur"),
        }

    def get(self, request, groupe_pk: int):
        """Affiche la page de gestion manuelle des membres."""
        groupe = self._get_groupe(request, groupe_pk)
        source_formation_id = _parse_source_formation_id(request.GET.get("source_formation"))
        return render(request, self.template_name, self._context_membres(request, groupe, source_formation_id))

    def post(self, request, groupe_pk: int):
        """Ajoute un ou plusieurs auditeurs au groupe."""
        from django.core.exceptions import PermissionDenied

        if not request.user.has_perm("groupes.add_groupeauditeur"):
            raise PermissionDenied
        groupe = get_groupe_pour_utilisateur(
            request.user, groupe_pk, queryset=queryset_groupes(request.user).only("formation_id", "nom")
        )
        source_formation_id = _parse_source_formation_id(
            request.POST.get("source_formation") or request.GET.get("source_formation")
        )
        auditeur_ids = request.POST.getlist("auditeur_ids")
        service = _make_service()
        if source_formation_id and request.user.has_perm("groupes.add_groupe"):
            service.assurer_groupes_homologues_depuis_source(
                groupe.formation_id,
                source_formation_id,
                noms_requis=[groupe.nom],
            )
        nb_ok = 0
        for aid in auditeur_ids:
            try:
                auditeur_id = int(aid)
                if source_formation_id:
                    nom_source = GroupeService.nom_groupe_source_pour_auditeur(source_formation_id, auditeur_id)
                    if nom_source is None:
                        raise ValueError("Cet auditeur n'appartient à aucun groupe dans la formation source.")
                    if nom_source != groupe.nom:
                        raise ValueError(
                            f"Cet auditeur doit être ajouté au groupe « {nom_source} » "
                            f"(groupe homologue dans la formation source)."
                        )
                service.affecter_ou_deplacer_auditeur(groupe_id=groupe_pk, auditeur_id=auditeur_id)
                nb_ok += 1
            except ValueError as e:
                messages.warning(request, str(e))
        if nb_ok:
            messages.success(request, f"{nb_ok} auditeur(s) ajouté(s) au groupe.")
        elif not auditeur_ids:
            messages.warning(request, "Aucun auditeur sélectionné.")
        if request.POST.get("from_page") == "membres":
            url = reverse("groupes:membre_add", kwargs={"groupe_pk": groupe_pk})
            if source_formation_id:
                url = f"{url}?source_formation={source_formation_id}"
            return redirect(url)
        return _redirect_liste_groupes(
            groupe.formation_id,
            fragment_groupe_pk=groupe_pk,
            source_formation_id=source_formation_id,
        )


class MembreDeleteView(RoleProtectedMixin, View):
    """Retire un auditeur d'un groupe."""

    permission_required = "groupes.delete_groupeauditeur"

    def post(self, request, groupe_pk: int, auditeur_pk: int):
        """Supprime l'appartenance de l'auditeur au groupe."""
        groupe = get_groupe_pour_utilisateur(
            request.user, groupe_pk, queryset=queryset_groupes(request.user).only("formation_id", "nom")
        )
        source_formation_id = _parse_source_formation_id(request.POST.get("source_formation"))
        try:
            _make_service().retirer_auditeur(groupe_pk, auditeur_pk)
        except ValueError as exc:
            messages.error(request, str(exc))
            if request.POST.get("redirect_to") == "membres":
                url = reverse("groupes:membre_add", kwargs={"groupe_pk": groupe_pk})
                if source_formation_id:
                    url = f"{url}?source_formation={source_formation_id}"
                return redirect(url)
            return _redirect_liste_groupes(groupe.formation_id, source_formation_id=source_formation_id)
        messages.success(request, "Auditeur retiré du groupe.")
        if request.POST.get("redirect_to") == "membres":
            url = reverse("groupes:membre_add", kwargs={"groupe_pk": groupe_pk})
            if source_formation_id:
                url = f"{url}?source_formation={source_formation_id}"
            return redirect(url)
        return _redirect_liste_groupes(
            groupe.formation_id,
            fragment_groupe_pk=groupe_pk,
            source_formation_id=source_formation_id,
        )
