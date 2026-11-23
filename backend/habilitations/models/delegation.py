"""Délégation temporaire d'habilitations entre deux comptes.

Une délégation est toujours bornée dans le temps et ne peut pas être
re-déléguée (ces règles sont appliquées par les services en U5 ; U1 porte
les données et l'état calculé). Les actions accomplies par délégation seront
journalisées au nom du délégataire avec mention du délégant.
"""
from django.conf import settings
from django.db import models
from django.utils import timezone

from .perimetre import Perimetre


class DelegationHabilitation(models.Model):
    class Statut(models.TextChoices):
        PROPOSEE = 'PROPOSEE', 'Proposée'
        ACTIVE = 'ACTIVE', 'Active'
        TERMINEE = 'TERMINEE', 'Terminée'
        REVOQUEE = 'REVOQUEE', 'Révoquée'

    delegant = models.ForeignKey(
        'habilitations.CompteUtilisateur', on_delete=models.CASCADE,
        related_name='delegations_donnees',
        help_text="Titulaire qui délègue ses attributions.",
    )
    delegataire = models.ForeignKey(
        'habilitations.CompteUtilisateur', on_delete=models.CASCADE,
        related_name='delegations_recues',
        help_text="Compte qui exerce temporairement les attributions.",
    )

    roles = models.ManyToManyField(
        'habilitations.RoleMetier', blank=True, related_name='delegations',
    )
    permissions = models.ManyToManyField(
        'habilitations.PermissionMetier', blank=True, related_name='delegations',
    )
    perimetres = models.ManyToManyField(
        Perimetre, blank=True, related_name='delegations',
    )

    date_debut = models.DateField(default=timezone.localdate)
    date_fin = models.DateField(help_text="Toute délégation est obligatoirement bornée.")
    motif = models.TextField(help_text="Motif de la délégation, obligatoire.")
    statut = models.CharField(
        max_length=12, choices=Statut.choices, default=Statut.PROPOSEE,
        db_index=True,
    )
    valide_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        blank=True, related_name='delegations_validees',
    )
    raison_arret = models.TextField(blank=True, default='')
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
    # U5 — dernier préavis d'expiration (J-7) envoyé, une seule fois.
    notification_echeance_le = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = 'Délégation d’habilitation'
        verbose_name_plural = 'Délégations d’habilitation'
        ordering = ('-date_creation',)
        constraints = [
            models.CheckConstraint(
                check=~models.Q(delegant=models.F('delegataire')),
                name='hab_delegation_pas_soi_meme',
            ),
        ]

    def __str__(self):
        return f'{self.delegant_id} → {self.delegataire_id} [{self.statut}]'

    def est_active(self, aujourdhui=None):
        aujourdhui = aujourdhui or timezone.localdate()
        if self.statut != self.Statut.ACTIVE:
            return False
        return self.date_debut <= aujourdhui <= self.date_fin

    def contraintes(self):
        """Codes de violation purs, non bloquants en U1."""
        violations = []
        if self.delegant_id and self.delegant_id == self.delegataire_id:
            violations.append('DELEGATION_SOI_MEME')
        if self.date_fin and self.date_debut and self.date_fin < self.date_debut:
            violations.append('PERIODE_INCOHERENTE')
        return violations
