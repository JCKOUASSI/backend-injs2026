"""
Modèles de l'app seances.
"""

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class Seance(models.Model):
    """
    Séance de formation : une demi-journée ou journée d'un module pour un groupe.
    Générée automatiquement en fonction de la configuration du groupe.
    """

    groupe = models.ForeignKey(
        "groupes.Groupe",
        on_delete=models.CASCADE,
        related_name="seances",
    )
    module = models.ForeignKey(
        "referentiels.Module",
        on_delete=models.PROTECT,
        related_name="seances",
    )
    site_nom = models.CharField(max_length=100, blank=True, default="")
    batiment_nom = models.CharField(max_length=100, blank=True, default="")
    salle_nom = models.CharField(max_length=100, blank=True, default="")
    salle = models.ForeignKey(
        "parametrage.Salle",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="seances",
        help_text="Référence référentiel (collisions fiables) ; les champs nom restent le snapshot export.",
    )
    formateur_nom = models.CharField(max_length=150, blank=True, default="")
    formateur_prenom = models.CharField(max_length=150, blank=True, default="")
    formateur_numero = models.CharField(max_length=30, blank=True, default="")
    formateur_email = models.EmailField(blank=True, default="")
    formateur_telephone = models.CharField(max_length=30, blank=True, default="")
    formateur_organisation = models.CharField(max_length=150, blank=True, default="")
    formateur_referentiel = models.ForeignKey(
        "formations.Formateur",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="seances_planifiees",
        help_text="Référence référentiel (collisions fiables) ; les champs nom restent le snapshot export.",
    )
    date = models.DateField()
    heure_debut = models.TimeField()
    heure_fin = models.TimeField()
    duree_minutes = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        help_text="Durée calculée en minutes",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Séance"
        verbose_name_plural = "Séances"
        ordering = ["date", "heure_debut"]

    def __str__(self) -> str:
        return f"{self.groupe.nom} — {self.module.titre} — {self.date} {self.heure_debut}"

    @property
    def duree_heures(self) -> float:
        """Durée en heures."""
        return round(self.duree_minutes / 60, 2)

    @property
    def formateur_libelle(self) -> str:
        """Libellé court pour affichage (nom + prénom, ou numéro si seul)."""
        n = (self.formateur_nom or "").strip()
        p = (self.formateur_prenom or "").strip()
        if n or p:
            return f"{n} {p}".strip()
        num = (self.formateur_numero or "").strip()
        if num:
            return num
        return ""


class PlanningAuditLog(models.Model):
    """Journal des actions de planification pour assurer la traçabilité."""

    class Action(models.TextChoices):
        GENERATE = "GENERATE", "Génération planning"
        EXPORT = "EXPORT", "Export Excel"
        CREATE = "CREATE", "Création séance"
        UPDATE = "UPDATE", "Modification séance"
        DELETE = "DELETE", "Suppression séance"

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="planning_audit_logs",
    )
    action = models.CharField(max_length=20, choices=Action.choices)
    groupe = models.ForeignKey(
        "groupes.Groupe",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="planning_audit_logs",
    )
    seance = models.ForeignKey(
        Seance,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Audit planning"
        verbose_name_plural = "Audit planning"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        actor = self.actor.username if self.actor_id else "SYSTEM"
        return f"{self.get_action_display()} par {actor} ({self.created_at:%d/%m/%Y %H:%M})"


class PlanningRun(models.Model):
    """Rapport persisté d'une génération de planning (formation entière)."""

    class Statut(models.TextChoices):
        EN_COURS = "running", "En cours"
        TERMINE = "done", "Terminé"
        ERREUR = "error", "Erreur"

    formation = models.ForeignKey(
        "formations.Formation",
        on_delete=models.CASCADE,
        related_name="planning_runs",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="planning_runs",
    )
    mode = models.CharField(max_length=32, default="best_effort")
    statut = models.CharField(max_length=16, choices=Statut.choices, default=Statut.EN_COURS)
    synthese = models.JSONField(default=dict, blank=True)
    groupes = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Rapport de planning"
        verbose_name_plural = "Rapports de planning"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Planning {self.formation_id} — {self.get_statut_display()} ({self.created_at:%d/%m/%Y %H:%M})"
