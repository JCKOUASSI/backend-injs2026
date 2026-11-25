"""Modèles de persistance pour la simulation."""

from django.conf import settings
from django.db import models


class ScenarioSimulation(models.Model):
    """Scénario de simulation sauvegardé par un utilisateur."""

    auteur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="scenarios_simulation",
    )
    libelle = models.CharField(max_length=200)
    payload = models.JSONField(help_text="Paramètres du formset (liste de blocs formation).")
    marge_pct = models.PositiveSmallIntegerField(default=20)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Scénario de simulation"
        verbose_name_plural = "Scénarios de simulation"
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return self.libelle
