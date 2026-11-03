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


class Fiabilite(models.TextChoices):
    """Degré de fiabilité d'une valeur de référentiel (traçabilité source)."""

    OFFICIEL = 'OFFICIEL', 'Officiel (attesté par la source)'
    MODELISE = 'MODELISE', 'Modélisé dans la source (proposition)'
    CADRAGE = 'CADRAGE', 'Cadrage fonctionnel (à valider par l’INJS)'
    A_RENSEIGNER = 'A_RENSEIGNER', 'À renseigner'


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

    # ── Traçabilité de la provenance (exigence mission Référentiels) ──
    # Toute valeur importée d'un document porte la référence exacte de ce
    # document et son degré de fiabilité. Aucune donnée n'est présentée comme
    # officielle si la source ne l'atteste pas explicitement.
    source_document = models.CharField(
        max_length=255, blank=True, default='',
        help_text="Référence du document source ayant attesté la valeur.",
    )
    fiabilite = models.CharField(
        max_length=20, choices=Fiabilite.choices, default=Fiabilite.A_RENSEIGNER,
        db_index=True,
        help_text="Degré de fiabilité de la valeur au regard de sa source.",
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

    def reactiver(self, user=None, motif=''):
        """Sort une valeur de l'archive **et** la rend de nouveau utilisable.

        L'archivage désactive la valeur (règle 3) : réactiver sans réactiver
        laissait une valeur visible dans le journal mais absente de tous les
        sélecteurs et du filtre « Actifs » — l'utilisateur croyait l'opération
        sans effet. Réactivation et remise en service vont donc de pair.
        """
        self.archive = False
        self.actif = True
        self.date_activation = timezone.now()
        self.date_desactivation = None
        self.save(update_fields=[
            'archive', 'actif', 'date_activation', 'date_desactivation', 'modifie_le',
        ])
        self.journaliser(ReferentielJournal.Action.REACTIVATION, user, {'motif': motif})
        return self

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
        REACTIVATION = 'REACTIVATION', 'Réactivation'

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


# ═══════════════════════════════════════════════════════════════════════════
# RÉFÉRENTIELS DE L'OFFRE DE FORMATION INJS (refonte mission « Référentiels »)
#
# Chaîne métier officielle (document « Formations et Modules INJS », §1) :
#     ÉCOLE → MENTION → FILIÈRE → FORMATION (cycle Licence/Master)
#                    → PARCOURS → NIVEAU → SEMESTRE → UE → ECUE
# Les niveaux, semestres, parcours, maquettes, UE et ECUE restent portés par
# l'app `scolarite` (source unique existante, non dupliquée ici).
# ═══════════════════════════════════════════════════════════════════════════


class RefTypeCursus(RefSocle):
    """Nature du cursus — sépare le LMD des formations non universitaires.

    Le LMD (Licence/Master) ne doit jamais être confondu avec les cycles
    professionnels, la formation continue ou les préparations aux concours :
    ces catégories n'ont ni semestres académiques ni maquettes LMD.
    """

    class Meta(RefSocle.Meta):
        verbose_name = 'Référentiel – Type de cursus'
        verbose_name_plural = 'Référentiels – Types de cursus'


class RefEcole(RefSocle):
    """Écoles supérieures de l'INJS (ENSEPS, ENSEP)."""

    nom_complet = models.CharField(
        max_length=255, blank=True, default='',
        help_text="Dénomination développée de l'école.",
    )

    class Meta(RefSocle.Meta):
        verbose_name = 'Référentiel – École'
        verbose_name_plural = 'Référentiels – Écoles'


class RefMention(RefSocle):
    """Mention de rattachement (STAPS pour l'ENSEPS, STASE pour l'ENSEP)."""

    ecole = models.ForeignKey(
        RefEcole, on_delete=models.PROTECT, null=True, blank=True,
        related_name='mentions',
    )
    nom_complet = models.CharField(max_length=255, blank=True, default='')

    class Meta(RefSocle.Meta):
        verbose_name = 'Référentiel – Mention'
        verbose_name_plural = 'Référentiels – Mentions'


class RefFiliere(RefSocle):
    """Filière officielle de l'INJS (EM, ES, MS, APA, AND, LOI, ECJP, GER).

    La filière est le niveau de rattachement *métier* : une filière porte les
    cycles Licence et Master d'un même domaine. Elle est distincte de la
    formation (cycle diplômant), du parcours (spécialisation interne) et de la
    mention (regroupement disciplinaire).
    """

    ecole = models.ForeignKey(
        RefEcole, on_delete=models.PROTECT, related_name='filieres',
    )
    mention = models.ForeignKey(
        RefMention, on_delete=models.PROTECT, null=True, blank=True,
        related_name='filieres',
    )
    type_cursus = models.ForeignKey(
        RefTypeCursus, on_delete=models.PROTECT, related_name='filieres',
        null=True, blank=True,
    )
    ordre = models.PositiveSmallIntegerField(default=1)
    code_dossier = models.CharField(
        max_length=10, blank=True, default='', db_index=True,
        help_text='Code de dossier du référentiel A-4.5 (F01…F08) — clé de '
                  'réconciliation avec les cycles déjà importés.',
    )

    class Meta(RefSocle.Meta):
        ordering = ['ordre', 'code']
        verbose_name = 'Référentiel – Filière'
        verbose_name_plural = 'Référentiels – Filières'


class RefStatutVague(RefSocle):
    """Cycle de vie d'une vague de recrutement (document « Vagues INJS 2026 »)."""

    est_ouvert = models.BooleanField(
        default=False,
        help_text="Le statut autorise l'accueil de nouvelles candidatures.",
    )

    class Meta(RefSocle.Meta):
        verbose_name = 'Référentiel – Statut de vague'
        verbose_name_plural = 'Référentiels – Statuts de vague'


class RefTypeEnseignement(RefSocle):
    """Nature d'un enseignement : CM, TD, TP, stage (document « Volumes horaires »)."""

    abrege = models.CharField(max_length=10, blank=True, default='')
    est_stage = models.BooleanField(default=False)

    class Meta(RefSocle.Meta):
        verbose_name = "Référentiel – Type d'enseignement"
        verbose_name_plural = "Référentiels – Types d'enseignement"


class RefVolumeHoraireFormation(models.Model):
    """Volume horaire d'un module tel qu'il figure dans un document de cadrage.

    Distinct de ``formations.RefModuleVolumeHoraire`` (module × catégorie
    d'étudiant) : ici on décrit la répartition CM / TD / TP / stage d'un module
    pour une formation, avec la provenance exacte du chiffre. Les volumes du
    document de cadrage sont explicitement des **propositions** : ils sont donc
    importés avec ``fiabilite = MODELISE`` et ne valent jamais règle
    réglementaire.
    """

    formation = models.ForeignKey(
        'formations.RefFormation', on_delete=models.CASCADE,
        related_name='volumes_horaires_referentiel',
    )
    intitule_module = models.CharField(max_length=200)
    heures_cm = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    heures_td = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    heures_tp = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    heures_stage = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    heures_total = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)

    source_document = models.CharField(max_length=255, blank=True, default='')
    fiabilite = models.CharField(
        max_length=20, choices=Fiabilite.choices, default=Fiabilite.MODELISE,
    )
    cree_le = models.DateTimeField(auto_now_add=True)
    modifie_le = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['formation__intitule', 'intitule_module']
        verbose_name = 'Référentiel – Volume horaire (modélisation)'
        verbose_name_plural = 'Référentiels – Volumes horaires (modélisation)'
        constraints = [
            models.UniqueConstraint(
                fields=['formation', 'intitule_module'],
                name='uniq_volume_formation_module',
            ),
        ]

    def __str__(self):
        return f'{self.intitule_module} — {self.formation_id}'


class RefModuleOfficiel(models.Model):
    """Module (UE ou matière) tel qu'il figure dans une maquette officielle INJS.

    Pourquoi ce référentiel ? Les documents publient les listes de modules par
    formation et, pour Éducation et Motricité uniquement, par semestre. Ventiler
    de force les autres listes dans des semestres reviendrait à inventer une
    maquette. Ce référentiel conserve donc **la nomenclature officielle avec son
    degré de précision réel** (``semestre`` renseigné ou non) et expose l'écart
    à combler pour la ventilation en UE/ECUE du module Maquettes.
    """

    class EtatVentilation(models.TextChoices):
        A_VENTILER = 'A_VENTILER', 'À ventiler en maquette'
        VENTILE = 'VENTILE', 'Ventilé en maquette'

    formation = models.ForeignKey(
        'formations.RefFormation', on_delete=models.CASCADE,
        related_name='modules_officiels',
    )
    filiere_code = models.CharField(
        max_length=10, blank=True, default='', db_index=True,
        help_text='Code court de la filière (EM, APA, ES, MS, AND, LOI, ECJP, GER) '
                  'telle que la source la nomme ; le code dossier (F01…F08) est '
                  'porté par RefFiliere.code_dossier.',
    )
    semestre = models.CharField(
        max_length=10, blank=True, default='',
        help_text='Localisation documentée par la source : semestre (S1…S10), '
                  'plage (S1-S3) ou niveau (M1/M2). Vide si la source ne le précise pas.',
    )
    libelle = models.CharField(max_length=255)
    ordre = models.PositiveSmallIntegerField(default=1)
    etat_ventilation = models.CharField(
        max_length=20, choices=EtatVentilation.choices,
        default=EtatVentilation.A_VENTILER,
    )
    source_document = models.CharField(max_length=255, blank=True, default='')
    fiabilite = models.CharField(
        max_length=20, choices=Fiabilite.choices, default=Fiabilite.OFFICIEL,
    )
    cree_le = models.DateTimeField(auto_now_add=True)
    modifie_le = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['formation__intitule', 'semestre', 'ordre', 'libelle']
        verbose_name = 'Référentiel – Module officiel (maquette)'
        verbose_name_plural = 'Référentiels – Modules officiels (maquettes)'
        constraints = [
            models.UniqueConstraint(
                fields=['formation', 'semestre', 'libelle'],
                name='uniq_module_officiel_formation_semestre',
            ),
        ]

    def __str__(self):
        prefixe = f'{self.semestre} — ' if self.semestre else ''
        return f'{prefixe}{self.libelle}'
