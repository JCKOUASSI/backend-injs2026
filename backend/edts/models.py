"""Modèles du module Emploi du temps (lot L8 — app edts).

Principes :
- les créneaux sont des unités horaires de base ;
- un emploi du temps est paramétrable par année académique et par
  population cible (formation, groupe, enseignant, salle) ;
- les affectations expriment ce qui est placé dans un créneau ;
- les conflits sont détectés côté service et peuvent être journalisés.

Chaîne canonique INJS-LMD (décision d'architecture validée, 2026-09-28) :
    Année académique → Formation → Parcours/Spécialité → Niveau → Semestre
                    → Groupe → Maquette → UE → ECUE → AffectationPedagogique
                    → Besoin horaire → AffectationCreneau (séance planifiable)
                    → EmploiDuTemps publié → Pointage (présence/QR)

**Il n'existe PAS de table `Promotion`** (arbitrage explicite du commanditaire,
2026-09-28). Le modèle `scolarite.Groupe` est l'entité qui porte la promotion
pédagogique : année académique + formation INJS + parcours/spécialité + niveau +
vague + groupe. Créer une table `Promotion` reviendrait à reproduire
l'architecture héritée CPFAE/Sygepcpfae, ce que le périmètre INJS interdit. Le
service `edts.services.besoins` expose si besoin une notion **calculée** de
promotion dérivée du Groupe, sans nouvelle table ni nouvelle clé étrangère.
"""

from datetime import datetime, time

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from scolarite.models import AnneeAcademique, Groupe

JOUR_CHOICES = [
    ('LUNDI', 'Lundi'),
    ('MARDI', 'Mardi'),
    ('MERCREDI', 'Mercredi'),
    ('JEUDI', 'Jeudi'),
    ('VENDREDI', 'Vendredi'),
    ('SAMEDI', 'Samedi'),
    ('DIMANCHE', 'Dimanche'),
]

NATURE_CHOICES = [
    ('COURS', 'Cours'),
    ('TD', 'Travaux dirigés'),
    ('TP', 'Travaux pratiques'),
    ('EVALUATION', 'Évaluation'),
    ('REMPLACEMENT', 'Remplacement'),
    ('AUTRE', 'Autre'),
]

POPULATION_TYPE_CHOICES = [
    ('FORMATION', 'Formation'),
    ('GROUPE', 'Groupe'),
    ('ENSEIGNANT', 'Enseignant'),
    ('SALLE', 'Salle'),
]

EDT_STATUT_CHOICES = [
    ('BROUILLON', 'Brouillon'),
    ('EN_VALIDATION', 'En validation'),
    ('VALIDE', 'Validé'),
    ('PUBLIE', 'Publié'),
    ('ARCHIVE', 'Archivé'),
]

CONFLIT_TYPE_CHOICES = [
    ('HORAIRE_ENSEIGNANT', 'Chevauchement enseignant'),
    ('HORAIRE_GROUPETUDIANT', 'Chevauchement groupe/étudiant'),
    ('HORAIRE_SALLE', 'Chevauchement salle'),
    ('HORAIRE_MODULE', 'Chevauchement module'),
    ('CAPACITE', 'Capacité de salle insuffisante'),
    ('COMPATIBILITE_SALLE', 'Salle incompatible avec le type d’enseignement'),
    ('HORS_CALENDRIER', 'Séance hors période autorisée'),
    ('DISPONIBILITE', 'Indisponibilité enseignant ou salle'),
    ('MANUEL', 'Signalé manuellement'),
]

# Lot L8 — nature de la période déclarée par un enseignant ou une salle.
# Les trois statuts séparent la contrainte FORTE (INDISPONIBLE) des préférences
# (PREFERENCE, contrainte souple au sens de l'étape K) et des ouvertures
# explicites (DISPONIBLE).
DISPONIBILITE_STATUT_CHOICES = [
    ('DISPONIBLE', 'Disponible'),
    ('INDISPONIBLE', 'Indisponible'),
    ('PREFERENCE', 'Préférence'),
]


class CreneauTemplate(models.Model):
    """Référentiel de créneaux types (jour + horaire).

    **Représentation temporelle stable et idempotente.** Un créneau est un
    repère horaire d'emploi du temps : il doit donc être identifié par son seul
    couple (jour, heure de début, heure de fin). Les heures sont normalisées à la
    minute à l'écriture pour que deux exécutions d'un même plan de création
    reconduisent le **même** créneau au lieu d'en produire un nouveau à chaque
    fois — le cas classique étant ``datetime.now().time()``, qui embarque des
    microsecondes et rend toute comparaison/recréation instable.
    """

    jour = models.CharField(max_length=10, choices=JOUR_CHOICES, db_index=True)
    heure_debut = models.TimeField()
    heure_fin = models.TimeField()
    duree_prevue_minutes = models.PositiveSmallIntegerField(
        blank=True,
        null=True,
        help_text='Durée calculée (laisser None pour auto-calcul).',
    )

    #: Les heures sont un repère d'agenda : la granularité utile est la minute.
    #: Toute granularité plus fine n'a aucun sens métier et casse l'idempotence.
    GRANULARITE_MINUTES = 1

    class Meta:
        ordering = ['jour', 'heure_debut']
        verbose_name = 'LMD – Créneau type'
        verbose_name_plural = 'LMD – Créneaux types'
        indexes = [
            models.Index(fields=['jour', 'heure_debut', 'heure_fin']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['jour', 'heure_debut', 'heure_fin'],
                name='uniq_creneau_template_jour_horaires',
                violation_error_message=(
                    'Ce créneau horaire existe déjà pour ce jour : un créneau '
                    'identique (jour, début, fin) ne peut être créé deux fois.'
                ),
            ),
        ]

    @classmethod
    def normaliser(cls, valeur):
        """Convertit une heure texte et la ramène à la minute métier."""
        if valeur is None:
            return None
        if isinstance(valeur, datetime):
            valeur = valeur.time()
        elif isinstance(valeur, str):
            try:
                valeur = time.fromisoformat(valeur)
            except ValueError as exc:
                raise ValidationError('Saisissez une heure valide.') from exc
        if not isinstance(valeur, time):
            raise ValidationError('Saisissez une heure valide.')
        base = datetime(2000, 1, 1, valeur.hour, valeur.minute)
        return base.time()

    def clean(self):
        super().clean()
        self.heure_debut = self.normaliser(self.heure_debut)
        self.heure_fin = self.normaliser(self.heure_fin)
        if self.heure_debut and self.heure_fin and self.heure_debut >= self.heure_fin:
            raise ValidationError({
                'heure_fin': "L'heure de fin doit être strictement après l'heure de début.",
            })

    def save(self, *args, **kwargs):
        self.heure_debut = self.normaliser(self.heure_debut)
        self.heure_fin = self.normaliser(self.heure_fin)
        self.full_clean()
        if not self.duree_prevue_minutes and self.heure_debut and self.heure_fin:
            self.duree_prevue_minutes = self._calculer_duree_minutes()
        super().save(*args, **kwargs)

    def _calculer_duree_minutes(self):
        from datetime import datetime, timedelta

        base = datetime(2000, 1, 1, self.heure_debut.hour, self.heure_debut.minute)
        fin = datetime(2000, 1, 1, self.heure_fin.hour, self.heure_fin.minute)
        delta = fin - base
        if delta.total_seconds() <= 0:
            delta += timedelta(days=1)
        return int(delta.total_seconds() // 60)

    @property
    def duree_heures(self):
        if not self.duree_prevue_minutes:
            return None
        return round(self.duree_prevue_minutes / 60, 2)

    def __str__(self):
        return f"{self.get_jour_display()} {self.heure_debut}→{self.heure_fin}"


class EmploiDuTemps(models.Model):
    """Périmètre d'un emploi du temps éditable/publié.

    Un EDT est attaché à une année académique et à une population cible.
    """
    annee_academique = models.ForeignKey(
        AnneeAcademique,
        on_delete=models.PROTECT,
        related_name='emplois_du_temps',
    )
    population_type = models.CharField(
        max_length=15,
        choices=POPULATION_TYPE_CHOICES,
        db_index=True,
    )
    population_id = models.PositiveIntegerField(
        db_index=True,
        help_text='ID de la formation/groupe/enseignant/salle cible.',
    )
    population_denominateur = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text='Libellé humain pour affichage et recherche.',
    )
    titre = models.CharField(max_length=255, blank=True, default='')
    statut = models.CharField(
        max_length=15,
        choices=EDT_STATUT_CHOICES,
        default='BROUILLON',
        db_index=True,
    )
    semaine_debut = models.PositiveSmallIntegerField(
        default=1,
        help_text='Numéro de semaine académique de début (1-based).',
    )
    semaine_fin = models.PositiveSmallIntegerField(
        default=36,
        help_text='Numéro de semaine académique de fin (bornes de planification).',
    )
    rentree = models.DateField(
        null=True,
        blank=True,
        help_text='Date de rentrée pédagogique de cet EDT.',
    )
    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='edt_crees',
    )
    # --- Lot L8 (étape R) : versionnage et traçabilité du cycle de vie ---
    version = models.PositiveSmallIntegerField(
        default=1, db_index=True,
        help_text='Version de l\'EDT pour ce périmètre (V1, V2, V3…). '
                  'Une nouvelle version se crée par clonage, jamais par écrasement.',
    )
    motif_modification = models.CharField(
        max_length=255, blank=True, default='',
        help_text='Motif de la version courante (ex. « ajout salle TP Marcory »).',
    )
    valide_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='edt_valides',
    )
    valide_le = models.DateTimeField(null=True, blank=True)
    publie_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='edt_publies',
    )
    publie_le = models.DateTimeField(null=True, blank=True)
    # Empreinte des paramètres de génération : garantit l'idempotence (étape
    # 43) — relancer une génération strictement identique ne duplique rien.
    empreinte = models.CharField(
        max_length=64, blank=True, default='', db_index=True,
        help_text='SHA-256 des paramètres de génération (année, formation, parcours, '
                  'niveau, semestre, groupes, maquette, version).',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        verbose_name = 'LMD – Emploi du temps'
        verbose_name_plural = 'LMD – Emplois du temps'
        indexes = [
            models.Index(fields=['annee_academique', 'population_type', 'population_id']),
            models.Index(fields=['statut']),
            models.Index(fields=['empreinte']),
        ]
        # Étape R : la version entre dans la clé d'unicité pour autoriser
        # plusieurs versions d'un même périmètre (l'unicité stricte
        # annee+population rendait le versionnage impossible).
        unique_together = [
            ['annee_academique', 'population_type', 'population_id', 'version'],
        ]

    def clean(self):
        super().clean()
        erreurs = {}
        if self.semaine_debut and self.semaine_fin and self.semaine_fin < self.semaine_debut:
            erreurs['semaine_fin'] = 'La semaine de fin doit être ≥ à la semaine de début.'
        if self.statut and self.statut not in dict(EDT_STATUT_CHOICES):
            erreurs['statut'] = 'Statut inconnu.'
        if erreurs:
            raise ValidationError(erreurs)

    @property
    def population_label(self):
        """Libellé lisible de la population cible (jamais un champ fantôme)."""
        return (self.population_denominateur or '').strip() or f'{self.get_population_type_display()} #{self.population_id}'

    def __str__(self):
        return f"{self.titre or self.population_denominateur} — {self.get_statut_display()}"


class AffectationCreneau(models.Model):
    """Placement d'un créneau type dans un emploi du temps précis.

    C'est la donnée opérationnelle de l'EDT : qui enseigne quoi, où,
    à quelle période, avec quels étudiants.
    """

    emploi_du_temps = models.ForeignKey(
        EmploiDuTemps,
        on_delete=models.CASCADE,
        related_name='affectations',
    )
    creneau_template = models.ForeignKey(
        CreneauTemplate,
        on_delete=models.PROTECT,
        related_name='affectations',
    )
    semaine_debut = models.PositiveSmallIntegerField(
        db_index=True,
        help_text='Numéro de semaine académique de début (1-based).',
    )
    semaine_fin = models.PositiveSmallIntegerField(
        db_index=True,
        help_text='Numéro de semaine académique de fin.',
    )
    salle_nom = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text='Salle attendue (chaîne éditable).',
    )
    salle = models.ForeignKey(
        'formations.RefSalle',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='seances_edt',
        help_text=(
            "Salle du référentiel INJS (Lot L2). Complète `salle_nom`, conservé "
            "en lecture/transition : le rattachement est MANUEL et explicite, "
            "aucune déduction automatique n'est effectuée."
        ),
    )
    formation = models.ForeignKey(
        'formations.RefFormation',
        on_delete=models.PROTECT,
        related_name='edt_affectations',
        null=True,
        blank=True,
    )
    groupe = models.ForeignKey(
        Groupe,
        on_delete=models.PROTECT,
        related_name='edt_affectations',
        null=True,
        blank=True,
    )
    enseignant_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        db_index=True,
        help_text='ID utilisateur enseignant/encadrant.',
    )
    formateur = models.ForeignKey(
        'formations.Formateur',
        on_delete=models.PROTECT,
        related_name='edt_affectations',
        null=True,
        blank=True,
        help_text='Formateur de référence (socle INJS-LMD) pour la détection de surcharges.',
    )
    enseignant_nom = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text='Nom complet enseignant (dénormalisé pour recherche/planification).',
    )
    nature = models.CharField(
        max_length=15,
        choices=NATURE_CHOICES,
        default='COURS',
    )
    intitule = models.CharField(max_length=255, blank=True, default='')
    commentaire = models.TextField(blank=True, default='')
    affectation_pedagogique = models.ForeignKey(
        'scolarite.AffectationPedagogique',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='seances_edt',
        help_text=(
            "Contexte pédagogique de la séance (formation, parcours, niveau, semestre, "
            "UE, ECUE, groupe, enseignant). Rattachement MANUEL et explicite : aucune "
            "déduction automatique n'est effectuée."
        ),
    )
    actif = models.BooleanField(default=True, db_index=True)
    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='edt_affectations_crees',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = [
            'emploi_du_temps',
            'creneau_template__jour',
            'creneau_template__heure_debut',
            'semaine_debut',
        ]
        verbose_name = 'LMD – Affectation créneau'
        verbose_name_plural = 'LMD – Affectations créneaux'
        indexes = [
            models.Index(
                fields=['emploi_du_temps', 'creneau_template', 'semaine_debut', 'semaine_fin'],
                name='edts__edt_creneau_semaine_idx',
            ),
        ]

    def clean(self):
        super().clean()
        erreurs = {}
        if self.semaine_debut is None:
            erreurs['semaine_debut'] = 'La semaine de début est obligatoire.'
        if self.semaine_fin is None:
            erreurs['semaine_fin'] = 'La semaine de fin est obligatoire.'
        if (self.semaine_debut is not None and self.semaine_fin is not None
                and self.semaine_fin < self.semaine_debut):
            erreurs['semaine_fin'] = 'La semaine de fin doit être ≥ à la semaine de début.'
        if self.nature and self.nature not in dict(NATURE_CHOICES):
            erreurs['nature'] = 'Nature inconnue.'
        if erreurs:
            raise ValidationError(erreurs)

    @property
    def horaire(self):
        """Résumé lisible du créneau (jour + plage horaire) ou chaîne vide."""
        ct = self.creneau_template
        if not ct:
            return ''
        jours = dict(JOUR_CHOICES)
        return (f"{jours.get(ct.jour, ct.jour)} "
                f"{ct.heure_debut:%H:%M}–{ct.heure_fin:%H:%M}")

    def __str__(self):
        return (
            f"{self.creneau_template} | {self.get_nature_display()} "
            f"| s.{self.semaine_debut}-s.{self.semaine_fin} "
            f"| {self.enseignant_nom or self.formation or self.groupe}"
        )


class ConflitCreneau(models.Model):
    """Détection de conflit stockée pour audit et revue humaine.

    Les conflits peuvent être générés automatiquement ou signalés manuellement.
    """

    emploi_du_temps = models.ForeignKey(
        EmploiDuTemps,
        on_delete=models.CASCADE,
        related_name='conflits',
    )
    type_conflit = models.CharField(
        max_length=30,
        choices=CONFLIT_TYPE_CHOICES,
        db_index=True,
    )
    description = models.TextField()
    lignes_creneaux = models.JSONField(
        default=list,
        help_text='Liste des identifiants ou représentations brutes des affectations en conflit.',
    )
    recalcule_le = models.DateTimeField(auto_now=True)
    actif = models.BooleanField(default=True, db_index=True)
    signale_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='edt_conflits_signales',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-recalcule_le']
        verbose_name = 'LMD – Conflit créneau'
        verbose_name_plural = 'LMD – Conflits créneaux'
        indexes = [
            models.Index(fields=['emploi_du_temps', 'type_conflit']),
            models.Index(fields=['actif', 'recalcule_le']),
        ]

    def __str__(self):
        return f"{self.get_type_conflit_display()} — {self.emploi_du_temps}"


class DisponibiliteHoraire(models.Model):
    """Période de disponibilité/indisponibilité d'un enseignant ou d'une salle.

    Lote L8 (étape G/H). Complète ``scolarite.IndisponibiliteEnseignant``,
    purement datée et donc inexploitable pour un placement horaire : cette
    période exprime un **jour + plage horaire**, ce qui rend les contraintes
    fortes C5 (indisponibilité enseignant) et C6 (indisponibilité salle)
    évaluables par le moteur de génération.

    Une ligne porte EXACTEMENT un porteur (enseignant XOR salle) — contrainte
    appliquée par ``CheckConstraint`` : une disponibilité sans porteur n'a aucun
    sens métier et une double cible serait ambiguë pour le solveur.

    Statuts :

    * ``INDISPONIBLE`` — contrainte FORTE, aucun placement sur la période ;
    * ``PREFERENCE``  — contrainte SOUPLE (étape K), pénalité, jamais un blocage ;
    * ``DISPONIBLE``   — ouverture explicite (contournement d'une indisponibilité
      plus large, ou créneau réservé). Un créneau sans ligne vaut « disponible ».
    """

    annee_academique = models.ForeignKey(
        'scolarite.AnneeAcademique', on_delete=models.CASCADE,
        related_name='disponibilites_horaires',
        help_text='Année concernée : les disponibilités sont annuelles.',
    )
    enseignant = models.ForeignKey(
        'formations.Formateur', on_delete=models.CASCADE,
        related_name='disponibilites_horaires', null=True, blank=True,
    )
    salle = models.ForeignKey(
        'formations.RefSalle', on_delete=models.CASCADE,
        related_name='disponibilites_horaires', null=True, blank=True,
    )
    jour = models.CharField(max_length=10, choices=JOUR_CHOICES, db_index=True)
    heure_debut = models.TimeField()
    heure_fin = models.TimeField()
    statut = models.CharField(
        max_length=15, choices=DISPONIBILITE_STATUT_CHOICES,
        default='INDISPONIBLE', db_index=True,
    )
    motif = models.CharField(max_length=200, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['jour', 'heure_debut', 'heure_fin']
        verbose_name = 'EDT – Disponibilité horaire'
        verbose_name_plural = 'EDT – Disponibilités horaires'
        indexes = [
            models.Index(fields=['annee_academique', 'jour', 'heure_debut']),
            models.Index(fields=['enseignant', 'annee_academique', 'statut']),
            models.Index(fields=['salle', 'annee_academique', 'statut']),
        ]
        constraints = [
            # Exactement un porteur : enseignant XOR salle.
            models.CheckConstraint(
                condition=(
                    models.Q(enseignant__isnull=False, salle__isnull=True)
                    | models.Q(enseignant__isnull=True, salle__isnull=False)
                ),
                name='dispo_horaire_un_seul_porteur',
            ),
            # Plage horaire cohérente.
            models.CheckConstraint(
                condition=models.Q(heure_fin__gt=models.F('heure_debut')),
                name='dispo_horaire_plage_valide',
            ),
        ]

    def clean(self):
        super().clean()
        erreurs = {}
        if self.enseignant_id and self.salle_id:
            erreurs['salle'] = "Renseignez soit un enseignant, soit une salle — jamais les deux."
        if not self.enseignant_id and not self.salle_id:
            erreurs['enseignant'] = "Une disponibilité doit concerner un enseignant ou une salle."
        if self.heure_debut and self.heure_fin and self.heure_fin <= self.heure_debut:
            erreurs['heure_fin'] = "L'heure de fin doit être strictement postérieure à l'heure de début."
        if erreurs:
            raise ValidationError(erreurs)

    @property
    def porteur_label(self):
        if self.enseignant_id:
            return str(self.enseignant)
        if self.salle_id:
            return str(self.salle)
        return '—'

    def __str__(self):
        return (f'{self.annee_academique_id and self.annee_academique} — '
                f'{self.porteur_label} {self.get_jour_display()} '
                f'{self.heure_debut:%H:%M}–{self.heure_fin:%H:%M} '
                f'[{self.get_statut_display()}]')



# ══════════════════════════════════════════════════════════════════════════════
# GET-INJS — INSCRIPTIONS IMPORTÉES (cohortes hors parcours)
# ══════════════════════════════════════════════════════════════════════════════

class InscriptionImportee(models.Model):
    """Inscription **lue dans un fichier externe**, rattachée à une cohorte.

    Pourquoi cette table existe. Le moteur d'emploi du temps s'appuie sur la
    chaîne LMD interne (``AffectationPedagogique``), qui suppose que chaque
    étudiant a été inscrit **dans** l'application selon son parcours. Le
    commanditaire a demandé que le GET-INJS sache aussi produire les emplois du
    temps d'une année académique à partir d'un **fichier externe d'inscrits**,
    y compris lorsque l'inscription n'est pas passée par ce parcours.

    Cette table conserve donc la trace de ces inscriptions, **sans jamais**
    créer d'``Etudiant``, d'``Inscription`` ou d'``AffectationPedagogique``
    fictifs : les données importées restent identifiables comme telles
    (``fichier``, ``empreinte``, ``ligne_source``) et supprimables sans
    toucher aux dossiers métier réels.

    Rôle dans le calcul : la ``cohorte`` (année + formation + parcours + niveau
    + semestre + groupe + vague) porte l'**effectif réel** utilisé comme
    contrainte de capacité (C4) — auparavant l'effectif provenait uniquement de
    ``Groupe.capacite_max``, c'est-à-dire d'une capacité déclarée, jamais d'un
    dénombrement.
    """

    class Statut(models.TextChoices):
        INSCRIT = 'INSCRIT', 'Inscrit'
        RADIE = 'RADIE', 'Radié'

    class Sexe(models.TextChoices):
        MASCULIN = 'M', 'Masculin'
        FEMININ = 'F', 'Féminin'

    annee_academique = models.ForeignKey(
        AnneeAcademique,
        on_delete=models.CASCADE,
        related_name='inscriptions_importees',
    )
    # --- Identité
    matricule = models.CharField(
        max_length=64, db_index=True,
        help_text="Matricule tel que fourni par le fichier externe (clé d'idempotence).",
    )
    nom = models.CharField(max_length=150)
    prenoms = models.CharField(max_length=150, blank=True, default='')
    sexe = models.CharField(max_length=1, choices=Sexe.choices, blank=True, default='')
    date_naissance = models.DateField(null=True, blank=True)

    # --- Cohorte pédagogique (les mêmes entités que la chaîne LMD)
    filiere_code = models.CharField(
        max_length=10, blank=True, default='', db_index=True,
        help_text='Code de filière métier F01…F08 lu dans le fichier, si présent.',
    )
    ref_formation = models.ForeignKey(
        'formations.RefFormation',
        on_delete=models.PROTECT,
        related_name='inscriptions_importees',
    )
    parcours = models.ForeignKey(
        'scolarite.Parcours',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='inscriptions_importees',
    )
    niveau = models.ForeignKey(
        'scolarite.Niveau',
        on_delete=models.PROTECT,
        related_name='inscriptions_importees',
    )
    semestre = models.ForeignKey(
        'scolarite.Semestre',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='inscriptions_importees',
    )
    groupe = models.ForeignKey(
        'scolarite.Groupe',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='inscriptions_importees',
    )
    vague = models.ForeignKey(
        'formations.RefVague',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='inscriptions_importees',
    )

    # --- Traçabilité du fichier source
    statut = models.CharField(
        max_length=10, choices=Statut.choices, default=Statut.INSCRIT, db_index=True,
    )
    fichier = models.CharField(max_length=255, blank=True, default='')
    empreinte = models.CharField(
        max_length=64, blank=True, default='', db_index=True,
        help_text='SHA-256 du contenu du fichier importé (lot de rattachement).',
    )
    ligne_source = models.PositiveIntegerField(
        null=True, blank=True,
        help_text='Numéro de ligne dans le fichier d’origine (traçabilité).',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['annee_academique__libelle', 'ref_formation__intitule',
                    'niveau__ordre', 'groupe__nom', 'nom', 'prenoms']
        verbose_name = 'GET-INJS – Inscription importée'
        verbose_name_plural = 'GET-INJS – Inscriptions importées'
        constraints = [
            models.UniqueConstraint(
                fields=['annee_academique', 'matricule'],
                name='uniq_inscription_importee_annee_matricule',
            ),
        ]
        indexes = [
            models.Index(fields=['annee_academique', 'groupe']),
            models.Index(fields=['annee_academique', 'ref_formation', 'niveau']),
            models.Index(fields=['empreinte']),
        ]

    def __str__(self):
        return f'{self.matricule} — {self.nom} {self.prenoms}'.strip()

    @property
    def nom_complet(self):
        return f'{self.nom} {self.prenoms}'.strip()


# ══════════════════════════════════════════════════════════════════════════════
# GET-INJS APP — CAMPAGNES DE GÉNÉRATION (LOT 2)
# ══════════════════════════════════════════════════════════════════════════════

class CampagneGeneration(models.Model):
    """Campagne de génération des emplois du temps d'une année académique.

    Pourquoi cette entité. La génération existait, mais son exécution n'était
    qu'un appel HTTP : rien ne conservait le périmètre demandé, le bilan, les
    anomalies, l'auteur, la durée, ni la possibilité de rejouer la même
    campagne. Une campagne rend le traitement **traçable, reprenable et
    publiable** — et interdit deux exécutions simultanées du même périmètre.

    Cycle de vie (transitions contrôlées par ``edts.moteur.campagnes``) :

        BROUILLON → VALIDATION_DONNEES → PRET → EN_COURS
              → TERMINE | TERMINE_AVEC_ANOMALIES | ECHEC
              → VALIDE → PUBLIE
    """

    class Statut(models.TextChoices):
        BROUILLON = 'BROUILLON', 'Brouillon'
        VALIDATION_DONNEES = 'VALIDATION_DONNEES', 'Validation des données'
        PRET = 'PRET', 'Prêt à générer'
        EN_COURS = 'EN_COURS', 'En cours'
        TERMINE = 'TERMINE', 'Terminé'
        TERMINE_AVEC_ANOMALIES = 'TERMINE_AVEC_ANOMALIES', 'Terminé avec anomalies'
        ECHEC = 'ECHEC', 'Échec'
        VALIDE = 'VALIDE', 'Validé'
        PUBLIE = 'PUBLIE', 'Publié'

    annee_academique = models.ForeignKey(
        AnneeAcademique,
        on_delete=models.PROTECT,
        related_name='campagnes_getinjs',
    )
    libelle = models.CharField(max_length=255)
    #: Semaines académiques planifiées (ex. [1, 2, 3]).
    semaines = models.JSONField(
        default=list, blank=True,
        help_text='Semaines académiques ciblées ; liste vide = semaine 1.',
    )
    #: Périmètre : listes d'identifiants (formations, niveaux, groupes).
    #: Vide = tout le périmètre INJS de l'année.
    perimetre = models.JSONField(
        default=dict, blank=True,
        help_text='Filtres de périmètre : formations, niveaux, groupes.',
    )
    #: Paramètres passés au moteur (persister, remplacer, inclure_maquette…).
    parametres = models.JSONField(default=dict, blank=True)
    statut = models.CharField(
        max_length=25, choices=Statut.choices, default=Statut.BROUILLON,
        db_index=True,
    )
    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name='campagnes_getinjs_creees',
    )
    demarree_le = models.DateTimeField(null=True, blank=True)
    terminee_le = models.DateTimeField(null=True, blank=True)
    #: Bilan détaillé par groupe (celui de ``moteur.annee.generer_annee``).
    bilan = models.JSONField(default=dict, blank=True)
    #: Anomalies explicites : groupes non planifiés, séances non placées…
    anomalies = models.JSONField(default=list, blank=True)
    #: Mesures et compteurs (durée, effectif, séances, requêtes SQL si mesurées).
    statistiques = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'GET-INJS – Campagne de génération'
        verbose_name_plural = 'GET-INJS – Campagnes de génération'
        constraints = [
            models.UniqueConstraint(
                fields=['annee_academique', 'libelle'],
                name='uniq_campagne_annee_libelle',
            ),
        ]
        indexes = [
            models.Index(fields=['annee_academique', 'statut']),
            models.Index(fields=['statut', 'created_at']),
        ]

    def __str__(self):
        return f'{self.libelle} — {self.get_statut_display()}'

    @property
    def en_cours(self):
        return self.statut == self.Statut.EN_COURS


class ExecutionCampagne(models.Model):
    """Une exécution d'une campagne — historique complet, reprise et mesures.

    Chaque lancement crée une ligne, y compris les échecs : un échec silencieux
    est précisément ce que la mission interdit. Le bilan et les anomalies sont
    recopiés ici pour que l'historique reste lisible même si la campagne est
    relancée plusieurs fois.
    """

    class Statut(models.TextChoices):
        EN_COURS = 'EN_COURS', 'En cours'
        TERMINE = 'TERMINE', 'Terminé'
        TERMINE_AVEC_ANOMALIES = 'TERMINE_AVEC_ANOMALIES', 'Terminé avec anomalies'
        ECHEC = 'ECHEC', 'Échec'

    campagne = models.ForeignKey(
        CampagneGeneration, on_delete=models.CASCADE, related_name='executions',
    )
    numero = models.PositiveIntegerField(help_text='Numéro d’exécution dans la campagne (1, 2, 3…).')
    statut = models.CharField(
        max_length=25, choices=Statut.choices, default=Statut.EN_COURS, db_index=True,
    )
    lancee_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name='executions_campagnes_getinjs',
    )
    demarree_le = models.DateTimeField(default=timezone.now)
    terminee_le = models.DateTimeField(null=True, blank=True)
    duree_ms = models.PositiveBigIntegerField(null=True, blank=True)
    bilan = models.JSONField(default=dict, blank=True)
    anomalies = models.JSONField(default=list, blank=True)
    statistiques = models.JSONField(default=dict, blank=True)
    erreur = models.TextField(
        blank=True, default='',
        help_text='Message technique de l’échec — jamais masqué.',
    )

    class Meta:
        ordering = ['-numero']
        verbose_name = 'GET-INJS – Exécution de campagne'
        verbose_name_plural = 'GET-INJS – Exécutions de campagne'
        constraints = [
            models.UniqueConstraint(
                fields=['campagne', 'numero'],
                name='uniq_execution_campagne_numero',
            ),
        ]

    def __str__(self):
        return f'{self.campagne_id} / exécution {self.numero}'


class PolitiqueContraintesSouples(models.Model):
    """Politique des contraintes souples, réglable depuis l'admin Django.

    Pourquoi une table et pas seulement un réglage Django. Le réglage
    ``EDTS_CONTRAINTES_SOUPLES`` ne s'applique qu'au **déploiement** : l'INJS
    ne peut pas décider qu'une journée de 9 h devient problématique sans
    qu'un développeur modifie un fichier et redémarre le service. Cette ligne
    unique donne la main au secrétariat / à la direction, avec une trace
    (auteur, date, motif) et sans redéploiement.

    Trois garanties de conception :

    * **Ligne unique** — ``save()`` force la clé primaire à 1 : il n'existe
      jamais deux politiques concurrentes, donc jamais d'ambiguïté sur les
      règles appliquées ;
    * **Désactivée par défaut** — ``actives=False`` : créer la ligne ne change
      rien au comportement du solveur tant que personne ne l'active ;
    * **Traçable** — ``modifie_par``, ``modifie_le`` et ``motif`` sont
      conservés : « qui a décidé quoi, quand et pourquoi » reste lisible.

    Priorité effective (cf. ``edts.moteur.contraintes.politique_souples``) :
    défauts du code < réglage Django < **cette ligne** < paramètre explicite
    d'une génération. La ligne l'emporte sur le réglage Django parce qu'elle
    est la décision opérationnelle la plus récente ; le paramètre de génération
    l'emporte sur tout le reste parce qu'il est explicite et local.
    """

    actives = models.BooleanField(
        default=False,
        help_text='Si décoché, le moteur ignore entièrement les règles souples '
                  '(comportement historique).',
    )
    max_heures_consecutives = models.FloatField(
        default=4.0,
        help_text='Série de cours continue au-delà de laquelle une pénalité est '
                  'produite. La pause déjeuner, si elle est déclarée, rompt la série.',
    )
    max_heures_par_jour = models.FloatField(
        default=8.0,
        help_text='Total de cours d’une journée de groupe au-delà duquel une '
                  'pénalité est produite.',
    )
    tolerance_minutes = models.PositiveSmallIntegerField(
        default=15,
        help_text='Interruption entre deux séances qui n’est pas considérée '
                  'comme un trou (récréation, changement de salle).',
    )
    penaliser_trous = models.BooleanField(
        default=True,
        help_text='Produire une pénalité pour chaque trou horaire du groupe.',
    )
    pause_debut = models.TimeField(
        null=True, blank=True,
        help_text='Début de la pause institutionnelle (déjeuner). Vide = aucune '
                  'pause supposée : le moteur n’invente pas d’horaire.',
    )
    pause_fin = models.TimeField(
        null=True, blank=True,
        help_text='Fin de la pause institutionnelle. À remplir avec le début.',
    )
    poids_trou = models.PositiveSmallIntegerField(default=1)
    poids_consecutif = models.PositiveSmallIntegerField(default=2)
    poids_surcharge = models.PositiveSmallIntegerField(default=3)
    motif = models.TextField(
        blank=True, default='',
        help_text='Pourquoi cette politique (décision de la direction, '
                  'calendrier particulier…). Facultatif mais recommandé.',
    )
    modifie_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name='politiques_souples_modifiees',
        help_text='Dernier utilisateur à avoir enregistré cette politique.',
    )
    modifie_le = models.DateTimeField(auto_now=True)
    # ``default`` plutôt que ``auto_now_add`` : la clé primaire est forcée à 1
    # dans ``save()``, ce qui fait considérer la ligne comme « existante » et
    # enverrait ``created_at = NULL`` dans l'UPDATE. Un défaut est stable dans
    # les deux chemins (INSERT initial, UPDATE ultérieur).
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        verbose_name = 'GET-INJS – Politique des contraintes souples'
        verbose_name_plural = 'GET-INJS – Politique des contraintes souples'

    def __str__(self):
        etat = 'activée' if self.actives else 'désactivée'
        return (f'Contraintes souples ({etat}) — '
                f'{self.max_heures_consecutives:g} h consécutives, '
                f'{self.max_heures_par_jour:g} h/jour')

    # ── Validation ───────────────────────────────────────────────────────────
    def clean(self):
        """Refuse les politiques incohérentes — un réglage faux doit se voir.

        Les messages sont rédigés pour l'utilisateur de l'admin : ils disent ce
        qui ne va pas et quoi faire, sans jargon.
        """
        erreurs = {}
        if bool(self.pause_debut) != bool(self.pause_fin):
            erreurs['pause_debut'] = (
                'Renseignez le début ET la fin de la pause, ou laissez les deux '
                'vides pour n’en déclarer aucune.'
            )
        elif self.pause_debut and self.pause_fin <= self.pause_debut:
            erreurs['pause_fin'] = 'La fin de la pause doit être après son début.'
        if self.max_heures_consecutives is not None \
                and self.max_heures_consecutives <= 0:
            erreurs['max_heures_consecutives'] = (
                'La borne doit être supérieure à 0 h ; pour désactiver les '
                'règles souples, décochez « actives ».'
            )
        if self.max_heures_par_jour is not None and self.max_heures_par_jour <= 0:
            erreurs['max_heures_par_jour'] = (
                'La borne doit être supérieure à 0 h ; pour désactiver les '
                'règles souples, décochez « actives ».'
            )
        for champ in ('poids_trou', 'poids_consecutif', 'poids_surcharge'):
            if not getattr(self, champ, 1):
                erreurs[champ] = (
                    'Un poids nul rendrait la pénalité invisible. Pour ne pas '
                    'appliquer une règle, désactivez-la ou décochez la règle '
                    'correspondante.'
                )
        if erreurs:
            raise ValidationError(erreurs)
        super().clean()

    # ── Lecture par le moteur ────────────────────────────────────────────────
    def en_politique(self):
        """Convertit la ligne en politique lisible par ``contraintes``.

        Les bornes de la pause sont exprimées en **minutes depuis minuit**,
        l'unité interne du moteur (cf. ``contraintes.SOUPLES_DEFAUT``). Les
        heures et minutes lisibles sont produites à l'affichage par
        ``contraintes.pause_lisible`` : une seule conversion, jamais deux.
        """
        pause = None
        if self.pause_debut and self.pause_fin:
            pause = (self.pause_debut.hour * 60 + self.pause_debut.minute,
                     self.pause_fin.hour * 60 + self.pause_fin.minute)
        return {
            'actives': bool(self.actives),
            'max_heures_consecutives': float(self.max_heures_consecutives),
            'max_heures_par_jour': float(self.max_heures_par_jour),
            'tolerance_minutes': int(self.tolerance_minutes),
            'penaliser_trous': bool(self.penaliser_trous),
            'pause_dejeuner': pause,
            'poids_trou': int(self.poids_trou),
            'poids_consecutif': int(self.poids_consecutif),
            'poids_surcharge': int(self.poids_surcharge),
        }

    def resume(self):
        """Trace lisible pour l'API : qui a réglé quoi, quand et pourquoi."""
        return {
            'politique': self.en_politique(),
            'motif': self.motif or '',
            'modifie_par': (
                self.modifie_par.get_username() if self.modifie_par_id else None
            ),
            'modifie_le': self.modifie_le.isoformat() if self.modifie_le else None,
        }

    def save(self, *args, **kwargs):
        """Force la ligne unique : une seule politique peut exister."""
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def charger(cls):
        """Politique enregistrée, ou ``None`` si personne n'a encore réglé."""
        return cls.objects.filter(pk=1).first()
