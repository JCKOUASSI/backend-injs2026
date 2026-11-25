"""
Modèles de l'app groupes.
Groupe, GroupeAuditeur, ConfigGroupe et JourCours.
"""

from django.core.validators import MinValueValidator
from django.db import models


class Groupe(models.Model):
    """
    Groupe de travail au sein d'une formation.
    Chaque groupe a un nombre max d'auditeurs et une configuration horaire.
    Optionnellement, un groupe peut restreindre son rythme mensuel
    (1, 2, 3 semaines par mois, ou tout le mois). Cette contrainte
    s'ajoute en intersection à celle de la formation (AND).
    """

    class RythmeMensuel(models.TextChoices):
        UNE_SEMAINE = "1", "Une semaine par mois"
        DEUX_SEMAINES = "2", "Deux semaines par mois"
        TROIS_SEMAINES = "3", "Trois semaines par mois"
        TOUT_LE_MOIS = "4", "Tout le mois"

    formation = models.ForeignKey(
        "formations.Formation",
        on_delete=models.CASCADE,
        related_name="groupes",
    )
    nom = models.CharField(max_length=100)
    max_auditeurs = models.PositiveIntegerField(
        default=25,
        validators=[MinValueValidator(1)],
    )
    rythme_mensuel = models.CharField(
        max_length=1,
        choices=RythmeMensuel.choices,
        blank=True,
        default="",
        help_text=(
            "Cadence mensuelle du groupe. Vide ⇒ hérite du rythme mensuel "
            "défini sur la formation. Si défini, remplace (override) celui "
            "de la formation pour ce groupe."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Groupe"
        verbose_name_plural = "Groupes"
        ordering = ["formation", "nom"]
        unique_together = [("formation", "nom")]

    def __str__(self) -> str:
        return f"{self.formation.intitule} — {self.nom}"

    @property
    def nb_auditeurs(self) -> int:
        """Nombre d'auditeurs dans ce groupe."""
        cache = getattr(self, "_prefetched_objects_cache", None)
        if cache is not None and "membres" in cache:
            return len(cache["membres"])
        return self.membres.count()


class GroupeAuditeur(models.Model):
    """
    Appartenance d'un auditeur à un groupe.
    """

    groupe = models.ForeignKey(
        Groupe,
        on_delete=models.CASCADE,
        related_name="membres",
    )
    auditeur = models.ForeignKey(
        "auditeurs.Auditeur",
        on_delete=models.CASCADE,
        related_name="groupes",
    )

    class Meta:
        verbose_name = "Membre du groupe"
        verbose_name_plural = "Membres du groupe"
        unique_together = [("groupe", "auditeur")]

    def __str__(self) -> str:
        return f"{self.auditeur} → {self.groupe.nom}"


class ConfigGroupe(models.Model):
    """
    Configuration horaire d'un groupe (horaires matin/après-midi).
    Pré-remplie depuis ParametreGeneral.
    """

    groupe = models.OneToOneField(
        Groupe,
        on_delete=models.CASCADE,
        related_name="config",
    )
    matin_actif = models.BooleanField(default=True)
    matin_heure_debut = models.TimeField(default="08:00")
    matin_heure_fin = models.TimeField(default="12:00")
    soir_actif = models.BooleanField(default=True)
    soir_heure_debut = models.TimeField(default="13:00")
    soir_heure_fin = models.TimeField(default="17:00")

    class Meta:
        verbose_name = "Configuration du groupe"
        verbose_name_plural = "Configurations des groupes"

    def __str__(self) -> str:
        return f"Config — {self.groupe.nom}"


class JourCours(models.Model):
    """
    Jours de cours actifs pour un groupe (0=lundi … 6=dimanche).
    Pré-remplie depuis ParametreGeneral.jours_defaut.
    """

    JOURS = [
        (0, "Lundi"),
        (1, "Mardi"),
        (2, "Mercredi"),
        (3, "Jeudi"),
        (4, "Vendredi"),
        (5, "Samedi"),
        (6, "Dimanche"),
    ]

    groupe = models.ForeignKey(
        Groupe,
        on_delete=models.CASCADE,
        related_name="jours_cours",
    )
    jour = models.PositiveSmallIntegerField(choices=JOURS)

    class Meta:
        verbose_name = "Jour de cours"
        verbose_name_plural = "Jours de cours"
        unique_together = [("groupe", "jour")]
        ordering = ["jour"]

    def __str__(self) -> str:
        return f"{self.groupe.nom} — {self.get_jour_display()}"
