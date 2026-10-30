from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'
    verbose_name = 'Noyau transverse (audit unifié)'

    def ready(self):
        # Branche la réplication des journaux pilotes (débrayée par flag).
        from .signals import brancher
        brancher()

        # Complète l'administration pour les modèles métier non inscrits.
        # `django.contrib.admin` figure en tête d'INSTALLED_APPS : son
        # autodiscover() a déjà eu lieu, donc `admin.site.is_registered()` est
        # fiable ici. Aucun modèle déjà inscrit n'est remplacé.
        from .admin_completion import (
            completer_administration, enrichir_listes, optimiser_listes,
        )
        completer_administration()
        enrichir_listes()
        optimiser_listes()
