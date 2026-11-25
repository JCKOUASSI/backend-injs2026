"""
Modèles de l'app parametrage.
Contient les référentiels configurables par l'utilisateur :
Grade, Vague, ParametreGeneral, ModuleTypeFormation.
"""

from __future__ import annotations

from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
from django.db import models


class Grade(models.Model):
    """
    Grade des auditeurs (ex: A3, A4, B3, C3).
    Utilisé à l'import pour la détection automatique et au tri des groupes.
    Configurable par l'utilisateur dans le paramétrage.

    Les grades sont triés par :
    1. Ordre (1, 2, 3...)
    2. Libellé (A3, A4, B3...)
    """

    libelle = models.CharField(max_length=20, unique=True, help_text="Ex: A3, A4, B3, B4, C3, C4, D3, D4")
    ordre = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        help_text="Ordre d'affichage et de tri (1=premier, 2=deuxième, etc.)",
    )
    actif = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Grade"
        verbose_name_plural = "Grades"
        ordering = ["ordre", "libelle"]

    def __str__(self) -> str:
        return self.libelle


class Vague(models.Model):
    """
    Label de vague prédéfini (ex: Vague 1, 2024-A).
    Proposé en liste déroulante à la création d'une formation.
    Configurable par l'utilisateur dans le paramétrage.
    """

    libelle = models.CharField(max_length=50, unique=True)
    actif = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Vague"
        verbose_name_plural = "Vagues"
        ordering = ["libelle"]

    def __str__(self) -> str:
        return self.libelle


class Site(models.Model):
    """Site physique configurable dans le paramétrage."""

    nom = models.CharField(max_length=100)
    actif = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Site"
        verbose_name_plural = "Sites"
        ordering = ["nom"]

    def __str__(self) -> str:
        return self.nom

    def clean(self) -> None:
        """Empêche la désactivation si des bâtiments actifs existent."""
        super().clean()
        if self.pk and not self.actif and self.batiments.filter(actif=True).exists():
            raise ValidationError(
                {"actif": "Impossible de désactiver ce site : des bâtiments actifs y sont rattachés."}
            )

    def save(self, *args, **kwargs):
        """Valide les contraintes métier avant sauvegarde."""
        self.full_clean()
        return super().save(*args, **kwargs)


class PeriodeDisponibiliteSite(models.Model):
    """
    Plage [date_debut, date_fin] pendant laquelle un site est disponible pour accueillir
    des séances. Un site peut posséder plusieurs périodes. Si un site n'a aucune période
    définie, il est considéré comme **toujours disponible** (rétrocompatibilité).
    """

    site = models.ForeignKey(
        Site,
        on_delete=models.CASCADE,
        related_name="periodes_disponibilite",
    )
    date_debut = models.DateField()
    date_fin = models.DateField()

    class Meta:
        verbose_name = "Période de disponibilité d'un site"
        verbose_name_plural = "Périodes de disponibilité des sites"
        ordering = ["site__nom", "date_debut"]

    def __str__(self) -> str:
        return f"{self.site.nom} : {self.date_debut:%d/%m/%Y} → {self.date_fin:%d/%m/%Y}"

    def clean(self) -> None:
        super().clean()
        if self.date_debut and self.date_fin and self.date_fin < self.date_debut:
            raise ValidationError({"date_fin": "La date de fin doit être postérieure ou égale à la date de début."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class Batiment(models.Model):
    """Bâtiment configurable dans le paramétrage."""

    site = models.ForeignKey(
        Site,
        on_delete=models.CASCADE,
        related_name="batiments",
        null=True,
        blank=True,
    )
    nom = models.CharField(max_length=100)
    actif = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Bâtiment"
        verbose_name_plural = "Bâtiments"
        ordering = ["nom"]
        unique_together = [("site", "nom")]

    def __str__(self) -> str:
        if self.site_id:
            return f"{self.site.nom} / {self.nom}"
        return self.nom

    def clean(self) -> None:
        """Empêche la désactivation si des salles actives existent."""
        super().clean()
        if self.pk and not self.actif and self.salles.filter(actif=True).exists():
            raise ValidationError(
                {"actif": "Impossible de désactiver ce bâtiment : des salles actives y sont rattachées."}
            )

    def save(self, *args, **kwargs):
        """Valide les contraintes métier avant sauvegarde."""
        self.full_clean()
        return super().save(*args, **kwargs)


class Salle(models.Model):
    """Salle configurable dans le paramétrage."""

    batiment = models.ForeignKey(
        Batiment,
        on_delete=models.CASCADE,
        related_name="salles",
        null=True,
        blank=True,
    )
    nom = models.CharField(max_length=100, unique=True)
    capacite_max = models.PositiveIntegerField(
        default=25,
        validators=[MinValueValidator(1)],
        help_text="Capacité maximale d'accueil de la salle",
    )
    actif = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Salle"
        verbose_name_plural = "Salles"
        ordering = ["nom"]
        unique_together = [("batiment", "nom")]

    def __str__(self) -> str:
        if self.batiment_id:
            return f"{self.batiment.nom} / {self.nom}"
        return self.nom


PARAMETRES_PLANIFICATION_FIELD_NAMES = (
    "max_auditeurs_groupe_defaut",
    "groupes_auto_mixage_grades",
    "matin_heure_debut_defaut",
    "matin_heure_fin_defaut",
    "soir_heure_debut_defaut",
    "soir_heure_fin_defaut",
    "jours_defaut",
    "duree_seance_defaut_minutes",
    "max_seances_par_jour_defaut",
    "max_salles_simultanees_module",
    "tolerance_capacite_salle",
    "verrouiller_salle_groupe_formation",
    "repartir_reliquat_sur_seances",
    "poids_score_ecart_capacite",
    "poids_score_rotation_module",
    "poids_score_equilibrage_global",
)


class ParametresPlanificationMixin(models.Model):
    """Champs de planification partagés entre le modèle global et le modèle par formation."""

    max_auditeurs_groupe_defaut = models.PositiveIntegerField(default=25, validators=[MinValueValidator(1)])
    groupes_auto_mixage_grades = models.BooleanField(
        default=False,
        help_text=(
            "Génération auto des groupes : autoriser plusieurs grades dans un même groupe "
            "au sein d'une même catégorie (répartition tournante). "
            "Désactivé = un groupe par grade."
        ),
    )
    matin_heure_debut_defaut = models.TimeField(default="08:00")
    matin_heure_fin_defaut = models.TimeField(default="12:00")
    soir_heure_debut_defaut = models.TimeField(default="13:00")
    soir_heure_fin_defaut = models.TimeField(default="17:00")
    jours_defaut = models.JSONField(
        default=list,
        help_text="Liste des entiers 0-6 (0=lundi). Ex: [0,1,2,3,4]",
    )
    duree_seance_defaut_minutes = models.PositiveIntegerField(
        default=240,
        validators=[MinValueValidator(30)],
        help_text="Durée standard d'une séance en minutes",
    )
    max_seances_par_jour_defaut = models.PositiveIntegerField(
        default=2,
        validators=[MinValueValidator(1)],
        help_text="Nombre maximal de séances autorisées par groupe et par jour",
    )
    max_salles_simultanees_module = models.PositiveIntegerField(
        default=10,
        validators=[MinValueValidator(1)],
        help_text=(
            "Nombre maximal de salles différentes pouvant accueillir le même module "
            "sur une même journée (entre groupes d'une même formation)."
        ),
    )
    tolerance_capacite_salle = models.PositiveIntegerField(
        default=0,
        help_text=(
            "Tolérance (auditeurs) pour le veto de capacité salle : une salle est exclue "
            "si capacite_max < effectif − tolerance. 0 = veto strict (capacité ≥ effectif). "
            "Augmenter pour autoriser une légère surcharge (ex. 2 → tolère 2 auditeurs en trop)."
        ),
    )
    verrouiller_salle_groupe_formation = models.BooleanField(
        default=False,
        help_text=(
            "Génération auto des séances : si activé, la première salle attribuée à un groupe "
            "(premier module planifié) est verrouillée pour TOUS les modules suivants de ce "
            "groupe, du début à la fin de la formation."
        ),
    )
    repartir_reliquat_sur_seances = models.BooleanField(
        default=False,
        help_text=(
            "Génération auto des séances : si des heures n'ont pas pu être planifiées sur un "
            "module, étendre les séances existantes du module pour absorber le reliquat. "
            "Maximum +1 h par séance, en commençant par +30 min, puis +30 min supplémentaires."
        ),
    )
    poids_score_ecart_capacite = models.PositiveIntegerField(
        default=10,
        validators=[MinValueValidator(1)],
        help_text="Poids du critère de proximité de capacité lors du choix de salle",
    )
    poids_score_rotation_module = models.PositiveIntegerField(
        default=2,
        validators=[MinValueValidator(1)],
        help_text="Poids du critère de rotation des salles pour un même module",
    )
    poids_score_equilibrage_global = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        help_text="Poids du critère d'équilibrage global d'usage des salles",
    )

    class Meta:
        abstract = True


def copier_parametres_planification(source, cible) -> None:
    """Copie les champs de planification d'une instance vers une autre."""
    for field_name in PARAMETRES_PLANIFICATION_FIELD_NAMES:
        setattr(cible, field_name, getattr(source, field_name))


class ParametreGeneral(ParametresPlanificationMixin):
    """
    Paramètres globaux de l'application — singleton (une seule ligne en base).
    Fournit les valeurs par défaut pré-remplies dans les formulaires de création.

    Champs :
    - max_auditeurs_groupe_defaut : pré-remplit max_auditeurs à la création d'un groupe
    - matin_heure_debut_defaut    : pré-remplit ConfigGroupe.matin_heure_debut
    - matin_heure_fin_defaut      : pré-remplit ConfigGroupe.matin_heure_fin
    - soir_heure_debut_defaut     : pré-remplit ConfigGroupe.soir_heure_debut
    - soir_heure_fin_defaut       : pré-remplit ConfigGroupe.soir_heure_fin
    - jours_defaut                : JSON list des int (0=lundi..6=dim) pré-cochés
    - duree_seance_defaut_minutes : durée standard d'une séance (par défaut 240 min)
    - max_seances_par_jour_defaut : nombre maximal de séances par groupe et par jour
    - max_salles_simultanees_module : nb max de salles pouvant accueillir un même module le même jour
    - poids_score_ecart_capacite  : poids du critère "capacité la plus proche"
    - poids_score_rotation_module : poids du critère "rotation des salles par module"
    - poids_score_equilibrage_global : poids du critère "équilibrage global des salles"
    """

    marge_simulation_pct = models.PositiveIntegerField(
        default=5,
        validators=[MinValueValidator(0)],
        help_text=(
            "Marge ajoutée au plancher théorique dans la simulation (en %). "
            "Minimum recommandé = plancher × (1 + marge/100). "
            "20 % = valeur par défaut conservatrice. "
            "Réduire à 5–10 % si les salles sont bien dimensionnées et les formations peu concurrentes."
        ),
    )

    class Meta:
        verbose_name = "Paramètre général"
        verbose_name_plural = "Paramètres généraux"

    def __str__(self) -> str:
        return "Paramètres généraux"

    def save(self, *args, **kwargs) -> None:
        """Garantit le singleton : toujours pk=1."""
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get(cls) -> "ParametreGeneral":
        """Retourne l'instance unique, la crée si elle n'existe pas."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class ParametreFormation(ParametresPlanificationMixin):
    """
    Paramètres de planification propres à une formation.
    Chaque formation possède sa propre configuration, indépendante des autres.
    """

    formation = models.OneToOneField(
        "formations.Formation",
        on_delete=models.CASCADE,
        related_name="parametres",
    )

    class Meta:
        verbose_name = "Paramètres de formation"
        verbose_name_plural = "Paramètres de formation"

    def __str__(self) -> str:
        return f"Paramètres — {self.formation}"

    @classmethod
    def creer_depuis_generaux(cls, formation, generaux: ParametreGeneral | None = None) -> "ParametreFormation":
        """Initialise les paramètres d'une formation à partir du modèle global."""
        generaux = generaux or ParametreGeneral.get()
        params = cls(formation=formation)
        copier_parametres_planification(generaux, params)
        params.save()
        return params

    @classmethod
    def get_for_formation(cls, formation_id: int) -> "ParametreFormation":
        """Retourne les paramètres d'une formation, en les créant depuis le modèle global si besoin."""
        params = cls.objects.filter(formation_id=formation_id).first()
        if params is not None:
            return params
        from apps.formations.models import Formation

        formation = Formation.objects.get(pk=formation_id)
        return cls.creer_depuis_generaux(formation)


def get_parametres_pour_formation(formation_id: int) -> ParametreFormation:
    """Point d'entrée unique pour récupérer les paramètres de planification d'une formation."""
    return ParametreFormation.get_for_formation(formation_id)


class ModuleTypeFormation(models.Model):
    """
    Association Module ↔ TypeFormation avec volume horaire par défaut.
    Créée dans le paramétrage, utilisée comme valeur pré-remplie
    lors de la création d'un FormationModule.

    Exemple : "Culture Civique" → FAC : 20h par défaut, FAB : 30h par défaut
    """

    module = models.ForeignKey(
        "referentiels.Module",
        on_delete=models.CASCADE,
        related_name="type_associations",
    )
    type_formation = models.ForeignKey(
        "referentiels.TypeFormation",
        on_delete=models.CASCADE,
        related_name="module_associations",
    )
    grade_cible = models.CharField(
        max_length=20,
        blank=True,
        default="",
        help_text="Grade ciblé (laisser vide pour tous les grades)",
    )
    volume_horaire_defaut = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        help_text="Volume horaire par défaut en heures pour ce type de formation",
    )

    class Meta:
        verbose_name = "Association module / type"
        verbose_name_plural = "Associations modules / types"
        unique_together = [("module", "type_formation", "grade_cible")]

    def __str__(self) -> str:
        suffix_grade = f" [{self.grade_cible}]" if self.grade_cible else ""
        return f"{self.module.titre} → {self.type_formation.code}{suffix_grade} : " f"{self.volume_horaire_defaut}h"


class JourFerie(models.Model):
    """Jour non ouvré à exclure automatiquement de la planification."""

    date = models.DateField(unique=True)
    libelle = models.CharField(max_length=120)
    actif = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Jour férié"
        verbose_name_plural = "Jours fériés"
        ordering = ["date"]

    def __str__(self) -> str:
        return f"{self.date:%d/%m/%Y} — {self.libelle}"
