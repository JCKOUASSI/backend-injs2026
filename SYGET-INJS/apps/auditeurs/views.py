"""
Vues de l'app auditeurs.
"""

from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from shared.permissions import RoleProtectedMixin

from .forms import AuditeurForm, ImportAuditeursForm
from .models import Auditeur
from .repositories import AuditeurRepository
from .services import AuditeurService


class AuditeurListView(RoleProtectedMixin, View):
    permission_required = "auditeurs.view_auditeur"
    """Affiche la liste des auditeurs avec recherche rapide."""

    template_name = "auditeurs/list.html"

    def get(self, request):
        """Retourne la liste paginée des auditeurs, filtrée si un paramètre q est fourni."""
        query = request.GET.get("q", "").strip()
        repo = AuditeurRepository()
        paginator = Paginator(repo.search_queryset(query), repo.PAGE_SIZE)
        page_obj = paginator.get_page(request.GET.get("page") or 1)
        return render(
            request,
            self.template_name,
            {"page_obj": page_obj, "auditeurs": page_obj.object_list, "query": query},
        )


def _extraire_champs_auditeur(form) -> dict:
    """Extrait les champs nettoyés du formulaire auditeur."""
    cd = form.cleaned_data
    return {
        "nom": cd["nom"],
        "prenom": cd["prenom"],
        "genre": cd.get("genre", ""),
        "date_naissance": cd.get("date_naissance"),
        "lieu_naissance": cd.get("lieu_naissance", ""),
        "telephone_1": cd.get("telephone_1", ""),
        "telephone_2": cd.get("telephone_2", ""),
        "type_concours": cd.get("type_concours", ""),
        "libelle_concours": cd.get("libelle_concours", ""),
        "categorie": cd.get("categorie", ""),
        "grade": cd.get("grade", ""),
        "email": cd.get("email", ""),
    }


class AuditeurCreateView(RoleProtectedMixin, View):
    """Crée un auditeur individuellement (sans Excel)."""

    permission_required = "auditeurs.add_auditeur"
    template_name = "auditeurs/form.html"

    def get(self, request):
        """Affiche le formulaire de création."""
        return render(request, self.template_name, {"form": AuditeurForm(), "action": "Créer"})

    def post(self, request):
        """Traite la soumission du formulaire de création."""
        form = AuditeurForm(request.POST)
        if form.is_valid():
            try:
                service = AuditeurService(AuditeurRepository())
                auditeur = service.creer(**_extraire_champs_auditeur(form))
                messages.success(request, f"Auditeur {auditeur.nom_complet} créé (matricule : {auditeur.matricule}).")
                return redirect("auditeurs:detail", pk=auditeur.pk)
            except ValueError as e:
                messages.error(request, str(e))
        return render(request, self.template_name, {"form": form, "action": "Créer"})


class AuditeurUpdateView(RoleProtectedMixin, View):
    """Modifie un auditeur existant."""

    permission_required = "auditeurs.change_auditeur"
    template_name = "auditeurs/form.html"

    def get(self, request, pk: int):
        """Affiche le formulaire de modification."""
        auditeur = get_object_or_404(Auditeur, pk=pk)
        form = AuditeurForm(instance=auditeur)
        return render(request, self.template_name, {"form": form, "auditeur": auditeur, "action": "Modifier"})

    def post(self, request, pk: int):
        """Traite la soumission du formulaire de modification."""
        auditeur = get_object_or_404(Auditeur, pk=pk)
        form = AuditeurForm(request.POST, instance=auditeur)
        if form.is_valid():
            try:
                AuditeurService(AuditeurRepository()).modifier(pk=pk, **_extraire_champs_auditeur(form))
                messages.success(request, "Auditeur mis à jour.")
                return redirect("auditeurs:detail", pk=pk)
            except ValueError as e:
                messages.error(request, str(e))
        return render(request, self.template_name, {"form": form, "auditeur": auditeur, "action": "Modifier"})


class AuditeurDeleteView(RoleProtectedMixin, View):
    """Supprime un auditeur."""

    permission_required = "auditeurs.delete_auditeur"

    def post(self, request, pk: int):
        """Supprime l'auditeur identifié par pk."""
        auditeur = get_object_or_404(Auditeur, pk=pk)
        nom = auditeur.nom_complet
        try:
            AuditeurService(AuditeurRepository()).supprimer(pk)
            messages.success(request, f"Auditeur {nom} supprimé.")
        except ValueError as e:
            messages.error(request, str(e))
            return redirect("auditeurs:detail", pk=pk)
        return redirect("auditeurs:list")


class AuditeurDetailView(RoleProtectedMixin, View):
    """Page détail d'un auditeur : formations inscrites, groupes d'appartenance."""

    permission_required = "auditeurs.view_auditeur"
    template_name = "auditeurs/detail.html"

    def get(self, request, pk: int):
        """Retourne le détail d'un auditeur."""
        auditeur = get_object_or_404(
            Auditeur.objects.prefetch_related(
                "inscriptions__formation_module__module",
                "inscriptions__formation__type_formation",
                "groupes__groupe__formation__type_formation",
            ),
            pk=pk,
        )
        return render(request, self.template_name, {"auditeur": auditeur})


class AuditeurImportView(RoleProtectedMixin, View):
    """Import d'auditeurs depuis un fichier Excel."""

    permission_required = "auditeurs.add_auditeur"
    template_name = "auditeurs/import.html"

    def get(self, request):
        """Affiche le formulaire d'import."""
        return render(request, self.template_name, {"form": ImportAuditeursForm()})

    def post(self, request):
        """Traite l'import du fichier Excel."""
        form = ImportAuditeursForm(request.POST, request.FILES)
        if form.is_valid():
            service = AuditeurService(AuditeurRepository())
            formation = form.cleaned_data["formation"]
            report = service.importer_depuis_excel(
                request.FILES["fichier"],
                formation_id=formation.pk,
            )
            if report.erreurs:
                for err in report.erreurs[:20]:
                    messages.warning(request, err)
                if len(report.erreurs) > 20:
                    messages.warning(
                        request, f"… et {len(report.erreurs) - 20} autre(s) erreur(s) (voir le rapport CSV)."
                    )
            for av in report.avertissements[:10]:
                messages.warning(request, av)
            if len(report.avertissements) > 10:
                messages.warning(
                    request,
                    f"… et {len(report.avertissements) - 10} autre(s) avertissement(s) (voir le rapport CSV).",
                )
            request.session["last_import_report_csv"] = report.to_csv()
            request.session["last_import_report_formation"] = formation.intitule
            messages.success(
                request,
                f"Import terminé ({formation.intitule}) : {report.nb_crees} auditeur(s) créé(s), "
                f"{report.nb_inscriptions} inscription(s) aux modules, "
                f"{report.nb_ignores} ligne(s) ignorée(s), {report.nb_erreurs} erreur(s).",
            )
            return redirect("auditeurs:list")
        return render(request, self.template_name, {"form": form})


class AuditeurImportRapportView(RoleProtectedMixin, View):
    """Télécharge le rapport CSV du dernier import (session)."""

    permission_required = "auditeurs.view_auditeur"

    def get(self, request):
        from django.http import HttpResponse

        csv_content = request.session.pop("last_import_report_csv", None)
        formation = request.session.pop("last_import_report_formation", "import")
        if not csv_content:
            messages.warning(request, "Aucun rapport d'import récent.")
            return redirect("auditeurs:list")
        response = HttpResponse(csv_content, content_type="text/csv; charset=utf-8")
        safe_name = str(formation).replace('"', "")[:80]
        response["Content-Disposition"] = f'attachment; filename="rapport-import-{safe_name}.csv"'
        return response
