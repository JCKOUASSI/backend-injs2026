"""
Modèles de l'app Statistiques & Bilans — SYGEP-CPFAE.
"""
import hashlib
import json
from django.conf import settings
from django.db import models
from django.utils import timezone


class ConfigAlerteSeuil(models.Model):
    """Seuils paramétrables pour les alertes automatiques."""

    class Indicateur(models.TextChoices):
        TAUX_PRESENCE       = 'taux_presence',       'Taux de présence (%)'
        TAUX_ABSENCE        = 'taux_absence',         'Taux d\'absence (%)'
        TAUX_ABANDON        = 'taux_abandon',          'Taux d\'abandon (%)'
        TAUX_EXECUTION_VH   = 'taux_execution_vh',    'Taux d\'exécution volume horaire (%)'
        NB_ABSENCES_NOTOIRES= 'nb_absences_notoires', 'Absences notoires (nombre)'
        SATURATION_GROUPE   = 'saturation_groupe',    'Saturation du groupe (%)'

    indicateur         = models.CharField(max_length=50, choices=Indicateur.choices, unique=True)
    seuil_avertissement = models.FloatField(help_text="Seuil déclenchant un avertissement (ex: 70)")
    seuil_critique      = models.FloatField(help_text="Seuil déclenchant une alerte critique (ex: 50)")
    actif              = models.BooleanField(default=True)
    updated_at         = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = 'Configuration alerte – seuil'
        verbose_name_plural = 'Configuration alertes – seuils'
        ordering            = ['indicateur']

    def __str__(self):
        return f"{self.get_indicateur_display()} (⚠ {self.seuil_avertissement} / 🔴 {self.seuil_critique})"


class Rapport(models.Model):
    """Rapport périodique généré, avec workflow de validation."""

    class Type(models.TextChoices):
        QUOTIDIEN      = 'QUOTIDIEN',      'Quotidien'
        HEBDOMADAIRE   = 'HEBDOMADAIRE',   'Hebdomadaire'
        MENSUEL        = 'MENSUEL',         'Mensuel'
        TRIMESTRIEL    = 'TRIMESTRIEL',     'Trimestriel'
        SEMESTRIEL     = 'SEMESTRIEL',      'Semestriel'
        ANNUEL         = 'ANNUEL',          'Annuel'
        MI_PARCOURS    = 'MI_PARCOURS',     'À mi-parcours'
        CONSOLIDE      = 'CONSOLIDE',       'Consolidé FAB + FAC'
        FAB            = 'FAB',             'Spécifique FAB'
        FAC            = 'FAC',             'Spécifique FAC'

    class Statut(models.TextChoices):
        BROUILLON      = 'BROUILLON',      'Brouillon'
        EN_VALIDATION  = 'EN_VALIDATION',  'En validation'
        VALIDE         = 'VALIDE',         'Validé'
        PUBLIE         = 'PUBLIE',         'Publié'
        REJETE         = 'REJETE',         'Rejeté'

    titre          = models.CharField(max_length=255)
    type           = models.CharField(max_length=30, choices=Type.choices)
    statut         = models.CharField(max_length=20, choices=Statut.choices, default=Statut.BROUILLON)
    periode_debut  = models.DateField()
    periode_fin    = models.DateField()
    formation      = models.ForeignKey(
        'formations.Formation',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='rapports',
        help_text="Formation ciblée (null = toutes formations)",
    )
    secretariat    = models.ForeignKey(
        'formations.Secretariat',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='rapports',
        help_text='Secrétariat ciblé (null = périmètre global)',
    )
    generateur     = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='rapports_generes',
    )
    validateur     = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='rapports_valides',
    )
    date_validation   = models.DateTimeField(null=True, blank=True)
    date_publication  = models.DateTimeField(null=True, blank=True)
    donnees_json      = models.JSONField(default=dict, help_text="Snapshot des statistiques calculées")
    commentaire       = models.TextField(blank=True)
    created_at        = models.DateTimeField(auto_now_add=True)
    updated_at        = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = 'Rapport'
        verbose_name_plural = 'Rapports'
        ordering            = ['-created_at']

    def __str__(self):
        return f"{self.titre} ({self.get_statut_display()})"

    @property
    def hash_donnees(self):
        payload = json.dumps(self.donnees_json, sort_keys=True, default=str)
        return hashlib.sha256(payload.encode()).hexdigest()


class ObservationQualitative(models.Model):
    """Saisie manuelle des difficultés et points positifs associés à un rapport."""

    class Type(models.TextChoices):
        DIFF_LOGISTIQUE        = 'DIFF_LOG',  'Difficulté logistique'
        DIFF_PEDAGOGIQUE       = 'DIFF_PED',  'Difficulté pédagogique'
        DIFF_TECHNIQUE         = 'DIFF_TECH', 'Difficulté technique'
        DIFF_ORGANISATIONNELLE = 'DIFF_ORG',  'Difficulté organisationnelle'
        POINT_POSITIF          = 'POSITIF',   'Point positif'

    rapport      = models.ForeignKey(Rapport, on_delete=models.CASCADE, related_name='observations')
    type         = models.CharField(max_length=20, choices=Type.choices)
    description  = models.TextField()
    auteur       = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
    )
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = 'Observation qualitative'
        verbose_name_plural = 'Observations qualitatives'
        ordering            = ['rapport', 'type']

    def __str__(self):
        return f"[{self.get_type_display()}] {self.description[:60]}"


class SignatureRapport(models.Model):
    """Visa hiérarchique et signature numérique d'un rapport."""

    rapport         = models.ForeignKey(Rapport, on_delete=models.CASCADE, related_name='signatures')
    signataire      = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
    )
    role_signataire = models.CharField(max_length=50)
    date_signature  = models.DateTimeField(auto_now_add=True)
    commentaire     = models.TextField(blank=True)
    hash_rapport    = models.CharField(max_length=64, help_text="SHA-256 du contenu du rapport au moment de la signature")

    class Meta:
        verbose_name        = 'Signature de rapport'
        verbose_name_plural = 'Signatures de rapports'
        ordering            = ['-date_signature']

    def __str__(self):
        return f"Signature de {self.signataire} sur « {self.rapport.titre} »"


class NotificationRapport(models.Model):
    """Notification in-app (et e-mail) lors de la modification ou suppression d'un rapport."""

    class Evenement(models.TextChoices):
        MODIFIE  = 'MODIFIE',  'Rapport modifié'
        SUPPRIME = 'SUPPRIME', 'Rapport supprimé'
        SOUMIS   = 'SOUMIS',   'Rapport soumis à validation'
        VALIDE   = 'VALIDE',   'Rapport validé'
        PUBLIE   = 'PUBLIE',   'Rapport publié'
        REJETE   = 'REJETE',   'Rapport rejeté'

    destinataire  = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications_rapport',
    )
    evenement     = models.CharField(max_length=20, choices=Evenement.choices)
    rapport_id    = models.PositiveIntegerField(null=True, blank=True)
    rapport_titre = models.CharField(max_length=255)
    message       = models.TextField()
    auteur        = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='notifications_rapport_emises',
    )
    lu            = models.BooleanField(default=False)
    created_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = 'Notification rapport'
        verbose_name_plural = 'Notifications rapports'
        ordering            = ['-created_at']

    def __str__(self):
        return f"{self.get_evenement_display()} — {self.rapport_titre} → {self.destinataire}"
