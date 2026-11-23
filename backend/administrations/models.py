"""Modèles du lot L7 — Administration générale.

Conformité aux bonnes pratiques du dépôt INJS-LMD :
  - cycle de vie auditée via ``scolarite.JournalScolarite`` ;
  - les documents officiels et courriers ne sont jamais supprimés
    physiquement : ils passent à l'état ARCHIVE ;
  - permissions par rôles (``authentication.role_groups.user_in_roles``).
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class Courrier(models.Model):
    """Courrier entrant/sortant avec traçabilité et cycle de vie."""

    class Sens(models.TextChoices):
        ENTRANT = 'ENTRANT', 'Entrant'
        SORTANT = 'SORTANT', 'Sortant'

    class Statut(models.TextChoices):
        RECU = 'RECU', 'Reçu'
        EN_COURS = 'EN_COURS', 'En cours de traitement'
        REPONDU = 'REPONDU', 'Répondu'
        CLASSE = 'CLASSE', 'Classé'
        ARCHIVE = 'ARCHIVE', 'Archivé'

    sens = models.CharField(max_length=10, choices=Sens.choices)
    reference = models.CharField(max_length=100, unique=True)
    objet = models.CharField(max_length=255)
    expediteur = models.CharField(max_length=255, blank=True, default='')
    destinataire = models.CharField(max_length=255, blank=True, default='')
    date_courrier = models.DateField(null=True, blank=True)
    fichier = models.FileField(upload_to='administrations/courriers/', blank=True)
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.RECU)
    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        related_name='courriers_crees', null=True, blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'LMD – Courrier'
        verbose_name_plural = 'LMD – Courriers'

    def __str__(self):
        return f'{self.sens} {self.reference} – {self.objet}'

    def clean(self):
        if not self.reference.strip():
            raise ValidationError({'reference': 'La référence est obligatoire.'})


class DocumentOfficiel(models.Model):
    """Document officiel : note de service, arrêté, décision… versionné."""

    class Type(models.TextChoices):
        NOTE_SERVICE = 'NOTE_SERVICE', 'Note de service'
        ARRETE = 'ARRETE', 'Arrêté'
        DECISION = 'DECISION', 'Décision'
        CIRCULAIRE = 'CIRCULAIRE', 'Circulaire'
        AUTRE = 'AUTRE', 'Autre'

    class Statut(models.TextChoices):
        BROUILLON = 'BROUILLON', 'Brouillon'
        EN_VALIDATION = 'EN_VALIDATION', 'En validation'
        SIGNE = 'SIGNE', 'Signé'
        PUBLIE = 'PUBLIE', 'Publié'
        ARCHIVE = 'ARCHIVE', 'Archivé'

    type_document = models.CharField(max_length=20, choices=Type.choices, default=Type.NOTE_SERVICE)
    reference = models.CharField(max_length=100, blank=True, default='')
    titre = models.CharField(max_length=255)
    contenu = models.TextField(blank=True, default='')
    document_pdf = models.FileField(upload_to='administrations/documents/', blank=True)
    statut = models.CharField(max_length=20, choices=Statut.choices, default=Statut.BROUILLON)
    signe_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        related_name='documents_signes', null=True, blank=True,
    )
    date_signature = models.DateTimeField(null=True, blank=True)
    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        related_name='documents_crees', null=True, blank=True,
    )
    extra = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'LMD – Document officiel'
        verbose_name_plural = 'LMD – Documents officiels'

    def __str__(self):
        return f'{self.get_type_document_display()} {self.reference} – {self.titre}'


class VersionDocument(models.Model):
    """Version d'un document officiel (append-only, jamais modifiée)."""

    document = models.ForeignKey(
        DocumentOfficiel, on_delete=models.CASCADE, related_name='versions',
    )
    numero_version = models.PositiveIntegerField(default=1)
    contenu = models.TextField(blank=True, default='')
    fichier = models.FileField(upload_to='administrations/documents_versions/', blank=True)
    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['numero_version']
        unique_together = ('document', 'numero_version')

    def __str__(self):
        return f'{self.document} – v{self.numero_version}'
class ReunionCommission(models.Model):
    """Réunion ou commission avec ordre du jour et PV."""

    class Statut(models.TextChoices):
        PLANIFIEE = 'PLANIFIEE', 'Planifiée'
        TENUE = 'TENUE', 'Tenue'
        PV_EMIS = 'PV_EMIS', 'PV émis'
        ANNULEE = 'ANNULEE', 'Annulée'

    type_reunion = models.CharField(max_length=150)
    titre = models.CharField(max_length=255)
    date_reunion = models.DateField()
    heure_debut = models.TimeField(null=True, blank=True)
    heure_fin = models.TimeField(null=True, blank=True)
    lieu = models.CharField(max_length=255, blank=True, default='')
    ordre_du_jour = models.TextField(blank=True, default='')
    participants = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name='reunions')
    pv_contenu = models.TextField(blank=True, default='')
    pv_fichier = models.FileField(upload_to='administrations/reunions/pv/', blank=True)
    statut = models.CharField(max_length=15, choices=Statut.choices, default=Statut.PLANIFIEE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date_reunion']
        verbose_name = 'LMD – Réunion / Commission'

    def __str__(self):
        return f'{self.titre} – {self.date_reunion}'


class Mission(models.Model):
    """Mission / déplacement avec dates, lieu et budget."""

    class Statut(models.TextChoices):
        PROPOSEE = 'PROPOSEE', 'Proposée'
        VALIDEE = 'VALIDEE', 'Validée'
        REFUSEE = 'REFUSEE', 'Refusée'
        EN_COURS = 'EN_COURS', 'En cours'
        TERMINEE = 'TERMINEE', 'Terminée'
        ANNULEE = 'ANNULEE', 'Annulée'

    agent = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        related_name='missions', null=True, blank=True,
    )
    objet = models.CharField(max_length=255)
    lieu = models.CharField(max_length=255)
    date_debut = models.DateField()
    date_fin = models.DateField()
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.PROPOSEE)
    budget = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    motif_refus = models.TextField(blank=True, default='')
    valide_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        related_name='missions_validees', null=True, blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date_debut']
        verbose_name = 'LMD – Mission'

    def __str__(self):
        return f'{self.objet} – {self.lieu}'

    def clean(self):
        if self.date_fin < self.date_debut:
            raise ValidationError({'date_fin': 'La date de fin est antérieure à la date de début.'})

# ─────────────────────────────────────────────────────────────────────────────
# Organisation institutionnelle (complétion module Utilisateurs — 2026-09)
# ─────────────────────────────────────────────────────────────────────────────
# Référentiel additif Direction → Département, rattachant les services RH
# existants. Aucun service/secretariat existant n'est modifié : le rattachement
# est nullable (un service existe légitimement sans département rattaché) et le
# périmètre CURP « DIRECTION » portera ces entités (note J2).
class Direction(models.Model):
    """Direction de l'établissement (Direction Générale, Secrétariat Général…)."""

    code = models.CharField(max_length=30, unique=True, db_index=True)
    libelle = models.CharField(max_length=150)
    description = models.TextField(blank=True, default='')
    ordre = models.PositiveSmallIntegerField(default=0)
    actif = models.BooleanField(default=True)
    # Modèle fonctionnel 13.3 : la structure porte un responsable, un adjoint,
    # un contact et une localisation — sinon ces informations restent vides.
    responsable = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='directions_pilotees', verbose_name='Responsable',
    )
    adjoint = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='directions_adjointees', verbose_name='Adjoint(e)',
    )
    telephone = models.CharField(max_length=30, blank=True, default='', verbose_name='Téléphone')
    email = models.EmailField(blank=True, default='', verbose_name='E-mail')
    localisation = models.CharField(max_length=150, blank=True, default='',
                                    verbose_name='Localisation (bâtiment, étage, porte)')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['ordre', 'libelle']
        verbose_name = 'LMD – Direction'
        verbose_name_plural = 'LMD – Directions'

    def __str__(self):
        return self.libelle


class Departement(models.Model):
    """Département rattaché à une direction (ou autonome tant que non rattaché)."""

    code = models.CharField(max_length=30, unique=True, db_index=True)
    libelle = models.CharField(max_length=150)
    description = models.TextField(blank=True, default='')
    direction = models.ForeignKey(
        Direction, on_delete=models.PROTECT, null=True, blank=True,
        related_name='departements',
        help_text='Direction de rattachement (nullable : département autonome).',
    )
    ordre = models.PositiveSmallIntegerField(default=0)
    actif = models.BooleanField(default=True)
    # Modèle fonctionnel 13.3 : la structure porte un responsable, un adjoint,
    # un contact et une localisation — sinon ces informations restent vides.
    responsable = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='departements_pilotes', verbose_name='Responsable',
    )
    adjoint = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='departements_adjointes', verbose_name='Adjoint(e)',
    )
    telephone = models.CharField(max_length=30, blank=True, default='', verbose_name='Téléphone')
    email = models.EmailField(blank=True, default='', verbose_name='E-mail')
    localisation = models.CharField(max_length=150, blank=True, default='',
                                    verbose_name='Localisation (bâtiment, étage, porte)')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['ordre', 'libelle']
        verbose_name = 'LMD – Département'
        verbose_name_plural = 'LMD – Départements'

    def __str__(self):
        return self.libelle
