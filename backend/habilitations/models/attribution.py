"""Attribution de rôle et dérogation de permission (cœur du dispositif).

U1 pose les données et des contrôles **purs et non bloquants** (les
``contraintes_*`` renvoient des libellés de violation sans rien refuser) :
les refus effectifs et la séparation des tâches sont appliqués par le moteur
``est_autorise`` en U2, après la période d'observation (règle R3).
"""
from django.conf import settings
from django.db import models
from django.utils import timezone

from .enums import NiveauAcces
from .perimetre import Perimetre


class AttributionRole(models.Model):
    """Lien entre un compte, un rôle, un niveau effectif et des périmètres."""

    class Statut(models.TextChoices):
        PROPOSEE = 'PROPOSEE', 'Proposée'
        ACTIVE = 'ACTIVE', 'Active'
        SUSPENDUE = 'SUSPENDUE', 'Suspendue'
        EXPIREE = 'EXPIREE', 'Expirée'
        REVOQUEE = 'REVOQUEE', 'Révoquée'

    compte = models.ForeignKey(
        'habilitations.CompteUtilisateur', on_delete=models.CASCADE,
        related_name='attributions',
    )
    role = models.ForeignKey(
        'habilitations.RoleMetier', on_delete=models.PROTECT,
        related_name='attributions',
    )
    niveau_effectif = models.CharField(max_length=2, choices=NiveauAcces.choices)
    perimetres = models.ManyToManyField(
        Perimetre, blank=True, related_name='attributions',
    )

    date_debut = models.DateField(default=timezone.localdate)
    date_fin = models.DateField(null=True, blank=True)
    motif = models.TextField(help_text="Motif d'attribution obligatoire.")

    attribue_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        blank=True, related_name='attributions_realisees',
    )
    valide_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        blank=True, related_name='attributions_validees',
        help_text="Seconde signature exigée pour les rôles sensibles.",
    )
    date_validation = models.DateTimeField(null=True, blank=True)

    statut = models.CharField(
        max_length=12, choices=Statut.choices, default=Statut.PROPOSEE,
        db_index=True,
    )
    motif_revocation = models.TextField(blank=True, default='')
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
    # U5 — date du dernier préavis d'expiration envoyé (J-7), pour n'en
    # envoyer qu'un seul.
    notification_echeance_le = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = 'Attribution de rôle'
        verbose_name_plural = 'Attributions de rôle'
        ordering = ('-date_creation',)
        constraints = [
            models.UniqueConstraint(
                fields=['compte', 'role'],
                condition=models.Q(statut='ACTIVE'),
                name='hab_attribution_active_unique',
            ),
        ]
        indexes = [models.Index(fields=['compte', 'statut'])]

    def __str__(self):
        return f'{self.compte_id} ← {self.role.code} [{self.statut}]'

    def est_active(self, aujourdhui=None):
        aujourdhui = aujourdhui or timezone.localdate()
        if self.statut != self.Statut.ACTIVE:
            return False
        if self.date_debut and aujourdhui < self.date_debut:
            return False
        if self.date_fin and aujourdhui > self.date_fin:
            return False
        return True

    def contraintes(self):
        """Liste de codes de violation (PURE, ne bloque rien en U1)."""
        violations = []
        if self.role_id and not self.role.module_est_installe():
            violations.append('MODULE_REQUIS_ABSENT')
        if self.role_id and self.role.sensible and not self.valide_par_id:
            violations.append('ROLE_SENSIBLE_SANS_SECONDE_SIGNATURE')
        # Incompatibilité avec une autre attribution ACTIVE du même compte.
        if self.compte_id and self.role_id:
            incompatibles = set(
                self.role.incompatible_avec.values_list('pk', flat=True)
            )
            if incompatibles:
                conflit = self.compte.attributions.filter(
                    statut=self.Statut.ACTIVE, role__pk__in=incompatibles,
                ).exclude(pk=self.pk)
                if conflit.exists():
                    violations.append('ROLES_INCOMPATIBLES')
        # Un périmètre SECRETARIAT est exigé quand le rôle en relève.
        if self.role_id and self.role.perimetre_defaut == Perimetre.Type.SECRETARIAT:
            if not self.perimetres.filter(type=Perimetre.Type.SECRETARIAT).exists():
                violations.append('PERIMETRE_SECRETARIAT_MANQUANT')
        return violations


class PermissionAttribuee(models.Model):
    """Dérogation maîtrisée : OCTROI ou RETRAIT d'une permission atomique."""

    class Sens(models.TextChoices):
        OCTROI = 'OCTROI', 'Octroi exceptionnel'
        RETRAIT = 'RETRAIT', 'Retrait exceptionnel'

    class Statut(models.TextChoices):
        PROPOSEE = 'PROPOSEE', 'Proposée'
        ACTIVE = 'ACTIVE', 'Active'
        EXPIREE = 'EXPIREE', 'Expirée'
        REVOQUEE = 'REVOQUEE', 'Révoquée'

    compte = models.ForeignKey(
        'habilitations.CompteUtilisateur', on_delete=models.CASCADE,
        related_name='derogations',
    )
    permission = models.ForeignKey(
        'habilitations.PermissionMetier', on_delete=models.PROTECT,
        related_name='derogations',
    )
    sens = models.CharField(max_length=8, choices=Sens.choices)
    perimetre = models.ForeignKey(
        Perimetre, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='derogations',
    )

    motif = models.TextField(help_text="Motif de la dérogation, obligatoire.")
    date_debut = models.DateField(default=timezone.localdate)
    date_fin = models.DateField(
        null=True, blank=True,
        help_text="Obligatoire pour un OCTROI (dérogation toujours temporaire).",
    )

    attribue_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        blank=True, related_name='derogations_realisees',
    )
    valide_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        blank=True, related_name='derogations_validees',
    )
    statut = models.CharField(
        max_length=12, choices=Statut.choices, default=Statut.PROPOSEE,
        db_index=True,
    )
    date_creation = models.DateTimeField(auto_now_add=True)
    # U5 — dernier préavis d'expiration (J-7) envoyé, une seule fois.
    notification_echeance_le = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = 'Permission attribuée (dérogation)'
        verbose_name_plural = 'Permissions attribuées (dérogations)'
        ordering = ('-date_creation',)

    def __str__(self):
        return f'{self.sens} {self.permission.code} pour compte {self.compte_id}'

    def est_active(self, aujourdhui=None):
        aujourdhui = aujourdhui or timezone.localdate()
        if self.statut != self.Statut.ACTIVE:
            return False
        if self.date_debut and aujourdhui < self.date_debut:
            return False
        if self.date_fin and aujourdhui > self.date_fin:
            return False
        return True
