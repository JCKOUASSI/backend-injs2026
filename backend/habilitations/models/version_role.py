"""Versionnage additif des rôles métier (Lot B).

Chaque :class:`RoleVersion` est un instantané immuable de l'état d'un
:class:`RoleMetier` (champs + permissions + incompatibilités). Le modèle
``RoleMetier`` n'est PAS modifié : le versionnement s'ajoute en périphérie
et reste compatible avec le moteur RBAC existant (aucune lecture du moteur
ne dépend de ``RoleVersion``).
"""
from django.conf import settings
from django.db import models

#: Champs de ``RoleMetier`` couverts par un instantané. Le ``code`` est
#: volontairement exclu : identifiant stable de référencement, il n'est
#: jamais restauré.
CHAMPS_VERSIONNES = (
    'libelle',
    'libelle_court',
    'description',
    'domaine',
    'niveau_defaut',
    'perimetre_defaut',
    'sensible',
    'cumulable',
    'canal_impose',
    'ordre',
    'actif',
)


class RoleVersion(models.Model):
    """Instantané versionné de l'état d'un rôle métier."""

    class Source(models.TextChoices):
        MANUEL = 'MANUEL', 'Capture manuelle'
        AVANT_RESTAURATION = (
            'AVANT_RESTAURATION', 'Capture automatique avant restauration',
        )
        RESTAURATION = 'RESTAURATION', 'État restauré'

    role = models.ForeignKey(
        'habilitations.RoleMetier', on_delete=models.CASCADE,
        related_name='versions',
    )
    numero = models.PositiveIntegerField(
        help_text="Numéro de version, croissant par rôle (1, 2, 3…).",
    )
    instant = models.DateTimeField(auto_now_add=True, db_index=True)
    auteur = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        blank=True, related_name='versions_roles_creees',
    )
    motif = models.TextField(
        blank=True, default='',
        help_text="Motif de la capture ou de la restauration.",
    )
    source = models.CharField(
        max_length=20, choices=Source.choices, default=Source.MANUEL,
    )
    donnees = models.JSONField(
        help_text=(
            'Instantané : champs versionnés + codes des permissions et des '
            'rôles incompatibles au moment de la capture.'
        ),
    )

    class Meta:
        verbose_name = 'Version de rôle métier'
        verbose_name_plural = 'Versions des rôles métier'
        constraints = [
            models.UniqueConstraint(
                fields=['role', 'numero'],
                name='hab_roleversion_role_numero_unique',
            ),
        ]
        ordering = ('role', '-numero')

    def __str__(self):
        return f'{self.role.code} v{self.numero} [{self.source}]'
