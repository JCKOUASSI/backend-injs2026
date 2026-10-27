"""Administration Django du socle d'habilitation (U1).

Le journal est strictement consultatif (aucun ajout/modification/suppression
manuel). Les autres écrans permettent d'alimenter le référentiel pendant la
phase de construction ; les règles métier (contrôles bloquants) arrivent en
U2 et les écrans dédiés en U4.
"""
from django.contrib import admin

from .models import (
    AttributionRole,
    CompteUtilisateur,
    DelegationHabilitation,
    ExecutionImport,
    JournalHabilitation,
    NotificationHabilitation,
    PermissionAttribuee,
    PermissionMetier,
    Perimetre,
    Personne,
    PolitiqueSecurite,
    PropositionProvisionnement,
    RoleMetier,
)


@admin.register(Personne)
class PersonneAdmin(admin.ModelAdmin):
    list_display = ('matricule', 'nom', 'prenoms', 'situation', 'statut')
    search_fields = ('matricule', 'nom', 'prenoms', 'email_institutionnel',
                     'email_personnel', 'telephone')
    list_filter = ('situation', 'statut', 'sexe')
    readonly_fields = ('date_creation', 'date_modification')


@admin.register(CompteUtilisateur)
class CompteUtilisateurAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'statut', 'canal', 'mfa_actif', 'date_expiration')
    list_filter = ('statut', 'canal', 'mfa_actif')
    search_fields = ('user__username', 'personne__matricule', 'personne__nom')
    raw_id_fields = ('user', 'personne', 'cree_par')


@admin.register(RoleMetier)
class RoleMetierAdmin(admin.ModelAdmin):
    list_display = ('code', 'libelle', 'domaine', 'niveau_defaut',
                    'disponible', 'sensible', 'actif', 'ordre')
    list_filter = ('domaine', 'disponible', 'sensible', 'actif')
    search_fields = ('code', 'libelle')
    filter_horizontal = ('incompatible_avec',)


@admin.register(PermissionMetier)
class PermissionMetierAdmin(admin.ModelAdmin):
    list_display = ('code', 'module', 'ressource', 'action',
                    'criticite', 'actif')
    list_filter = ('module', 'action', 'criticite', 'actif')
    search_fields = ('code', 'libelle', 'ressource')


@admin.register(Perimetre)
class PerimetreAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'type', 'reference_lisible')
    list_filter = ('type',)
    search_fields = ('reference_lisible', 'libelle')


@admin.register(AttributionRole)
class AttributionRoleAdmin(admin.ModelAdmin):
    list_display = ('id', 'compte', 'role', 'niveau_effectif',
                    'statut', 'date_debut', 'date_fin')
    list_filter = ('statut', 'niveau_effectif')
    raw_id_fields = ('compte', 'role', 'attribue_par', 'valide_par')
    filter_horizontal = ('perimetres',)
    date_hierarchy = 'date_creation'


@admin.register(PermissionAttribuee)
class PermissionAttribueeAdmin(admin.ModelAdmin):
    list_display = ('id', 'compte', 'permission', 'sens', 'statut',
                    'date_debut', 'date_fin')
    list_filter = ('sens', 'statut')
    raw_id_fields = ('compte', 'permission', 'perimetre',
                     'attribue_par', 'valide_par')


@admin.register(DelegationHabilitation)
class DelegationHabilitationAdmin(admin.ModelAdmin):
    list_display = ('id', 'delegant', 'delegataire', 'date_debut',
                    'date_fin', 'statut')
    list_filter = ('statut',)
    raw_id_fields = ('delegant', 'delegataire', 'valide_par')
    filter_horizontal = ('roles', 'permissions', 'perimetres')


@admin.register(PolitiqueSecurite)
class PolitiqueSecuriteAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'longueur_min_mot_de_passe',
                    'duree_max_derogation_jours', 'date_modification')

    def has_add_permission(self, request):
        return not PolitiqueSecurite.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(JournalHabilitation)
class JournalHabilitationAdmin(admin.ModelAdmin):
    list_display = ('numero', 'horodatage', 'type_evenement',
                    'acteur_label', 'compte_concerne')
    list_filter = ('type_evenement',)
    search_fields = ('acteur_label', 'motif', 'correlation_id', 'objet_libelle')
    date_hierarchy = 'horodatage'
    ordering = ('-numero',)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PropositionProvisionnement)
class PropositionProvisionnementAdmin(admin.ModelAdmin):
    list_display = ('id', 'declencheur', 'action_proposee', 'statut',
                    'source_app', 'source_modele', 'cree_le', 'approuve_par')
    list_filter = ('statut', 'declencheur', 'action_proposee')
    search_fields = ('source_libelle', 'motif', 'motif_rejet',
                     'cle_dedoublonnage')
    date_hierarchy = 'cree_le'
    readonly_fields = ('cree_le', 'traite_le')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ExecutionImport)
class ExecutionImportAdmin(admin.ModelAdmin):
    list_display = ('reference', 'statut', 'total', 'crees', 'erreurs',
                    'lance_par', 'date_execution')
    list_filter = ('statut',)
    search_fields = ('reference', 'nom_fichier', 'motif_annulation')
    date_hierarchy = 'date_execution'

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(NotificationHabilitation)
class NotificationHabilitationAdmin(admin.ModelAdmin):
    list_display = ('id', 'categorie', 'destinataire', 'titre', 'lu',
                    'date_creation')
    list_filter = ('categorie', 'lu')
    search_fields = ('titre', 'message')
    date_hierarchy = 'date_creation'

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
