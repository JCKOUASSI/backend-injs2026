"""Lot L5 — Équivalences et dispenses.

Une demande reconnaît des acquis antérieurs (équivalence) ou exempte un
étudiant d'une UE/ECUE (dispense), selon une décision officielle tracée.
Mécanique unique pour les deux types (``type_demande``) : ni duplication du
domaine ni réécriture de scolarite/admissions. Toute décision est audité
(JournalScolarite) et l'application d'une dispense alimente l'historique
académique (EvenementScolarite) et met à jour l'inscription pédagogique
existante au statut DISPENSEE.
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class DemandeEquivalenceDispense(models.Model):
    """Demande d'équivalence ou de dispense, version officielle tracée."""

    class TypeDemande(models.TextChoices):
        EQUIVALENCE = 'EQUIVALENCE', 'Équivalence'
        DISPENSE = 'DISPENSE', 'Dispense'

    class Statut(models.TextChoices):
        BROUILLON = 'BROUILLON', 'Brouillon'
        SOUMISE = 'SOUMISE', 'Soumise'
        EN_INSTRUCTION = 'EN_INSTRUCTION', 'En instruction'
        A_COMPLETER = 'A_COMPLETER', 'À compléter'
        AVIS_PEDAGOGIQUE = 'AVIS_PEDAGOGIQUE', 'Avis pédagogique'
        DECISION = 'DECISION', 'Décision'
        VALIDEE = 'VALIDEE', 'Validée'
        REJETEE = 'REJETEE', 'Rejetée'
        APPLIQUEE = 'APPLIQUEE', 'Appliquée'

    class Decision(models.TextChoices):
        EN_ATTENTE = 'EN_ATTENTE', 'En attente'
        FAVORABLE = 'FAVORABLE', 'Favorable'
        DEFAVORABLE = 'DEFAVORABLE', 'Défavorable'

    # ── Identification ──
    type_demande = models.CharField(max_length=15, choices=TypeDemande.choices)
    etudiant = models.ForeignKey(
        'scolarite.DossierEtudiant', on_delete=models.PROTECT,
        related_name='demandes_equivalence',
        help_text="Rattaché au dossier étudiant (matricule porté par Participant).",
    )
    annee_academique = models.ForeignKey(
        'scolarite.AnneeAcademique', on_delete=models.PROTECT, related_name='demandes_equivalence',
    )
    ref_formation = models.ForeignKey(
        'formations.RefFormation', on_delete=models.PROTECT, related_name='demandes_equivalence',
    )
    parcours = models.ForeignKey(
        'scolarite.Parcours', on_delete=models.PROTECT,
        related_name='demandes_equivalence', null=True, blank=True,
    )
    niveau = models.ForeignKey(
        'scolarite.Niveau', on_delete=models.PROTECT, related_name='demandes_equivalence',
    )
    semestre = models.ForeignKey(
        'scolarite.Semestre', on_delete=models.PROTECT,
        related_name='demandes_equivalence', null=True, blank=True,
    )
    ue = models.ForeignKey(
        'scolarite.UE', on_delete=models.PROTECT,
        related_name='demandes_equivalence', null=True, blank=True,
    )
    ecue = models.ForeignKey(
        'scolarite.ECUE', on_delete=models.PROTECT,
        related_name='demandes_equivalence', null=True, blank=True,
    )

    # ── Acquis antérieurs ──
    etablissement_origine = models.CharField(max_length=200, blank=True, default='')
    diplome_origine = models.CharField(max_length=200, blank=True, default='')
    annee_obtention = models.PositiveSmallIntegerField(null=True, blank=True)

    # ── Analyse, commission, décision ──
    analyse_pedagogique = models.TextField(blank=True, default='')
    commission = models.CharField(max_length=200, blank=True, default='')
    date_commission = models.DateField(null=True, blank=True)
    decision = models.CharField(
        max_length=15, choices=Decision.choices, default=Decision.EN_ATTENTE,
    )
    credits_reconnus = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text='Crédits ECTS reconnus (équivalence).',
    )
    note_transferee = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text='Note transférée éventuelle (sur 20).',
    )
    motif = models.TextField(blank=True, default='')
    autorite_validation = models.CharField(max_length=200, blank=True, default='')

    # ── Effet et validité ──
    date_effet = models.DateField(null=True, blank=True)
    fin_validite = models.DateField(
        null=True, blank=True,
        help_text='Au-delà, la dispense/équivalence n’est plus applicable.',
    )

    # ── Workflow ──
    statut = models.CharField(max_length=20, choices=Statut.choices, default=Statut.BROUILLON)
    appliquee_le = models.DateTimeField(null=True, blank=True)
    appliquee_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        related_name='equivalences_appliquees', null=True, blank=True,
    )
    # Règle : toute modification après validation passe par une rectification
    # tracée (jamais d'édition directe ni de suppression).
    rectifiee_le = models.DateTimeField(null=True, blank=True)
    motif_rectification = models.TextField(blank=True, default='')
    decision_rectifiee = models.CharField(
        max_length=15, choices=Decision.choices, blank=True, default='',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Équivalence/Dispense – Demande'
        verbose_name_plural = 'Équivalences/Dispenses – Demandes'
        indexes = [
            models.Index(fields=['etudiant', 'statut']),
            models.Index(fields=['type_demande', 'statut']),
        ]

    def __str__(self):
        return (
            f'{self.get_type_demande_display()} {self.get_statut_display()} – '
            f'{self.etudiant.matricule} ({self.ref_formation})'
        )

    @property
    def est_verrouillee(self):
        """Après validation, la demande n'est modifiable que par rectification."""
        return self.statut in (
            self.Statut.VALIDEE, self.Statut.REJETEE, self.Statut.APPLIQUEE,
        )

    def clean(self):
        erreurs = {}
        if self.ecue_id and self.ue_id and self.ecue.ue_id != self.ue_id:
            erreurs['ecue'] = "L'ECUE n'appartient pas à l'UE sélectionnée."
        if self.date_effet and self.fin_validite and self.fin_validite < self.date_effet:
            erreurs['fin_validite'] = 'La fin de validité précède la date d’effet.'
        if (
            self.type_demande == self.TypeDemande.EQUIVALENCE
            and self.decision == self.Decision.FAVORABLE
            and self.credits_reconnus is None
        ):
            erreurs['credits_reconnus'] = (
                'Indiquer les crédits reconnus pour une équivalence favorable.'
            )
        if erreurs:
            raise ValidationError(erreurs)

    def journaliser(self, action, utilisateur=None, **champs):
        from scolarite.models import journaliser
        journaliser(action, objet=self, acteur=utilisateur, **champs)


class PieceEquivalence(models.Model):
    """Pièce justificative d'une demande (référence : complétude admissions).

    Réutilise ``admissions.TypePiece`` comme catalogue sans dupliquer le
    modèle de fichiers d'admissions : chaque demande liste ses pièces
    requises et leur statut de validation.
    """

    class Statut(models.TextChoices):
        MANQUANTE = 'MANQUANTE', 'Manquante'
        FOURNIE = 'FOURNIE', 'Fournie'
        VALIDE = 'VALIDEE', 'Validée'
        REFUSEE = 'REFUSEE', 'Refusée'

    demande = models.ForeignKey(
        DemandeEquivalenceDispense, on_delete=models.CASCADE, related_name='pieces',
    )
    type_piece = models.ForeignKey(
        'admissions.TypePiece', on_delete=models.PROTECT,
        related_name='pieces_equivalence', null=True, blank=True,
    )
    libelle = models.CharField(max_length=200, blank=True, default='')
    obligatoire = models.BooleanField(default=True)
    statut = models.CharField(max_length=15, choices=Statut.choices, default=Statut.MANQUANTE)
    commentaire = models.TextField(blank=True, default='')
    verifie_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        related_name='pieces_equivalence_verifiees', null=True, blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']
        verbose_name = 'Équivalence/Dispense – Pièce'
        verbose_name_plural = 'Équivalences/Dispenses – Pièces'

    def __str__(self):
        return f'{self.libelle or self.type_piece} – demande #{self.demande_id}'

    @property
    def est_validee(self):
        return self.statut == self.Statut.VALIDE or (
            not self.obligatoire and self.statut == self.Statut.FOURNIE
        )


class HistoriqueEquivalence(models.Model):
    """Lot L5 — trace immuable des changements de statut et décisions."""

    demande = models.ForeignKey(
        DemandeEquivalenceDispense, on_delete=models.CASCADE, related_name='historique',
    )
    statut = models.CharField(max_length=20, choices=DemandeEquivalenceDispense.Statut.choices)
    decision = models.CharField(
        max_length=15, choices=DemandeEquivalenceDispense.Decision.choices, blank=True, default='',
    )
    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        related_name='actions_equivalences', null=True, blank=True,
    )
    commentaire = models.TextField(blank=True, default='')
    horodatage = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-horodatage']
        verbose_name = 'Équivalence/Dispense – Historique'
        verbose_name_plural = 'Équivalences/Dispenses – Historiques'

    def __str__(self):
        return f'{self.demande_id} : {self.statut} @ {self.horodatage:%Y-%m-%d %H:%M}'
    diplome_origine = models.CharField(max_length=200, blank=True, default='')
    annee_obtention = models.PositiveSmallIntegerField(null=True, blank=True)