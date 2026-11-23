"""Admin du lot L7 — Patrimoine."""
from django.contrib import admin

from .models import Equipement, Inventaire, LigneInventaire, Maintenance, MouvementPatrimonial, ReservationEspace, Vehicule


@admin.register(Equipement)
class EquipementAdmin(admin.ModelAdmin):
    list_display = ['nom', 'type_equipement', 'etat', 'espace', 'num_serie']
    list_filter = ['type_equipement', 'etat']
    search_fields = ['nom', 'num_serie', 'marque']


@admin.register(Vehicule)
class VehiculeAdmin(admin.ModelAdmin):
    list_display = ['immatriculation', 'marque', 'modele', 'kilometrage', 'prochaine_revision']
    search_fields = ['immatriculation', 'marque']


@admin.register(Inventaire)
class InventaireAdmin(admin.ModelAdmin):
    list_display = ['date_inventaire', 'responsable', 'created_at']
    readonly_fields = ['created_at']


@admin.register(LigneInventaire)
class LigneInventaireAdmin(admin.ModelAdmin):
    list_display = ['inventaire', 'equipement', 'etat_constate']
    list_filter = ['etat_constate']


@admin.register(Maintenance)
class MaintenanceAdmin(admin.ModelAdmin):
    list_display = ['equipement', 'salle', 'type_maintenance', 'statut', 'date_debut']
    list_filter = ['type_maintenance', 'statut']
    search_fields = ['description']


@admin.register(ReservationEspace)
class ReservationEspaceAdmin(admin.ModelAdmin):
    list_display = ['salle', 'motif', 'date_debut', 'date_fin', 'statut']
    list_filter = ['statut']
    search_fields = ['motif']


@admin.register(MouvementPatrimonial)
class MouvementPatrimonialAdmin(admin.ModelAdmin):
    list_display = ['type_mouvement', 'equipement', 'vehicule', 'created_at']
    list_filter = ['type_mouvement']
    readonly_fields = ['type_mouvement', 'equipement', 'vehicule', 'detail',
                       'ancienne_valeur', 'nouvelle_valeur', 'acteur', 'created_at']
    actions = None