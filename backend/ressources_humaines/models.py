"""Modèles du lot L7 — Ressources Humaines.

Agents, services, fonctions, affectations RH et disponibilités.
Règles :
  - chevauchement de disponibilités interdit (garde en clean) ;
  - une affectation RH est historisée (AffectationRH, jamais écrasée) ;
  - indépendant de ``formations.Formateur`` : la paie formateurs reste
    gérée par le module formations existant (aucune duplication).
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class Service(models.Model):
    """Service de l'établissement (modèle fonctionnel 13.3 : unit =
    Direction / Département / Service / Bureau — le Service est l'unité
    feuille de l'organigramme, rattachée à un département)."""

    code = models.CharField(max_length=30, blank=True, default='', db_index=True,
                            help_text='Code court du service (ex. SCOL01).')
    # Modèle 13.4 : la feuille de l'organigramme est typée et imbriquable —
    # un SERVICE peut porter des BUREAUX / UNITÉS / CELLULES sans coder de
    # niveau fixe (« représenter l'organisation réelle sans la figer »).
    class TypeUnite(models.TextChoices):
        SERVICE = 'SERVICE', 'Service'
        BUREAU = 'BUREAU', 'Bureau'
        UNITE = 'UNITE', 'Unité'
        CELLULE = 'CELLULE', 'Cellule'
        AUTRE = 'AUTRE', 'Autre'

    type_unite = models.CharField(max_length=12, choices=TypeUnite.choices,
                                  default=TypeUnite.SERVICE, verbose_name='Type d’unité')
    parent = models.ForeignKey(
        'self', on_delete=models.PROTECT, null=True, blank=True,
        related_name='sous_unites', verbose_name='Unité rattachante',
        help_text='Pour les sous-unités (bureau, unité, cellule) d’un service.',
    )
    nom = models.CharField(max_length=150, unique=True)
    description = models.TextField(blank=True, default='')
    responsable = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='services_pilotes', verbose_name='Responsable',
    )
    adjoint = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='services_adjointes', verbose_name='Adjoint(e)',
    )
    telephone = models.CharField(max_length=30, blank=True, default='', verbose_name='Téléphone')
    email = models.EmailField(blank=True, default='', verbose_name='E-mail')
    localisation = models.CharField(max_length=150, blank=True, default='',
                                    verbose_name='Localisation (bâtiment, étage, porte)')
    departement = models.ForeignKey(
        'administrations.Departement', on_delete=models.PROTECT,
        null=True, blank=True, related_name='services',
        help_text='Département de rattachement (nullable : service non rattaché).',
    )
    actif = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['nom']
        verbose_name = 'LMD – Service'

    def __str__(self):
        return self.nom


class Fonction(models.Model):
    """Fonction occupée par un agent au sein d'un service."""

    intitule = models.CharField(max_length=150)
    service = models.ForeignKey(Service, on_delete=models.PROTECT, related_name='fonctions')
    grade = models.CharField(max_length=100, blank=True, default='')
    actif = models.BooleanField(default=True)

    class Meta:
        ordering = ['intitule']
        unique_together = ('intitule', 'service')
        verbose_name = 'LMD – Fonction'

    def __str__(self):
        return f'{self.intitule} ({self.service.nom})'


class Agent(models.Model):
    """Agent de l'établissement (personnel administratif et technique)."""

    class TypeContrat(models.TextChoices):
        CONTRAT = 'CONTRAT', 'Contractuel'
        VACATAIRE = 'VACATAIRE', 'Vacataire'
        FONCTIONNAIRE = 'FONCTIONNAIRE', 'Fonctionnaire'
        BENEVOLE = 'BENEVOLE', 'Bénévole'

    class Statut(models.TextChoices):
        ACTIF = 'ACTIF', 'Actif'
        INACTIF = 'INACTIF', 'Inactif'

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        related_name='agent_rh', null=True, blank=True,
    )
    matricule = models.CharField(max_length=50, unique=True)
    nom = models.CharField(max_length=100)
    prenom = models.CharField(max_length=100, blank=True, default='')
    email = models.EmailField(blank=True, default='')
    telephone = models.CharField(max_length=30, blank=True, default='')
    type_contrat = models.CharField(max_length=20, choices=TypeContrat.choices, default=TypeContrat.CONTRAT)
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.ACTIF)
    date_entree = models.DateField(null=True, blank=True)
    date_sortie = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['nom', 'prenom']
        verbose_name = 'LMD – Agent'
        verbose_name_plural = 'LMD – Agents'

    def __str__(self):
        return f'{self.nom} {self.prenom}'.strip() or self.matricule

    def clean(self):
        if not self.nom.strip():
            raise ValidationError({'nom': 'Le nom est obligatoire.'})


class AffectationRH(models.Model):
    """Affectation d'un agent à une fonction (historisée)."""

    agent = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name='affectations')
    fonction = models.ForeignKey(Fonction, on_delete=models.PROTECT, related_name='affectations')
    date_debut = models.DateField()
    date_fin = models.DateField(null=True, blank=True)
    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date_debut']
        verbose_name = 'LMD – Affectation RH'

    def __str__(self):
        return f'{self.agent} → {self.fonction} ({self.date_debut})'


class DisponibiliteAgent(models.Model):
    """Période d'indisponibilité d'un agent (congé, mission, formation)."""

    class TypeIndispo(models.TextChoices):
        CONGE = 'CONGE', 'Congé'
        MISSION = 'MISSION', 'Mission'
        FORMATION = 'FORMATION', 'Formation'
        MALADIE = 'MALADIE', 'Maladie'
        AUTRE = 'AUTRE', 'Autre'

    agent = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name='disponibilites')
    type_indispo = models.CharField(max_length=15, choices=TypeIndispo.choices, default=TypeIndispo.CONGE)
    motif = models.CharField(max_length=255, blank=True, default='')
    date_debut = models.DateField()
    date_fin = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date_debut']
        verbose_name = 'LMD – Disponibilité agent'

    def __str__(self):
        return f'{self.agent} – {self.get_type_indispo_display()} ({self.date_debut}→{self.date_fin})'

    def clean(self):
        if self.date_fin < self.date_debut:
            raise ValidationError({'date_fin': 'La date de fin est antérieure à la date de début.'})
        collisions = DisponibiliteAgent.objects.filter(agent=self.agent)
        if self.pk:
            collisions = collisions.exclude(pk=self.pk)
        for d in collisions:
            if d.date_debut <= self.date_fin and d.date_fin >= self.date_debut:
                raise ValidationError(
                    {'date_debut': f'Chevauchement avec {d.get_type_indispo_display()} '
                                   f'({d.date_debut} → {d.date_fin}).'}
                )


class DocumentRH(models.Model):
    """Document administratif d'un agent (contrat, évaluation…)."""

    class TypeDocument(models.TextChoices):
        CONTRAT = 'CONTRAT', 'Contrat'
        AVIS = 'AVIS', 'Avis de situation'
        EVALUATION = 'EVALUATION', 'Évaluation'
        ATTESTATION = 'ATTESTATION', 'Attestation'
        AUTRE = 'AUTRE', 'Autre'

    agent = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name='documents')
    type_document = models.CharField(max_length=15, choices=TypeDocument.choices, default=TypeDocument.CONTRAT)
    intitule = models.CharField(max_length=255)
    fichier = models.FileField(upload_to='rh/documents/', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'LMD – Document RH'

    def __str__(self):
        return f'{self.agent} – {self.get_type_document_display()} {self.intitule}'
