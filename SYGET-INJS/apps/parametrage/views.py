"""
Vues de l'app parametrage.
Page unique /parametrage/ avec toutes les sections configurables.

RBAC : le paramétrage est considéré comme sensible (sites, salles, jours fériés,
paramètres généraux). La lecture (page index) est ouverte aux trois groupes
(`view_parametregeneral`) mais l'écriture est réservée aux administrateurs
(`add_*` / `change_*` / `delete_*` sur les modèles correspondants).
"""

from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View

from apps.referentiels.models import TypeFormation
from apps.referentiels.repositories import ModuleRepository, TypeFormationRepository
from apps.referentiels.services import TypeFormationService
from shared.formations_scope import get_formation_pour_utilisateur
from shared.permissions import RoleProtectedMixin

from .forms import (
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
from .models import (
    Batiment,
    Grade,
    JourFerie,
    ParametreGeneral,
    PeriodeDisponibiliteSite,
    Salle,
    Site,
    Vague,
)
from .repositories import GradeRepository, ParametreFormationRepository, ParametreGeneralRepository, VagueRepository
from .services import (
    GradeService,
    ModuleAssociationData,
    ModuleParametrageService,
    ParametreFormationService,
    ParametreGeneralService,
    VagueService,
)


from .view_helpers import (
    build_parametrage_index_forms,
    make_parametrage_service,
    parse_formation_id,
    redirect_parametrage,
)

_redirect_parametrage = redirect_parametrage
_parse_formation_id = parse_formation_id


class ParametrageIndexView(RoleProtectedMixin, View):
    """
    Page de paramétrage principale — page unique avec toutes les sections.
    GET  : affiche toutes les sections avec leurs données.
    """

    permission_required = "parametrage.view_parametregeneral"
    template_name = "parametrage/index.html"

    def get(self, request):
        """Construit le contexte complet et affiche la page."""
        service = make_parametrage_service()
        formation_id = parse_formation_id(request.GET.get("formation"))
        ctx = service.get_context(request.user, formation_id=formation_id)
        return render(
            request,
            self.template_name,
            {"ctx": ctx, **build_parametrage_index_forms(ctx)},
        )


# ── Types de formation ────────────────────────────────────────────────────────


class TypeFormationCreateView(RoleProtectedMixin, View):
    """Crée un type de formation."""

    permission_required = "referentiels.add_typeformation"

    def post(self, request):
        """Traite la création d'un type de formation."""
        form = TypeFormationForm(request.POST)
        if form.is_valid():
            try:
                TypeFormationService(TypeFormationRepository()).creer(
                    code=form.cleaned_data["code"],
                    libelle=form.cleaned_data["libelle"],
                )
                messages.success(request, "Type de formation créé.")
            except ValueError as e:
                messages.error(request, str(e))
        else:
            messages.error(request, "Formulaire invalide.")
        return HttpResponseRedirect(f"{reverse('parametrage:index')}#types-formation")


class TypeFormationUpdateView(RoleProtectedMixin, View):
    """Modifie un type de formation."""

    permission_required = "referentiels.change_typeformation"

    def post(self, request, pk: int):
        """Traite la modification d'un type de formation."""
        tf = get_object_or_404(TypeFormation, pk=pk)
        form = TypeFormationForm(request.POST, instance=tf)
        if form.is_valid():
            try:
                TypeFormationService(TypeFormationRepository()).modifier(
                    pk, form.cleaned_data["code"], form.cleaned_data["libelle"]
                )
                messages.success(request, "Type de formation modifié.")
            except ValueError as e:
                messages.error(request, str(e))
        else:
            messages.error(request, "Formulaire invalide.")
        return HttpResponseRedirect(f"{reverse('parametrage:index')}#types-formation")


class TypeFormationDeleteView(RoleProtectedMixin, View):
    """Supprime un type de formation."""

    permission_required = "referentiels.delete_typeformation"

    def post(self, request, pk: int):
        """Supprime le type de formation identifié par pk."""
        try:
            TypeFormationService(TypeFormationRepository()).supprimer(pk)
            messages.success(request, "Type de formation supprimé.")
        except ValueError as e:
            messages.error(request, str(e))
        return HttpResponseRedirect(f"{reverse('parametrage:index')}#types-formation")


# ── Grades ────────────────────────────────────────────────────────────────────


class GradeCreateView(RoleProtectedMixin, View):
    """Ajoute un grade via POST."""

    permission_required = "parametrage.add_grade"

    def post(self, request):
        """Crée un grade à partir du formulaire soumis."""
        form = GradeForm(request.POST)
        if form.is_valid():
            try:
                next_ordre = Grade.objects.count() + 1
                GradeService(GradeRepository()).creer(
                    libelle=form.cleaned_data["libelle"],
                    ordre=next_ordre,
                )
                messages.success(request, "Grade ajouté avec succès.")
            except ValueError as e:
                messages.error(request, str(e))
        else:
            messages.error(request, "Formulaire invalide.")
        return redirect("parametrage:index")


class GradeDeleteView(RoleProtectedMixin, View):
    """Supprime un grade — vérifie qu'il n'est pas utilisé."""

    permission_required = "parametrage.delete_grade"

    def post(self, request, pk: int):
        """Supprime le grade identifié par pk."""
        try:
            GradeService(GradeRepository()).supprimer(pk)
            messages.success(request, "Grade supprimé.")
        except (ValueError, Grade.DoesNotExist) as e:
            messages.error(request, str(e))
        return redirect("parametrage:index")


# ── Vagues ────────────────────────────────────────────────────────────────────


class VagueCreateView(RoleProtectedMixin, View):
    """Ajoute une vague."""

    permission_required = "parametrage.add_vague"

    def post(self, request):
        """Crée une vague à partir du formulaire soumis."""
        form = VagueForm(request.POST)
        if form.is_valid():
            try:
                VagueService(VagueRepository()).creer(libelle=form.cleaned_data["libelle"])
                messages.success(request, "Vague ajoutée avec succès.")
            except ValueError as e:
                messages.error(request, str(e))
        else:
            messages.error(request, "Formulaire invalide.")
        return redirect("parametrage:index")


class VagueDeleteView(RoleProtectedMixin, View):
    """Supprime une vague — vérifie qu'elle n'est pas utilisée."""

    permission_required = "parametrage.delete_vague"

    def post(self, request, pk: int):
        """Supprime la vague identifiée par pk."""
        try:
            VagueService(VagueRepository()).supprimer(pk)
            messages.success(request, "Vague supprimée.")
        except (ValueError, Vague.DoesNotExist) as e:
            messages.error(request, str(e))
        return redirect("parametrage:index")


# ── Lieux (sites / bâtiments / salles) ───────────────────────────────────────


class SiteCreateView(RoleProtectedMixin, View):
    """Ajoute un site."""

    permission_required = "parametrage.add_site"

    def post(self, request):
        form = SiteForm(request.POST)
        if form.is_valid():
            nom = form.cleaned_data["nom"].strip()
            if Site.objects.filter(nom__iexact=nom).exists():
                messages.error(request, f"Le site '{nom}' existe déjà.")
            else:
                Site.objects.create(nom=nom)
                messages.success(request, "Site ajouté.")
        else:
            messages.error(request, "Formulaire site invalide.")
        return redirect("parametrage:index")


class SiteDeleteView(RoleProtectedMixin, View):
    """Supprime un site."""

    permission_required = "parametrage.delete_site"

    def post(self, request, pk: int):
        Site.objects.filter(pk=pk).delete()
        messages.success(request, "Site supprimé.")
        return redirect("parametrage:index")


class SiteUpdateView(RoleProtectedMixin, View):
    """Modifie un site."""

    permission_required = "parametrage.change_site"

    def post(self, request, pk: int):
        site = get_object_or_404(Site, pk=pk)
        form = SiteForm(request.POST, instance=site)
        if form.is_valid():
            nom = form.cleaned_data["nom"].strip()
            if Site.objects.exclude(pk=site.pk).filter(nom__iexact=nom).exists():
                messages.error(request, f"Le site '{nom}' existe déjà.")
            else:
                site.nom = nom
                site.save(update_fields=["nom"])
                messages.success(request, "Site modifié.")
        else:
            messages.error(request, "Formulaire site invalide.")
        return redirect("parametrage:index")


class BatimentCreateView(RoleProtectedMixin, View):
    """Ajoute un bâtiment."""

    permission_required = "parametrage.add_batiment"

    def post(self, request):
        form = BatimentForm(request.POST)
        if form.is_valid():
            nom = form.cleaned_data["nom"].strip()
            site = form.cleaned_data["site"]
            if Batiment.objects.filter(site=site, nom__iexact=nom).exists():
                messages.error(request, f"Le bâtiment '{nom}' existe déjà pour ce site.")
            else:
                Batiment.objects.create(site=site, nom=nom)
                messages.success(request, "Bâtiment ajouté.")
        else:
            messages.error(request, "Formulaire bâtiment invalide.")
        return redirect("parametrage:index")


class BatimentDeleteView(RoleProtectedMixin, View):
    """Supprime un bâtiment."""

    permission_required = "parametrage.delete_batiment"

    def post(self, request, pk: int):
        Batiment.objects.filter(pk=pk).delete()
        messages.success(request, "Bâtiment supprimé.")
        return redirect("parametrage:index")


class BatimentUpdateView(RoleProtectedMixin, View):
    """Modifie un bâtiment."""

    permission_required = "parametrage.change_batiment"

    def post(self, request, pk: int):
        batiment = get_object_or_404(Batiment, pk=pk)
        form = BatimentForm(request.POST, instance=batiment)
        if form.is_valid():
            nom = form.cleaned_data["nom"].strip()
            site = form.cleaned_data["site"]
            if Batiment.objects.exclude(pk=batiment.pk).filter(site=site, nom__iexact=nom).exists():
                messages.error(request, f"Le bâtiment '{nom}' existe déjà pour ce site.")
            else:
                batiment.site = site
                batiment.nom = nom
                batiment.save(update_fields=["site", "nom"])
                messages.success(request, "Bâtiment modifié.")
        else:
            messages.error(request, "Formulaire bâtiment invalide.")
        return redirect("parametrage:index")


class SalleCreateView(RoleProtectedMixin, View):
    """Ajoute une salle."""

    permission_required = "parametrage.add_salle"

    def post(self, request):
        form = SalleForm(request.POST)
        if form.is_valid():
            nom = form.cleaned_data["nom"].strip()
            batiment = form.cleaned_data["batiment"]
            if Salle.objects.filter(nom__iexact=nom).exists():
                messages.error(request, f"La salle '{nom}' existe déjà.")
            else:
                Salle.objects.create(
                    batiment=batiment,
                    nom=nom,
                    capacite_max=form.cleaned_data.get("capacite_max") or 25,
                )
                messages.success(request, "Salle ajoutée.")
        else:
            messages.error(request, "Formulaire salle invalide.")
        return redirect("parametrage:index")


class SalleDeleteView(RoleProtectedMixin, View):
    """Supprime une salle."""

    permission_required = "parametrage.delete_salle"

    def post(self, request, pk: int):
        Salle.objects.filter(pk=pk).delete()
        messages.success(request, "Salle supprimée.")
        return redirect("parametrage:index")


class SalleUpdateView(RoleProtectedMixin, View):
    """Modifie une salle."""

    permission_required = "parametrage.change_salle"

    def post(self, request, pk: int):
        salle = get_object_or_404(Salle, pk=pk)
        form = SalleForm(request.POST, instance=salle)
        if form.is_valid():
            nom = form.cleaned_data["nom"].strip()
            batiment = form.cleaned_data["batiment"]
            capacite_max = form.cleaned_data.get("capacite_max") or 25
            if Salle.objects.exclude(pk=salle.pk).filter(nom__iexact=nom).exists():
                messages.error(request, f"La salle '{nom}' existe déjà.")
            else:
                salle.batiment = batiment
                salle.nom = nom
                salle.capacite_max = capacite_max
                salle.save(update_fields=["batiment", "nom", "capacite_max"])
                messages.success(request, "Salle modifiée.")
        else:
            messages.error(request, "Formulaire salle invalide.")
        return redirect("parametrage:index")


class PeriodeDisponibiliteSiteCreateView(RoleProtectedMixin, View):
    """Ajoute une période de disponibilité pour un site."""

    permission_required = "parametrage.add_periodedisponibilitesite"

    def post(self, request):
        form = PeriodeDisponibiliteSiteForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Période de disponibilité ajoutée.")
        else:
            messages.error(request, "Formulaire période de disponibilité invalide.")
        return redirect(f"{reverse('parametrage:index')}#lieux-pedagogiques")


class PeriodeDisponibiliteSiteUpdateView(RoleProtectedMixin, View):
    """Modifie une période de disponibilité d'un site."""

    permission_required = "parametrage.change_periodedisponibilitesite"

    def post(self, request, pk: int):
        periode = get_object_or_404(PeriodeDisponibiliteSite, pk=pk)
        form = PeriodeDisponibiliteSiteForm(request.POST, instance=periode)
        if form.is_valid():
            form.save()
            messages.success(request, "Période de disponibilité modifiée.")
        else:
            messages.error(request, "Formulaire période de disponibilité invalide.")
        return redirect(f"{reverse('parametrage:index')}#lieux-pedagogiques")


class PeriodeDisponibiliteSiteDeleteView(RoleProtectedMixin, View):
    """Supprime une période de disponibilité d'un site."""

    permission_required = "parametrage.delete_periodedisponibilitesite"

    def post(self, request, pk: int):
        PeriodeDisponibiliteSite.objects.filter(pk=pk).delete()
        messages.success(request, "Période de disponibilité supprimée.")
        return redirect(f"{reverse('parametrage:index')}#lieux-pedagogiques")


class SiteToggleActifView(RoleProtectedMixin, View):
    """Active ou désactive un site."""

    permission_required = "parametrage.change_site"

    def post(self, request, pk: int):
        site = get_object_or_404(Site, pk=pk)
        cible_actif = not site.actif
        site.actif = cible_actif
        try:
            site.save()
            etat = "activé" if site.actif else "désactivé"
            messages.success(request, f"Site {etat}.")
            return _redirect_parametrage(anchor="lieux-pedagogiques")
        except ValidationError as exc:
            site.refresh_from_db()
            detail = "; ".join(msg for msgs in getattr(exc, "message_dict", {}).values() for msg in msgs) or str(exc)
            messages.error(request, detail)
            return _redirect_parametrage()


class BatimentToggleActifView(RoleProtectedMixin, View):
    """Active ou désactive un bâtiment."""

    permission_required = "parametrage.change_batiment"

    def post(self, request, pk: int):
        batiment = get_object_or_404(Batiment, pk=pk)
        cible_actif = not batiment.actif
        batiment.actif = cible_actif
        try:
            batiment.save()
            etat = "activé" if batiment.actif else "désactivé"
            messages.success(request, f"Bâtiment {etat}.")
            return _redirect_parametrage(anchor="lieux-pedagogiques")
        except ValidationError as exc:
            batiment.refresh_from_db()
            detail = "; ".join(msg for msgs in getattr(exc, "message_dict", {}).values() for msg in msgs) or str(exc)
            messages.error(request, detail)
            return _redirect_parametrage()


class SalleToggleActifView(RoleProtectedMixin, View):
    """Active ou désactive une salle."""

    permission_required = "parametrage.change_salle"

    def post(self, request, pk: int):
        salle = get_object_or_404(Salle, pk=pk)
        salle.actif = not salle.actif
        salle.save(update_fields=["actif"])
        etat = "activée" if salle.actif else "désactivée"
        messages.success(request, f"Salle {etat}.")
        return _redirect_parametrage(anchor="lieux-pedagogiques")


# ── Paramètres généraux ───────────────────────────────────────────────────────


class ParametreFormationUpdateView(RoleProtectedMixin, View):
    """Met à jour les paramètres de planification d'une formation."""

    permission_required = "parametrage.change_parametregeneral"

    def post(self, request):
        formation_id = _parse_formation_id(request.POST.get("formation_id"))
        if formation_id is None:
            messages.error(request, "Formation invalide.")
            return redirect("parametrage:index")

        get_formation_pour_utilisateur(request.user, formation_id)
        params = ParametreFormationRepository().get_for_formation(formation_id)
        form = ParametreFormationForm(request.POST, instance=params)
        if form.is_valid():
            ParametreFormationService(ParametreFormationRepository()).mettre_a_jour(formation_id, form.cleaned_data)
            messages.success(request, "Paramètres de la formation enregistrés.")
        else:
            messages.error(request, f"Erreur : {form.errors}")
        return redirect(f"{reverse('parametrage:index')}?formation={formation_id}#parametres-formation")


class ParametreGeneralUpdateView(RoleProtectedMixin, View):
    """Met à jour les valeurs par défaut (modèle global)."""

    permission_required = "parametrage.change_parametregeneral"

    def post(self, request):
        """Traite la soumission du formulaire des valeurs par défaut."""
        params = ParametreGeneral.get()
        form = ParametreGeneralForm(request.POST, instance=params)
        if form.is_valid():
            ParametreGeneralService(ParametreGeneralRepository()).mettre_a_jour(form.cleaned_data)
            messages.success(request, "Valeurs par défaut enregistrées.")
        else:
            messages.error(request, f"Erreur : {form.errors}")
        formation_id = _parse_formation_id(request.POST.get("formation_id"))
        if formation_id is not None:
            return redirect(f"{reverse('parametrage:index')}?formation={formation_id}#parametres-defaut")
        return redirect(f"{reverse('parametrage:index')}#parametres-defaut")


# ── Jours fériés ───────────────────────────────────────────────────────────────


class JourFerieCreateView(RoleProtectedMixin, View):
    """Ajoute un jour férié à exclure automatiquement de la planification."""

    permission_required = "parametrage.add_jourferie"

    def post(self, request):
        form = JourFerieForm(request.POST)
        if form.is_valid():
            date = form.cleaned_data["date"]
            libelle = form.cleaned_data["libelle"].strip()
            if JourFerie.objects.filter(date=date).exists():
                messages.error(request, "Un jour férié existe déjà pour cette date.")
            else:
                JourFerie.objects.create(date=date, libelle=libelle)
                messages.success(request, "Jour férié ajouté.")
        else:
            messages.error(request, "Formulaire jour férié invalide.")
        return redirect("parametrage:index")


class JourFerieDeleteView(RoleProtectedMixin, View):
    """Supprime un jour férié."""

    permission_required = "parametrage.delete_jourferie"

    def post(self, request, pk: int):
        JourFerie.objects.filter(pk=pk).delete()
        messages.success(request, "Jour férié supprimé.")
        return redirect("parametrage:index")


# ── Modules ───────────────────────────────────────────────────────────────────


class ModuleCreateView(RoleProtectedMixin, View):
    """Crée un module dans le référentiel global."""

    permission_required = "referentiels.add_module"

    def post(self, request):
        """Crée un module à partir du formulaire soumis."""
        form = ModuleForm(request.POST)
        if form.is_valid():
            try:
                ModuleParametrageService(ModuleRepository(), TypeFormationRepository()).creer_module(
                    titre=form.cleaned_data["titre"]
                )
                messages.success(request, "Module créé avec succès.")
            except ValueError as e:
                messages.error(request, str(e))
        else:
            messages.error(request, "Formulaire invalide.")
        return redirect("parametrage:index")


class ModuleAssocierView(RoleProtectedMixin, View):
    """Associe un module à un type de formation avec volume horaire par défaut."""

    permission_required = "parametrage.add_moduletypeformation"

    def post(self, request):
        """Crée ou met à jour une (ou plusieurs) associations module/type/grade."""
        form = ModuleTypeFormationForm(request.POST)
        if form.is_valid():
            grades: list[str] = form.cleaned_data["grade_cible"] or [""]
            service = ModuleParametrageService(ModuleRepository(), TypeFormationRepository())
            for grade in grades:
                service.associer_a_type(
                    ModuleAssociationData(
                        module_id=form.cleaned_data["module"].pk,
                        type_formation_id=form.cleaned_data["type_formation"].pk,
                        grade_cible=grade,
                        volume_horaire_defaut=form.cleaned_data["volume_horaire_defaut"],
                    )
                )
            if len(grades) == 1 and not grades[0]:
                messages.success(request, "Association enregistrée pour tous les grades.")
            else:
                libelle = ", ".join(grades) if grades else "—"
                messages.success(
                    request,
                    f"Association enregistrée pour {len(grades)} grade(s) : {libelle}.",
                )
        else:
            messages.error(request, "Formulaire invalide.")
        return redirect("parametrage:index")


class ModuleDissocierView(RoleProtectedMixin, View):
    """Supprime l'association entre un module et un type de formation."""

    permission_required = "parametrage.delete_moduletypeformation"

    def post(self, request, association_id: int):
        """Supprime l'association identifiée par son id."""
        ModuleParametrageService(ModuleRepository(), TypeFormationRepository()).dissocier(association_id)
        messages.success(request, "Association supprimée.")
        return redirect("parametrage:index")
