"""
Base ModelAdmin partagée : réduit les temps de chargement sur grosses tables.
"""

from unfold.admin import ModelAdmin as UnfoldModelAdmin


class AdminModelAdmin(UnfoldModelAdmin):
    """
    - show_full_result_count=False : pas de COUNT(*) sur toute la table (séances, inscriptions…)
    - list_per_page / list_max_show_all : limite le HTML généré
    """

    show_full_result_count = False
    list_per_page = 50
    list_max_show_all = 100
