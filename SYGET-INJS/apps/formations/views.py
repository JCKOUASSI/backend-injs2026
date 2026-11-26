"""
Vues de l'app formations.
"""

from __future__ import annotations

import logging

from django.contrib import messages
from django.db import DatabaseError
from django.http import Http404, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View

from shared.formations_scope import (
    filtrer_seances_selon_perimetre,
    formateur_eligible_pour_module,
    get_formation_pour_utilisateur,
    get_groupe_pour_utilisateur,
    module_rup_id_pour_utilisateur,
    modules_up_formation_pour_utilisateur,
    queryset_formations,
    queryset_formateurs_pour_utilisateur,
    queryset_groupes,
    utilisateur_est_rup,
    utilisateur_peut_gerer_module_up,
    utilisateur_voit_formation_entierement,
    utilisateur_voit_toutes_les_formations,
)
from shared.permissions import RoleProtectedMixin

from .forms import (
    FormationForm,
    FormationModuleForm,
    FormationPeriodeForm,
    ImportFormateursForm,
)
from .models import AffectationFormateurGroupe, Formateur, Formation, FormationModule, FormationPeriode
from .repositories import FormationModuleRepository, FormationRepository, InscriptionRepository
from .services import FormationService, InscriptionService, exporter_auditeurs_formation_xlsx
from .view_context import build_formation_detail_context, location_json_context

logger = logging.getLogger(__name__)


def _utilisateur_peut_affecter_formateur(user) -> bool:
    return user.has_perm("formations.change_affectationformateurgroupe") or user.has_perm(
        "formations.add_affectationformateurgroupe"
    )


def _appliquer_formateur_aux_seances(groupe_id: int, module_id: int, formateur=None) -> int:
    """Met à jour les séances existantes après changement d'affectation formateur."""
    from apps.seances.models import Seance
    from apps.seances.planning.trainer_allocator import dict_formateur_depuis_instance, dict_formateur_vide

    if formateur is None:
        data = dict_formateur_vide()
        ref_id = None
    else:
        data = dict_formateur_depuis_instance(formateur)
        ref_id = formateur.pk

    update_kw = {
        "formateur_nom": data["nom"],
        "formateur_prenom": data["prenom"],
        "formateur_numero": data["numero"],
        "formateur_email": data["email"],
        "formateur_telephone": data["telephone"],
        "formateur_organisation": data["organisation"],
        "formateur_referentiel_id": ref_id,
    }
    return Seance.objects.filter(groupe_id=groupe_id, module_id=module_id).update(**update_kw)


def _redirect_apres_affectation_rup(request, formation_pk: int):
    if (request.POST.get("next") or "").strip() == "groupes":
        return redirect("groupes:list", formation_pk=formation_pk)
    return redirect("formations:rup_unite", pk=formation_pk)


def _executer_import_formateurs(request, fichier) -> HttpResponseRedirect:
    """Exécute l'import référentiel global, messages + redirection liste formateurs."""
    redirect_url = reverse("formations:formateurs_list")
    report = FormationService(FormationRepository(), FormationModuleRepository()).importer_formateurs_depuis_excel(
        fichier=fichier,
    )

    if report.erreurs:
        for err in report.erreurs[:20]:
            messages.warning(request, err)
    messages.success(
        request,
        f"Import formateurs terminé: {report.nb_lignes} ligne(s) lue(s), "
        f"{report.nb_formateurs_importes} formateur(s) importé(s), "
        f"{report.nb_formateurs_mis_a_jour} mis à jour, {report.nb_erreurs} erreur(s).",
    )
    return redirect(redirect_url)


class FormationListView(RoleProtectedMixin, View):
    """Affiche la liste de toutes les formations."""

    permission_required = "formations.view_formation"
    template_name = "formations/list.html"

    def get(self, request):
        """Retourne la liste des formations."""
        formations = FormationRepository().list_for_user(request.user)
        return render(
            request,
            self.template_name,
            {
                "formations": formations,
                "create_form": FormationForm(),
                "est_rup": utilisateur_est_rup(request.user),
            },
        )


class FormateursListView(RoleProtectedMixin, View):
    """Liste du référentiel global des formateurs."""

    permission_required = "formations.view_formateur"
    template_name = "formations/formateurs_list.html"

    def get(self, request):
        formateurs = list(queryset_formateurs_pour_utilisateur(request.user))
        return render(
            request,
            self.template_name,
            {
                "formateurs": formateurs,
                "filtre_specialite_rup": utilisateur_est_rup(request.user)
                and not utilisateur_voit_toutes_les_formations(request.user),
            },
        )


class FormateursImportPageView(RoleProtectedMixin, View):
    """Page dédiée d’import Excel du référentiel formateurs (fichier seul, sans formation ni module)."""

    permission_required = "formations.add_formateur"
    template_name = "formations/formateurs_import.html"

    def get(self, request):
        form = ImportFormateursForm()
        return render(request, self.template_name, {"form": form})

    def post(self, request):
        form = ImportFormateursForm(request.POST, request.FILES)
        if form.is_valid():
            return _executer_import_formateurs(request, form.cleaned_data["fichier"])
        return render(request, self.template_name, {"form": form})


class FormationCreateView(RoleProtectedMixin, View):
    """Crée une nouvelle formation."""

    permission_required = "formations.add_formation"
    template_name = "formations/create.html"

    def get(self, request):
        """Affiche le formulaire de création."""
        return render(request, self.template_name, {"form": FormationForm()})

    def post(self, request):
        """Traite la soumission du formulaire de création."""
        form = FormationForm(request.POST)
        if form.is_valid():
            try:
                service = FormationService(FormationRepository(), FormationModuleRepository())
                formation = service.creer(
                    type_formation_id=form.cleaned_data["type_formation"].pk,
                    intitule=form.cleaned_data["intitule"],
                    vague=form.cleaned_data.get("vague", ""),
                    date_debut=form.cleaned_data["date_debut"],
                    date_fin=form.cleaned_data["date_fin"],
                    rythme_mensuel=form.cleaned_data.get("rythme_mensuel"),
                    responsable=request.user,
                )
                messages.success(request, "Formation créée avec succès.")
                return redirect("formations:detail", pk=formation.pk)
            except ValueError as e:
                messages.error(request, str(e))
        return render(request, self.template_name, {"form": form})


class FormationUpdateView(RoleProtectedMixin, View):
    """Modifie les informations générales d'une formation."""

    permission_required = "formations.change_formation"
    template_name = "formations/edit.html"

    def get(self, request, pk: int):
        formation = get_formation_pour_utilisateur(request.user, pk)
        return render(request, self.template_name, {"formation": formation, "form": FormationForm(instance=formation)})

    def post(self, request, pk: int):
        formation = get_formation_pour_utilisateur(request.user, pk)
        form = FormationForm(request.POST, instance=formation)
        if form.is_valid():
            try:
                FormationService(FormationRepository(), FormationModuleRepository()).modifier(
                    formation_id=pk,
                    type_formation_id=form.cleaned_data["type_formation"].pk,
                    intitule=form.cleaned_data["intitule"],
                    vague=form.cleaned_data.get("vague", "") or "",
                    date_debut=form.cleaned_data["date_debut"],
                    date_fin=form.cleaned_data["date_fin"],
                    rythme_mensuel=form.cleaned_data.get("rythme_mensuel"),
                )
                messages.success(request, "Formation mise à jour.")
                return redirect("formations:detail", pk=pk)
            except ValueError as e:
                messages.error(request, str(e))
        return render(request, self.template_name, {"formation": formation, "form": form})


class FormationDeleteView(RoleProtectedMixin, View):
    """Supprime une formation."""

    permission_required = "formations.delete_formation"

    def post(self, request, pk: int):
        get_formation_pour_utilisateur(request.user, pk)
        try:
            FormationService(FormationRepository(), FormationModuleRepository()).supprimer(pk)
            messages.success(request, "Formation supprimée.")
        except ValueError as e:
            messages.error(request, str(e))
            return redirect("formations:detail", pk=pk)
        return redirect("formations:list")


class FormationAuditeursExportView(RoleProtectedMixin, View):
    """Export Excel : auditeurs affectés aux groupes de la formation (après génération / affectation)."""

    permission_required = "formations.view_formation"

    def get(self, request, pk: int):
        from apps.groupes.models import Groupe

        formation = get_formation_pour_utilisateur(request.user, pk)
        if not Groupe.objects.filter(formation_id=pk).exists():
            return HttpResponse(
                "Créez d'abord les groupes (par ex. « Régénérer auto » sur la page Groupes) "
                "avant d'exporter la liste des auditeurs.",
                status=400,
                content_type="text/plain; charset=utf-8",
            )
        try:
            contenu = exporter_auditeurs_formation_xlsx(pk)
        except ValueError:
            raise Http404()
        base = "".join(c if c.isalnum() else "_" for c in formation.intitule).strip("_")[:60] or "formation"
        fname = f"auditeurs_{base}_{pk}.xlsx"
        response = HttpResponse(
            contenu,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="{fname}"'
        return response


class FormationDetailView(RoleProtectedMixin, View):
    """Affiche le détail d'une formation."""

    permission_required = "formations.view_formation"
    template_name = "formations/detail.html"

    def get(self, request, pk: int):
        """Retourne le détail d'une formation."""
        formation = get_formation_pour_utilisateur(
            request.user,
            pk,
            queryset=queryset_formations(request.user).prefetch_related(
                "periodes",
                "modules__module",
                "modules__periode",
                "groupes",
            ),
        )
        module_form = FormationModuleForm(formation=formation)
        periode_form = FormationPeriodeForm(formation=formation)
        context = build_formation_detail_context(formation, module_form, periode_form=periode_form)
        context["est_rup"] = utilisateur_est_rup(request.user)
        context["perimetre_partiel"] = not utilisateur_voit_formation_entierement(request.user, formation)
        context["modules_up_rup"] = list(modules_up_formation_pour_utilisateur(request.user, pk))
        return render(
            request,
            self.template_name,
            context,
        )


class FormationModuleAddView(RoleProtectedMixin, View):
    """Ajoute un module à une formation."""

    permission_required = "formations.add_formationmodule"

    def post(self, request, pk: int):
        """Traite l'ajout d'un module."""
        formation = get_formation_pour_utilisateur(
            request.user,
            pk,
            queryset=queryset_formations(request.user).prefetch_related(
                "periodes",
                "modules__module",
                "modules__periode",
                "groupes",
            ),
        )
        form = FormationModuleForm(request.POST, formation=formation)
        if form.is_valid():
            try:
                service = FormationService(FormationRepository(), FormationModuleRepository())
                common = {
                    "grade_cible": form.cleaned_data["grade_cible"],
                    "creneau_mode": form.cleaned_data["creneau_mode"],
                    "periode_id": form.cleaned_data["periode"].pk,
                    "site_noms": [s.nom for s in form.cleaned_data["sites"]],
                    "batiment_noms": [b.nom for b in form.cleaned_data["batiments"]],
                    "salle_noms": [s.nom for s in form.cleaned_data["salles"]],
                }
                for module in form.cleaned_data["modules"]:
                    service.ajouter_module(
                        formation_id=pk,
                        module_id=module.pk,
                        **common,
                    )
                nb = len(form.cleaned_data["modules"])
                messages.success(
                    request,
                    f"{nb} module{'s' if nb > 1 else ''} ajouté{'s' if nb > 1 else ''}.",
                )
                return redirect("formations:detail", pk=pk)
            except ValueError as e:
                form.add_error(None, str(e))
            except DatabaseError:
                logger.exception("Erreur DB lors de l'ajout de module (formation_id=%s).", pk)
                form.add_error(
                    None,
                    "Une erreur technique est survenue pendant l'ajout du module. "
                    "Vérifiez les migrations du serveur puis réessayez.",
                )
        else:
            messages.error(request, "Merci de corriger les champs du formulaire.")

        detail_view = FormationDetailView()
        return render(
            request,
            detail_view.template_name,
            build_formation_detail_context(
                formation,
                form,
                periode_form=FormationPeriodeForm(formation=formation),
            ),
        )


class FormationPeriodeAddView(RoleProtectedMixin, View):
    """Ajoute une période pédagogique à une formation."""

    permission_required = "formations.change_formation"

    def post(self, request, pk: int):
        formation = get_formation_pour_utilisateur(request.user, pk)
        form = FormationPeriodeForm(request.POST, formation=formation)
        if form.is_valid():
            try:
                FormationService(FormationRepository(), FormationModuleRepository()).ajouter_periode(
                    formation_id=pk,
                    libelle=form.cleaned_data["libelle"],
                    date_debut=form.cleaned_data["date_debut"],
                    date_fin=form.cleaned_data["date_fin"],
                    rythme_mensuel=form.cleaned_data["rythme_mensuel"],
                )
                messages.success(request, "Période ajoutée.")
            except ValueError as e:
                messages.error(request, str(e))
        else:
            messages.error(request, "Merci de corriger le formulaire de période.")
        return redirect("formations:detail", pk=pk)


class FormationPeriodeUpdateView(RoleProtectedMixin, View):
    """Modifie une période pédagogique."""

    permission_required = "formations.change_formation"

    def post(self, request, pk: int, periode_pk: int):
        formation = get_formation_pour_utilisateur(request.user, pk)
        periode = get_object_or_404(FormationPeriode, pk=periode_pk, formation_id=pk)
        form = FormationPeriodeForm(request.POST, instance=periode, formation=formation)
        if form.is_valid():
            try:
                FormationService(FormationRepository(), FormationModuleRepository()).modifier_periode(
                    periode_id=periode.pk,
                    formation_id=pk,
                    libelle=form.cleaned_data["libelle"],
                    date_debut=form.cleaned_data["date_debut"],
                    date_fin=form.cleaned_data["date_fin"],
                    rythme_mensuel=form.cleaned_data["rythme_mensuel"],
                )
                messages.success(request, "Période mise à jour.")
            except ValueError as e:
                messages.error(request, str(e))
        else:
            messages.error(request, "Merci de corriger le formulaire de période.")
        return redirect("formations:detail", pk=pk)


class FormationPeriodeDeleteView(RoleProtectedMixin, View):
    """Supprime une période vide."""

    permission_required = "formations.change_formation"

    def post(self, request, pk: int, periode_pk: int):
        get_formation_pour_utilisateur(request.user, pk)
        try:
            FormationService(FormationRepository(), FormationModuleRepository()).supprimer_periode(pk, periode_pk)
            messages.success(request, "Période supprimée.")
        except ValueError as e:
            messages.error(request, str(e))
        return redirect("formations:detail", pk=pk)


class FormationModuleUpdateView(RoleProtectedMixin, View):
    """Modifie un module déjà rattaché à la formation."""

    permission_required = "formations.change_formationmodule"
    template_name = "formations/module_edit.html"

    @staticmethod
    def _initial_from_module(formation_module):
        from apps.parametrage.models import Batiment, Salle, Site
        from shared.utils.grades import split_grade_cibles

        site_noms = [n.strip() for n in (formation_module.site_nom or "").split(",") if n.strip()]
        bat_noms = [n.strip() for n in (formation_module.batiment_nom or "").split(",") if n.strip()]
        salle_noms = [n.strip() for n in (formation_module.salle_nom or "").split(",") if n.strip()]
        grade_values = split_grade_cibles(formation_module.grade_cible)
        if not grade_values:
            grade_values = ["__ALL__"]

        return {
            "module": formation_module.module_id,
            "periode": formation_module.periode_id,
            "grade_cible": grade_values,
            "creneau_mode": formation_module.creneau_mode,
            "sites": list(Site.objects.filter(nom__in=site_noms).values_list("pk", flat=True)),
            "batiments": list(Batiment.objects.filter(nom__in=bat_noms).values_list("pk", flat=True)),
            "salles": list(Salle.objects.filter(nom__in=salle_noms).values_list("pk", flat=True)),
        }

    def get(self, request, pk: int, module_pk: int):
        formation = get_formation_pour_utilisateur(request.user, pk)
        formation_module = get_object_or_404(
            FormationModule.objects.select_related("formation", "module", "periode"),
            pk=module_pk,
            formation_id=pk,
        )
        form = FormationModuleForm(
            formation=formation,
            initial=self._initial_from_module(formation_module),
        )
        ctx = {
            "formation": formation,
            "formation_module": formation_module,
            "form": form,
            **location_json_context(),
        }
        return render(request, self.template_name, ctx)

    def post(self, request, pk: int, module_pk: int):
        formation = get_formation_pour_utilisateur(request.user, pk)
        formation_module = get_object_or_404(
            FormationModule.objects.select_related("formation", "module", "periode"),
            pk=module_pk,
            formation_id=pk,
        )
        form = FormationModuleForm(request.POST, formation=formation)
        if form.is_valid():
            try:
                FormationService(FormationRepository(), FormationModuleRepository()).modifier_module(
                    formation_module_id=formation_module.pk,
                    module_id=form.cleaned_data["module"].pk,
                    grade_cible=form.cleaned_data["grade_cible"],
                    creneau_mode=form.cleaned_data["creneau_mode"],
                    periode_id=form.cleaned_data["periode"].pk,
                    site_noms=[s.nom for s in form.cleaned_data["sites"]],
                    batiment_noms=[b.nom for b in form.cleaned_data["batiments"]],
                    salle_noms=[s.nom for s in form.cleaned_data["salles"]],
                )
                messages.success(request, "Module mis à jour.")
                return redirect("formations:detail", pk=pk)
            except ValueError as e:
                form.add_error(None, str(e))
            except DatabaseError:
                logger.exception(
                    "Erreur DB lors de la mise à jour de module (formation_id=%s, module_pk=%s).",
                    pk,
                    module_pk,
                )
                form.add_error(
                    None,
                    "Une erreur technique est survenue pendant la mise à jour du module. "
                    "Vérifiez les migrations du serveur puis réessayez.",
                )
        else:
            messages.error(request, "Merci de corriger les champs du formulaire.")
        ctx = {
            "formation": formation,
            "formation_module": formation_module,
            "form": form,
            **location_json_context(),
        }
        return render(request, self.template_name, ctx)


class FormationModuleDeleteView(RoleProtectedMixin, View):
    """Supprime un module d'une formation."""

    permission_required = "formations.delete_formationmodule"

    def post(self, request, pk: int, module_pk: int):
        """Supprime le module identifié par module_pk de la formation pk."""
        get_formation_pour_utilisateur(request.user, pk)
        FormationService(FormationRepository(), FormationModuleRepository()).supprimer_module(module_pk)
        messages.success(request, "Module supprimé.")
        return redirect("formations:detail", pk=pk)


class InscriptionAddView(RoleProtectedMixin, View):
    """Inscrit un ou plusieurs auditeurs à un module de formation."""

    permission_required = "formations.add_inscription"

    def post(self, request, pk: int):
        """Traite l'inscription d'un ou plusieurs auditeurs sur un module."""
        get_formation_pour_utilisateur(request.user, pk)
        auditeur_ids = request.POST.getlist("auditeur_ids")
        module_id = int(request.POST.get("module_id", "0") or 0)
        formation_module = get_object_or_404(
            FormationModule.objects.select_related("formation"),
            pk=module_id,
            formation_id=pk,
        )
        service = InscriptionService(InscriptionRepository(), FormationRepository())
        nb_ok = 0
        for aid in auditeur_ids:
            try:
                service.inscrire(formation_module_id=formation_module.pk, auditeur_id=int(aid))
                nb_ok += 1
            except ValueError as e:
                messages.warning(request, str(e))
        if nb_ok:
            messages.success(request, f"{nb_ok} auditeur(s) inscrit(s).")
        target = reverse("formations:detail", kwargs={"pk": pk})
        return redirect(target)


class InscriptionDeleteView(RoleProtectedMixin, View):
    """Désinscrit un auditeur d'un module."""

    permission_required = "formations.delete_inscription"

    def post(self, request, pk: int, auditeur_pk: int):
        """Supprime l'inscription d'un auditeur pour le module sélectionné."""
        get_formation_pour_utilisateur(request.user, pk)
        module_id = int(request.POST.get("module_id", "0") or 0)
        formation_module = get_object_or_404(
            FormationModule.objects.select_related("formation"),
            pk=module_id,
            formation_id=pk,
        )
        InscriptionService(InscriptionRepository(), FormationRepository()).desinscrire(
            formation_module_id=formation_module.pk,
            auditeur_id=auditeur_pk,
        )
        messages.success(request, "Auditeur désinscrit.")
        target = reverse("formations:detail", kwargs={"pk": pk})
        return redirect(target)


class InscriptionCopierView(RoleProtectedMixin, View):
    """
    Permet de copier les auditeurs d'une formation source vers la formation cible.
    Chaque auditeur sélectionné est inscrit à tous les modules de la formation cible.
    """

    permission_required = "formations.add_inscription"
    template_name = "formations/inscription_copier.html"

    def _get_formation(self, request, pk: int):
        return get_formation_pour_utilisateur(
            request.user,
            pk,
            queryset=queryset_formations(request.user),
        )

    def get(self, request, pk: int):
        import types

        from apps.auditeurs.models import Auditeur

        formation = self._get_formation(request, pk)
        toutes_formations = list(queryset_formations(request.user).exclude(pk=pk).order_by("-date_debut", "intitule"))

        source_formation = None
        auditeurs_source: list = []
        deja_inscrits_ids: set[int] = set()

        raw = request.GET.get("source_formation", "").strip()
        if raw:
            try:
                source_id = int(raw)
                source_formation = get_formation_pour_utilisateur(request.user, source_id)
            except (ValueError, TypeError, Formation.DoesNotExist):
                source_formation = None

        groupe_source_par_auditeur: dict[int, str] = {}
        if source_formation:
            from apps.formations.models import Inscription as Ins
            from shared.services.pool_inscriptions import (
                groupe_source_par_auditeur as _groupe_source_par_auditeur,
                ids_auditeurs_formation_source,
            )

            groupe_source_par_auditeur = _groupe_source_par_auditeur(source_formation.pk)
            ids_source = ids_auditeurs_formation_source(source_formation.pk)
            deja_inscrits_ids = set(
                Ins.objects.filter(formation_id=pk).values_list("auditeur_id", flat=True).distinct()
            )
            for aud in Auditeur.objects.filter(pk__in=ids_source).order_by("nom", "prenom"):
                auditeurs_source.append(
                    types.SimpleNamespace(
                        auditeur=aud,
                        pk=aud.pk,
                        nom=aud.nom,
                        prenom=aud.prenom,
                        matricule=aud.matricule,
                        grade=aud.grade,
                        categorie=aud.categorie,
                        groupe_source=groupe_source_par_auditeur.get(aud.pk, ""),
                    )
                )

        return render(
            request,
            self.template_name,
            {
                "formation": formation,
                "toutes_formations": toutes_formations,
                "source_formation": source_formation,
                "auditeurs_source": auditeurs_source,
                "deja_inscrits_ids": deja_inscrits_ids,
            },
        )

    def post(self, request, pk: int):
        from django.db import transaction

        from apps.formations.models import Inscription as Ins

        self._get_formation(request, pk)
        auditeur_ids_raw = request.POST.getlist("auditeur_ids")
        auditeur_ids = []
        for aid in auditeur_ids_raw:
            try:
                auditeur_ids.append(int(aid))
            except (ValueError, TypeError):
                pass

        if not auditeur_ids:
            messages.warning(request, "Aucun auditeur sélectionné.")
            return redirect(reverse("formations:inscription_copier", kwargs={"pk": pk}))

        modules_cible = list(FormationModule.objects.filter(formation_id=pk).values_list("pk", flat=True))
        if not modules_cible:
            messages.warning(
                request,
                "Cette formation n'a pas encore de modules. Ajoutez des modules avant d'inscrire des auditeurs.",
            )
            return redirect(reverse("formations:detail", kwargs={"pk": pk}))

        # Inscriptions existantes pour ne pas créer de doublons
        existantes: set[tuple[int, int]] = set(
            Ins.objects.filter(formation_id=pk, auditeur_id__in=auditeur_ids).values_list(
                "formation_module_id", "auditeur_id"
            )
        )

        a_creer = [
            Ins(formation_id=pk, formation_module_id=fm_id, auditeur_id=aud_id)
            for aud_id in auditeur_ids
            for fm_id in modules_cible
            if (fm_id, aud_id) not in existantes
        ]

        source_formation_id = None
        raw_source = request.POST.get("source_formation", "").strip()
        if raw_source:
            try:
                source_formation_id = int(raw_source)
            except (ValueError, TypeError):
                source_formation_id = None

        with transaction.atomic():
            Ins.objects.bulk_create(a_creer, ignore_conflicts=True)

        nb_inscrits = len({ins.auditeur_id for ins in a_creer})
        messages.success(
            request,
            f"{nb_inscrits} auditeur(s) inscrit(s) à {len(modules_cible)} module(s) de la formation.",
        )

        if source_formation_id and source_formation_id != pk:
            from apps.groupes.repositories import (
                ConfigGroupeRepository,
                GroupeRepository,
                JourCoursRepository,
            )
            from apps.groupes.services import GroupeService

            stats = GroupeService(
                GroupeRepository(),
                ConfigGroupeRepository(),
                JourCoursRepository(),
            ).reporter_membres_depuis_formation_source(pk, source_formation_id, auditeur_ids=auditeur_ids)
            if stats.get("groupes_crees"):
                messages.success(
                    request,
                    f"{stats['groupes_crees']} groupe(s) créé(s) sur cette formation "
                    f"(mêmes noms que dans la formation source).",
                )
            if stats["ajoutes"]:
                messages.success(
                    request,
                    f"{stats['ajoutes']} auditeur(s) affecté(s) à leur groupe homologue "
                    f"(même nom que dans la formation source).",
                )
            if stats["ignores"]:
                messages.warning(
                    request,
                    f"{stats['ignores']} affectation(s) de groupe ignorée(s) "
                    "(groupe homologue absent sur cette formation ou auditeur déjà affecté).",
                )

        return redirect(reverse("formations:detail", kwargs={"pk": pk}))


class FormationRupView(RoleProtectedMixin, View):
    """Espace RUP : affectation formateurs par groupe pour ses unités pédagogiques."""

    permission_required = "formations.view_affectationformateurgroupe"
    template_name = "formations/rup_unite.html"

    def get(self, request, pk: int):
        from apps.seances.models import Seance

        formation = get_formation_pour_utilisateur(request.user, pk)
        modules_up = list(modules_up_formation_pour_utilisateur(request.user, pk))
        if utilisateur_est_rup(request.user) and not modules_up:
            messages.warning(
                request,
                "Votre module ne figure pas dans le programme de cette formation.",
            )
            return redirect("formations:list")

        module_rup = None
        mid = module_rup_id_pour_utilisateur(request.user)
        if mid:
            from apps.referentiels.models import Module

            module_rup = Module.objects.filter(pk=mid).select_related("specialite").first()

        groupes = list(
            queryset_groupes(request.user)
            .filter(formation_id=pk)
            .prefetch_related("affectations_formateurs__formateur")
            .order_by("nom", "pk")
        )
        module_ids = [fm.module_id for fm in modules_up]
        affectations = {
            (a.groupe_id, a.module_id): a
            for a in AffectationFormateurGroupe.objects.filter(
                groupe__formation_id=pk,
                module_id__in=module_ids,
            ).select_related("formateur")
        }
        formateurs_qs = queryset_formateurs_pour_utilisateur(request.user)
        assigned_ids = {a.formateur_id for a in affectations.values() if a.formateur_id}
        if assigned_ids:
            formateurs_qs = (
                (
                    Formateur.objects.filter(pk__in=formateurs_qs.values("pk"))
                    | Formateur.objects.filter(pk__in=assigned_ids)
                )
                .distinct()
                .order_by("nom", "prenom")
            )
        formateurs = list(formateurs_qs.prefetch_related("specialites"))
        seances_qs = (
            Seance.objects.filter(groupe__formation_id=pk, module_id__in=module_ids)
            .select_related("groupe", "module")
            .order_by("module_id", "groupe__nom", "date", "heure_debut")
        )
        seances_filtrees = filtrer_seances_selon_perimetre(request.user, formation, seances_qs)
        seances_par_module: dict[int, list] = {}
        for seance in seances_filtrees:
            seances_par_module.setdefault(seance.module_id, []).append(seance)

        sections = []
        for fm in modules_up:
            rows = [{"groupe": g, "affectation": affectations.get((g.pk, fm.module_id))} for g in groupes]
            sections.append(
                {
                    "formation_module": fm,
                    "rows": rows,
                    "seances": seances_par_module.get(fm.module_id, []),
                }
            )

        return render(
            request,
            self.template_name,
            {
                "formation": formation,
                "sections": sections,
                "formateurs": formateurs,
                "est_rup": utilisateur_est_rup(request.user),
                "perimetre_partiel": not utilisateur_voit_formation_entierement(request.user, formation),
                "module_rup": module_rup,
                "peut_affecter_formateur": _utilisateur_peut_affecter_formateur(request.user),
            },
        )


class RupAffectationFormateurView(RoleProtectedMixin, View):
    """Enregistre ou retire l'affectation formateur groupe/module pour une UP."""

    permission_required = "formations.change_affectationformateurgroupe"

    def has_permission(self):
        return _utilisateur_peut_affecter_formateur(self.request.user)

    def post(self, request, formation_pk: int, groupe_pk: int, module_pk: int):
        from django.core.exceptions import PermissionDenied

        if not utilisateur_peut_gerer_module_up(request.user, module_pk):
            raise PermissionDenied
        formation = get_formation_pour_utilisateur(request.user, formation_pk)
        groupe = get_groupe_pour_utilisateur(request.user, groupe_pk)
        if groupe.formation_id != formation.pk:
            raise Http404
        if not FormationModule.objects.filter(formation_id=formation_pk, module_id=module_pk).exists():
            raise Http404

        raw = (request.POST.get("formateur_id") or "").strip()
        if raw:
            formateur = get_object_or_404(Formateur, pk=int(raw))
            if utilisateur_est_rup(request.user) and not formateur_eligible_pour_module(formateur, module_pk):
                messages.error(
                    request,
                    "Ce formateur n'a pas la spécialité requise pour ce module.",
                )
                return _redirect_apres_affectation_rup(request, formation_pk)
            AffectationFormateurGroupe.objects.update_or_create(
                groupe_id=groupe_pk,
                module_id=module_pk,
                defaults={"formateur_id": formateur.pk},
            )
            nb = _appliquer_formateur_aux_seances(groupe_pk, module_pk, formateur)
            msg = f"Formateur affecté pour {groupe.nom}."
            if nb:
                msg += f" {nb} séance(s) mise(s) à jour."
            messages.success(request, msg)
        else:
            deleted, _ = AffectationFormateurGroupe.objects.filter(
                groupe_id=groupe_pk,
                module_id=module_pk,
            ).delete()
            if deleted:
                nb = _appliquer_formateur_aux_seances(groupe_pk, module_pk, None)
                msg = f"Affectation retirée pour {groupe.nom}."
                if nb:
                    msg += f" {nb} séance(s) mise(s) à jour."
                messages.info(request, msg)
        return _redirect_apres_affectation_rup(request, formation_pk)
