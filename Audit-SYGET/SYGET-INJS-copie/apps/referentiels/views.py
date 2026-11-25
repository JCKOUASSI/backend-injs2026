"""
Vues de l'app referentiels.
Gestion des types de formation et modules (lecture seule depuis les autres apps).
"""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from shared.permissions import RoleProtectedMixin

from .forms import ModuleForm
from .models import Module
from .repositories import ModuleRepository
from .services import ModuleService


class ModuleListView(RoleProtectedMixin, View):
    """Affiche la liste des modules du référentiel."""

    permission_required = "referentiels.view_module"
    template_name = "referentiels/module_list.html"

    def get(self, request):
        """Retourne la liste des modules."""
        modules = ModuleRepository().list_all()
        form = ModuleForm()
        return render(request, self.template_name, {"modules": modules, "form": form})


class ModuleCreateView(RoleProtectedMixin, View):
    """Crée un nouveau module dans le référentiel."""

    permission_required = "referentiels.add_module"

    def post(self, request):
        """Traite la soumission du formulaire de création."""
        form = ModuleForm(request.POST)
        if form.is_valid():
            try:
                service = ModuleService(ModuleRepository())
                service.get_or_create(
                    titre=form.cleaned_data["titre"],
                    specialite=form.cleaned_data["specialite"],
                )
                messages.success(request, "Module créé avec succès.")
            except ValueError as e:
                messages.error(request, str(e))
        else:
            messages.error(request, "Formulaire invalide.")
        return redirect("referentiels:module_list")


class ModuleUpdateView(RoleProtectedMixin, View):
    """Met à jour un module du référentiel."""

    permission_required = "referentiels.change_module"

    def post(self, request, pk: int):
        module = get_object_or_404(Module, pk=pk)
        form = ModuleForm(request.POST, instance=module)
        if form.is_valid():
            try:
                ModuleService(ModuleRepository()).modifier(
                    pk=pk,
                    titre=form.cleaned_data["titre"],
                    actif=module.actif,
                    specialite=form.cleaned_data["specialite"],
                )
                messages.success(request, "Module mis à jour.")
            except ValueError as e:
                messages.error(request, str(e))
        else:
            messages.error(request, "Formulaire invalide.")
        return redirect("referentiels:module_list")


class ModuleDeleteView(RoleProtectedMixin, View):
    """Supprime un module du référentiel."""

    permission_required = "referentiels.delete_module"

    def post(self, request, pk: int):
        try:
            ModuleService(ModuleRepository()).supprimer(pk)
            messages.success(request, "Module supprimé.")
        except ValueError as e:
            messages.error(request, str(e))
        return redirect("referentiels:module_list")


class TypeFormationListView(RoleProtectedMixin, View):
    """Redirige vers la page paramétrage qui gère les types."""

    permission_required = "referentiels.view_typeformation"

    def get(self, request):
        """Redirige vers la page paramétrage."""
        return redirect("parametrage:index")
