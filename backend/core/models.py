"""Noyau transverse de la refonte INJS-LMD (LOT 1, P01-01).

Ce module porte pour l'instant le **journal d'audit unifié** : un registre
append-only qui agrège, derrière le feature flag ``flag.lot01_...``, les
entrées des journaux applicatifs existants (``presences.AuditLog``,
``scolarite.JournalScolarite``, ``referentiels.ReferentielJournal``).

Les journaux sources ne sont ni déplacés ni modifiés (P01-01 : « journaux
existants intacts ») : le journal core en est une réplique normalisée,
synchronisée par signaux et relue par l'API ``/api/core/audit/``.

Chaque événement porte un **code métier unique et atomique** du type
``AUDIT-AAAAMMJJ-NNNNNN`` (séquence continue par jour calendaire), généré
sous verrou via :class:`CompteurCode`.
"""
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import Q
from django.utils import timezone


class JournalImmuableError(RuntimeError):
    """Levée quand on tente de modifier ou supprimer un événement déjà tracé."""


class CompteurCode(models.Model):
    """Compteur nommé servant à la génération atomique de codes métier.

    Une ligne par clé (ex. ``AUDIT-20260913``). L'incrément se fait sous
    ``select_for_update`` sur PostgreSQL ; sur SQLite (sans verrou de ligne)
    l'unicité stricte du code produit reste garantie par la contrainte unique
    et la boucle de reprise du service.
    """

    cle = models.CharField(max_length=64, unique=True)
    dernier_numero = models.PositiveBigIntegerField(default=0)

    class Meta:
        verbose_name = 'Compteur de codes'
        verbose_name_plural = 'Compteurs de codes'

    def __str__(self):
        return f'{self.cle} → {self.dernier_numero}'


class EvenementAuditQuerySet(models.QuerySet):
    """QuerySet qui préserve l'immutabilité, y compris pour les actions en masse."""

    def delete(self, *args, **kwargs):
        raise JournalImmuableError(
            'Le journal d’audit est append-only : aucune suppression n’est autorisée.'
        )

    def update(self, *args, **kwargs):
        raise JournalImmuableError(
            'Le journal d’audit est append-only : aucune mise à jour n’est autorisée.'
        )


class EvenementAudit(models.Model):
    """Une entrée du journal d'audit unifié (immuable, append-only)."""

    class Source(models.TextChoices):
        PRESENCES = 'presences', 'Présences'
        SCOLARITE = 'scolarite', 'Scolarité'
        REFERENTIELS = 'referentiels', 'Référentiels'
        CORE = 'core', 'Noyau'

    # Code métier unique, ex. AUDIT-20260913-000001.
    code = models.CharField(max_length=40, unique=True, db_index=True)

    source = models.CharField(max_length=30, choices=Source.choices, db_index=True)
    action = models.CharField(max_length=100, db_index=True)
    # ``default`` plutôt que ``auto_now_add`` : une réplication porte la date
    # de l'entrée source ; une création native utilise la date courante.
    horodatage = models.DateTimeField(default=timezone.now, db_index=True)

    acteur = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='evenements_audit_core',
    )
    acteur_label = models.CharField(max_length=150, blank=True)

    # Cible polymorphe (GFK) + libellés dénormalisés pour rester lisible
    # même si la cible est supprimée un jour.
    content_type = models.ForeignKey(
        ContentType, on_delete=models.SET_NULL, null=True, blank=True,
    )
    object_id = models.PositiveBigIntegerField(null=True, blank=True, db_index=True)
    cible = GenericForeignKey('content_type', 'object_id')
    objet_type = models.CharField(max_length=100, blank=True)
    objet_id = models.CharField(max_length=64, blank=True)
    objet_libelle = models.CharField(max_length=255, blank=True)

    detail = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    # Idempotence de la réplication : identifiant de l'entrée source dupliquée.
    source_entree_id = models.PositiveBigIntegerField(null=True, blank=True)

    objects = EvenementAuditQuerySet.as_manager()

    class Meta:
        verbose_name = 'Événement d’audit'
        verbose_name_plural = 'Journal d’audit unifié'
        ordering = ['-horodatage', '-id']
        constraints = [
            models.UniqueConstraint(
                fields=['source', 'source_entree_id'],
                condition=Q(source_entree_id__isnull=False),
                name='core_audit_une_replique_par_source',
            ),
        ]
        indexes = [
            models.Index(fields=['source', 'action']),
            models.Index(fields=['content_type', 'object_id'], name='core_audit_cible_idx'),
            models.Index(fields=['acteur', 'horodatage']),
        ]
        # L'admin et les permissions par défaut ; pas d'ajout/modif manuels.
        default_permissions = ('view',)

    def __str__(self):
        return f'{self.code} · {self.source}/{self.action}'

    def save(self, *args, **kwargs):
        # Création seule : toute mise à jour d'une ligne existante est refusée.
        # Le schéma (auto_now_add) comme la règle métier imposent l'append-only.
        if not self._state.adding:
            raise JournalImmuableError(
                f'L’événement d’audit {self.code} est immuable : créez un nouvel événement.'
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise JournalImmuableError(
            f'L’événement d’audit {self.code} est immuable : suppression interdite.'
        )
