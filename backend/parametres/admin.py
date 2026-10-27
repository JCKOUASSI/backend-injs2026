"""
Admin Django pour le module Paramètres.

Interface administration des paramètres avec historique.
"""

from django.contrib import admin
from django.utils.html import format_html
from .models import Parametre, ParametreHistorique


@admin.register(Parametre)
class ParametreAdmin(admin.ModelAdmin):
    """
    Admin pour les paramètres.
    """
    list_display = [
        'cle',
        'libelle',
        'categorie',
        'type',
        'valeur_display',
        'modifiable_badge',
        'actif_badge',
    ]
    list_filter = ['categorie', 'type', 'modifiable', 'actif', 'modifie_le']
    search_fields = ['cle', 'libelle', 'description']
    readonly_fields = [
        'cle',
        'cree_par',
        'cree_le',
        'modifie_par',
        'modifie_le',
        'historique_display',
    ]

    fieldsets = (
        ('Identification', {
            'fields': ('cle', 'libelle', 'description'),
        }),
        ('Catégorie et Type', {
            'fields': ('categorie', 'type', 'ordre'),
        }),
        ('Valeurs', {
            'fields': ('valeur', 'valeur_defaut', 'choices_json', 'regex_validation'),
        }),
        ('Contrôle d\'accès', {
            'fields': ('modifiable', 'modifiable_par_roles', 'lecturable_par_roles'),
        }),
        ('État', {
            'fields': ('actif',),
        }),
        ('Audit', {
            'fields': ('cree_par', 'cree_le', 'modifie_par', 'modifie_le'),
            'classes': ('collapse',),
        }),
        ('Historique', {
            'fields': ('historique_display',),
            'classes': ('collapse',),
        }),
    )

    def valeur_display(self, obj):
        """Affichage tronqué de la valeur."""
        val = obj.valeur or ''
        if len(val) > 50:
            return val[:47] + '...'
        return val or '—'
    valeur_display.short_description = 'Valeur'

    def modifiable_badge(self, obj):
        """Badge modifiable/gelé."""
        if obj.modifiable:
            return format_html(
                '<span style="background-color: #00c000; color: white; padding: 3px 8px; '
                'border-radius: 3px; font-weight: bold;">Modifiable</span>'
            )
        return format_html(
            '<span style="background-color: #cc0000; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-weight: bold;">Gelé</span>'
        )
    modifiable_badge.short_description = 'État modification'

    def actif_badge(self, obj):
        """Badge actif/inactif."""
        if obj.actif:
            return format_html(
                '<span style="background-color: #0066cc; color: white; padding: 3px 8px; '
                'border-radius: 3px; font-weight: bold;">Actif</span>'
            )
        return format_html(
            '<span style="background-color: #999999; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-weight: bold;">Inactif</span>'
        )
    actif_badge.short_description = 'Actif'

    def historique_display(self, obj):
        """Affiche les 5 dernières modifications."""
        if not obj.pk:
            return '(aucun historique)'
        historiques = obj.historiques.all()[:5]
        if not historiques:
            return '(aucune modification)'
        html_items = []
        for h in historiques:
            user_str = h.modifie_par.username if h.modifie_par else 'système'
            date_str = h.modifie_le.strftime('%Y-%m-%d %H:%M:%S')
            motif = f" ({h.motif_modification})" if h.motif_modification else ""
            html_items.append(
                f"<li><strong>{date_str}</strong> par <em>{user_str}</em>{motif}<br/>"
                f"  {h.ancienne_valeur} → {h.nouvelle_valeur}</li>"
            )
        return format_html(f"<ul>{''.join(html_items)}</ul>")
    historique_display.short_description = 'Historique récent'


@admin.register(ParametreHistorique)
class ParametreHistoriqueAdmin(admin.ModelAdmin):
    """
    Admin pour l'historique des paramètres (read-only).
    """
    list_display = [
        'parametre_cle',
        'modifie_le',
        'modifie_par_display',
        'ancienne_valeur_display',
        'nouvelle_valeur_display',
    ]
    list_filter = ['modifie_le', 'parametre__categorie']
    search_fields = ['parametre__cle', 'parametre__libelle', 'motif_modification']
    readonly_fields = [
        'parametre',
        'ancienne_valeur',
        'nouvelle_valeur',
        'modifie_par',
        'modifie_le',
        'motif_modification',
        'adresse_ip',
    ]

    fieldsets = (
        ('Paramètre', {
            'fields': ('parametre',),
        }),
        ('Modification', {
            'fields': ('ancienne_valeur', 'nouvelle_valeur', 'motif_modification'),
        }),
        ('Audit', {
            'fields': ('modifie_par', 'modifie_le', 'adresse_ip'),
        }),
    )

    def parametre_cle(self, obj):
        """Affiche la clé du paramètre."""
        return obj.parametre.cle
    parametre_cle.short_description = 'Clé paramètre'

    def modifie_par_display(self, obj):
        """Affiche l'utilisateur avec son nom complet."""
        if not obj.modifie_par:
            return '—'
        return f"{obj.modifie_par.username} ({obj.modifie_par.get_full_name()})"
    modifie_par_display.short_description = 'Modifié par'

    def ancienne_valeur_display(self, obj):
        """Affichage tronqué de l'ancienne valeur."""
        val = obj.ancienne_valeur or '(vide)'
        if len(val) > 80:
            return val[:77] + '...'
        return val
    ancienne_valeur_display.short_description = 'Ancienne valeur'

    def nouvelle_valeur_display(self, obj):
        """Affichage tronqué de la nouvelle valeur."""
        val = obj.nouvelle_valeur or '(vide)'
        if len(val) > 80:
            return val[:77] + '...'
        return val
    nouvelle_valeur_display.short_description = 'Nouvelle valeur'

    def has_add_permission(self, request):
        """Interdire création manuelle d'historique."""
        return False

    def has_delete_permission(self, request, obj=None):
        """Interdire suppression d'historique."""
        return False

    def has_change_permission(self, request, obj=None):
        """Interdire modification d'historique."""
        return False
