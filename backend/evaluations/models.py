"""Lot C1 — SOCLE technique des « Évaluations académiques » INJS-LMD.

Périmètre de ce fichier : STRUCTURE uniquement (contrat B.1 §21).

Il contient volontairement **aucun calcul métier** :
    * pas de moyenne ECUE / UE / semestre / ECTS (C2) ;
    * pas de politique d'absence, de pondération par défaut, de seuil ;
    * pas de rattrapage, de jury automatique, de délibération ;
    * pas de relevé définitif ;
    * aucun seed de référentiel (les types d'évaluation sont saisis).

Chaîne canonique (contrat B.1 §7, correction n°4) :
    InscriptionPedagogique → EvaluationParticipant → Evaluation
        → AffectationPedagogique → ECUE → EvaluationComponent → EvaluationGrade

Règle structurante : **Module (formations) ≠ ECUE (scolarite)**.
``ECUE.ref_module`` reste une passerelle de compatibilité *déclarée* ;
elle n'est jamais utilisée comme résolution d'un ECUE par le socle.

Toutes les clés pédagogiques utilisent ``on_delete=PROTECT`` : aucune
suppression en cascade d'un ECUE, d'une UE, d'une inscription ou d'un
formateur tant que des données d'évaluation les référencent.
"""
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Coalesce

from scolarite.models import (
    AffectationPedagogique,
    AnneeAcademique,
    ECUE,
    Groupe,
    InscriptionPedagogique,
    Maquette,
    Niveau,
    Parcours,
    Semestre,
    UE,
)

#: États d'une session d'évaluation (contrat B.1 §14).
#: Un état = une responsabilité unique : aucune confusion entre « clôture de
#: la saisie » (CLOTUREE) et « validation des résultats » (RESULTATS_VALIDES).
STATUTS_SESSION = (
    ('BROUILLON', 'Brouillon'),
    ('PLANIFIEE', 'Planifiée'),
    ('PUBLIEE', 'Publiée'),
    ('OUVERTE', 'Ouverte (saisie possible)'),
    ('CLOTUREE', 'Clôturée (saisie fermée)'),
    ('CALCULS', 'Calculs effectués'),
    ('RESULTATS_VALIDES', 'Résultats validés'),
    ('VERROUILLEE', 'Verrouillée'),
    ('ARCHIVEE', 'Archivée'),
)

#: États d'une épreuve (contrat B.1 §15). Pas de redondance : une épreuve
#: ne peut être « terminée » et « en correction » en même temps.
STATUTS_EPREUVE = (
    ('PLANIFIEE', 'Planifiée'),
    ('PROGRAMMEE', 'Programmée'),
    ('CONVOCEE', 'Convocations émises'),
    ('EN_COURS', 'En cours'),
    ('CORRECTION', 'En correction'),
    ('CORRIGEE', 'Corrigée'),
    ('CLOTUREE', 'Clôturée'),
    ('ANNULEE', 'Annulée'),
)

#: États de participation (contrat B.1 §12).
STATUTS_PARTICIPATION = (
    ('EN_ATTENTE', 'En attente'),
    ('PRESENT', 'Présent'),
    ('ABSENT', 'Absent'),
    ('ABSENT_JUSTIFIE', 'Absent justifié'),
    ('ABSENT_INJUSTIFIE', 'Absent injustifié'),
    ('DISPENSE', 'Dispensé'),
    ('EXCLU', 'Exclu'),
    ('NON_INSCRIT', 'Non inscrit'),
    ('EN_ATTENTE_NOTE', 'Note en attente'),
)

#: États d'émargement (contrat B.1 §12).
#: ABSENT/COPIE_ANNULEE ne sont PAS des notes : ils ne produisent aucune
#: valeur de calcul (invariant testé en C1).
STATUTS_PRESENCE = (
    ('PRESENT', 'Présent'),
    ('ABSENT', 'Absent'),
    ('ABSENT_JUSTIFIE', 'Absent justifié'),
    ('ABSENT_INJUSTIFIE', 'Absent injustifié'),
    ('DISPENSE', 'Dispensé'),
    ('EXCLU', 'Exclu'),
    ('COPIE_ANNULEE', 'Copie annulée'),
    ('EN_ATTENTE', 'En attente'),
)

#: États d'une note. Le cycle BROUILLON → SOUMISE → VALIDEE du workflow
#: existant (formations.NoteModule, lot L1) est conservé tel quel
#: (contrat B.1 §8) ; CORRECTION_DEMANDEE est un retour de validation.
STATUTS_NOTE = (
    ('BROUILLON', 'Brouillon'),
    ('SOUMISE', 'Soumise'),
    ('CORRECTION_DEMANDEE', 'Correction demandée'),
    ('VALIDEE', 'Validée (verrouillée)'),
)

#: Catégories de règles. Aucune règle n'est présentée comme « officielle INJS »
#: sans source : tout ce qui n'est pas sourcé reste catégorie C (contrat B.1 §20).
CATEGORIES_REGLE = (
    ('A', 'Règle INJS documentée'),
    ('B', 'Règle LMD / cadre national'),
    ('C', 'Paramètre configurable / non sourcé'),
)

#: Sources autorisées pour un résultat. COMPAT_MODULE est strictement
#: conditionnel (contrat B.1 §8) et n'est produit par aucun code en C1 :
#: il n'est créé que par le moteur C2, sous ses 7 conditions cumulatives.
SOURCES_RESULTAT = (
    ('MOTEUR_LMD', 'Moteur LMD (source canonique)'),
    ('COMPAT_MODULE', 'Compatibilité historique (passerelle ref_module)'),
    ('SAISIE_MANUELLE', 'Saisie manuelle autorisée'),
)

MIGRATION_STATUS = (
    ('CONFIRMED', 'Confirmé'),
    ('AMBIGUOUS', 'Ambigu'),
    ('LEGACY', 'Legacy'),
    ('UNMAPPED', 'Non mappé (aucun résultat inventé)'),
)

class RegleCalcul(models.Model):
    """Familie logique de règle (niveau 1 du versionnement, B.1 §9).

    Codes attendus : ``PONDERATION_ECUE``, ``VALIDATION_UE``, ``ABSENCE``,
    ``ARRONDI``, ``RATTRAPAGE``. Le socle ne crée **aucune** règle : les
    familles sont saisies par la scolarité puis versionnées (DECISION-1 :
    aucun seuil ni pondération par défaut inventé).
    """

    code = models.CharField(max_length=50, unique=True)
    libelle = models.CharField(max_length=255)
    categorie = models.CharField(max_length=1, choices=CATEGORIES_REGLE, default='C')
    source = models.TextField(
        blank=True, default='',
        help_text='Référence exacte de la source, ou « PARAMETRABLE ».',
    )
    description = models.TextField(blank=True, default='')
    actif = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['code']
        verbose_name = 'LMD – Famille de règle de calcul'
        verbose_name_plural = 'LMD – Familles de règles de calcul'

    def __str__(self):
        return f'{self.code} ({self.categorie})'


class RegleCalculVersion(models.Model):
    """Version d'une règle pour un périmètre et une période (niveau 2).

    ``verrouillee=True`` rend la version immuable. Le snapshot copié dans
    chaque résultat reste de toute façon autoritaire (B.1 §9).
    """

    regle = models.ForeignKey(
        RegleCalcul, on_delete=models.PROTECT, related_name='versions',
    )
    version = models.PositiveIntegerField(default=1)
    ref_formation = models.ForeignKey(
        'formations.RefFormation', on_delete=models.PROTECT,
        related_name='regles_calcul_evaluations', null=True, blank=True,
        verbose_name='Formation (cycle) — vide = global',
    )
    niveau = models.ForeignKey(
        Niveau, on_delete=models.PROTECT, related_name='regles_calcul_evaluations',
        null=True, blank=True,
    )
    semestre = models.ForeignKey(
        Semestre, on_delete=models.PROTECT,
        related_name='regles_calcul_evaluations', null=True, blank=True,
    )
    date_effet = models.DateField()
    date_fin = models.DateField(null=True, blank=True)
    parametres = models.JSONField(
        default=dict, blank=True,
        help_text='Paramètres appliqués (copiés à l\'instantané du calcul).',
    )
    verrouillee = models.BooleanField(default=False)
    publiee_le = models.DateTimeField(null=True, blank=True)
    publiee_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='regles_calcul_evaluations_publiees',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['regle__code', '-version', '-date_effet']
        verbose_name = 'LMD – Version de règle de calcul'
        verbose_name_plural = 'LMD – Versions de règles de calcul'
        constraints = [
            models.UniqueConstraint(
                fields=['regle', 'version', 'ref_formation', 'niveau', 'semestre', 'date_effet'],
                name='uniq_regle_calcul_version_perimetre',
            ),
        ]

    def __str__(self):
        return f'{self.regle.code} v{self.version}'

    def clean(self):
        if self.date_fin and self.date_fin < self.date_effet:
            raise ValidationError({'date_fin': 'La fin doit être postérieure au début.'})

    def save(self, *args, **kwargs):
        # Immuabilité dès verrouillage : les déverrouillages métier
        # appartiennent à C2, pas au socle.
        if self.pk and self.verrouillee:
            version = RegleCalculVersion.objects.filter(pk=self.pk).first()
            if version is not None and version.verrouillee:
                raise ValidationError(
                    f'Version de règle verrouillée ({self}) : créez une nouvelle version.'
                )
        self.clean()
        super().save(*args, **kwargs)


class TypeEvaluation(models.Model):
    """Référentiel des types d'évaluation — paramétrable, sans seed en C1."""

    code = models.CharField(max_length=30, unique=True)
    libelle = models.CharField(max_length=255)
    categorie = models.CharField(
        max_length=30, blank=True, default='',
        help_text='Libellé libre de regroupement (contrôle continu, examen, oral…).',
    )
    actif = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['code']
        verbose_name = 'LMD – Type d\'évaluation'
        verbose_name_plural = 'LMD – Types d\'évaluation'

    def __str__(self):
        return self.code

class SessionEvaluation(models.Model):
    """Session d'évaluation LMD (contrat B.1 §14).

    NORMALE / RATTRAPAGE / RECTIFICATION. Le périmètre est explicite
    (année, formation, parcours, niveau, semestre, maquette) : aucun
    module ni groupe n'est déduit.
    """

    class TypeSession(models.TextChoices):
        NORMALE = 'NORMALE', 'Session normale'
        RATTRAPAGE = 'RATTRAPAGE', 'Rattrapage'
        RECTIFICATION = 'RECTIFICATION', 'Rectification'

    annee_academique = models.ForeignKey(
        AnneeAcademique, on_delete=models.PROTECT, related_name='sessions_evaluation',
    )
    ref_formation = models.ForeignKey(
        'formations.RefFormation', on_delete=models.PROTECT,
        related_name='sessions_evaluation', verbose_name='Formation (cycle)',
    )
    parcours = models.ForeignKey(
        Parcours, on_delete=models.PROTECT, related_name='sessions_evaluation',
        null=True, blank=True,
    )
    niveau = models.ForeignKey(
        Niveau, on_delete=models.PROTECT, related_name='sessions_evaluation',
    )
    semestre = models.ForeignKey(
        Semestre, on_delete=models.PROTECT, related_name='sessions_evaluation',
        null=True, blank=True, help_text='Vide = session annuelle.',
    )
    maquette = models.ForeignKey(
        Maquette, on_delete=models.PROTECT, related_name='sessions_evaluation',
        help_text='Version de maquette supportant la session.',
    )
    type_session = models.CharField(
        max_length=15, choices=TypeSession.choices, default=TypeSession.NORMALE,
    )
    session_origine = models.ForeignKey(
        'self', on_delete=models.PROTECT, related_name='sessions_derivees',
        null=True, blank=True,
        help_text="Session normale d'origine (obligatoire si RATTRAPAGE).",
    )
    libelle = models.CharField(max_length=255, blank=True, default='')
    date_debut = models.DateField(null=True, blank=True)
    date_fin = models.DateField(null=True, blank=True)
    statut = models.CharField(
        max_length=20, choices=STATUTS_SESSION, default='BROUILLON', db_index=True,
    )
    verrouillee = models.BooleanField(default=False, db_index=True)
    verrouillee_le = models.DateTimeField(null=True, blank=True)
    verrouillee_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='sessions_evaluation_verrouillees',
    )
    regle_version = models.ForeignKey(
        RegleCalculVersion, on_delete=models.PROTECT,
        related_name='sessions_evaluation', null=True, blank=True,
        help_text='Gelé au passage en CALCULS (DECISION-14).',
    )
    creee_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='sessions_evaluation_creees',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-annee_academique__libelle', 'semestre__numero', 'type_session']
        verbose_name = "LMD – Session d'évaluation"
        verbose_name_plural = "LMD – Sessions d'évaluation"
        constraints = [
            # Contrainte d'unicité sur expressions : les parcours et
            # semestres nullables utiliseraient sinon des NULL (NULL != NULL
            # en SQL) et la contrainte serait inopérante. Coalesce(x, 0)
            # matérialise « pas de parcours / pas de semestre ».
            models.UniqueConstraint(
                'annee_academique_id',
                'ref_formation_id',
                'niveau_id',
                Coalesce('semestre_id', models.Value(0)),
                Coalesce('parcours_id', models.Value(0)),
                'type_session',
                name='uniq_session_evaluation_perimetre',
            ),
        ]
        indexes = [
            models.Index(fields=['annee_academique', 'ref_formation']),
            models.Index(fields=['statut']),
        ]

    def __str__(self):
        return f'{self.type_session} {self.annee_academique} — {self.ref_formation}'

    def clean(self):
        erreurs = {}
        if self.date_debut and self.date_fin and self.date_fin < self.date_debut:
            erreurs['date_fin'] = 'La fin doit être postérieure au début.'
        if self.type_session == self.TypeSession.RATTRAPAGE and not self.session_origine_id:
            erreurs['session_origine'] = "Un rattrapage doit référencer sa session d'origine."
        if self.session_origine_id and self.session_origine_id == self.pk:
            erreurs['session_origine'] = 'Une session ne peut pas être sa propre origine.'
        if self.maquette_id and self.annee_academique_id:
            if self.maquette.annee_academique_id != self.annee_academique_id:
                erreurs['maquette'] = "La maquette n'appartient pas à l'année de la session."
            if self.maquette.ref_formation_id != self.ref_formation_id:
                erreurs['maquette'] = "La maquette n'appartient pas à la formation de la session."
        if erreurs:
            raise ValidationError(erreurs)

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)


class Evaluation(models.Model):
    """Ce qui est évalué : ECUE + affectation + session + type (B.1 §4).

    Les notions de poids restent **séparées et jamais multipliées entre
    niveaux** (B.1 §5) :
      * ``poids``  → part de l'évaluation dans la moyenne de l'ECUE ;
      * ``bareme`` → échelle de l'évaluation ;
      * le coefficient de l'ECUE dans son UE reste ``scolarite.ECUE.coefficient``.
    Le champ ``coefficient_pedagogique`` du rapport B est SUPPRIMÉ (aucun
    rôle métier démontré).
    """

    session = models.ForeignKey(
        SessionEvaluation, on_delete=models.PROTECT, related_name='evaluations',
    )
    ecue = models.ForeignKey(
        ECUE, on_delete=models.PROTECT, related_name='evaluations_academiques',
        help_text="ECUE évaluée — résolution EXPLICITE, jamais déduite d'un module.",
    )
    affectation_pedagogique = models.ForeignKey(
        AffectationPedagogique, on_delete=models.PROTECT,
        related_name='evaluations_academiques',
        help_text="Affectation pédagogique de l'ECUE (source canonique).",
    )
    type_evaluation = models.ForeignKey(
        TypeEvaluation, on_delete=models.PROTECT, related_name='evaluations',
    )
    libelle = models.CharField(max_length=255)
    description = models.TextField(blank=True, default='')
    bareme = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('20.00'),
        help_text="Échelle de l'évaluation.",
    )
    poids = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('100.00'),
        help_text="Part de l'évaluation dans la moyenne de l'ECUE (0 < poids ≤ 100).",
    )
    date_prevue = models.DateField(null=True, blank=True)
    statut = models.CharField(
        max_length=20,
        choices=[('BROUILLON', 'Brouillon'), ('PUBLIEE', 'Publiée'),
                 ('CLOTUREE', 'Clôturée'), ('ANNULEE', 'Annulée')],
        default='BROUILLON', db_index=True,
    )
    composition_verrouillee = models.BooleanField(default=False)
    regle_version = models.ForeignKey(
        RegleCalculVersion, on_delete=models.PROTECT,
        related_name='evaluations_academiques', null=True, blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['session', 'ecue__code']
        verbose_name = 'LMD – Évaluation académique'
        verbose_name_plural = 'LMD – Évaluations académiques'
        constraints = [
            models.UniqueConstraint(
                fields=['session', 'ecue', 'type_evaluation', 'libelle'],
                name='uniq_evaluation_academique',
            ),
            models.CheckConstraint(
                condition=Q(poids__gt=Decimal('0')) & Q(poids__lte=Decimal('100')),
                name='eval_poids_domaine',
            ),
            models.CheckConstraint(
                condition=Q(bareme__gt=Decimal('0')), name='eval_bareme_positif',
            ),
        ]
        indexes = [
            models.Index(fields=['session', 'ecue']),
            models.Index(fields=['affectation_pedagogique']),
        ]

    def __str__(self):
        return f'{self.libelle} — {self.ecue}'

    def clean(self):
        erreurs = {}
        # Domaines de valeurs : validés ici pour renvoyer une erreur
        # explicite à l'API ; les mêmes domaines sont garantis en base par
        # les CHECK constraints (défense en profondeur).
        if self.poids is not None and not (Decimal('0') < self.poids <= Decimal('100')):
            erreurs['poids'] = 'Le poids doit être strictement positif et ≤ 100.'
        if self.bareme is not None and self.bareme <= Decimal('0'):
            erreurs['bareme'] = 'Le barème doit être strictement positif.'
        if self.affectation_pedagogique_id and self.ecue_id:
            affectation = self.affectation_pedagogique
            if affectation.ecue_id != self.ecue_id:
                erreurs['affectation_pedagogique'] = (
                    "L'affectation pédagogique ne porte pas cet ECUE."
                )
            if affectation.annee_academique_id != self.session.annee_academique_id:
                erreurs['affectation_pedagogique'] = (
                    "L'affectation n'appartient pas à l'année de la session."
                )
        if self.ecue_id and self.session_id:
            if self.ecue.ue_id and self.ecue.ue.maquette_id != self.session.maquette_id:
                erreurs['ecue'] = "L'ECUE n'appartient pas à la maquette de la session."
        if erreurs:
            raise ValidationError(erreurs)

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)


class EvaluationComponent(models.Model):
    """Composant pondéré d'une évaluation (B.1 §4 et §5).

    ``poids`` = part du composant **dans l'évaluation** (0 < poids ≤ 100).
    ``ordre`` fixe l'ordre canonique de l'empreinte déterministe. La somme
    des poids n'est validée qu'au verrouillage de la composition.
    """

    evaluation = models.ForeignKey(
        Evaluation, on_delete=models.PROTECT, related_name='components',
    )
    code = models.CharField(max_length=30)
    libelle = models.CharField(max_length=255)
    poids = models.DecimalField(max_digits=5, decimal_places=2)
    bareme = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('20.00'),
    )
    ordre = models.PositiveIntegerField(default=1)
    obligatoire = models.BooleanField(default=True)
    actif = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['evaluation', 'ordre', 'id']
        verbose_name = "LMD – Composant d'évaluation"
        verbose_name_plural = "LMD – Composants d'évaluation"
        constraints = [
            models.UniqueConstraint(
                fields=['evaluation', 'code'], name='uniq_evaluation_component_code',
            ),
            models.CheckConstraint(
                condition=Q(poids__gt=Decimal('0')) & Q(poids__lte=Decimal('100')),
                name='eval_component_poids_domaine',
            ),
            models.CheckConstraint(
                condition=Q(bareme__gt=Decimal('0')),
                name='eval_component_bareme_positif',
            ),
        ]

    def __str__(self):
        return f'{self.code} ({self.poids})'

    def clean(self):
        erreurs = {}
        if self.poids is not None and not (Decimal('0') < self.poids <= Decimal('100')):
            erreurs['poids'] = 'Le poids doit être strictement positif et ≤ 100.'
        if self.bareme is not None and self.bareme <= Decimal('0'):
            erreurs['bareme'] = 'Le barème doit être strictement positif.'
        if erreurs:
            raise ValidationError(erreurs)

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)


class Epreuve(models.Model):
    """Quand, où et dans quelles conditions l'évaluation est passée (B.1 §4).

    Ne porte **aucune** note : l'émargement et la correction en dépendent,
    mais la note appartient à ``EvaluationGrade``. La détection des conflits
    (salle, enseignant, étudiant, chevauchement) est un service de C2 : le
    socle se limite à la structure et aux invariants simples.
    """

    evaluation = models.ForeignKey(
        Evaluation, on_delete=models.PROTECT, related_name='epreuves',
    )
    groupe = models.ForeignKey(
        Groupe, on_delete=models.SET_NULL, related_name='epreuves_academiques',
        null=True, blank=True,
    )
    date = models.DateField()
    heure_debut = models.TimeField()
    heure_fin = models.TimeField()
    duree_minutes = models.PositiveIntegerField(null=True, blank=True)
    salle = models.ForeignKey(
        'formations.RefSalle', on_delete=models.SET_NULL,
        related_name='epreuves_academiques', null=True, blank=True,
        help_text='Capacité du lieu = nombre de candidats simultanés (B.1 §13).',
    )
    enseignant_responsable = models.ForeignKey(
        'formations.Formateur', on_delete=models.PROTECT,
        related_name='epreuves_academiques', null=True, blank=True,
    )
    bareme = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
    )
    statut = models.CharField(
        max_length=20, choices=STATUTS_EPREUVE, default='PLANIFIEE', db_index=True,
    )
    motif_annulation = models.TextField(blank=True, default='')
    convocations_generees_le = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['date', 'heure_debut', 'id']
        verbose_name = 'LMD – Épreuve LMD'
        verbose_name_plural = 'LMD – Épreuves LMD'
        indexes = [
            models.Index(fields=['salle', 'date']),
            models.Index(fields=['enseignant_responsable', 'date']),
            models.Index(fields=['date', 'statut']),
        ]

    def __str__(self):
        return f'{self.date} {self.heure_debut} — {self.evaluation}'

    def clean(self):
        erreurs = {}
        if self.heure_debut and self.heure_fin and self.heure_fin <= self.heure_debut:
            erreurs['heure_fin'] = "L'heure de fin doit être postérieure à l'heure de début."
        if self.statut == 'ANNULEE' and not (self.motif_annulation or '').strip():
            erreurs['motif_annulation'] = 'Une annulation doit être motivée.'
        if erreurs:
            raise ValidationError(erreurs)

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)


class EpreuveSurveillant(models.Model):
    """Enseignant affecté à la surveillance ou à la correction d'une épreuve."""

    class Role(models.TextChoices):
        TITULAIRE = 'TITULAIRE', 'Titulaire'
        SURVEILLANT = 'SURVEILLANT', 'Surveillant'
        CORRECTEUR = 'CORRECTEUR', 'Correcteur'

    epreuve = models.ForeignKey(
        Epreuve, on_delete=models.PROTECT, related_name='surveillants',
    )
    formateur = models.ForeignKey(
        'formations.Formateur', on_delete=models.PROTECT,
        related_name='epreuves_surveillance',
    )
    role = models.CharField(
        max_length=15, choices=Role.choices, default=Role.SURVEILLANT,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['epreuve', 'role', 'id']
        verbose_name = "LMD – Surveillant / correcteur d'épreuve"
        verbose_name_plural = "LMD – Surveillants / correcteurs d'épreuve"
        constraints = [
            models.UniqueConstraint(
                fields=['epreuve', 'formateur'], name='uniq_epreuve_surveillant',
            ),
        ]

    def __str__(self):
        return f'{self.formateur} — {self.get_role_display()}'


class EvaluationParticipant(models.Model):
    """Qui est évalué dans cette évaluation (B.1 §16).

    Source canonique : ``inscription_pedagogique``. Aucun ``Participant``
    (formations) ni ``DossierEtudiant`` n'est stocké ici : matricule et
    identité se lisent par la chaîne d'inscription, ce qui évite toute
    dénormalisation source de divergence.
    """

    evaluation = models.ForeignKey(
        Evaluation, on_delete=models.PROTECT, related_name='participants',
    )
    inscription_pedagogique = models.ForeignKey(
        InscriptionPedagogique, on_delete=models.PROTECT,
        related_name='evaluations_participants',
    )
    groupe = models.ForeignKey(
        Groupe, on_delete=models.SET_NULL,
        related_name='evaluations_participants', null=True, blank=True,
    )
    statut_participation = models.CharField(
        max_length=20, choices=STATUTS_PARTICIPATION, default='EN_ATTENTE',
        db_index=True,
    )
    motif = models.TextField(blank=True, default='')
    source = models.CharField(
        max_length=10, choices=[('AUTO', 'Généré'), ('MANUEL', 'Manuel')],
        default='MANUEL',
    )
    eligible_rattrapage = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['evaluation', 'id']
        verbose_name = 'LMD – Participant à une évaluation'
        verbose_name_plural = 'LMD – Participants aux évaluations'
        constraints = [
            models.UniqueConstraint(
                fields=['evaluation', 'inscription_pedagogique'],
                name='uniq_evaluation_participant',
            ),
        ]
        indexes = [
            models.Index(fields=['evaluation', 'statut_participation']),
            models.Index(fields=['inscription_pedagogique']),
        ]

    def __str__(self):
        return f'{self.inscription_pedagogique} — {self.statut_participation}'

    def clean(self):
        erreurs = {}
        if self.inscription_pedagogique_id and self.evaluation_id:
            inscription = self.inscription_pedagogique
            if inscription.ecue_id != self.evaluation.ecue_id:
                erreurs['inscription_pedagogique'] = (
                    "L'inscription pédagogique ne porte pas l'ECUE évalué."
                )
            if inscription.semestre_id and self.evaluation.session.semestre_id:
                if inscription.semestre_id != self.evaluation.session.semestre_id:
                    erreurs['inscription_pedagogique'] = (
                        "L'inscription pédagogique porte un autre semestre."
                    )
            if self.groupe_id and inscription.groupe_id:
                if self.groupe_id != inscription.groupe_id:
                    erreurs['groupe'] = (
                        "Le groupe diffère de celui de l'inscription pédagogique."
                    )
        if self.statut_participation == 'EXCLU' and not (self.motif or '').strip():
            erreurs['motif'] = "L'exclusion d'un participant doit être motivée."
        if erreurs:
            raise ValidationError(erreurs)

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)


class EvaluationAttendance(models.Model):
    """Émargement d'une épreuve (B.1 §12 et §13).

    Modèle **autonome** : une présence à une épreuve n'est pas un
    ``presences.Pointage`` de séance EDT (QR, géolocalisation). Aucune
    conversion automatique vers une note : ``ABSENT`` ne produit pas de 0
    (invariant vérifié par les tests C1).
    """

    evaluation_participant = models.ForeignKey(
        EvaluationParticipant, on_delete=models.PROTECT, related_name='presences',
    )
    epreuve = models.ForeignKey(
        Epreuve, on_delete=models.PROTECT, related_name='presences',
    )
    statut = models.CharField(
        max_length=20, choices=STATUTS_PRESENCE, default='EN_ATTENTE', db_index=True,
    )
    heure_arrivee = models.TimeField(null=True, blank=True)
    heure_depart = models.TimeField(null=True, blank=True)
    observation = models.TextField(blank=True, default='')
    motif = models.TextField(blank=True, default='')
    saisi_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='presences_evaluations_academiques',
    )
    saisi_le = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['epreuve', 'evaluation_participant']
        verbose_name = "LMD – Émargement d'épreuve"
        verbose_name_plural = "LMD – Émargements d'épreuves"
        constraints = [
            models.UniqueConstraint(
                fields=['epreuve', 'evaluation_participant'],
                name='uniq_presence_par_epreuve',
            ),
        ]

    def __str__(self):
        return f'{self.epreuve} — {self.statut}'


class EvaluationGrade(models.Model):
    """Note obtenue pour un composant (B.1 §14).

    ``valeur`` est une valeur brute : l'absence est portée par
    ``EvaluationAttendance`` / ``statut_participation``, jamais par un 0
    implicite. Le contrôle ``0 ≤ valeur ≤ barème`` est appliqué ici et dans
    le serializer ; « composant obligatoire manquant » et les politiques
    d'absence relèvent de C2 (DECISION-2 et DECISION-6).
    """

    evaluation_participant = models.ForeignKey(
        EvaluationParticipant, on_delete=models.PROTECT, related_name='notes',
    )
    component = models.ForeignKey(
        EvaluationComponent, on_delete=models.PROTECT, related_name='notes',
    )
    valeur = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
    )
    bareme = models.DecimalField(
        max_digits=6, decimal_places=2,
        help_text='Barème applicable au moment de la saisie.',
    )
    statut = models.CharField(
        max_length=20, choices=STATUTS_NOTE, default='BROUILLON', db_index=True,
    )
    verrouillee = models.BooleanField(default=False, db_index=True)
    saisie_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='notes_evaluations_academiques',
    )
    saisie_le = models.DateTimeField(auto_now=True)
    motif_correction = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['component__ordre', 'evaluation_participant_id']
        verbose_name = "LMD – Note d'évaluation"
        verbose_name_plural = "LMD – Notes d'évaluation"
        constraints = [
            models.UniqueConstraint(
                fields=['component', 'evaluation_participant'],
                name='uniq_evaluation_grade',
            ),
        ]
        indexes = [
            models.Index(fields=['component', 'statut']),
            models.Index(fields=['evaluation_participant']),
        ]

    def __str__(self):
        return f'{self.evaluation_participant} / {self.component} : {self.valeur}'

    def clean(self):
        erreurs = {}
        if self.valeur is not None and self.bareme:
            if self.valeur < Decimal('0'):
                erreurs['valeur'] = 'Une note ne peut pas être négative.'
            if self.valeur > self.bareme:
                erreurs['valeur'] = f'La note dépasse le barème ({self.bareme}).'
        if self.verrouillee and self.statut != 'VALIDEE':
            erreurs['statut'] = 'Une note verrouillée doit être au statut VALIDEE.'
        if erreurs:
            raise ValidationError(erreurs)

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)


class EvaluationGradeHistory(models.Model):
    """Historique **append-only** des notes (B.1 §10).

    L'API n'expose ni écriture directe ni suppression sur ce modèle : chaque
    transition de note y écrit une ligne, sur le modèle de référence
    ``formations.CorrectionNoteModule``.
    """

    class Action(models.TextChoices):
        SAISIE = 'SAISIE', 'Saisie'
        MODIFICATION = 'MODIFICATION', 'Modification'
        SOUMISSION = 'SOUMISSION', 'Soumission'
        VALIDATION = 'VALIDATION', 'Validation'
        CORRECTION = 'CORRECTION', 'Correction'
        VERROUILLAGE = 'VERROUILLAGE', 'Verrouillage'
        DEVERROUILLAGE = 'DEVERROUILLAGE', 'Déverrouillage'

    grade = models.ForeignKey(
        EvaluationGrade, on_delete=models.PROTECT, related_name='historique',
    )
    action = models.CharField(max_length=15, choices=Action.choices)
    ancienne_valeur = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
    )
    nouvelle_valeur = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
    )
    motif = models.TextField(blank=True, default='')
    auteur = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='historique_notes_evaluations_academiques',
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at', '-id']
        verbose_name = "LMD – Historique de note d'évaluation"
        verbose_name_plural = "LMD – Historiques de notes d'évaluation"

    def __str__(self):
        return f'{self.action} {self.grade}'


class ConvocationEvaluation(models.Model):
    """Convocation d'un participant à une épreuve (structure C1)."""

    evaluation_participant = models.ForeignKey(
        EvaluationParticipant, on_delete=models.PROTECT, related_name='convocations',
    )
    epreuve = models.ForeignKey(
        Epreuve, on_delete=models.PROTECT, related_name='convocations',
    )
    reference = models.CharField(max_length=120, unique=True)
    statut = models.CharField(
        max_length=15,
        choices=[('GENEREE', 'Générée'), ('ENVOYEE', 'Envoyée'),
                 ('RETOURNEE', 'Retournée'), ('ANNULEE', 'Annulée')],
        default='GENEREE', db_index=True,
    )
    date_generation = models.DateTimeField(auto_now_add=True)
    date_envoi = models.DateTimeField(null=True, blank=True)
    support = models.CharField(
        max_length=10,
        choices=[('PDF', 'PDF'), ('EMAIL', 'Courriel'), ('PAPIER', 'Papier')],
        default='PDF',
    )

    class Meta:
        ordering = ['epreuve', 'evaluation_participant']
        verbose_name = "LMD – Convocation à une épreuve"
        verbose_name_plural = "LMD – Convocations à une épreuve"
        constraints = [
            models.UniqueConstraint(
                fields=['epreuve', 'evaluation_participant'],
                name='uniq_convocation_par_participant',
            ),
        ]

    def __str__(self):
        return f'{self.reference} — {self.statut}'


class _ResultatBase(models.Model):
    """Champs communs aux résultats persistés (structure réservée à C2).

    Aucun service de calcul n'existe en C1 : ces tables préparent la
    traçabilité exigée par B.1 §10 (règle, snapshot, empreinte) sans
    produire la moindre moyenne. ``source`` et ``migration_status`` sont
    renseignés **par le moteur C2** : un résultat sans source explicite
    reste ``UNMAPPED`` et ne constitue pas un résultat.
    """

    moyenne = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
    )
    moyenne_brute = models.CharField(
        max_length=20, blank=True, default='',
        help_text="Valeur non arrondie conservée pour l'explication du calcul.",
    )
    bareme = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('20.00'),
    )
    statut = models.CharField(max_length=20, default='BROUILLON', db_index=True)
    source = models.CharField(
        max_length=20, choices=SOURCES_RESULTAT, default='MOTEUR_LMD',
    )
    migration_status = models.CharField(
        max_length=12, choices=MIGRATION_STATUS, default='UNMAPPED', db_index=True,
    )
    regle_version = models.ForeignKey(
        RegleCalculVersion, on_delete=models.PROTECT,
        null=True, blank=True,
        help_text='Version de règle appliquée ; le snapshot fait foi (B.1 §9).',
    )
    regle_snapshot = models.JSONField(
        default=dict, blank=True,
        help_text='Copie immuable des paramètres réellement appliqués (B.1 §9).',
    )
    formule_version = models.CharField(max_length=20, blank=True, default='')
    detail = models.JSONField(default=dict, blank=True)
    empreinte = models.CharField(
        max_length=64, blank=True, default='', db_index=True,
        help_text='SHA-256 canonique du calcul (B.1 §10).',
    )
    complet = models.BooleanField(default=True)
    avec_dispense = models.BooleanField(default=False)
    imputation_absence = models.BooleanField(default=False)
    calcule_le = models.DateTimeField(null=True, blank=True)
    calcule_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        help_text='Auteur du calcul (moteur C2).',
    )
    verrouillee = models.BooleanField(default=False, db_index=True)
    verrouillee_le = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class ECUEResult(_ResultatBase):
    """Résultat d'un ECUE — table réservée, alimentée par C2."""

    inscription_pedagogique = models.ForeignKey(
        InscriptionPedagogique, on_delete=models.PROTECT,
        related_name='resultats_ecue',
    )
    session = models.ForeignKey(
        SessionEvaluation, on_delete=models.PROTECT, related_name='resultats_ecue',
    )
    ecue = models.ForeignKey(
        ECUE, on_delete=models.PROTECT, related_name='resultats_ecue',
    )

    class Meta:
        ordering = ['session', 'ecue']
        verbose_name = 'LMD – Résultat ECUE'
        verbose_name_plural = 'LMD – Résultats ECUE'
        constraints = [
            models.UniqueConstraint(
                fields=['inscription_pedagogique', 'session', 'ecue', 'formule_version'],
                name='uniq_ecue_result_formule',
            ),
        ]
        indexes = [
            models.Index(fields=['session', 'ecue']),
            models.Index(fields=['statut']),
        ]


class UEResult(_ResultatBase):
    """Résultat d'une UE — table réservée, alimentée par C2."""

    inscription = models.ForeignKey(
        'scolarite.InscriptionAdministrative', on_delete=models.PROTECT,
        related_name='resultats_ue',
    )
    session = models.ForeignKey(
        SessionEvaluation, on_delete=models.PROTECT, related_name='resultats_ue',
    )
    ue = models.ForeignKey(
        UE, on_delete=models.PROTECT, related_name='resultats_ue',
    )
    credits = models.PositiveSmallIntegerField(default=0)
    statut_ue = models.CharField(
        max_length=20,
        choices=[('ACQUISE', 'Acquise'), ('NON_ACQUISE', 'Non acquise'),
                 ('COMPENSEE', 'Compensée'), ('BROUILLON', 'Brouillon')],
        default='BROUILLON', db_index=True,
    )

    class Meta:
        ordering = ['session', 'ue']
        verbose_name = 'LMD – Résultat UE'
        verbose_name_plural = 'LMD – Résultats UE'
        constraints = [
            models.UniqueConstraint(
                fields=['inscription', 'session', 'ue', 'formule_version'],
                name='uniq_ue_result_formule',
            ),
        ]


class SemesterResult(_ResultatBase):
    """Résultat d'un semestre — table réservée, alimentée par C2."""

    inscription = models.ForeignKey(
        'scolarite.InscriptionAdministrative', on_delete=models.PROTECT,
        related_name='resultats_semestre',
    )
    session = models.ForeignKey(
        SessionEvaluation, on_delete=models.PROTECT,
        related_name='resultats_semestre',
    )
    semestre = models.ForeignKey(
        Semestre, on_delete=models.PROTECT, related_name='resultats_semestre',
    )
    credits_attendus = models.PositiveIntegerField(default=0)
    credits_acquis = models.PositiveIntegerField(default=0)
    compense = models.BooleanField(default=False)
    statut_semestre = models.CharField(
        max_length=20,
        choices=[('VALIDE', 'Validé'), ('NON_VALIDE', 'Non validé'),
                 ('EN_ATTENTE', 'En attente')],
        default='EN_ATTENTE', db_index=True,
    )

    class Meta:
        ordering = ['session', 'semestre']
        verbose_name = 'LMD – Résultat de semestre'
        verbose_name_plural = 'LMD – Résultats de semestre'
        constraints = [
            models.UniqueConstraint(
                fields=['inscription', 'session', 'semestre', 'formule_version'],
                name='uniq_semestre_result_formule',
            ),
        ]


class ReleveNotes(models.Model):
    """Relevé de notes versionné (structure C1, génération C2).

    Une correction ne réécrit jamais un relevé : elle produit une nouvelle
    version (``version`` incrémentée) avec sa propre empreinte SHA-256,
    sur le modèle de ``jurys.PVJury``.
    """

    inscription = models.ForeignKey(
        'scolarite.InscriptionAdministrative', on_delete=models.PROTECT,
        related_name='releves_evaluations',
    )
    session = models.ForeignKey(
        SessionEvaluation, on_delete=models.PROTECT,
        related_name='releves_evaluations',
    )
    version = models.PositiveIntegerField(default=1)
    fichier = models.FileField(upload_to='releves/', max_length=300)
    sha256 = models.CharField(max_length=64)
    genere_le = models.DateTimeField(auto_now_add=True)
    genere_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='releves_evaluations_generes',
    )
    verrouillee = models.BooleanField(default=False)

    class Meta:
        ordering = ['-genere_le']
        verbose_name = 'LMD – Relevé de notes'
        verbose_name_plural = 'LMD – Relevés de notes'
        constraints = [
            models.UniqueConstraint(
                fields=['inscription', 'session', 'version'],
                name='uniq_releve_version',
            ),
        ]

    def __str__(self):
        return f'Relevé v{self.version} — {self.inscription}'