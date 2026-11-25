"""
Vues de l'app seances.
"""

import datetime
from typing import Optional

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from apps.groupes.models import Groupe
from shared.formations_scope import (
    filtrer_seances_selon_perimetre,
    get_formation_pour_utilisateur,
    get_groupe_pour_utilisateur,
    queryset_formations,
    queryset_groupes,
    utilisateur_peut_gerer_module_up,
    utilisateur_voit_formation_entierement,
)
from shared.permissions import RoleProtectedMixin

from .docx_synthese import SyntheseUPDocxService
from .forms import SeanceForm
from .models import PlanningAuditLog, Seance
from .overlap import detecter_chevauchements
from .pdf_export import ExportPlanningPDFService
from .repositories import SeanceRepository
from apps.seances.conflicts import detecter_conflits_planning
from apps.seances.excel_export import ExportSeancesService
from .services import PlanningService

# Noms historiques des groupes planning, conservés pour la documentation et le seed.
ROLE_ADMIN = "ADMIN_EDT"
ROLE_GESTIONNAIRE = "GESTIONNAIRE_EDT"
ROLE_DIRECTION = "DIRECTION_EDT"

# Permissions Django utilisées comme source de vérité (alimentées par seed_roles).
PERM_VIEW_SEANCE = "seances.view_seance"
PERM_CHANGE_SEANCE = "seances.change_seance"


def _log_planning_action(
    request,
    action: str,
    groupe: Optional[Groupe] = None,
    seance: Optional[Seance] = None,
    details: Optional[dict] = None,
) -> None:
    """Enregistre une entrée d'audit planning."""
    PlanningAuditLog.objects.create(
        actor=request.user if getattr(request, "user", None) and request.user.is_authenticated else None,
        action=action,
        groupe=groupe,
        seance=seance,
        details=details or {},
    )


class PlanningReadAccessMixin(RoleProtectedMixin):
    """Accès lecture planning : exige la permission Django `seances.view_seance`."""

    permission_required = PERM_VIEW_SEANCE


class PlanningWriteAccessMixin(RoleProtectedMixin):
    """Accès écriture planning : exige `seances.change_seance`."""

    permission_required = PERM_CHANGE_SEANCE


class SeancePreviewView(PlanningReadAccessMixin, View):
    """Affiche le planning d'un groupe et permet de le générer / exporter."""

    template_name = "seances/preview.html"

    def _render_preview_page(self, request, groupe: Groupe, extra_context: Optional[dict] = None):
        """Rend la page preview avec les séances persistées et un contexte optionnel."""
        seances_brutes = SeanceRepository().list_by_groupe(groupe.pk)
        vue_complete = utilisateur_voit_formation_entierement(request.user, groupe.formation)
        seances = filtrer_seances_selon_perimetre(request.user, groupe.formation, seances_brutes)
        conflits_base = seances_brutes if vue_complete else seances
        conflits = detecter_conflits_planning(groupe, conflits_base)
        total_heures = round(sum((s.duree_minutes or 0) for s in seances) / 60, 2)
        create_form = SeanceForm(formation=groupe.formation)
        seances_with_forms = [(s, SeanceForm(instance=s, formation=groupe.formation)) for s in seances]

        # Modules distincts ayant des séances dans ce groupe (pour export Synthèse DOCX)
        modules_vus: dict[int, str] = {}
        for s in seances:
            if s.module_id and s.module_id not in modules_vus:
                modules_vus[s.module_id] = s.module.titre if s.module else f"Module {s.module_id}"
        modules_avec_seances = [
            {"module_id": mid, "titre": titre} for mid, titre in sorted(modules_vus.items(), key=lambda x: x[1])
        ]

        context = {
            "groupe": groupe,
            "seances": seances,
            "seances_with_forms": seances_with_forms,
            "conflits": conflits,
            "create_form": create_form,
            "total_heures": total_heures,
            "modules_avec_seances": modules_avec_seances,
            "perimetre_partiel": not vue_complete,
        }
        if extra_context:
            context.update(extra_context)
        return render(request, self.template_name, context)

    def get(self, request, groupe_pk: int):
        """Affiche les séances existantes du groupe."""
        groupe = get_groupe_pour_utilisateur(
            request.user,
            groupe_pk,
            queryset=queryset_groupes(request.user)
            .select_related("formation", "config")
            .prefetch_related("jours_cours"),
        )
        return self._render_preview_page(request, groupe)

    def post(self, request, groupe_pk: int):
        """Génère les séances du groupe."""
        if not request.user.has_perm(PERM_CHANGE_SEANCE):
            raise PermissionDenied
        groupe = get_groupe_pour_utilisateur(
            request.user,
            groupe_pk,
            queryset=queryset_groupes(request.user)
            .select_related("formation", "config")
            .prefetch_related("jours_cours", "membres__auditeur", "formation__modules__module"),
        )
        mode = (request.POST.get("mode") or "generate").strip().lower()
        try:
            service = PlanningService(SeanceRepository())
            if mode == "preview":
                seances, report = service.previsualiser_pour_groupe(groupe_pk, actor=request.user)
                total_heures = round(sum((s.duree_minutes or 0) for s in seances) / 60, 2)
                conflits = detecter_conflits_planning(groupe, seances)
                message = (
                    f"Prévisualisation: {len(seances)} séance(s) potentielles, {total_heures}h au total, "
                    f"{len(conflits)} conflit(s) détecté(s)."
                )
                messages.info(request, message)
                messages.info(request, "Aucune séance n'a été enregistrée (mode prévisualisation).")
                return self._render_preview_page(
                    request,
                    groupe,
                    extra_context={
                        "preview_mode": True,
                        "preview_module_report": report,
                        "preview_total_seances": len(seances),
                        "preview_total_heures": total_heures,
                        "preview_conflits_count": len(conflits),
                    },
                )
            else:
                seances = service.generer_pour_groupe(groupe_pk, mode="best_effort", actor=request.user)
                echecs = list(getattr(service, "_derniers_echecs_modules", []) or [])
                _log_planning_action(
                    request,
                    PlanningAuditLog.Action.GENERATE,
                    groupe=groupe,
                    details={
                        "nb_seances": len(seances),
                        "nb_modules_partiels": len(echecs),
                    },
                )
                messages.success(request, f"{len(seances)} séances générées.")
                if echecs:
                    titres = ", ".join(e.get("module_titre", "") for e in echecs[:3])
                    suffix = "" if len(echecs) <= 3 else f" (+{len(echecs) - 3} autres)"
                    messages.warning(
                        request,
                        f"{len(echecs)} module(s) non entièrement planifié(s) : {titres}{suffix}.",
                    )
        except (ValueError, Exception) as e:
            messages.error(request, str(e))
        return redirect("seances:preview", groupe_pk=groupe_pk)


class SeancePreviewHtmxView(PlanningReadAccessMixin, View):
    """Fragment HTMX : prévisualisation sans rechargement complet de la page."""

    template_name = "seances/_preview_htmx.html"

    def post(self, request, groupe_pk: int):
        if not request.user.has_perm(PERM_CHANGE_SEANCE):
            raise PermissionDenied
        groupe = get_groupe_pour_utilisateur(
            request.user,
            groupe_pk,
            queryset=queryset_groupes(request.user)
            .select_related("formation", "config")
            .prefetch_related("jours_cours", "membres__auditeur", "formation__modules__module"),
        )
        try:
            service = PlanningService(SeanceRepository())
            seances, report = service.previsualiser_pour_groupe(groupe_pk, actor=request.user)
            total_heures = round(sum((s.duree_minutes or 0) for s in seances) / 60, 2)
            conflits = detecter_conflits_planning(groupe, seances)
            return render(
                request,
                self.template_name,
                {
                    "preview_module_report": report,
                    "preview_total_seances": len(seances),
                    "preview_total_heures": total_heures,
                    "preview_conflits_count": len(conflits),
                },
            )
        except ValueError as exc:
            return render(
                request,
                self.template_name,
                {
                    "preview_module_report": [],
                    "preview_total_seances": 0,
                    "preview_total_heures": 0,
                    "preview_conflits_count": 0,
                    "preview_error": str(exc),
                },
            )


class PlanningChevauchementsView(PlanningReadAccessMixin, View):
    """Détecte et affiche les chevauchements de salle entre formations.

    Critère : même date + même salle (site/bâtiment/salle) + formations distinctes.
    Les conflits "réels" sont ceux dont les créneaux horaires se chevauchent ;
    les autres cas (même salle/jour, créneaux disjoints) sont présentés à part
    comme points de vigilance.
    """

    template_name = "seances/chevauchements.html"

    def get(self, request):
        from shared.formations_scope import filter_formation_ids_pour_utilisateur

        ids_param = request.GET.getlist("formation")
        try:
            formation_ids = [int(x) for x in ids_param if x.strip()]
        except (TypeError, ValueError):
            formation_ids = []

        formation_ids = filter_formation_ids_pour_utilisateur(request.user, formation_ids)
        report = detecter_chevauchements(formation_ids or None)
        all_formations = list(queryset_formations(request.user).order_by("date_debut", "intitule"))

        context = {
            "report": report,
            "formations_choices": all_formations,
            "formation_ids_selected": set(formation_ids),
        }
        return render(request, self.template_name, context)


class SeanceAuditListView(PlanningReadAccessMixin, View):
    """Affiche l'historique des actions de planning avec filtres."""

    template_name = "seances/audit_list.html"

    def get(self, request):
        logs = PlanningAuditLog.objects.select_related("actor", "groupe", "seance").all()

        action = (request.GET.get("action") or "").strip()
        if action and action in dict(PlanningAuditLog.Action.choices):
            logs = logs.filter(action=action)

        username = (request.GET.get("username") or "").strip()
        if username:
            logs = logs.filter(actor__username__icontains=username)

        groupe_nom = (request.GET.get("groupe") or "").strip()
        if groupe_nom:
            logs = logs.filter(groupe__nom__icontains=groupe_nom)

        date_from = (request.GET.get("date_from") or "").strip()
        date_to = (request.GET.get("date_to") or "").strip()
        if date_from:
            logs = logs.filter(created_at__date__gte=date_from)
        if date_to:
            logs = logs.filter(created_at__date__lte=date_to)

        return render(
            request,
            self.template_name,
            {
                "logs": logs[:300],
                "actions": PlanningAuditLog.Action.choices,
                "filters": {
                    "action": action,
                    "username": username,
                    "groupe": groupe_nom,
                    "date_from": date_from,
                    "date_to": date_to,
                },
            },
        )


class SeanceExportView(PlanningReadAccessMixin, View):
    """Exporte les séances d'un groupe en fichier Excel."""

    def get(self, request, groupe_pk: int):
        """Retourne le fichier XLSX des séances."""
        groupe = get_groupe_pour_utilisateur(
            request.user,
            groupe_pk,
            queryset=queryset_groupes(request.user).prefetch_related("membres__auditeur"),
        )
        format_export = (request.GET.get("format") or "cours").strip().lower()
        if format_export == "complet":
            format_export = "cours"
        if format_export not in {"cours", "seances", "formateurs"}:
            format_export = "cours"
        contenu = ExportSeancesService(SeanceRepository()).exporter(
            groupe_pk,
            format_export=format_export,
        )
        _log_planning_action(
            request,
            PlanningAuditLog.Action.EXPORT,
            groupe=groupe,
            details={"format_export": format_export},
        )
        from shared.utils.groupes import nom_fichier_emploi_du_temps

        variante = format_export if format_export in {"seances", "formateurs"} else ""
        nom_fichier = nom_fichier_emploi_du_temps(
            groupe=groupe,
            extension="xlsx",
            variante=variante,
        )
        response = HttpResponse(
            contenu,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="{nom_fichier}"'
        return response


class SeanceFormationExportView(PlanningReadAccessMixin, View):
    """Exporte les séances de tous les groupes d'une formation en fichier Excel."""

    def get(self, request, formation_pk: int):
        """Retourne le fichier XLSX des séances multi-groupes d'une formation."""
        formation = get_formation_pour_utilisateur(request.user, formation_pk)
        format_export = (request.GET.get("format") or "cours").strip().lower()
        if format_export == "complet":
            format_export = "cours"
        if format_export not in {"cours", "seances", "formateurs"}:
            format_export = "cours"
        contenu = ExportSeancesService(SeanceRepository()).exporter_par_formation(
            formation_pk,
            format_export=format_export,
        )
        _log_planning_action(
            request,
            PlanningAuditLog.Action.EXPORT,
            details={
                "format_export": format_export,
                "scope": "formation",
                "formation_id": formation.pk,
            },
        )
        from shared.utils.groupes import nom_fichier_emploi_du_temps_formation

        variante = format_export if format_export in {"seances", "formateurs"} else ""
        nom_fichier = nom_fichier_emploi_du_temps_formation(formation, extension="xlsx")
        if variante:
            base = nom_fichier.rsplit(".", 1)[0]
            nom_fichier = f"{base}_{variante}.xlsx"
        response = HttpResponse(
            contenu,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="{nom_fichier}"'
        return response


class SeancePDFExportView(PlanningReadAccessMixin, View):
    """Exporte le planning d'un groupe en PDF de synthèse (A4 paysage)."""

    def get(self, request, groupe_pk: int):
        """Retourne le fichier PDF du planning du groupe."""
        groupe = get_groupe_pour_utilisateur(
            request.user,
            groupe_pk,
            queryset=queryset_groupes(request.user).select_related("formation").prefetch_related("membres__auditeur"),
        )
        contenu = ExportPlanningPDFService(SeanceRepository()).exporter_groupe(groupe_pk)
        _log_planning_action(
            request,
            PlanningAuditLog.Action.EXPORT,
            groupe=groupe,
            details={"format_export": "pdf", "scope": "groupe"},
        )
        from shared.utils.groupes import nom_fichier_emploi_du_temps

        nom_fichier = nom_fichier_emploi_du_temps(groupe=groupe, extension="pdf")
        response = HttpResponse(contenu, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{nom_fichier}"'
        return response


class SeanceFormationPDFExportView(PlanningReadAccessMixin, View):
    """Exporte le planning de tous les groupes d'une formation en un PDF unique."""

    def get(self, request, formation_pk: int):
        """Retourne le fichier PDF de synthèse multi-groupes."""
        formation = get_formation_pour_utilisateur(request.user, formation_pk)
        contenu = ExportPlanningPDFService(SeanceRepository()).exporter_formation(formation_pk)
        _log_planning_action(
            request,
            PlanningAuditLog.Action.EXPORT,
            details={
                "format_export": "pdf",
                "scope": "formation",
                "formation_id": formation.pk,
            },
        )
        from shared.utils.groupes import nom_fichier_emploi_du_temps_formation

        nom_fichier = nom_fichier_emploi_du_temps_formation(formation, extension="pdf")
        response = HttpResponse(contenu, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{nom_fichier}"'
        return response


class SeanceFormationPDFZipExportView(PlanningReadAccessMixin, View):
    """Exporte un PDF emploi du temps par groupe, regroupés dans une archive ZIP."""

    def get(self, request, formation_pk: int):
        """Retourne une archive ZIP (un PDF par groupe)."""
        formation = get_formation_pour_utilisateur(request.user, formation_pk)
        contenu = ExportPlanningPDFService(SeanceRepository()).exporter_formation_zip(formation_pk)
        _log_planning_action(
            request,
            PlanningAuditLog.Action.EXPORT,
            details={
                "format_export": "pdf",
                "scope": "formation_zip",
                "formation_id": formation.pk,
            },
        )
        from shared.utils.groupes import nom_fichier_emploi_du_temps_formation

        nom_fichier = nom_fichier_emploi_du_temps_formation(formation, extension="zip")
        response = HttpResponse(contenu, content_type="application/zip")
        response["Content-Disposition"] = f'attachment; filename="{nom_fichier}"'
        return response


class SeanceFormationZipExportView(PlanningReadAccessMixin, View):
    """Exporte un fichier Excel par groupe, regroupés dans une archive ZIP."""

    def get(self, request, formation_pk: int):
        """Retourne une archive ZIP (un XLSX par groupe)."""
        formation = get_formation_pour_utilisateur(request.user, formation_pk)
        format_export = (request.GET.get("format") or "cours").strip().lower()
        if format_export == "complet":
            format_export = "cours"
        if format_export not in {"cours", "seances", "formateurs"}:
            format_export = "cours"
        contenu = ExportSeancesService(SeanceRepository()).exporter_formation_zip(
            formation_pk,
            format_export=format_export,
        )
        _log_planning_action(
            request,
            PlanningAuditLog.Action.EXPORT,
            details={
                "format_export": format_export,
                "scope": "formation_zip",
                "formation_id": formation.pk,
            },
        )
        from shared.utils.groupes import nom_fichier_emploi_du_temps_formation

        variante = format_export if format_export in {"seances", "formateurs"} else ""
        nom_fichier = nom_fichier_emploi_du_temps_formation(formation, extension="zip")
        if variante:
            base = nom_fichier.rsplit(".", 1)[0]
            nom_fichier = f"{base}_{variante}.zip"
        response = HttpResponse(contenu, content_type="application/zip")
        response["Content-Disposition"] = f'attachment; filename="{nom_fichier}"'
        return response


class SeanceCreateView(PlanningWriteAccessMixin, View):
    """Ajoute une séance manuellement."""

    def post(self, request, groupe_pk: int):
        groupe = get_groupe_pour_utilisateur(
            request.user, groupe_pk, queryset=queryset_groupes(request.user).select_related("formation")
        )
        form = SeanceForm(request.POST, formation=groupe.formation)
        if form.is_valid():
            seance = form.save(commit=False)
            seance.groupe = groupe
            dt_debut = datetime.datetime.combine(seance.date, seance.heure_debut)
            dt_fin = datetime.datetime.combine(seance.date, seance.heure_fin)
            seance.duree_minutes = int((dt_fin - dt_debut).total_seconds() // 60)
            seance.save()
            _log_planning_action(
                request,
                PlanningAuditLog.Action.CREATE,
                groupe=groupe,
                seance=seance,
                details={
                    "date": seance.date.isoformat(),
                    "heure_debut": seance.heure_debut.isoformat(),
                    "heure_fin": seance.heure_fin.isoformat(),
                    "salle_nom": seance.salle_nom,
                    "formateur_nom": seance.formateur_nom,
                    "formateur_prenom": seance.formateur_prenom,
                    "formateur_numero": seance.formateur_numero,
                    "formateur_email": seance.formateur_email,
                    "formateur_telephone": seance.formateur_telephone,
                    "formateur_organisation": seance.formateur_organisation,
                },
            )
            messages.success(request, "Séance ajoutée.")
        else:
            messages.error(request, f"Erreur création séance: {form.errors}")
        return redirect("seances:preview", groupe_pk=groupe_pk)


class SeanceUpdateView(PlanningWriteAccessMixin, View):
    """Modifie une séance existante."""

    def post(self, request, pk: int):
        formation_ids = queryset_formations(request.user).values("pk")
        seance = get_object_or_404(
            Seance.objects.select_related("groupe__formation").filter(groupe__formation_id__in=formation_ids),
            pk=pk,
        )
        avant = {
            "date": seance.date.isoformat(),
            "heure_debut": seance.heure_debut.isoformat(),
            "heure_fin": seance.heure_fin.isoformat(),
            "salle_nom": seance.salle_nom,
            "formateur_nom": seance.formateur_nom,
            "formateur_prenom": seance.formateur_prenom,
            "formateur_numero": seance.formateur_numero,
            "formateur_email": seance.formateur_email,
            "formateur_telephone": seance.formateur_telephone,
            "formateur_organisation": seance.formateur_organisation,
            "module_id": seance.module_id,
        }
        form = SeanceForm(request.POST, instance=seance, formation=seance.groupe.formation)
        if form.is_valid():
            seance = form.save(commit=False)
            dt_debut = datetime.datetime.combine(seance.date, seance.heure_debut)
            dt_fin = datetime.datetime.combine(seance.date, seance.heure_fin)
            seance.duree_minutes = int((dt_fin - dt_debut).total_seconds() // 60)
            seance.save()
            _log_planning_action(
                request,
                PlanningAuditLog.Action.UPDATE,
                groupe=seance.groupe,
                seance=seance,
                details={
                    "avant": avant,
                    "apres": {
                        "date": seance.date.isoformat(),
                        "heure_debut": seance.heure_debut.isoformat(),
                        "heure_fin": seance.heure_fin.isoformat(),
                        "salle_nom": seance.salle_nom,
                        "formateur_nom": seance.formateur_nom,
                        "formateur_prenom": seance.formateur_prenom,
                        "formateur_numero": seance.formateur_numero,
                        "formateur_email": seance.formateur_email,
                        "formateur_telephone": seance.formateur_telephone,
                        "formateur_organisation": seance.formateur_organisation,
                        "module_id": seance.module_id,
                    },
                },
            )
            messages.success(request, "Séance mise à jour.")
        else:
            messages.error(request, f"Erreur modification séance: {form.errors}")
        return redirect("seances:preview", groupe_pk=seance.groupe_id)


class SeanceFormationModuleSyntheseDocxView(PlanningReadAccessMixin, View):
    """
    Exporte la synthèse UP (Unité Pédagogique) d'une formation pour un module donné,
    au format DOCX institutionnel (modèle SYNTHESE UP ... FAB SESSION ...).
    Une page par groupe ayant des séances pour ce module.

    URL : /seances/formation/<formation_pk>/module/<module_pk>/synthese-docx/
    """

    def get(self, request, formation_pk: int, module_pk: int):
        from apps.referentiels.models import Module

        formation = get_formation_pour_utilisateur(request.user, formation_pk)
        module = get_object_or_404(Module, pk=module_pk)
        if not utilisateur_voit_formation_entierement(request.user, formation):
            if not utilisateur_peut_gerer_module_up(request.user, module_pk):
                from django.core.exceptions import PermissionDenied

                raise PermissionDenied

        contenu = SyntheseUPDocxService(SeanceRepository()).exporter(
            formation_id=formation_pk,
            module_id=module_pk,
        )
        _log_planning_action(
            request,
            PlanningAuditLog.Action.EXPORT,
            details={
                "format_export": "docx_synthese_up",
                "scope": "formation_module",
                "formation_id": formation.pk,
                "module_id": module.pk,
            },
        )
        module_slug = module.titre.replace(" ", "_").replace("/", "-")[:40]
        annee = formation.date_debut.year if formation.date_debut else "SESSION"
        nom_fichier = f"SYNTHESE_UP_{module_slug}_FAB_{annee}.docx"
        response = HttpResponse(
            contenu,
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        response["Content-Disposition"] = f'attachment; filename="{nom_fichier}"'
        return response


class SeanceGroupeModuleSyntheseDocxView(PlanningReadAccessMixin, View):
    """
    Exporte la synthèse UP pour UN seul groupe et UN module donné.
    Un seul groupe = une seule page.

    URL : /seances/groupe/<groupe_pk>/module/<module_pk>/synthese-docx/
    """

    def get(self, request, groupe_pk: int, module_pk: int):
        from apps.referentiels.models import Module

        groupe = get_groupe_pour_utilisateur(
            request.user, groupe_pk, queryset=queryset_groupes(request.user).select_related("formation")
        )
        module = get_object_or_404(Module, pk=module_pk)
        if not utilisateur_voit_formation_entierement(request.user, groupe.formation):
            if not utilisateur_peut_gerer_module_up(request.user, module_pk):
                from django.core.exceptions import PermissionDenied

                raise PermissionDenied

        contenu = SyntheseUPDocxService(SeanceRepository()).exporter(
            formation_id=groupe.formation_id,
            module_id=module_pk,
            groupe_id=groupe_pk,
        )
        _log_planning_action(
            request,
            PlanningAuditLog.Action.EXPORT,
            groupe=groupe,
            details={
                "format_export": "docx_synthese_up",
                "scope": "groupe_module",
                "formation_id": groupe.formation_id,
                "module_id": module.pk,
                "groupe_id": groupe.pk,
            },
        )
        module_slug = module.titre.replace(" ", "_").replace("/", "-")[:40]
        groupe_slug = groupe.nom.replace(" ", "_").replace("/", "-")[:30]
        annee = groupe.formation.date_debut.year if groupe.formation and groupe.formation.date_debut else "SESSION"
        nom_fichier = f"SYNTHESE_UP_{module_slug}_{groupe_slug}_FAB_{annee}.docx"
        response = HttpResponse(
            contenu,
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        response["Content-Disposition"] = f'attachment; filename="{nom_fichier}"'
        return response


class SeanceDeleteView(PlanningWriteAccessMixin, View):
    """Supprime une séance."""

    def post(self, request, pk: int):
        formation_ids = queryset_formations(request.user).values("pk")
        seance = get_object_or_404(Seance.objects.filter(groupe__formation_id__in=formation_ids), pk=pk)
        groupe_pk = seance.groupe_id
        details = {
            "seance_id": seance.pk,
            "date": seance.date.isoformat(),
            "heure_debut": seance.heure_debut.isoformat(),
            "heure_fin": seance.heure_fin.isoformat(),
            "module_id": seance.module_id,
            "salle_nom": seance.salle_nom,
            "formateur_nom": seance.formateur_nom,
            "formateur_prenom": seance.formateur_prenom,
            "formateur_numero": seance.formateur_numero,
            "formateur_email": seance.formateur_email,
            "formateur_telephone": seance.formateur_telephone,
            "formateur_organisation": seance.formateur_organisation,
        }
        groupe = seance.groupe
        seance.delete()
        _log_planning_action(
            request,
            PlanningAuditLog.Action.DELETE,
            groupe=groupe,
            details=details,
        )
        messages.success(request, "Séance supprimée.")
        return redirect("seances:preview", groupe_pk=groupe_pk)
