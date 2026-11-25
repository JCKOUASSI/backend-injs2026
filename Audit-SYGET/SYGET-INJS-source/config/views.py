"""
Vue de la page d'accueil.
Agrège les statistiques globales et les formations récentes.
"""

import datetime

from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render
from django.views import View

JOURS_NOMS = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]


class HomeView(LoginRequiredMixin, View):
    """
    Page d'accueil — tableau de bord.
    Affiche les statistiques globales, les formations récentes
    et les paramètres actifs.
    """

    template_name = "home/index.html"

    def get(self, request):
        """Construit le contexte du tableau de bord."""
        from apps.auditeurs.models import Auditeur
        from apps.parametrage.models import Grade, ParametreGeneral, Vague
        from apps.referentiels.models import Module, TypeFormation
        from apps.seances.models import Seance

        from shared.formations_scope import queryset_formations, queryset_groupes

        nb_formations = queryset_formations(request.user).count()
        nb_auditeurs = Auditeur.objects.count()
        nb_groupes = queryset_groupes(request.user).count()
        nb_seances = Seance.objects.filter(
            groupe__formation_id__in=queryset_formations(request.user).values("pk")
        ).count()

        stats = [
            {
                "label": "Formations",
                "valeur": nb_formations,
                "icon": "bi bi-mortarboard-fill",
                "color": "#3b82f6",
                "sous_texte": None,
            },
            {
                "label": "Auditeurs",
                "valeur": nb_auditeurs,
                "icon": "bi bi-people-fill",
                "color": "#10b981",
                "sous_texte": None,
            },
            {
                "label": "Groupes",
                "valeur": nb_groupes,
                "icon": "bi bi-diagram-3-fill",
                "color": "#8b5cf6",
                "sous_texte": None,
            },
            {
                "label": "Séances planifiées",
                "valeur": nb_seances,
                "icon": "bi bi-calendar-check-fill",
                "color": "#f59e0b",
                "sous_texte": None,
            },
        ]

        formations_recentes = list(
            queryset_formations(request.user).prefetch_related("inscriptions", "groupes").order_by("-created_at")[:6]
        )

        params = ParametreGeneral.get()
        jours_labels = [JOURS_NOMS[j] for j in (params.jours_defaut or [])]

        stats_ref = {
            "nb_types": TypeFormation.objects.count(),
            "nb_modules": Module.objects.count(),
            "nb_grades": Grade.objects.count(),
            "nb_vagues": Vague.objects.count(),
        }

        return render(
            request,
            self.template_name,
            {
                "today": datetime.date.today(),
                "stats": stats,
                "formations_recentes": formations_recentes,
                "params": params,
                "jours_labels": jours_labels,
                "stats_ref": stats_ref,
            },
        )


def custom_404(request, exception=None):
    """Handler pour les pages 404."""
    return render(request, "404.html", status=404)
