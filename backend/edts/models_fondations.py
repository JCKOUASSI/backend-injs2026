"""Modèles additifs de la phase 2 GET-INJS (aucune activation du moteur).

Un calendrier non validé ne déclenche aucune génération. Les données déjà
persistées, en particulier les séances QR, restent inchangées.
"""
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q


class RevisionCalendrier(models.Model):
    """Version immuable de référence pour l'évaluation du calendrier."""

    annee_academique = models.ForeignKey(
        'scolarite.AnneeAcademique', on_delete=models.PROTECT,
        related_name='revisions_calendrier_getinjs',
    )
    numero = models.PositiveIntegerField()
    motif = models.CharField(max_length=255, blank=True, default='')
    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(
            fields=['annee_academique', 'numero'], name='edt_v2_rev_annee_num_unique',
        )]


class PeriodeAcademique(models.Model):
    """Période datée et sourcée, non officielle tant que non validée."""

    class Type(models.TextChoices):
        COURS = 'COURS', 'Cours'
        VACANCES = 'VACANCES', 'Vacances'
        EXAMENS = 'EXAMENS', 'Examens'
        FERIE = 'FERIE', 'Férié'
        FERMETURE = 'FERMETURE', 'Fermeture'

    class Portee(models.TextChoices):
        GLOBAL = 'GLOBAL', 'Toute l’année'
        FORMATION = 'FORMATION', 'Formation'
        NIVEAU = 'NIVEAU', 'Niveau'
        GROUPE = 'GROUPE', 'Groupe'

    class Validation(models.TextChoices):
        A_CONFIRMER = 'A_CONFIRMER', 'À confirmer'
        VALIDEE = 'VALIDEE', 'Validée par l’administration'

    annee_academique = models.ForeignKey(
        'scolarite.AnneeAcademique', on_delete=models.PROTECT,
        related_name='periodes_getinjs',
    )
    revision = models.ForeignKey(
        RevisionCalendrier, on_delete=models.PROTECT,
        related_name='periodes',
    )
    type = models.CharField(max_length=12, choices=Type.choices)
    portee = models.CharField(max_length=12, choices=Portee.choices, default=Portee.GLOBAL)
    formation = models.ForeignKey('formations.RefFormation', on_delete=models.PROTECT,
                                  null=True, blank=True, related_name='periodes_getinjs')
    niveau = models.ForeignKey('scolarite.Niveau', on_delete=models.PROTECT,
                               null=True, blank=True, related_name='periodes_getinjs')
    groupe = models.ForeignKey('scolarite.Groupe', on_delete=models.PROTECT,
                               null=True, blank=True, related_name='periodes_getinjs')
    date_debut = models.DateField()
    date_fin = models.DateField()
    source_document = models.CharField(max_length=255, blank=True, default='')
    fiabilite = models.CharField(max_length=20, choices=[
        ('A_RENSEIGNER', 'À renseigner'), ('CADRAGE', 'Cadrage'),
        ('MODELISE', 'Modélisé'), ('OFFICIEL', 'Officiel vérifié'),
    ], default='A_RENSEIGNER')
    statut_validation = models.CharField(
        max_length=12, choices=Validation.choices, default=Validation.A_CONFIRMER,
    )
    actif = models.BooleanField(default=True)
    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(date_fin__gte=F('date_debut')),
                                   name='edt_v2_periode_dates_valides'),
            models.CheckConstraint(condition=(
                Q(portee='GLOBAL', formation__isnull=True, niveau__isnull=True, groupe__isnull=True) |
                Q(portee='FORMATION', formation__isnull=False, niveau__isnull=True, groupe__isnull=True) |
                Q(portee='NIVEAU', formation__isnull=True, niveau__isnull=False, groupe__isnull=True) |
                Q(portee='GROUPE', formation__isnull=True, niveau__isnull=True, groupe__isnull=False)
            ), name='edt_v2_periode_portee_coherente'),
        ]
        indexes = [
            models.Index(fields=['annee_academique', 'revision', 'actif', 'date_debut', 'date_fin'],
                         name='edt_v2_periode_dates_idx'),
            models.Index(fields=['groupe', 'date_debut'], name='edt_v2_periode_groupe_idx'),
        ]

    def clean(self):
        super().clean()
        erreurs = {}
        if self.date_debut and self.date_fin and self.date_fin < self.date_debut:
            erreurs['date_fin'] = 'La fin précède le début.'
        if self.annee_academique_id and self.revision_id:
            if self.revision.annee_academique_id != self.annee_academique_id:
                erreurs['revision'] = 'La révision appartient à une autre année.'
        if self.annee_academique_id and self.date_debut and self.date_fin:
            annee = self.annee_academique
            if not (annee.date_debut <= self.date_debut <= self.date_fin <= annee.date_fin):
                erreurs['date_debut'] = 'La période doit être comprise dans l’année.'
        if self.portee == self.Portee.GROUPE and self.groupe_id:
            if self.groupe.annee_academique_id != self.annee_academique_id:
                erreurs['groupe'] = 'Le groupe appartient à une autre année.'
        if self.statut_validation == self.Validation.VALIDEE:
            if not self.source_document.strip() or self.fiabilite != 'OFFICIEL':
                erreurs['source_document'] = 'Une source officielle vérifiée est exigée.'
        if erreurs:
            raise ValidationError(erreurs)


class ExecutionLigne(models.Model):
    """Résultat technique d'un travail ; ne persiste pas le besoin institutionnel."""

    class Statut(models.TextChoices):
        PLACEE = 'PLACEE', 'Placée'
        ECHEC = 'ECHEC', 'Échec'
        A_REVOIR = 'A_REVOIR', 'À revoir'

    execution = models.ForeignKey('edts.ExecutionCampagne', on_delete=models.CASCADE,
                                   related_name='lignes_v2')
    cle_travail = models.CharField(max_length=64)
    cle_occurrence_v2 = models.CharField(max_length=64, null=True, blank=True)
    groupe = models.ForeignKey('scolarite.Groupe', on_delete=models.SET_NULL,
                               null=True, blank=True, related_name='lignes_edt_v2')
    ecue = models.ForeignKey('scolarite.ECUE', on_delete=models.SET_NULL,
                             null=True, blank=True, related_name='lignes_edt_v2')
    type_seance = models.CharField(max_length=4, choices=[
        ('CM', 'Cours magistral'), ('TD', 'Travaux dirigés'),
        ('TP', 'Travaux pratiques'), ('EXAM', 'Examen'),
    ])
    date_candidate = models.DateField(null=True, blank=True)
    statut = models.CharField(max_length=8, choices=Statut.choices)
    code_contrainte = models.CharField(max_length=80, blank=True, default='')
    score_souple = models.FloatField(null=True, blank=True)
    version_calendrier = models.PositiveIntegerField(null=True, blank=True)
    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(
            fields=['execution', 'cle_travail'], name='edt_v2_exec_ligne_unique',
        )]
        indexes = [
            models.Index(fields=['execution', 'statut', 'id'], name='edt_v2_exec_statut_idx'),
            models.Index(fields=['execution', 'groupe', 'cle_travail'],
                         name='edt_v2_exec_groupe_idx'),
        ]


class VerrouJour(models.Model):
    """Rangée à verrouiller via select_for_update avant tout placement d'un jour."""

    annee_academique = models.ForeignKey('scolarite.AnneeAcademique',
                                          on_delete=models.PROTECT, related_name='verrous_edt_v2')
    date = models.DateField()

    class Meta:
        constraints = [models.UniqueConstraint(
            fields=['annee_academique', 'date'], name='edt_v2_verrou_jour_unique',
        )]
