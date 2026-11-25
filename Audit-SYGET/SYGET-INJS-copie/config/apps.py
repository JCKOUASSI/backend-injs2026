from django.apps import AppConfig


class ConfigAppConfig(AppConfig):
    """Configuration de l'app config (commandes de gestion)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "config"
    label = "config_app"
    verbose_name = "Configuration"

    def ready(self):
        """Demarre le logger Cursor en mode developpement."""
        from .cursor_agent_logger import maybe_start_cursor_logger

        maybe_start_cursor_logger()
        import config.admin  # noqa: F401 — enregistre UserAdmin Unfold + inline RUP
