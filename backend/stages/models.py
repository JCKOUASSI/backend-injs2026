"""Modèles du lot L5 — Stages et conventions.

Conception validée (Prompt 14) :
  - OrganismeAccueil : organisation externe accueillant l'étudiant (entreprise,
    institution, ONG…). Réutilisable via FK PROTECT.
  - TuteurExterne : encadrant professionnel au sein de l'organisme.
  - ConventionStage : rattachée à DossierEtudiant + AnneeAcademique + organisme +
    tuteur externe + encadrant interne (Formateur). Workflow à 9 états contrôlé
    par le service, transitions journalisées via scolarite.JournalScolarite.
  - EvaluationStage : une seule par convention, créée à la fin du stage par le
    tuteur externe, complétée par l'encadrant interne (validation).

Aucune duplication d'identité étudiante : DossierEtudiant via Participant.matricule
reste la source de vérité (cf. règle L1 / socle scolarite).
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class OrganismeAccueil(models.Model):
    """Organisation externe qui accueille un étudiant en stage."""
    nom = models.CharField(max_length=255, unique=True)
    raison_sociale = models.CharField(max_length=255, blank=True, default='')
    adresse = models.TextField(blank=True, default='')
    ville = models.CharField(max_length=100, blank=True, default='')
    pays = models.CharField(max_length=100, default="Côte d'Ivoire")
    contact_nom = models.CharField(max_length=150, blank=True, default='')
    contact_telephone = models.CharField(max_length=30, blank=True, default='')
    contact_email = models.EmailField(blank=True, default='')
    actif = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['nom']
        verbose_name = "LMD – Organisme d'accueil"
        verbose_name_plural = "LMD – Organismes d'accueil"

    def __str__(self):
        return self.nom


class TuteurExterne(models.Model):
    """Encadrant professionnel au sein d'un organisme d'accueil."""
    organisme = models.ForeignKey(
        OrganismeAccueil, on_delete=models.CASCADE, related_name='tuteurs',
    )
    nom = models.CharField(max_length=100)
    prenom = models.CharField(max_length=100, blank=True, default='')
    fonction = models.CharField(max_length=150, blank=True, default='')
    email = models.EmailField(blank=True, default='')
    telephone = models.CharField(max_length=30, blank=True, default='')
    actif = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['organisme__nom', 'nom', 'prenom']
        verbose_name = "LMD – Tuteur externe"
        verbose_name_plural = "LMD – Tuteurs externes"
        unique_together = ('organisme', 'nom', 'prenom')

    def __str__(self):
        return f'{self.nom} {self.prenom}'.strip() + f' ({self.organisme})'


class ConventionStage(models.Model):
    """Convention de stage LMD d'un étudiant pour une année académique.

    Workflow contrôlé par ``stages.services`` — pas d'édition libre du statut ;
    toute transition est journalisée via ``scolarite.JournalScolarite``.
    """

    class Statut(models.TextChoices):
        BROUILLON = 'BROUILLON', 'Brouillon'
        SOUMISE = 'SOUMISE', 'Soumise (à valider)'
        VALIDEE = 'VALIDEE', 'Validée (admin)'
        REFUSEE = 'REFUSEE', 'Refusée'
        SIGNEE = 'SIGNEE', 'Signée'
        EN_COURS = 'EN_COURS', 'En cours'
        TERMINEE = 'TERMINEE', 'Terminée (rapport rendu)'
        SOUTENUE = 'SOUTENUE', 'Soutenue'
        VALIDEE_JURY = 'VALIDEE_JURY', 'Validée par jury'
        ARCHIVEE = 'ARCHIVEE', 'Archivée'

    # Identité étudiante (la FK PROTECT évite la suppression d'un DossierEtudiant rattaché)
    etudiant = models.ForeignKey(
        'scolarite.DossierEtudiant', on_delete=models.PROTECT, related_name='conventions_stage',
    )
    annee_academique = models.ForeignKey(
        'scolarite.AnneeAcademique', on_delete=models.PROTECT, related_name='conventions_stage',
    )
    ref_formation = models.ForeignKey(
        'formations.RefFormation', on_delete=models.PROTECT, related_name='conventions_stage',
        null=True, blank=True,
    )

    # Organisme d'accueil et tuteurs
    organisme = models.ForeignKey(
        OrganismeAccueil, on_delete=models.PROTECT, related_name='conventions',
    )
    tuteur_externe = models.ForeignKey(
        TuteurExterne, on_delete=models.SET_NULL, related_name='conventions',
        null=True, blank=True,
    )
    encadrant_interne = models.ForeignKey(
        'authentication.User', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='conventions_encadrees',
        help_text="Encadrant interne INJS (rôle ENCADRANT).",
    )

    # Période et contenu du stage
    intitule = models.CharField(max_length=255)
    sujet = models.TextField()
    objectifs = models.TextField(blank=True, default='')
    date_debut = models.DateField()
    date_fin = models.DateField()
    lieu = models.CharField(max_length=150, blank=True, default='')

    # Workflow
    statut = models.CharField(max_length=20, choices=Statut.choices, default=Statut.BROUILLON)
    motif_refus = models.TextField(blank=True, default='')
    date_soumission = models.DateTimeField(null=True, blank=True)
    date_validation_admin = models.DateTimeField(null=True, blank=True)
    valide_par = models.ForeignKey(
        'authentication.User', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='conventions_validees',
    )
    date_signature = models.DateTimeField(null=True, blank=True)
    date_debut_effectif = models.DateField(null=True, blank=True)
    date_fin_effective = models.DateField(null=True, blank=True)
    date_soutenance = models.DateTimeField(null=True, blank=True)
    note_rapport = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0)],
    )
    note_soutenance = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0)],
    )
    mention = models.CharField(max_length=30, blank=True, default='')
    rapport_fichier = models.FileField(
        upload_to='stages/rapports/', max_length=300, null=True, blank=True,
    )
    convention_pdf = models.FileField(
        upload_to='stages/conventions/', max_length=300, null=True, blank=True,
    )
    cree_par = models.ForeignKey(
        'authentication.User', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='conventions_creees',
    )
    archive_par = models.ForeignKey(
        'authentication.User', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='conventions_archivees',
    )
    date_archivage = models.DateTimeField(null=True, blank=True)
    commentaires = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "LMD – Convention de stage"
        verbose_name_plural = "LMD – Conventions de stage"
        constraints = [
            models.UniqueConstraint(
                fields=['etudiant', 'annee_academique'],
                name='uniq_convention_stage_par_etudiant_annee',
                condition=~models.Q(statut='ARCHIVEE'),
                violation_error_message=(
                    "Un étudiant ne peut avoir qu'une seule convention de stage active "
                    "par année académique."
                ),
            ),
        ]

    def __str__(self):
        return f'{self.etudiant.matricule} – {self.intitule} ({self.get_statut_display()})'

    def clean(self):
        erreurs = {}
        if self.date_debut and self.date_fin and self.date_fin < self.date_debut:
            erreurs['date_fin'] = "La date de fin doit être postérieure à la date de début."
        if self.statut == self.Statut.REFUSEE and not (self.motif_refus or '').strip():
            erreurs['motif_refus'] = "Un refus doit être motivé."
        if self.date_debut_effectif and self.date_fin_effective and \
                self.date_fin_effective < self.date_debut_effectif:
            erreurs['date_fin_effective'] = (
                "La date de fin effective doit être postérieure à la date de début effectif."
            )
        if self.statut == self.Statut.VALIDEE_JURY:
            if self.note_rapport is None or self.note_soutenance is None:
                erreurs['note_rapport'] = (
                    "Validation jury : note de rapport et note de soutenance obligatoires."
                )
        if erreurs:
            raise ValidationError(erreurs)


class EvaluationStage(models.Model):
    """Évaluation finale d'un étudiant en stage par le tuteur externe.

    Une seule par convention (OneToOne). Complétée par l'encadrant interne INJS
    pour la validation finale (note de soutenance + mention).
    """

    class Mention(models.TextChoices):
        TRES_BIEN = 'TRES_BIEN', 'Très bien'
        BIEN = 'BIEN', 'Bien'
        ASSEZ_BIEN = 'ASSEZ_BIEN', 'Assez bien'
        PASSABLE = 'PASSABLE', 'Passable'
        INSUFFISANT = 'INSUFFISANT', 'Insuffisant'

    convention = models.OneToOneField(
        ConventionStage, on_delete=models.CASCADE, related_name='evaluation',
    )
    # Évaluation par le tuteur externe
    note_aptitude = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="Aptitude professionnelle /20",
        validators=[MinValueValidator(0)],
    )
    note_integration = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="Intégration dans l'équipe /20",
        validators=[MinValueValidator(0)],
    )
    note_autonomie = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="Autonomie et initiative /20",
        validators=[MinValueValidator(0)],
    )
    note_production = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="Qualité de la production /20",
        validators=[MinValueValidator(0)],
    )
    note_rapport = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="Qualité du rapport de stage /20",
        validators=[MinValueValidator(0)],
    )
    appreciation_libre = models.TextField(blank=True, default='')
    # Validation finale INJS
    note_finale = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="Note finale /20 (moyenne pondérée des critères).",
    )
    mention = models.CharField(
        max_length=15, choices=Mention.choices, blank=True, default='',
    )
    evalue_par = models.ForeignKey(
        'authentication.User', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='evaluations_stage_realisees',
        help_text="Utilisateur INJS qui a saisi l'évaluation du tuteur externe.",
    )
    valide_par = models.ForeignKey(
        'authentication.User', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='evaluations_stage_validees',
        help_text="Encadrant interne INJS qui valide la note finale.",
    )
    date_evaluation = models.DateTimeField(auto_now_add=True)
    date_validation = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-date_evaluation']
        verbose_name = "LMD – Évaluation de stage"
        verbose_name_plural = "LMD – Évaluations de stage"

    def __str__(self):
        return f'Évaluation {self.convention}'

    def clean(self):
        # Toutes les notes sont optionnelles (saisie progressive), mais si la note
        # finale est renseignée alors tous les critères doivent l'être.
        if self.note_finale is not None:
            manquants = [c for c in (
                'note_aptitude', 'note_integration', 'note_autonomie',
                'note_production', 'note_rapport',
            ) if getattr(self, c) is None]
            if manquants:
                raise ValidationError(
                    {c: "Note manquante pour calculer la note finale."
                     for c in manquants}
                )

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)


