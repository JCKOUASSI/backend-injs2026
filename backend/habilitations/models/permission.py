"""Permission atomique ``PermissionMetier`` (quadruple module/ressource/action/portée).

Le code canonique suit la convention ``<module>.<ressource>.<action>`` du
catalogue de l'annexe A3 (ex. ``evaluations.note.valider``). Le catalogue
initial est chargé en U3 ; U1 définit la structure et les 13 actions du
modèle fonctionnel de référence.
"""
from django.db import models

from .perimetre import Perimetre


class PermissionMetier(models.Model):
    class Action(models.TextChoices):
        # Les treize verbes canoniques du modèle fonctionnel de référence.
        CONSULTER = 'consulter', 'Consulter'
        CREER = 'creer', 'Créer'
        MODIFIER = 'modifier', 'Modifier'
        SOUMETTRE = 'soumettre', 'Soumettre'
        VALIDER = 'valider', 'Valider'
        REJETER = 'rejeter', 'Rejeter'
        PUBLIER = 'publier', 'Publier'
        ANNULER = 'annuler', 'Annuler'
        EXPORTER = 'exporter', 'Exporter'
        IMPRIMER = 'imprimer', 'Imprimer'
        ARCHIVER = 'archiver', 'Archiver'
        SUPPRIMER = 'supprimer', 'Supprimer'
        ADMINISTRER = 'administrer', 'Administrer'
        # Verbes métier supplémentaires utilisés par le catalogue de
        # permissions de l'annexe A3 (U3). Chacun est rattaché à un niveau
        # d'accès dans referentiel/catalogue_modules.py (NIVEAU_VERBE).
        SAISIR = 'saisir', 'Saisir'
        VERROUILLER = 'verrouiller', 'Verrouiller'
        CALCULER = 'calculer', 'Calculer'
        SIGNER = 'signer', 'Signer'
        GENERER = 'generer', 'Générer'
        EDITER = 'editer', 'Éditer'
        REVOQUER = 'revoquer', 'Révoquer'
        DEPOSER = 'deposer', 'Déposer'
        INSTRUIRE = 'instruire', 'Instruire'
        DECIDER = 'decider', 'Décider'
        OUVRIR = 'ouvrir', 'Ouvrir'
        CLOTURER = 'cloturer', 'Clôturer'
        FORCER = 'forcer', 'Forcer'
        CERTIFIER = 'certifier', 'Certifier'
        DEPLACER = 'deplacer', 'Déplacer'
        REMPLACER = 'remplacer', 'Remplacer'
        RESOUDRE = 'resoudre', 'Résoudre'
        CONFIGURER = 'configurer', 'Configurer'

    class Criticite(models.TextChoices):
        NORMALE = 'NORMALE', 'Normale'
        SENSIBLE = 'SENSIBLE', 'Sensible'
        CRITIQUE = 'CRITIQUE', 'Critique'

    code = models.CharField(
        max_length=120, unique=True, db_index=True,
        help_text="Code canonique module.ressource.action.",
    )
    module = models.CharField(max_length=60, db_index=True)
    ressource = models.CharField(max_length=80)
    action = models.CharField(max_length=20, choices=Action.choices)
    portee_maximale = models.CharField(
        max_length=20, choices=Perimetre.Type.choices,
        default=Perimetre.Type.INJS_ENTIER,
        help_text="Portée la plus large dans laquelle cette permission peut s'exercer.",
    )

    libelle = models.CharField(max_length=200)
    description = models.TextField(blank=True, default='')
    criticite = models.CharField(
        max_length=12, choices=Criticite.choices, default=Criticite.NORMALE,
    )

    necessite_motif = models.BooleanField(default=False)
    necessite_double_validation = models.BooleanField(default=False)
    journalisee = models.BooleanField(
        default=True,
        help_text="Toute action issue de cette permission est tracée (vrai sauf consultation).",
    )

    actif = models.BooleanField(default=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Permission métier'
        verbose_name_plural = 'Permissions métier'
        ordering = ('module', 'ressource', 'action')
        indexes = [
            models.Index(fields=['module', 'ressource']),
        ]

    def __str__(self):
        return self.code

    def save(self, *args, **kwargs):
        # Le code est dérivé et normalisé de la quadruple décomposition.
        if self.module and self.ressource and self.action:
            self.code = f'{self.module}.{self.ressource}.{self.action}'
        # Par défaut, seule la consultation n'est pas journalisée ; le
        # paramétrage explicite reste possible ensuite.
        if not self.pk and self.action == self.Action.CONSULTER:
            self.journalisee = False
        super().save(*args, **kwargs)
