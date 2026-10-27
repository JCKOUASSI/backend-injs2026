"""Socle commun des référentiels INJS (lot L0/L7 — prompt n°4).

Règles appliquées à tous les référentiels (existants et nouveaux) :
1. code métier unique ;
2. jamais de suppression physique d'une valeur utilisée (archivage/soft delete) ;
3. dates d'activation/désactivation ;
4. anti-doublons (unicité Lower() comme Parcours/Groupe/UE/ECUE) ;
5. une valeur archivée ne peut pas être utilisée dans une nouvelle opération ;
6. historisation des modifications (ReferentielJournal) ;
7. rattachement facultatif à AnneeAcademique.
Règles 8 et 9 : aucune duplication formation/étudiant/module/année entre apps ;
aucune valeur métier codée en dur côté React/Flutter (tout passe par l'API).
"""
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone


class RefSocle(models.Model):
    """Socle abstrait commun à tous les référentiels de l'app referentiels."""

    code = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        help_text="Code métier unique (ex: ECRIT, VIREMENT, EXAMEN).",
    )
    libelle = models.CharField(max_length=150)
    description = models.TextField(blank=True, default='')

    # Règle 3 — dates d'activation/désactivation
    actif = models.BooleanField(default=True, db_index=True)
    date_activation = models.DateTimeField(null=True, blank=True)
    date_desactivation = models.DateTimeField(null=True, blank=True)

    # Règle 2 — archivage (soft delete), jamais de suppression physique
    archive = models.BooleanField(default=False, db_index=True)

    # Règle 7 — rattachement facultatif à une année académique
    annee_academique = models.ForeignKey(
        'scolarite.AnneeAcademique',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='+',
        help_text="Renseigner si la valeur est propre à une année académique.",
    )

    cree_le = models.DateTimeField(auto_now_add=True)
    modifie_le = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ['libelle']
        # Règle 4 — anti-doublons insensibles à la casse (comme Parcours/Groupe/UE/ECUE)
        constraints = [
            models.UniqueConstraint(
                Lower('libelle'),
                name='%(app_label)s_%(class)s_libelle_lower_uniq',
            ),
        ]

    def __str__(self):
        return f'{self.libelle} ({self.code})'

    # ── Cycle de vie (règles 2, 3, 5, 6) ──
    def activer(self, user=None, motif=''):
        self.actif = True
        self.date_activation = timezone.now()
        self.date_desactivation = None
        self.save(update_fields=['actif', 'date_activation', 'date_desactivation', 'modifie_le'])
        self.journaliser(ReferentielJournal.Action.ACTIVATION, user, {'motif': motif})

    def desactiver(self, user=None, motif=''):
        self.actif = False
        self.date_desactivation = timezone.now()
        self.save(update_fields=['actif', 'date_desactivation', 'modifie_le'])
        self.journaliser(ReferentielJournal.Action.DESACTIVATION, user, {'motif': motif})

    def archiver(self, user=None, motif=''):
        """Règle 2 : archivage au lieu de suppression — réversible."""
        self.archive = True
        if self.actif:
            self.actif = False
            self.date_desactivation = timezone.now()
        self.save(update_fields=['archive', 'actif', 'date_desactivation', 'modifie_le'])
        self.journaliser(ReferentielJournal.Action.ARCHIVAGE, user, {'motif': motif})

    @classmethod
    def usables(cls):
        """Règle 5 : valeurs utilisables dans une nouvelle opération."""
        return cls.objects.filter(actif=True, archive=False)

    def journaliser(self, action, user=None, detail=None):
        ReferentielJournal.objects.create(
            content_type=ContentType.objects.get_for_model(self),
            object_id=self.pk,
            action=action,
            utilisateur=user if (user and user.is_authenticated) else None,
            detail=detail or {},
        )


class ReferentielJournal(models.Model):
    """Règle 6 — historique immuable (append-only) des modifications."""

    class Action(models.TextChoices):
        CREATION = 'CREATION', 'Création'
        MODIFICATION = 'MODIFICATION', 'Modification'
        ACTIVATION = 'ACTIVATION', 'Activation'
        DESACTIVATION = 'DESACTIVATION', 'Désactivation'
        ARCHIVAGE = 'ARCHIVAGE', 'Archivage'

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveBigIntegerField(db_index=True)
    cible = GenericForeignKey('content_type', 'object_id')

    action = models.CharField(max_length=20, choices=Action.choices, db_index=True)
    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='modifications_referentiels',
    )
    horodatage = models.DateTimeField(auto_now_add=True, db_index=True)
    detail = models.JSONField(null=True, blank=True)

    class Meta:
        verbose_name = 'Journal référentiel'
        verbose_name_plural = 'Journal référentiels'
        ordering = ['-horodatage']
        indexes = [
            models.Index(fields=['content_type', 'object_id'], name='refjournal_cible_idx'),
            models.Index(fields=['action', 'horodatage'], name='refjournal_action_idx'),
        ]

    def __str__(self):
        return f'{self.action} #{self.object_id} @ {self.horodatage:%Y-%m-%d %H:%M}'



class RefTypeEvaluation(RefSocle):
    """Types d'évaluation (examen, contrôle continu, rattrapage…)."""

    class Meta(RefSocle.Meta):
        verbose_name = 'Référentiel – Type d’évaluation'
        verbose_name_plural = 'Référentiel – Types d’évaluation'


class RefTypeDocument(RefSocle):
    """Types de documents officiels et justificatifs."""

    class Meta(RefSocle.Meta):
        verbose_name = 'Référentiel – Type de document'
        verbose_name_plural = 'Référentiel – Types de document'


class RefGradeEnseignant(RefSocle):
    """Grades / statuts des enseignants et encadrants."""

    class Meta(RefSocle.Meta):
        verbose_name = 'Référentiel – Grade enseignant'
        verbose_name_plural = 'Référentiel – Grades enseignants'


class RefTypeFrais(RefSocle):
    """Types de frais (inscription, scolarité, examen, réinscription…)."""

    class Meta(RefSocle.Meta):
        verbose_name = 'Référentiel – Type de frais'
        verbose_name_plural = 'Référentiel – Types de frais'


class RefModePaiement(RefSocle):
    """Modes de paiement (espèces, virement, mobile money…)."""

    class Meta(RefSocle.Meta):
        verbose_name = 'Référentiel – Mode de paiement'
        verbose_name_plural = 'Référentiel – Modes de paiement'


class RefTypeDecision(RefSocle):
    """Types de décisions pédagogiques et de jury."""

    class Meta(RefSocle.Meta):
        verbose_name = 'Référentiel – Type de décision'
        verbose_name_plural = 'Référentiel – Types de décision'


class RefTypeNotification(RefSocle):
    """Types de notifications du système (alertes, rappels, validations…)."""

    class Meta(RefSocle.Meta):
        verbose_name = 'Référentiel – Type de notification'
        verbose_name_plural = 'Référentiel – Types de notification'


class RefTypeEspaceSportif(RefSocle):
    """Types d'espaces / équipements sportifs (terrain, gymnase, piscine…)."""

    class Meta(RefSocle.Meta):
        verbose_name = 'Référentiel – Type d’espace sportif'
        verbose_name_plural = 'Référentiel – Types d’espace sportif'
