"""Modèle ``Perimetre`` : portée d'une attribution ou d'une permission.

Décision d'architecture U1 (note de conception, décision 3) : la référence à
l'objet bornant le périmètre est **polymorphe** (``ContentType`` + clé
générique), afin de viser aussi bien un secrétariat, une formation, un
groupe, un module ECUE ou un étudiant sans coupler durement cette
application transverse aux vingt applications métier. Un champ
``reference_lisible`` porte le code métier (ex. ``SECR-DEMO-A``) et garantit
la lisibilité même si l'objet vient à disparaître.
"""
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models


class Perimetre(models.Model):
    """Une portée de données exploitable par une attribution.

    Les types globaux (``INJS_ENTIER``, ``PROPRE_COMPTE``) n'ont pas d'objet
    rattaché ; les types locaux (``SECRETARIAT``, ``FORMATION``…) pointent
    vers l'objet métier via la référence polymorphe.
    """

    class Type(models.TextChoices):
        INJS_ENTIER = 'INJS_ENTIER', 'INJS tout entière'
        DIRECTION = 'DIRECTION', 'Une direction'
        # LOT 5 (J2-4) : le département devient un périmètre bornable à part
        # entière (chaîne Direction ⊃ Département ⊃ Service) ; additif.
        DEPARTEMENT = 'DEPARTEMENT', 'Un département'
        SERVICE = 'SERVICE', 'Un service administratif'
        SECRETARIAT = 'SECRETARIAT', 'Un secrétariat'
        SITE = 'SITE', 'Un site physique'
        FORMATION = 'FORMATION', 'Une formation'
        PARCOURS = 'PARCOURS', 'Un parcours'
        NIVEAU = 'NIVEAU', 'Un niveau (L1, L2…)'
        GROUPE = 'GROUPE', 'Un groupe pédagogique'
        MODULE_ECUE = 'MODULE_ECUE', 'Un module / une ECUE'
        ETUDIANT = 'ETUDIANT', 'Un étudiant nommément désigné'
        PROPRE_COMPTE = 'PROPRE_COMPTE', 'Son propre compte / dossier'

    #: Types qui ne référencent aucun objet métier particulier.
    TYPES_GLOBAUX = frozenset({Type.INJS_ENTIER, Type.PROPRE_COMPTE})

    type = models.CharField(max_length=20, choices=Type.choices, db_index=True)
    libelle = models.CharField(
        max_length=255, blank=True,
        help_text="Libellé libre optionnel ; sinon le libellé calculé est utilisé.",
    )

    # Référence polymorphe à l'objet bornant le périmètre.
    content_type = models.ForeignKey(
        ContentType, on_delete=models.SET_NULL, null=True, blank=True,
    )
    object_id = models.PositiveBigIntegerField(null=True, blank=True, db_index=True)
    cible = GenericForeignKey('content_type', 'object_id')

    #: Code métier lisible (jamais l'identifiant technique dans les écrans).
    reference_lisible = models.CharField(max_length=100, blank=True, db_index=True)

    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Périmètre d’habilitation'
        verbose_name_plural = 'Périmètres d’habilitation'
        ordering = ('type', 'reference_lisible')
        indexes = [
            models.Index(fields=['content_type', 'object_id'],
                         name='hab_perim_cible_idx'),
        ]

    def __str__(self):
        if self.libelle:
            return f'{self.get_type_display()} · {self.libelle}'
        if self.reference_lisible:
            return f'{self.get_type_display()} · {self.reference_lisible}'
        return self.get_type_display()

    @property
    def est_global(self):
        return self.type in self.TYPES_GLOBAUX

    @classmethod
    def obtenir_ou_creer_global(cls, type_p):
        """Réutilise le périmètre global d'un type donné (INJS, propre compte)."""
        existant = cls.objects.filter(
            type=type_p, content_type__isnull=True,
            object_id__isnull=True, reference_lisible='',
        ).first()
        if existant is not None:
            return existant
        return cls.objects.create(type=type_p)
