"""Fondations d'interopérabilité GET-INJS → futur module Présences.

Extension architecturale du prompt maître GET INJS APP : GET constitue la
source de référence des séances pédagogiques publiées. Ce module ajoute,
**sans modifier aucune table existante**, les fondations que le futur
module de gestion des présences (QR Code, pointage manuel, géolocalisation)
consommera :

- ``SeanceRegistre`` (``gi_seance_registre``) : identité technique unique et
  permanente d'une séance (UUID + clé métier déterministe), cycle de vie
  (BROUILLON → … → PUBLIEE → … → TERMINEE), traçabilité de publication.
  Le registre survit à la suppression de l'affectation de placement
  (régénération) : la réconciliation le rattache à la nouvelle ligne
  représentant la même activité pédagogique, l'UUID ne change jamais.
- ``SeanceHistorique`` (``gi_seance_historique``) : journal non destructif
  des transitions, modifications et annulations (acteur, motif, avant/après).
- ``SeanceEvenement`` (``gi_seance_evenement``) : file d'événements
  contractuels (SEANCE_PUBLIEE, SEANCE_MODIFIEE, SEANCE_ANNULEE,
  SEANCE_REPROGRAMMEE, SEANCE_CLOTUREE) que le futur module consommera.
- ``SalleGeolocalisation`` (``gi_salle_geolocalisation``) : configuration
  géographique centralisée d'une salle du référentiel (jamais dupliquée).
- ``SeanceInstantaneAttendus`` (``gi_seance_instantane``) : instantané
  historique des étudiants attendus, constitué à la demande (par exemple à
  l'ouverture d'une session de présence), sans figer la liste dans la séance.

Aucun pointage, aucun QR Code, aucune statistique de présence n'est produit
ici : seules les fondations contractuelles sont posées (cf. §12 de
l'extension : préparation proportionnée, pas de module Présences anticipé).
"""

import uuid

from django.conf import settings
from django.db import models
from django.db.models.signals import pre_delete
from django.dispatch import receiver

from .models import AffectationCreneau


class SeanceRegistre(models.Model):
    """Identité permanente et cycle de vie d'une séance pédagogique.

    L'UUID est l'identifiant que les futurs modules (présences, contrôle
    académique, statistiques) référenceront. Il ne dépend ni de la date, ni
    de l'horaire, ni de la salle, ni de l'enseignant : un déplacement de
    créneau, un changement de salle ou d'enseignant conserve l'identité.
    Seule une annulation suivie d'une reprogrammation crée une nouvelle
    séance, reliée à l'ancienne par ``seance_origine``.
    """

    class Statut(models.TextChoices):
        BROUILLON = 'BROUILLON', 'Brouillon'
        SIMULATION = 'SIMULATION', 'Simulation'
        EN_ATTENTE_VALIDATION = 'EN_ATTENTE_VALIDATION', 'En attente de validation'
        VALIDEE = 'VALIDEE', 'Validée'
        PUBLIEE = 'PUBLIEE', 'Publiée'
        MODIFIEE = 'MODIFIEE', 'Publiée puis modifiée'
        ANNULEE = 'ANNULEE', 'Annulée'
        TERMINEE = 'TERMINEE', 'Terminée (clôturée)'

    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        db_index=True,
        help_text='Identifiant technique permanent de la séance (interopérabilité).',
    )
    affectation = models.OneToOneField(
        AffectationCreneau,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='registre_seance',
        help_text=(
            'Placement courant de la séance. SET_NULL : une régénération qui '
            'supprime la ligne de placement ne détruit pas l’identité ; la '
            'réconciliation rattache le registre à la nouvelle ligne.'
        ),
    )
    cle_metier = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        help_text=(
            'Empreinte déterministe du contexte pédagogique (année, semestre, '
            'groupe, ECUE/UE, type) — jamais l’horaire, la salle ou l’enseignant.'
        ),
    )
    statut = models.CharField(
        max_length=25,
        choices=Statut.choices,
        default=Statut.BROUILLON,
        db_index=True,
    )
    version = models.PositiveIntegerField(
        default=1,
        help_text='Version de programmation : incrémentée à chaque modification tracée.',
    )
    publie_le = models.DateTimeField(null=True, blank=True)
    publie_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='seances_publiees',
    )
    motif_annulation = models.CharField(max_length=255, blank=True, default='')
    seance_origine = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reprogrammations',
        help_text='Séance annulée que celle-ci reprogramme, le cas échéant.',
    )
    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='seances_creees',
    )
    modifie_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='seances_modifiees',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'gi_seance_registre'
        verbose_name = 'GET – Registre de séance (interopérabilité présences)'
        verbose_name_plural = 'GET – Registres de séances (interopérabilité présences)'
        indexes = [
            models.Index(fields=['statut', 'publie_le']),
        ]

    def __str__(self):
        return f'Séance {self.uuid} [{self.statut}]'


class SeanceHistorique(models.Model):
    """Journal non destructif des événements de vie d'une séance."""

    class Action(models.TextChoices):
        CREATION = 'CREATION', 'Création'
        RATTACHEMENT = 'RATTACHEMENT', 'Rattachement après régénération'
        TRANSITION = 'TRANSITION', 'Transition de statut'
        MODIFICATION = 'MODIFICATION', 'Modification de programmation'
        PUBLICATION = 'PUBLICATION', 'Publication'
        ANNULATION = 'ANNULATION', 'Annulation'
        REPROGRAMMATION = 'REPROGRAMMATION', 'Reprogrammation'
        INSTANTANE = 'INSTANTANE', 'Instantané des étudiants attendus'

    registre = models.ForeignKey(
        SeanceRegistre,
        on_delete=models.CASCADE,
        related_name='historique',
    )
    action = models.CharField(max_length=20, choices=Action.choices, db_index=True)
    statut_avant = models.CharField(max_length=25, blank=True, default='')
    statut_apres = models.CharField(max_length=25, blank=True, default='')
    details = models.JSONField(
        default=dict,
        blank=True,
        help_text='Détail structuré (champs modifiés, anciennes/nouvelles valeurs…).',
    )
    acteur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='seances_historique',
    )
    motif = models.CharField(max_length=255, blank=True, default='')
    horodatage = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'gi_seance_historique'
        ordering = ['-horodatage', '-id']
        verbose_name = 'GET – Historique de séance'
        verbose_name_plural = 'GET – Historiques de séances'


class SeanceEvenement(models.Model):
    """Événement contractuel émis vers le futur module de présence.

    File append-only : le consommateur lit les événements postérieurs au
    dernier id traité (``apres``) et peut marquer ``consomme``. Aucun
    mécanisme de file externe n'est imposé à ce stade.
    """

    class Type(models.TextChoices):
        SEANCE_PUBLIEE = 'SEANCE_PUBLIEE', 'Séance publiée'
        SEANCE_MODIFIEE = 'SEANCE_MODIFIEE', 'Séance modifiée'
        SEANCE_ANNULEE = 'SEANCE_ANNULEE', 'Séance annulée'
        SEANCE_REPROGRAMMEE = 'SEANCE_REPROGRAMMEE', 'Séance reprogrammée'
        SEANCE_CLOTUREE = 'SEANCE_CLOTUREE', 'Séance clôturée'

    type = models.CharField(max_length=25, choices=Type.choices, db_index=True)
    registre = models.ForeignKey(
        SeanceRegistre,
        on_delete=models.CASCADE,
        related_name='evenements',
    )
    charge_utile = models.JSONField(
        default=dict,
        blank=True,
        help_text='Aperçu contractuel (uuid, statut, horaire, salle, enseignant, groupe…).',
    )
    consomme = models.BooleanField(default=False, db_index=True)
    cree_le = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'gi_seance_evenement'
        ordering = ['id']
        verbose_name = 'GET – Événement de séance'
        verbose_name_plural = 'GET – Événements de séances'


class SalleGeolocalisation(models.Model):
    """Configuration géographique centralisée d'une salle du référentiel.

    Une ligne par salle (OneToOne) : la configuration est réutilisable par
    tout module de contrôle. La géolocalisation n'est jamais, à elle seule,
    une preuve de présence — elle prépare un contrôle combiné (QR + géo +
    serveur + humain), documenté dans le guide d'intégration.
    """

    class TypeEspace(models.TextChoices):
        AMPHITHEATRE = 'AMPHITHEATRE', 'Amphithéâtre'
        SALLE_COURS = 'SALLE_COURS', 'Salle de cours'
        LABORATOIRE = 'LABORATOIRE', 'Laboratoire'
        GYMNASE = 'GYMNASE', 'Gymnase'
        TERRAIN = 'TERRAIN', 'Terrain de sport'
        DOJO = 'DOJO', 'Dojo'
        PISCINE = 'PISCINE', 'Piscine'
        EXTERIEUR = 'EXTERIEUR', 'Espace extérieur'
        AUTRE = 'AUTRE', 'Autre espace'

    class StatutConfiguration(models.TextChoices):
        NON_CONFIGUREE = 'NON_CONFIGUREE', 'Non configurée'
        PARTIELLE = 'PARTIELLE', 'Partiellement configurée'
        CONFIGUREE = 'CONFIGUREE', 'Configurée'

    salle = models.OneToOneField(
        'formations.RefSalle',
        on_delete=models.CASCADE,
        related_name='geolocalisation',
    )
    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    rayon_tolerance_m = models.PositiveIntegerField(
        default=100,
        help_text='Rayon de tolérance du contrôle géographique, en mètres.',
    )
    zone_libelle = models.CharField(max_length=255, blank=True, default='')
    type_espace = models.CharField(
        max_length=20,
        choices=TypeEspace.choices,
        default=TypeEspace.SALLE_COURS,
    )
    statut_configuration = models.CharField(
        max_length=20,
        choices=StatutConfiguration.choices,
        default=StatutConfiguration.NON_CONFIGUREE,
        db_index=True,
    )
    actif = models.BooleanField(default=True)
    maj_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='salles_geolocalisation_maj',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'gi_salle_geolocalisation'
        verbose_name = 'GET – Géolocalisation de salle'
        verbose_name_plural = 'GET – Géolocalisations de salles'

    @property
    def coordonnees_disponibles(self):
        return self.latitude is not None and self.longitude is not None


class SeanceInstantaneAttendus(models.Model):
    """Instantané historique des étudiants attendus à une séance.

    Constitué à la demande (jamais figé dans la séance elle-même) : il
    préserve la cohérence historique si les inscriptions ou les affectations
    de groupe évoluent après sa constitution.
    """

    registre = models.ForeignKey(
        SeanceRegistre,
        on_delete=models.CASCADE,
        related_name='instantanes',
    )
    date_seance = models.DateField(
        null=True,
        blank=True,
        help_text="Date d'occurrence visée par l'instantané, si connue.",
    )
    base_calculee = models.CharField(
        max_length=120,
        blank=True,
        default='',
        help_text='Règle de calcul appliquée (groupe, inscriptions pédagogiques…).',
    )
    effectif = models.PositiveIntegerField(default=0)
    participants = models.JSONField(
        default=list,
        blank=True,
        help_text='[{participant_id, matricule, nom, prenom}] au moment de l’instantané.',
    )
    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='instantanes_seances',
    )
    cree_le = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'gi_seance_instantane'
        ordering = ['-cree_le', '-id']
        verbose_name = 'GET – Instantané des étudiants attendus'
        verbose_name_plural = 'GET – Instantanés des étudiants attendus'


@receiver(pre_delete, sender=AffectationCreneau)
def _proteger_seance_avec_pointages(sender, instance, **kwargs):
    """Une séance déjà associée à des pointages ne se supprime jamais.

    Règle de l'extension (§4.7) : l'historique de présence est préservé ;
    la voie correcte est l'annulation tracée du registre, pas la
    suppression physique de la ligne de placement.
    """
    from django.db.models.deletion import ProtectedError

    if instance.pointages.exists():
        raise ProtectedError(
            'Cette séance est associée à des pointages historiques : '
            'suppression physique interdite, utilisez l’annulation tracée.',
            list(instance.pointages.all()[:1]),
        )
