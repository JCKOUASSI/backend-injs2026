"""Workflow générique de demandes d'accès (Lot C, additif).

Sépare explicitement : DEMANDE → APPROBATION → PROVISIONNEMENT EFFECTIF.
L'approbation ne provisionne JAMAIS directement : pour une demande
d'attribution de rôle, elle crée une :class:`PropositionProvisionnement`
EN_ATTENTE dans la file existante (U5), traitée par les gestes console
habituels. Aucun contournement du RBAC ni du provisionnement.
"""
from django.conf import settings
from django.db import models

from .cycle_vie import PropositionProvisionnement
from .permission import PermissionMetier
from .role import RoleMetier


class DemandeAcces(models.Model):
    """Demande d'accès formalisée, instruite puis décidée par un validateur."""

    class Type(models.TextChoices):
        ATTRIBUTION_ROLE = 'ATTRIBUTION_ROLE', 'Attribution de rôle'
        PERMISSION_DIRECTE = 'PERMISSION_DIRECTE', 'Permission directe (dérogation)'

    class Statut(models.TextChoices):
        BROUILLON = 'BROUILLON', 'Brouillon'
        SOUMISE = 'SOUMISE', 'Soumise'
        EN_REVUE = 'EN_REVUE', 'En revue'
        APPROUVEE = 'APPROUVEE', 'Approuvée'
        REFUSEE = 'REFUSEE', 'Refusée'
        ANNULEE = 'ANNULEE', 'Annulée'

    demandeur = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='demandes_acces_emises',
        help_text='Administrateur ayant formulé la demande.',
    )
    compte_cible = models.ForeignKey(
        'habilitations.CompteUtilisateur', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='demandes_acces',
        help_text='Compte bénéficiaire de l’accès demandé.',
    )
    type_demande = models.CharField(max_length=20, choices=Type.choices)
    role = models.ForeignKey(
        RoleMetier, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='demandes_acces',
    )
    permission = models.ForeignKey(
        PermissionMetier, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='demandes_acces',
    )
    justification = models.TextField(
        help_text='Justification métier obligatoire de la demande.',
    )
    statut = models.CharField(
        max_length=12, choices=Statut.choices, default=Statut.BROUILLON,
        db_index=True,
    )
    approbateur = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='demandes_acces_traitees',
        help_text='Validateur ayant décidé (jamais le demandeur lui-même).',
    )
    motif_decision = models.TextField(blank=True, default='')
    date_soumission = models.DateTimeField(null=True, blank=True)
    date_decision = models.DateTimeField(null=True, blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    #: File de provisionnement alimentée par l'approbation (jamais appliquée
    #: seule : l'exécution reste un geste console existant).
    proposition = models.ForeignKey(
        PropositionProvisionnement, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='demande_acces_origine',
    )

    class Meta:
        verbose_name = 'Demande d’accès'
        verbose_name_plural = 'Demandes d’accès'
        ordering = ('-date_creation',)
        indexes = [models.Index(fields=['statut', 'type_demande'])]
        constraints = [
            models.CheckConstraint(
                check=~models.Q(approbateur=models.F('demandeur')),
                name='hab_demande_pas_auto_approbation',
            ),
        ]

    def __str__(self):
        cible = self.compte_cible_id or '—'
        return f'{self.get_type_demande_display()} · {cible} [{self.statut}]'
