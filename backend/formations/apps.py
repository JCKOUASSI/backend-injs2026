from django.apps import AppConfig


class FormationsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'formations'
    verbose_name = 'Formations'

    def ready(self):
        import formations.signals  # noqa: F401
