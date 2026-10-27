from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'
    verbose_name = 'Noyau transverse (audit unifié)'

    def ready(self):
        # Branche la réplication des journaux pilotes (débrayée par flag).
        from .signals import brancher
        brancher()
