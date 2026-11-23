from django.contrib import admin
from .models import ConfigAlerteSeuil, Rapport, ObservationQualitative, SignatureRapport, NotificationRapport


@admin.register(ConfigAlerteSeuil)
class ConfigAlerteSeuilAdmin(admin.ModelAdmin):
    list_display = ('indicateur', 'seuil_avertissement', 'seuil_critique', 'actif', 'updated_at')
    list_filter  = ('actif',)


class ObservationInline(admin.TabularInline):
    model = ObservationQualitative
    extra = 0


class SignatureInline(admin.TabularInline):
    model = SignatureRapport
    extra = 0
    readonly_fields = ('date_signature', 'hash_rapport')


@admin.register(Rapport)
class RapportAdmin(admin.ModelAdmin):
    list_display  = ('titre', 'type', 'statut', 'periode_debut', 'periode_fin', 'generateur', 'created_at')
    list_filter   = ('type', 'statut')
    search_fields = ('titre',)
    inlines       = [ObservationInline, SignatureInline]
    readonly_fields = ('created_at', 'updated_at')


@admin.register(NotificationRapport)
class NotificationRapportAdmin(admin.ModelAdmin):
    list_display = ('rapport_titre', 'evenement', 'destinataire', 'auteur', 'lu', 'created_at')
    list_filter = ('evenement', 'lu')
    readonly_fields = ('created_at',)
