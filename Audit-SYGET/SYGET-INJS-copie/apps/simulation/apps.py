from django.apps import AppConfig


class SimulationConfig(AppConfig):
    """Configuration de l'app simulation (outil de dimensionnement)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.simulation"
    verbose_name = "Simulation"
