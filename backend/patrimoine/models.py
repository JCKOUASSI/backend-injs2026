"""Modèles du lot L7 — Patrimoine.

Équipements, véhicules, inventaires, maintenances et réservations d'espaces.
Conformité aux règles du dépôt :
  - source unique de vérité des lieux : ``formations.RefSite/RefBatiment/RefSalle`` ;
  - mouvements tracés de manière append-only (``MouvementPatrimonial``) ;
  - une maintenance planifiée peut marquer un espace indisponible pour l'EDT.
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class Equipement(models.Model):
    """Équipement rattaché à un espace (salle, bâtiment, site)."""

    class TypeEquipement(models.TextChoices):
        INFORMATIQUE = 'INFO', 'Informatique'
        MATERIEL_SPORT = 'SPORT', 'Matériel sportif'
        MOBILIER = 'MOBILIER', 'Mobilier'
        ELECTROMENAGER = 'ELECTRO', 'Électroménager'
        AUTRE = 'AUTRE', 'Autre'

    class Etat(models.TextChoices):
        FONCTIONNEL = 'FONCTIONNEL', 'Fonctionnel'
        HORS_SERVICE = 'HORS_SERVICE', 'Hors service'
        EN_MAINTENANCE = 'EN_MAINTENANCE', 'En maintenance'
        REVOYE = 'REVOYE', 'Réformé'

    espace = models.ForeignKey(
        'formations.RefSalle', on_delete=models.PROTECT,
        related_name='equipements_patrimoine', null=True, blank=True,
        help_text="Salle d'affectation (source : référentiel formations).",
    )
    nom = models.CharField(max_length=200)
    type_equipement = models.CharField(max_length=15, choices=TypeEquipement.choices, default=TypeEquipement.AUTRE)
    marque = models.CharField(max_length=100, blank=True, default='')
    modele = models.CharField(max_length=100, blank=True, default='')
    num_serie = models.CharField(max_length=100, blank=True, default='')
    etat = models.CharField(max_length=15, choices=Etat.choices, default=Etat.FONCTIONNEL)
    date_acquisition = models.DateField(null=True, blank=True)
    note_inventaire = models.TextField(blank=True, default='')
    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        related_name='equipements_crees', null=True, blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['nom']
        verbose_name = 'LMD – Équipement'

    def __str__(self):
        return f'{self.nom} ({self.get_etat_display()})'


class Vehicule(models.Model):
    """Véhicule du parc patrimonial."""

    immatriculation = models.CharField(max_length=30, unique=True)
    marque = models.CharField(max_length=100, blank=True, default='')
    modele = models.CharField(max_length=100, blank=True, default='')
    annee_mise_en_circulation = models.PositiveIntegerField(null=True, blank=True)
    kilometrage = models.PositiveIntegerField(default=0)
    prochaine_revision = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['immatriculation']
        verbose_name = 'LMD – Véhicule'

    def __str__(self):
        return self.immatriculation


class Inventaire(models.Model):
    """Campagne d'inventaire du patrimoine."""

    date_inventaire = models.DateField()
    responsable = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='inventaires_realises',
    )
    commentaires = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date_inventaire']
        verbose_name = 'LMD – Inventaire'

    def __str__(self):
        return f'Inventaire du {self.date_inventaire}'

    def clean(self):
        if not self.date_inventaire:
            raise ValidationError({'date_inventaire': 'La date est obligatoire.'})
class LigneInventaire(models.Model):
    """Ligne d'inventaire : état constaté d'un équipement lors d'une campagne."""

    inventaire = models.ForeignKey(Inventaire, on_delete=models.CASCADE, related_name='lignes')
    equipement = models.ForeignKey(Equipement, on_delete=models.CASCADE, related_name='lignes_inventaire')
    etat_constate = models.CharField(
        max_length=15, choices=Equipement.Etat.choices, default=Equipement.Etat.FONCTIONNEL,
    )
    commentaires = models.TextField(blank=True, default='')

    class Meta:
        unique_together = ('inventaire', 'equipement')
        verbose_name = 'LMD – Ligne d’inventaire'

    def __str__(self):
        return f'{self.inventaire} → {self.equipement}'


class Maintenance(models.Model):
    """Intervention de maintenance sur un équipement ou un espace."""

    class TypeMaintenance(models.TextChoices):
        PREVENTIVE = 'PREVENTIVE', 'Préventive'
        CORRECTIVE = 'CORRECTIVE', 'Corrective'

    class Statut(models.TextChoices):
        PLANIFIEE = 'PLANIFIEE', 'Planifiée'
        EN_COURS = 'EN_COURS', 'En cours'
        TERMINEE = 'TERMINEE', 'Terminée'
        ANNULEE = 'ANNULEE', 'Annulée'

    equipement = models.ForeignKey(
        Equipement, on_delete=models.CASCADE, related_name='maintenances', null=True, blank=True,
    )
    salle = models.ForeignKey(
        'formations.RefSalle', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='maintenances',
    )
    type_maintenance = models.CharField(max_length=15, choices=TypeMaintenance.choices, default=TypeMaintenance.CORRECTIVE)
    description = models.TextField()
    date_debut = models.DateField()
    date_fin = models.DateField(null=True, blank=True)
    statut = models.CharField(max_length=15, choices=Statut.choices, default=Statut.PLANIFIEE)
    responsable = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='maintenances_suivies',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date_debut']
        verbose_name = 'LMD – Maintenance'

    def __str__(self):
        cible = self.equipement or self.salle
        return f'{self.get_type_maintenance_display()} – {cible} ({self.date_debut})'

    def clean(self):
        if self.date_fin and self.date_fin < self.date_debut:
            raise ValidationError({'date_fin': 'La date de fin est antérieure à la date de début.'})


class ReservationEspace(models.Model):
    """Réservation d'un espace (salle), validation obligatoire."""

    class Statut(models.TextChoices):
        PROVISOIRE = 'PROVISOIRE', 'Provisoire'
        VALIDEE = 'VALIDEE', 'Validée'
        REFUSEE = 'REFUSEE', 'Refusée'
        ANNULEE = 'ANNULEE', 'Annulée'

    salle = models.ForeignKey('formations.RefSalle', on_delete=models.PROTECT, related_name='reservations')
    motif = models.CharField(max_length=255)
    date_debut = models.DateTimeField()
    date_fin = models.DateTimeField()
    statut = models.CharField(max_length=15, choices=Statut.choices, default=Statut.PROVISOIRE)
    demande_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        related_name='reservations_demandees', null=True, blank=True,
    )
    valide_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        related_name='reservations_validees', null=True, blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date_debut']
        verbose_name = 'LMD – Réservation d’espace'

    def __str__(self):
        return f'{self.salle} – {self.motif}'

    def clean(self):
        if self.date_fin <= self.date_debut:
            raise ValidationError({'date_fin': 'La date de fin doit être postérieure à la date de début.'})


class MouvementPatrimonial(models.Model):
    """Trace append-only de tout mouvement patrimonial."""

    class TypeMouvement(models.TextChoices):
        ACQUISITION = 'ACQUISITION', 'Acquisition'
        AFFECTATION = 'AFFECTATION', 'Affectation'
        MUTATION = 'MUTATION', 'Mutation'
        MAINTENANCE = 'MAINTENANCE', 'Maintenance'
        REFORME = 'REFORME', 'Réforme'
        MISE_EN_SERVICE = 'MISE_EN_SERVICE', 'Mise en service'

    equipement = models.ForeignKey(Equipement, on_delete=models.CASCADE, null=True, blank=True, related_name='mouvements')
    vehicule = models.ForeignKey(Vehicule, on_delete=models.CASCADE, null=True, blank=True, related_name='mouvements')
    type_mouvement = models.CharField(max_length=20, choices=TypeMouvement.choices)
    detail = models.TextField(blank=True, default='')
    ancienne_valeur = models.JSONField(default=dict, blank=True)
    nouvelle_valeur = models.JSONField(default=dict, blank=True)
    acteur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'LMD – Mouvement patrimonial'

    def __str__(self):
        return f'{self.get_type_mouvement_display()} – {self.created_at.date()}'