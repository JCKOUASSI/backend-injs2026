"""
Modèles de l'app formations.
Formation et FormationModule constituent le programme pédagogique.
"""

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class Formation(models.Model):
    class CreneauMode(models.TextChoices):
        MATIN = "matin", "Matin uniquement"
        SOIR = "soir", "Soir uniquement"
        MATIN_ET_SOIR = "matin_et_soir", "Matin et soir"

    class RythmeMensuel(models.TextChoices):
        UNE_SEMAINE = "1", "Une semaine par mois"
        DEUX_SEMAINES = "2", "Deux semaines par mois"
        TROIS_SEMAINES = "3", "Trois semaines par mois"
        TOUT_LE_MOIS = "4", "Tout le mois"

    """
    Formation : entité principale regroupant des auditeurs, des modules
    et des groupes de travail. Identifiée par son type, son intitulé et sa vague.
    """

    type_formation = models.ForeignKey(
        "referentiels.TypeFormation",
        on_delete=models.PROTECT,
        related_name="formations",
    )
    intitule = models.CharField(max_length=200)
    vague = models.CharField(max_length=50, blank=True)
    date_debut = models.DateField()
    date_fin = models.DateField()
    planning_union_sites_programme = models.BooleanField(
        default=False,
        help_text=(
            "Si activé, pour chaque module sans liste de salles explicites, le dispatch utilise "
            "la réunion des sites déclarés sur tous les modules du programme (pas seulement les sites "
            "du module courant). Utile pour dé-saturer un module cantonné à un seul site."
        ),
    )
    rythme_mensuel = models.CharField(
        max_length=1,
        choices=RythmeMensuel.choices,
        default=RythmeMensuel.TOUT_LE_MOIS,
        help_text="Contraint le nombre de semaines planifiables par mois pour cette formation.",
    )
    responsable = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="formations_responsables",
        help_text="Gestionnaire propriétaire de cette formation (visibilité et droits d'édition).",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Formation"
        verbose_name_plural = "Formations"
        ordering = ["-date_debut", "intitule"]

    def __str__(self) -> str:
        return f"{self.intitule} ({self.type_formation.code})"

    @property
    def nb_inscrits(self) -> int:
        """Nombre d'auditeurs distincts inscrits aux modules de cette formation."""
        return self.inscriptions.values("auditeur_id").distinct().count()

    @property
    def nb_groupes(self) -> int:
        """Nombre de groupes rattachés à cette formation."""
        return self.groupes.count()


class FormationPeriode(models.Model):
    """
    Période pédagogique au sein d'une formation.
    Les modules du programme sont rattachés à une période ; le rythme mensuel
    de la période s'applique à leur planification (sauf override groupe).
    """

    formation = models.ForeignKey(
        Formation,
        on_delete=models.CASCADE,
        related_name="periodes",
    )
    libelle = models.CharField(max_length=100)
    date_debut = models.DateField()
    date_fin = models.DateField()
    rythme_mensuel = models.CharField(
        max_length=1,
        choices=Formation.RythmeMensuel.choices,
        default=Formation.RythmeMensuel.TOUT_LE_MOIS,
        help_text="Contraint le nombre de semaines planifiables par mois pour les modules de cette période.",
    )
    ordre = models.PositiveSmallIntegerField(
        default=0,
        help_text="Ordre d'affichage des périodes sur la fiche formation.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Période de formation"
        verbose_name_plural = "Périodes de formation"
        ordering = ["formation", "ordre", "date_debut", "pk"]

    def __str__(self) -> str:
        return f"{self.formation.intitule} — {self.libelle}"


class FormationModule(models.Model):
    """
    Association Formation ↔ Module avec dates d'enseignement et volume horaire.
    Représente le programme pédagogique d'une formation.
    Chaque module a sa propre période au sein de la formation.
    """

    formation = models.ForeignKey(
        Formation,
        on_delete=models.CASCADE,
        related_name="modules",
    )
    periode = models.ForeignKey(
        FormationPeriode,
        on_delete=models.PROTECT,
        related_name="modules",
        help_text="Période d'enseignement à laquelle ce module appartient.",
    )
    module = models.ForeignKey(
        "referentiels.Module",
        on_delete=models.PROTECT,
        related_name="formation_associations",
    )
    volume_horaire = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
        help_text="Volume en heures si fixe ; vide = volume issu du paramétrage (type × module × grade du groupe).",
    )
    grade_cible = models.CharField(
        max_length=500,
        blank=True,
        default="",
        help_text="Grade concerné par ce module (ex: A4, A3, B, C, D)",
    )
    creneau_mode = models.CharField(
        max_length=20,
        choices=Formation.CreneauMode.choices,
        default=Formation.CreneauMode.MATIN_ET_SOIR,
        help_text="Définit si ce module peut être planifié le matin, le soir, ou sur les deux créneaux.",
    )
    site_nombre = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        help_text="Nombre de sites mobilisés pour ce module",
    )
    site_nom = models.CharField(
        max_length=500,
        blank=True,
        default="",
        help_text="Nom(s) des sites (CSV)",
    )
    batiment_nombre = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        help_text="Nombre de bâtiments mobilisés pour ce module",
    )
    batiment_nom = models.CharField(
        max_length=500,
        blank=True,
        default="",
        help_text="Nom(s) des bâtiments (CSV)",
    )
    salle_nombre = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text=(
            "Nombre max. de salles prises dans le pool pour le dispatch si les salles ne sont pas "
            "listées explicitement : 0 = toutes les salles actives du/des site(s), N > 0 = les N "
            "premières du référentiel (ordre alphabétique). Ignoré lorsque des salles sont nommées dans "
            "`salle_nom`."
        ),
    )
    salle_nom = models.CharField(
        max_length=500,
        blank=True,
        default="",
        help_text="Nom(s) des salles (CSV)",
    )
    formateur_nom = models.CharField(
        max_length=150,
        blank=True,
        default="",
        help_text="Formateur affecté au module (un seul nom)",
    )
    formateur_prenom = models.CharField(
        max_length=150,
        blank=True,
        default="",
        help_text="Prénom du formateur affecté au module",
    )
    formateur_numero = models.CharField(
        max_length=30,
        blank=True,
        default="",
        help_text="Numéro de téléphone du formateur",
    )
    formateur_email = models.EmailField(
        blank=True,
        default="",
        help_text="Email du formateur",
    )
    formateur_telephone = models.CharField(
        max_length=30,
        blank=True,
        default="",
        help_text="Téléphone du formateur",
    )
    formateur_organisation = models.CharField(
        max_length=150,
        blank=True,
        default="",
        help_text="Organisation du formateur",
    )
    date_debut = models.DateField(
        null=True,
        blank=True,
        help_text="Date de début d'enseignement de ce module",
    )
    date_fin = models.DateField(
        null=True,
        blank=True,
        help_text="Date de fin d'enseignement de ce module",
    )

    class Meta:
        verbose_name = "Module de formation"
        verbose_name_plural = "Modules de formation"
        ordering = ["date_debut", "module__titre"]

    def __str__(self) -> str:
        suffix_grade = f" [{self.grade_cible}]" if self.grade_cible else ""
        vol = f"{self.volume_horaire}h" if self.volume_horaire is not None else "param. × grade"
        return f"{self.formation.intitule} — {self.module.titre}{suffix_grade} ({vol})"

    def save(self, *args, **kwargs):
        """Rattache une période par défaut et aligne les dates module sur la période."""
        if not self.periode_id and self.formation_id:
            periode = (
                FormationPeriode.objects.filter(formation_id=self.formation_id)
                .order_by("ordre", "date_debut", "pk")
                .first()
            )
            if periode is None:
                formation = (
                    self.formation
                    if getattr(self, "formation_id", None) and hasattr(self, "formation") and self.formation
                    else Formation.objects.get(pk=self.formation_id)
                )
                periode = FormationPeriode.objects.create(
                    formation_id=self.formation_id,
                    libelle="Période 1",
                    date_debut=formation.date_debut,
                    date_fin=formation.date_fin,
                    rythme_mensuel=formation.rythme_mensuel,
                    ordre=0,
                )
            self.periode_id = periode.pk
        if self.periode_id:
            if not hasattr(self, "periode") or self.periode is None:
                self.periode = FormationPeriode.objects.get(pk=self.periode_id)
            self.date_debut = self.periode.date_debut
            self.date_fin = self.periode.date_fin
        super().save(*args, **kwargs)

    @property
    def nb_inscrits(self) -> int:
        """Nombre d'auditeurs inscrits à ce module."""
        return self.inscriptions.values("auditeur_id").distinct().count()


class Formateur(models.Model):
    """
    Référentiel global des formateurs (import Excel, sans lien formation ni module).
    Les rattachements groupe/module se font via AffectationFormateurGroupe.
    """

    numero = models.CharField(max_length=30)
    nom = models.CharField(max_length=150)
    prenom = models.CharField(max_length=150)
    email = models.EmailField(blank=True, default="")
    telephone = models.CharField(max_length=30, blank=True, default="")
    organisation = models.CharField(max_length=150, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    specialites = models.ManyToManyField(
        "referentiels.Specialite",
        related_name="formateurs",
        help_text="Au moins une spécialité obligatoire ; utilisée pour le dispatch des séances.",
    )

    class Meta:
        verbose_name = "Formateur"
        verbose_name_plural = "Formateurs"
        ordering = ["nom", "prenom"]
        constraints = [
            models.UniqueConstraint(fields=["numero"], name="uniq_formateur_numero_global"),
        ]

    def __str__(self) -> str:
        return f"{self.nom} {self.prenom} ({self.numero})"


class AffectationFormateurGroupe(models.Model):
    """
    Affectation d'un formateur importé à un groupe pour un module donné.

    Règle métier : au plus un formateur pour un couple (groupe, module), choisi selon la
    spécialité du module et le référentiel formateurs.
    """

    groupe = models.ForeignKey(
        "groupes.Groupe",
        on_delete=models.CASCADE,
        related_name="affectations_formateurs",
    )
    module = models.ForeignKey(
        "referentiels.Module",
        on_delete=models.PROTECT,
        related_name="affectations_formateurs",
    )
    formateur = models.ForeignKey(
        Formateur,
        on_delete=models.CASCADE,
        related_name="affectations_groupes",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Affectation formateur/groupe"
        verbose_name_plural = "Affectations formateurs/groupes"
        ordering = ["groupe__nom", "module__titre", "formateur__nom", "formateur__prenom"]
        constraints = [
            models.UniqueConstraint(
                fields=["groupe", "module"],
                name="uniq_formateur_par_groupe_module",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.groupe.nom} — {self.module.titre} — {self.formateur.nom} {self.formateur.prenom}"


class ResponsableUnitePedagogique(models.Model):
    """
    Lie un utilisateur (rôle RUP_EDT) à un module du référentiel (``referentiels.Module``).

    Au sens métier, la « spécialité » du RUP est le **module** (matière) présent sur
    la plateforme — ex. Culture Civique, Informatique. Un RUP ne couvre qu'un seul
    module : il voit les formations où ce module figure au programme et affecte les
    formateurs pour ce module dans tous les groupes.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="responsabilite_up",
    )
    module = models.ForeignKey(
        "referentiels.Module",
        on_delete=models.PROTECT,
        related_name="responsables_up",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Responsable d'unité pédagogique"
        verbose_name_plural = "Responsables d'unités pédagogiques"
        ordering = ["module__titre", "user__username"]

    def __str__(self) -> str:
        return f"{self.user} — {self.module.titre}"


class Inscription(models.Model):
    """
    Inscription d'un auditeur à un module de formation.
    Le lien vers la formation est déduit du module.
    """

    formation = models.ForeignKey(
        Formation,
        on_delete=models.CASCADE,
        related_name="inscriptions",
    )
    formation_module = models.ForeignKey(
        FormationModule,
        on_delete=models.CASCADE,
        related_name="inscriptions",
        null=True,
        blank=True,
    )
    auditeur = models.ForeignKey(
        "auditeurs.Auditeur",
        on_delete=models.CASCADE,
        related_name="inscriptions",
    )
    date_inscription = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Inscription"
        verbose_name_plural = "Inscriptions"
        unique_together = [("formation_module", "auditeur")]

    def save(self, *args, **kwargs):
        """Synchronise systématiquement la formation depuis le module choisi."""
        if self.formation_module_id:
            self.formation_id = self.formation_module.formation_id
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        if self.formation_module_id:
            return f"{self.auditeur} inscrit au module {self.formation_module.module.titre}"
        return f"{self.auditeur} inscrit à {self.formation.intitule}"
