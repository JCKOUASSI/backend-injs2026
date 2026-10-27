"""Référentiels LMD et maquette pédagogique (INJS).

Couche additive : ces modèles s'appuient sur les référentiels existants de
l'app ``formations`` (RefFormation, RefVague, RefSite, RefModule) par clé
étrangère et n'en redéfinissent aucun. Le modèle opérationnel existant
(Formation / Module / ModuleParticipant) n'est pas modifié.
"""

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
from django.utils import timezone


class JournalScolarite(models.Model):
    """Journal d'audit des opérations sensibles de scolarité LMD.

    Volontairement distinct de ``presences.AuditLog`` : ce dernier énumère ses
    actions dans un champ à choix figé, l'étendre imposerait de modifier un
    modèle en production. Ce journal couvre le périmètre LMD uniquement.
    """

    class Action(models.TextChoices):
        CANDIDATURE_CREEE = 'CANDIDATURE_CREEE', 'Candidature créée'
        CANDIDATURE_TRANSITION = 'CANDIDATURE_TRANSITION', 'Changement de statut de candidature'
        PIECE_DEPOSEE = 'PIECE_DEPOSEE', 'Pièce déposée'
        PIECE_VERIFIEE = 'PIECE_VERIFIEE', 'Pièce vérifiée'
        ADMISSION_CREEE = 'ADMISSION_CREEE', 'Admission créée'
        ADMISSION_DECISION = 'ADMISSION_DECISION', 'Décision d’admission'
        ADMISSION_ANNULEE = 'ADMISSION_ANNULEE', 'Admission annulée'
        # Lot L2 — campagnes et concours
        CAMPAGNE_CREEE = 'CAMPAGNE_CREEE', 'Campagne d’admission créée'
        CAMPAGNE_TRANSITION = 'CAMPAGNE_TRANSITION', 'Changement de statut de campagne'
        CONCOURS_CONVOCATIONS = 'CONCOURS_CONVOCATIONS', 'Convocations générées'
        CONCOURS_EPREUVE_VERROUILLEE = 'CONCOURS_EPREUVE_VERROUILLEE', 'Épreuve verrouillée'
        CONCOURS_NOTE_CORRIGEE = 'CONCOURS_NOTE_CORRIGEE', 'Note de concours corrigée'
        CONCOURS_CLASSEMENT_CALCULE = 'CONCOURS_CLASSEMENT_CALCULE', 'Classement calculé'
        CONCOURS_CLASSEMENT_PUBLIE = 'CONCOURS_CLASSEMENT_PUBLIE', 'Classement publié'
        INSCRIPTION_CREEE = 'INSCRIPTION_CREEE', 'Inscription administrative créée'
        INSCRIPTION_TRANSITION = 'INSCRIPTION_TRANSITION', 'Changement de statut d’inscription'
        MATRICULE_GENERE = 'MATRICULE_GENERE', 'Matricule généré'
        INSCRIPTION_PEDAGOGIQUE_GENEREE = 'INSCRIPTION_PEDAGOGIQUE_GENEREE', 'Inscriptions pédagogiques générées'
        INSCRIPTION_PEDAGOGIQUE_MANUELLE = 'INSCRIPTION_PEDAGOGIQUE_MANUELLE', 'Modification pédagogique manuelle'
        GROUPE_AFFECTATION = 'GROUPE_AFFECTATION', 'Affectation à un groupe'
        GROUPE_CHANGEMENT = 'GROUPE_CHANGEMENT', 'Changement de groupe'
        REINSCRIPTION = 'REINSCRIPTION', 'Réinscription'
        EVENEMENT_SCOLARITE = 'EVENEMENT_SCOLARITE', 'Événement de scolarité'
        SYNCHRONISATION_EDT = 'SYNCHRONISATION_EDT', 'Export vers l’emploi du temps'
        # Module GET-INJS (lot L8) — journalisation des opérations sensibles EDT
        EDT_CREE = 'EDT_CREE', 'Emploi du temps créé'
        EDT_SOUMIS = 'EDT_SOUMIS', 'Emploi du temps soumis à validation'
        EDT_VALIDE = 'EDT_VALIDE', 'Emploi du temps validé'
        EDT_PUBLIE = 'EDT_PUBLIE', 'Emploi du temps publié'
        EDT_DEPUBLIE = 'EDT_DEPUBLIE', 'Emploi du temps dépublié'
        EDT_ARCHIVE = 'EDT_ARCHIVE', 'Emploi du temps archivé'
        EDT_SUPPRIME = 'EDT_SUPPRIME', 'Emploi du temps supprimé'
        EDT_GENERATION = 'EDT_GENERATION', 'Brouillon généré automatiquement'
        EDT_AFFECTATION_MODIFIEE = 'EDT_AFFECTATION_MODIFIEE', 'Affectation de créneau modifiée'
        EDT_CONFLIT_RESOLU = 'EDT_CONFLIT_RESOLU', 'Conflit EDT marqué résolu'
        # Lot L3 — Jurys
        JURY_SESSION_CREEE = 'JURY_SESSION_CREEE', 'Session de jury créée'
        JURY_TRANSITION = 'JURY_TRANSITION', 'Changement d’état d’une session de jury'
        JURY_MEMBRE = 'JURY_MEMBRE', 'Membre de jury ajouté'
        JURY_CALCUL = 'JURY_CALCUL', 'Propositions calculées par le moteur ECTS'
        JURY_DECISION = 'JURY_DECISION', 'Décision de jury enregistrée'
        JURY_PV_GENERE = 'JURY_PV_GENERE', 'PV de jury généré'
        JURY_PUBLICATION = 'JURY_PUBLICATION', 'Décisions de jury publiées'
        # Lot L4 — Diplômation et documents officiels
        DIPLOME_VALIDATION_PENDING = 'DIPLOME_VALIDATION_PENDING', 'Diplôme en attente de validation'
        DIPLOME_VALIDE = 'DIPLOME_VALIDE', 'Diplôme validé'
        DIPLOME_REVOQUE = 'DIPLOME_REVOQUE', 'Diplôme révoqué'
        DIPLOME_REEDITE = 'DIPLOME_REEDITE', 'Diplôme réédité'
        # Lot L5 — Stages et conventions
        STAGE_TRANSITION = 'STAGE_TRANSITION', 'Changement de statut de convention de stage'
        STAGE_NOTES = 'STAGE_NOTES', 'Notes de stage saisies (rapport/soutenance)'
        STAGE_EVALUATION_MODIFIEE = 'STAGE_EVALUATION_MODIFIEE', 'Évaluation de stage modifiée'
        STAGE_EVALUATION_VALIDEE = 'STAGE_EVALUATION_VALIDEE', 'Évaluation de stage validée'



    action = models.CharField(max_length=50, choices=Action.choices)
    objet_type = models.CharField(max_length=50, blank=True)
    objet_id = models.PositiveIntegerField(null=True, blank=True)
    objet_libelle = models.CharField(max_length=255, blank=True)
    acteur = models.ForeignKey(
        'authentication.User', on_delete=models.SET_NULL,
        related_name='journal_scolarite', null=True, blank=True,
    )
    acteur_label = models.CharField(max_length=150, blank=True)
    ancienne_valeur = models.CharField(max_length=255, blank=True)
    nouvelle_valeur = models.CharField(max_length=255, blank=True)
    commentaire = models.TextField(blank=True)
    extra = models.JSONField(default=dict, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-timestamp']
        verbose_name = 'LMD – Journal de scolarité'
        verbose_name_plural = 'LMD – Journal de scolarité'
        indexes = [
            models.Index(fields=['objet_type', 'objet_id']),
            models.Index(fields=['action', 'timestamp']),
        ]

    def __str__(self):
        return f'{self.get_action_display()} – {self.objet_libelle or self.objet_id}'


def journaliser(action, objet=None, acteur=None, **champs):
    """Écrit une entrée de journal. Ne lève jamais : l'audit ne doit pas casser une opération métier."""
    try:
        return JournalScolarite.objects.create(
            action=action,
            objet_type=objet.__class__.__name__ if objet is not None else '',
            objet_id=getattr(objet, 'pk', None),
            objet_libelle=str(objet)[:255] if objet is not None else '',
            acteur=acteur if getattr(acteur, 'pk', None) else None,
            acteur_label=(getattr(acteur, 'username', '') or '')[:150],
            **champs,
        )
    except Exception:  # noqa: BLE001 - l'audit est best-effort
        return None


class AnneeAcademique(models.Model):
    """Année académique LMD (ex: 2026-2027)."""

    libelle = models.CharField(max_length=20, unique=True, help_text='Format attendu : 2026-2027')
    date_debut = models.DateField()
    date_fin = models.DateField()
    courante = models.BooleanField(
        default=False,
        help_text="Une seule année peut être courante à la fois.",
    )
    actif = models.BooleanField(default=True)
    # Lot L1/L3 — workflow de clôture des années académiques
    cloturee = models.BooleanField(
        default=False,
        help_text="Une année clôturée n'accepte plus de nouvelle inscription.",
    )
    date_cloture = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-libelle']
        verbose_name = 'LMD – Année académique'
        verbose_name_plural = 'LMD – Années académiques'
        constraints = [
            models.UniqueConstraint(
                fields=['courante'],
                condition=Q(courante=True),
                name='uniq_annee_academique_courante',
            ),
        ]

    def clean(self):
        if self.date_debut and self.date_fin and self.date_fin <= self.date_debut:
            raise ValidationError({'date_fin': 'La date de fin doit être postérieure à la date de début.'})

    def __str__(self):
        return self.libelle

    @classmethod
    def courante_ou_none(cls):
        return cls.objects.filter(courante=True, actif=True).first()


class TypeFormation(models.Model):
    """Type de formation (Licence, Master, Formation continue…)."""

    code = models.CharField(max_length=30, unique=True)
    libelle = models.CharField(max_length=150)
    actif = models.BooleanField(default=True)

    class Meta:
        ordering = ['libelle']
        verbose_name = 'LMD – Type de formation'
        verbose_name_plural = 'LMD – Types de formation'

    def __str__(self):
        return self.libelle


class Niveau(models.Model):
    """Niveau LMD (L1, L2, L3, M1, M2…)."""

    class Cycle(models.TextChoices):
        LICENCE = 'LICENCE', 'Licence'
        MASTER = 'MASTER', 'Master'
        DOCTORAT = 'DOCTORAT', 'Doctorat'

    code = models.CharField(max_length=10, unique=True)
    libelle = models.CharField(max_length=100)
    cycle = models.CharField(max_length=20, choices=Cycle.choices, default=Cycle.LICENCE)
    ordre = models.PositiveSmallIntegerField(default=1, help_text="Ordre de progression (L1=1, L2=2…)")
    credits_requis = models.PositiveSmallIntegerField(
        default=60,
        help_text='Crédits ECTS requis pour valider le niveau.',
    )
    actif = models.BooleanField(default=True)

    class Meta:
        ordering = ['ordre', 'code']
        verbose_name = 'LMD – Niveau'
        verbose_name_plural = 'LMD – Niveaux'

    def __str__(self):
        return self.code


class RegleValidationLMD(models.Model):
    """Paramétrage de validation LMD (crédits / compensation) par formation.

    Utilisé par le moteur de validation (validation_services.py) et par les
    jurys. Une règle peut cibler un niveau précis ; une règle avec ``niveau``
    null sert de règle par défaut pour la formation.
    """

    class Compensation(models.TextChoices):
        AUCUNE = 'AUCUNE', 'Aucune compensation'
        SEMESTRE = 'SEMESTRE', 'Compensation au sein du semestre'

    ref_formation = models.ForeignKey(
        'formations.RefFormation', on_delete=models.CASCADE,
        related_name='regles_validation_lmd',
    )
    niveau = models.ForeignKey(
        Niveau, on_delete=models.CASCADE, related_name='regles_validation_lmd',
        null=True, blank=True,
        help_text='Niveau ciblé (null = règle par défaut de la formation).',
    )
    seuil_admission = models.DecimalField(
        max_digits=4, decimal_places=2, default=10,
        help_text='Moyenne /20 requise pour valider une UE ou un semestre.',
    )
    compensation = models.CharField(
        max_length=12, choices=Compensation.choices, default=Compensation.SEMESTRE,
    )
    seuil_elim = models.DecimalField(
        max_digits=4, decimal_places=2, null=True, blank=True,
        help_text='Moyenne UE en dessous de ce seuil : UE non acquise, même avec compensation.',
    )
    credits_semestre = models.PositiveSmallIntegerField(
        default=30, help_text='Crédits ECTS attendus par semestre.',
    )
    capitalisation_activee = models.BooleanField(
        default=True, help_text='Report des crédits acquis des sessions antérieures.',
    )
    actif = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['ref_formation', 'niveau__ordre']
        verbose_name = 'LMD – Règle de validation'
        verbose_name_plural = 'LMD – Règles de validation'
        constraints = [
            models.UniqueConstraint(
                fields=['ref_formation', 'niveau'], name='uniq_regle_formation_niveau',
            ),
            models.UniqueConstraint(
                fields=['ref_formation'], condition=Q(niveau__isnull=True),
                name='uniq_regle_defaut_formation',
            ),
        ]

    def __str__(self):
        cible = self.niveau.code if self.niveau else 'défaut'
        return f'Règle {self.ref_formation} / {cible}'


class Parcours(models.Model):
    """Parcours/filière rattaché à un cycle de formation existant."""

    ref_formation = models.ForeignKey(
        'formations.RefFormation',
        on_delete=models.PROTECT,
        related_name='parcours_lmd',
        verbose_name='Formation (cycle)',
    )
    type_formation = models.ForeignKey(
        TypeFormation,
        on_delete=models.PROTECT,
        related_name='parcours',
        null=True,
        blank=True,
    )
    code = models.CharField(max_length=30)
    intitule = models.CharField(max_length=255)
    actif = models.BooleanField(default=True)

    class Meta:
        ordering = ['ref_formation__intitule', 'code']
        verbose_name = 'LMD – Parcours'
        verbose_name_plural = 'LMD – Parcours'
        constraints = [
            models.UniqueConstraint(
                'ref_formation', Lower('code'),
                name='uniq_parcours_formation_code_ci',
            ),
        ]

    def __str__(self):
        return f'{self.code} – {self.intitule}'


class Semestre(models.Model):
    """Semestre d'un niveau (S1/S2 pour L1, etc.)."""

    niveau = models.ForeignKey(Niveau, on_delete=models.CASCADE, related_name='semestres')
    numero = models.PositiveSmallIntegerField(help_text='Numéro global du semestre (S1 → 1, S6 → 6)')
    libelle = models.CharField(max_length=50)
    actif = models.BooleanField(default=True)

    class Meta:
        ordering = ['numero']
        verbose_name = 'LMD – Semestre'
        verbose_name_plural = 'LMD – Semestres'
        unique_together = ('niveau', 'numero')

    def __str__(self):
        return self.libelle


class RegimeEtudes(models.Model):
    """Régime d'études (initial, continu, alternance…)."""

    code = models.CharField(max_length=30, unique=True)
    libelle = models.CharField(max_length=150)
    actif = models.BooleanField(default=True)

    class Meta:
        ordering = ['libelle']
        verbose_name = "LMD – Régime d'études"
        verbose_name_plural = "LMD – Régimes d'études"

    def __str__(self):
        return self.libelle


class StatutEtudiant(models.Model):
    """Statut administratif d'un étudiant (actif, suspendu, diplômé…)."""

    code = models.CharField(max_length=30, unique=True)
    libelle = models.CharField(max_length=150)
    bloque_inscription = models.BooleanField(
        default=False,
        help_text="Empêche toute nouvelle inscription tant que ce statut est actif.",
    )
    actif = models.BooleanField(default=True)

    class Meta:
        ordering = ['libelle']
        verbose_name = 'LMD – Statut étudiant'
        verbose_name_plural = 'LMD – Statuts étudiant'

    def __str__(self):
        return self.libelle


class Groupe(models.Model):
    """Groupe pédagogique (ex: L1-G1) pour une année, une formation et un niveau."""

    annee_academique = models.ForeignKey(
        AnneeAcademique, on_delete=models.PROTECT, related_name='groupes',
    )
    ref_formation = models.ForeignKey(
        'formations.RefFormation', on_delete=models.PROTECT, related_name='groupes_lmd',
        verbose_name='Formation (cycle)',
    )
    parcours = models.ForeignKey(
        Parcours, on_delete=models.PROTECT, related_name='groupes', null=True, blank=True,
    )
    niveau = models.ForeignKey(Niveau, on_delete=models.PROTECT, related_name='groupes')
    vague = models.ForeignKey(
        'formations.RefVague', on_delete=models.SET_NULL, related_name='groupes_lmd',
        null=True, blank=True,
    )
    site = models.ForeignKey(
        'formations.RefSite', on_delete=models.SET_NULL, related_name='groupes_lmd',
        null=True, blank=True,
    )
    nom = models.CharField(max_length=50, help_text='Ex: L1-G1')
    capacite_max = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text='Effectif maximum. Vide = pas de limite.',
    )
    actif = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['annee_academique__libelle', 'niveau__ordre', 'nom']
        verbose_name = 'LMD – Groupe'
        verbose_name_plural = 'LMD – Groupes'
        constraints = [
            models.UniqueConstraint(
                'annee_academique', 'ref_formation', 'niveau', Lower('nom'),
                name='uniq_groupe_annee_formation_niveau_nom_ci',
            ),
        ]
        indexes = [
            models.Index(fields=['annee_academique', 'niveau']),
        ]

    def clean(self):
        if self.parcours_id and self.ref_formation_id and self.parcours.ref_formation_id != self.ref_formation_id:
            raise ValidationError({'parcours': "Le parcours n'appartient pas à cette formation."})

    def __str__(self):
        return f'{self.nom} ({self.annee_academique})'


class DossierEtudiant(models.Model):
    """Dossier académique LMD d'un étudiant.

    Volontairement adossé à ``formations.Participant`` plutôt que de créer une
    seconde identité : le Participant reste l'entité opérationnelle référencée
    par les présences, les notes et la finance. Le matricule n'est pas dupliqué,
    il reste porté par le Participant.
    """

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    participant = models.OneToOneField(
        'formations.Participant', on_delete=models.PROTECT, related_name='dossier_etudiant',
    )
    statut = models.ForeignKey(
        StatutEtudiant, on_delete=models.PROTECT, related_name='dossiers',
        null=True, blank=True,
    )
    date_premiere_inscription = models.DateField(null=True, blank=True)
    observations = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['participant__nom', 'participant__prenom']
        verbose_name = 'LMD – Dossier étudiant'
        verbose_name_plural = 'LMD – Dossiers étudiants'

    def __str__(self):
        return f'{self.matricule} – {self.participant.nom} {self.participant.prenom}'

    @property
    def matricule(self):
        return self.participant.matricule

    @property
    def nom_complet(self):
        return f'{self.participant.nom} {self.participant.prenom}'.strip()

    @property
    def inscription_courante(self):
        return (
            self.inscriptions
            .filter(statut=InscriptionAdministrative.Statut.VALIDEE)
            .select_related('annee_academique', 'niveau')
            .order_by('-annee_academique__libelle')
            .first()
        )


class InscriptionAdministrative(models.Model):
    """Inscription d'un étudiant pour une année académique donnée."""

    class Statut(models.TextChoices):
        BROUILLON = 'BROUILLON', 'Brouillon'
        EN_ATTENTE = 'EN_ATTENTE', 'En attente'
        A_VALIDER = 'A_VALIDER', 'À valider'
        VALIDEE = 'VALIDEE', 'Validée'
        REJETEE = 'REJETEE', 'Rejetée'
        ANNULEE = 'ANNULEE', 'Annulée'
        SUSPENDUE = 'SUSPENDUE', 'Suspendue'
        TERMINEE = 'TERMINEE', 'Terminée'

    class Type(models.TextChoices):
        PREMIERE = 'PREMIERE', 'Première inscription'
        REINSCRIPTION = 'REINSCRIPTION', 'Réinscription'
        REDOUBLEMENT = 'REDOUBLEMENT', 'Redoublement'
        REPRISE = 'REPRISE', 'Reprise après suspension'
        REORIENTATION = 'REORIENTATION', 'Réorientation'
        TRANSFERT = 'TRANSFERT', 'Transfert'

    etudiant = models.ForeignKey(
        DossierEtudiant, on_delete=models.PROTECT, related_name='inscriptions',
    )
    annee_academique = models.ForeignKey(
        AnneeAcademique, on_delete=models.PROTECT, related_name='inscriptions',
    )
    ref_formation = models.ForeignKey(
        'formations.RefFormation', on_delete=models.PROTECT, related_name='inscriptions_lmd',
        verbose_name='Formation (cycle)',
    )
    parcours = models.ForeignKey(
        Parcours, on_delete=models.PROTECT, related_name='inscriptions', null=True, blank=True,
    )
    niveau = models.ForeignKey(Niveau, on_delete=models.PROTECT, related_name='inscriptions')
    vague = models.ForeignKey(
        'formations.RefVague', on_delete=models.SET_NULL, related_name='inscriptions_lmd',
        null=True, blank=True,
    )
    categorie = models.ForeignKey(
        'formations.RefCategorie', on_delete=models.SET_NULL, related_name='inscriptions_lmd',
        null=True, blank=True,
    )
    grade = models.ForeignKey(
        'formations.RefGrade', on_delete=models.SET_NULL, related_name='inscriptions_lmd',
        null=True, blank=True,
    )
    regime = models.ForeignKey(
        RegimeEtudes, on_delete=models.PROTECT, related_name='inscriptions', null=True, blank=True,
    )
    statut_etudiant = models.ForeignKey(
        StatutEtudiant, on_delete=models.PROTECT, related_name='inscriptions',
        null=True, blank=True,
    )
    admission = models.ForeignKey(
        'admissions.Admission', on_delete=models.SET_NULL, related_name='inscriptions',
        null=True, blank=True, verbose_name="Admission d'origine",
    )
    type_inscription = models.CharField(max_length=20, choices=Type.choices, default=Type.PREMIERE)
    statut = models.CharField(max_length=20, choices=Statut.choices, default=Statut.BROUILLON)
    date_inscription = models.DateField(default=timezone.localdate)
    date_validation = models.DateTimeField(null=True, blank=True)
    valide_par = models.ForeignKey(
        'authentication.User', on_delete=models.SET_NULL, related_name='inscriptions_validees',
        null=True, blank=True,
    )
    observations = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-annee_academique__libelle', 'etudiant__participant__nom']
        verbose_name = 'LMD – Inscription administrative'
        verbose_name_plural = 'LMD – Inscriptions administratives'
        constraints = [
            models.UniqueConstraint(
                fields=['etudiant', 'annee_academique', 'ref_formation', 'parcours', 'niveau'],
                condition=Q(statut='VALIDEE'),
                name='uniq_inscription_validee_par_annee_formation_niveau',
            ),
        ]
        indexes = [
            models.Index(fields=['annee_academique', 'statut']),
            models.Index(fields=['ref_formation', 'niveau']),
        ]

    def __str__(self):
        return f'{self.etudiant.matricule} – {self.annee_academique} – {self.niveau}'

    def clean(self):
        if self.parcours_id and self.ref_formation_id and self.parcours.ref_formation_id != self.ref_formation_id:
            raise ValidationError({'parcours': "Le parcours n'appartient pas à cette formation."})
        if self.grade_id and self.categorie_id and self.grade.categorie_id != self.categorie_id:
            raise ValidationError({'grade': "Le grade n'appartient pas à cette catégorie."})
        # Lot L1/L3 — une inscription d'une année clôturée ne peut pas être créée
        # (les inscriptions existantes restent consultables : aucune suppression).
        if self.annee_academique_id and self.annee_academique.cloturee and self.pk is None:
            raise ValidationError(
                {'annee_academique': 'Année académique clôturée : nouvelle inscription refusée.'}
            )
        # Lot L1/L3 — un étudiant ne peut pas avoir deux inscriptions VALIDEE
        # pour la même année académique, même sur des formations différentes.
        if self.statut == self.Statut.VALIDEE and self.etudiant_id and self.annee_academique_id:
            concurrente = InscriptionAdministrative.objects.filter(
                etudiant=self.etudiant,
                annee_academique=self.annee_academique,
                statut=self.Statut.VALIDEE,
            ).exclude(pk=self.pk).exists()
            if concurrente:
                raise ValidationError(
                    "Cet étudiant a déjà une inscription validée pour cette année "
                    "académique : deux inscriptions actives simultanées sont interdites."
                )

    @property
    def est_valide(self):
        return self.statut == self.Statut.VALIDEE


class AffectationGroupe(models.Model):
    """Rattachement d'une inscription à un groupe pédagogique, avec historique.

    Un changement de groupe clôture l'affectation précédente au lieu de
    l'écraser : l'historique complet reste consultable.
    """

    inscription = models.ForeignKey(
        InscriptionAdministrative, on_delete=models.CASCADE, related_name='affectations',
    )
    groupe = models.ForeignKey(Groupe, on_delete=models.PROTECT, related_name='affectations')
    date_debut = models.DateField(default=timezone.localdate)
    date_fin = models.DateField(null=True, blank=True)
    active = models.BooleanField(default=True)
    motif = models.TextField(blank=True)
    affecte_par = models.ForeignKey(
        'authentication.User', on_delete=models.SET_NULL, related_name='affectations_groupes',
        null=True, blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date_debut', '-id']
        verbose_name = 'LMD – Affectation de groupe'
        verbose_name_plural = 'LMD – Affectations de groupe'
        constraints = [
            models.UniqueConstraint(
                fields=['inscription'],
                condition=Q(active=True),
                name='uniq_affectation_active_par_inscription',
            ),
        ]

    def __str__(self):
        return f'{self.inscription.etudiant.matricule} → {self.groupe.nom}'


class EvenementScolarite(models.Model):
    """Événement marquant du parcours d'un étudiant (passage, redoublement, abandon…)."""

    class Type(models.TextChoices):
        PASSAGE = 'PASSAGE', 'Passage en année supérieure'
        REDOUBLEMENT = 'REDOUBLEMENT', 'Redoublement'
        REPRISE = 'REPRISE', 'Reprise après suspension'
        REORIENTATION = 'REORIENTATION', 'Changement de parcours'
        CHANGEMENT_FORMATION = 'CHANGEMENT_FORMATION', 'Changement de formation'
        CHANGEMENT_GROUPE = 'CHANGEMENT_GROUPE', 'Changement de groupe'
        SUSPENSION = 'SUSPENSION', 'Suspension'
        RADIATION = 'RADIATION', 'Radiation'
        EQUIVALENCE_DISPENSE = 'EQUIVALENCE_DISPENSE', 'Équivalence ou dispense appliquée'
        ABANDON = 'ABANDON', 'Abandon'
        TRANSFERT = 'TRANSFERT', 'Transfert'
        DIPLOMATION = 'DIPLOMATION', 'Obtention du diplôme'

    etudiant = models.ForeignKey(
        DossierEtudiant, on_delete=models.CASCADE, related_name='evenements',
    )
    inscription = models.ForeignKey(
        InscriptionAdministrative, on_delete=models.SET_NULL, related_name='evenements',
        null=True, blank=True,
    )
    type_evenement = models.CharField(max_length=30, choices=Type.choices)
    date_evenement = models.DateField(default=timezone.localdate)
    ancienne_valeur = models.CharField(max_length=255, blank=True)
    nouvelle_valeur = models.CharField(max_length=255, blank=True)
    commentaire = models.TextField(blank=True)
    enregistre_par = models.ForeignKey(
        'authentication.User', on_delete=models.SET_NULL, related_name='evenements_scolarite',
        null=True, blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date_evenement', '-id']
        verbose_name = 'LMD – Événement de scolarité'
        verbose_name_plural = 'LMD – Événements de scolarité'
        indexes = [
            models.Index(fields=['etudiant', 'date_evenement']),
        ]

    def __str__(self):
        return f'{self.get_type_evenement_display()} – {self.etudiant.matricule}'


class InscriptionPedagogique(models.Model):
    """Enseignement (ECUE) que l'étudiant doit suivre au titre de son inscription.

    Rattachée à l'inscription administrative, qui porte déjà l'étudiant, l'année,
    la formation, le parcours et le niveau : ces informations ne sont pas
    dupliquées ici.

    Lot L1 — dénormalisation documentée : le ``semestre`` est porté par la ligne
    d'inscription pédagogique (et non déduit de l'ECUE → UE → semestre) afin de
    préserver la trace du semestre réellement suivi au moment de l'inscription,
    même si la version de maquette applicable évolue ensuite (l'ECUE reste
    rattachée à sa version d'origine ; les nouvelles versions sont des clones).
    """

    class TypeEnseignement(models.TextChoices):
        CM = 'CM', 'Cours magistral'
        TD = 'TD', 'Travaux dirigés'
        TP = 'TP', 'Travaux pratiques'
        STAGE = 'STAGE', 'Stage'
        AUTRE = 'AUTRE', 'Autre'

    class Statut(models.TextChoices):
        PREVUE = 'PREVUE', 'Prévue'
        VALIDEE = 'VALIDEE', 'Validée'
        ABANDONNEE = 'ABANDONNEE', 'Abandonnée'
        DISPENSEE = 'DISPENSEE', 'Dispensée'

    class Origine(models.TextChoices):
        AUTOMATIQUE = 'AUTOMATIQUE', 'Générée depuis la maquette'
        MANUELLE = 'MANUELLE', 'Ajout manuel'

    inscription = models.ForeignKey(
        InscriptionAdministrative, on_delete=models.CASCADE, related_name='inscriptions_pedagogiques',
        verbose_name='Inscription administrative',
    )
    ecue = models.ForeignKey('ECUE', on_delete=models.PROTECT, related_name='inscriptions_pedagogiques')
    semestre = models.ForeignKey(
        Semestre, on_delete=models.PROTECT, related_name='inscriptions_pedagogiques',
    )
    groupe = models.ForeignKey(
        Groupe, on_delete=models.SET_NULL, related_name='inscriptions_pedagogiques',
        null=True, blank=True,
    )
    type_enseignement = models.CharField(
        max_length=10, choices=TypeEnseignement.choices, default=TypeEnseignement.CM,
    )
    credits = models.PositiveSmallIntegerField(default=0, verbose_name='Crédits ECTS')
    volume_horaire = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    statut = models.CharField(max_length=20, choices=Statut.choices, default=Statut.PREVUE)
    origine = models.CharField(max_length=20, choices=Origine.choices, default=Origine.AUTOMATIQUE)
    module_participant = models.ForeignKey(
        'formations.ModuleParticipant', on_delete=models.SET_NULL,
        related_name='inscriptions_pedagogiques', null=True, blank=True,
        help_text="Inscription au module opérationnel générée par la passerelle.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['semestre__numero', 'ecue__ue__ordre', 'ecue__ordre']
        verbose_name = 'LMD – Inscription pédagogique'
        verbose_name_plural = 'LMD – Inscriptions pédagogiques'
        constraints = [
            models.UniqueConstraint(
                fields=['inscription', 'ecue'], name='uniq_inscription_pedagogique_ecue',
            ),
        ]
        indexes = [
            models.Index(fields=['inscription', 'semestre']),
        ]

    def __str__(self):
        return f'{self.inscription.etudiant.matricule} – {self.ecue.code}'

    def clean(self):
        if self.groupe_id and self.inscription_id:
            if self.groupe.annee_academique_id != self.inscription.annee_academique_id:
                raise ValidationError({'groupe': "Le groupe n'appartient pas à la même année académique."})
            if self.groupe.niveau_id != self.inscription.niveau_id:
                raise ValidationError({'groupe': "Le groupe ne correspond pas au niveau de l'inscription."})


class Maquette(models.Model):
    """Maquette pédagogique versionnée d'une formation/parcours/niveau pour une année."""

    class Statut(models.TextChoices):
        BROUILLON = 'BROUILLON', 'Brouillon'
        VALIDEE = 'VALIDEE', 'Validée'
        ACTIVE = 'ACTIVE', 'Active'
        ARCHIVEE = 'ARCHIVEE', 'Archivée'

    annee_academique = models.ForeignKey(
        AnneeAcademique, on_delete=models.PROTECT, related_name='maquettes',
    )
    ref_formation = models.ForeignKey(
        'formations.RefFormation', on_delete=models.PROTECT, related_name='maquettes',
        verbose_name='Formation (cycle)',
    )
    parcours = models.ForeignKey(
        Parcours, on_delete=models.PROTECT, related_name='maquettes', null=True, blank=True,
    )
    niveau = models.ForeignKey(Niveau, on_delete=models.PROTECT, related_name='maquettes')
    version = models.PositiveSmallIntegerField(default=1)
    statut = models.CharField(max_length=20, choices=Statut.choices, default=Statut.BROUILLON)
    libelle = models.CharField(max_length=255, blank=True)
    # Lot L1 — traçabilité du workflow de validation
    validee_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='maquettes_validees',
    )
    validee_le = models.DateTimeField(null=True, blank=True)
    activee_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='maquettes_activees',
    )
    activee_le = models.DateTimeField(null=True, blank=True)
    commentaire_validation = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-annee_academique__libelle', 'niveau__ordre', '-version']
        verbose_name = 'LMD – Maquette pédagogique'
        verbose_name_plural = 'LMD – Maquettes pédagogiques'
        unique_together = ('annee_academique', 'ref_formation', 'parcours', 'niveau', 'version')

    def clean(self):
        if self.parcours_id and self.ref_formation_id and self.parcours.ref_formation_id != self.ref_formation_id:
            raise ValidationError({'parcours': "Le parcours n'appartient pas à cette formation."})

    # ── Lot L1 — garde-fou R4 : immutabilité des maquettes abouties ───────────
    STATUTS_VERROUILLES = (Statut.VALIDEE, Statut.ACTIVE, Statut.ARCHIVEE)
    # Transitions de statut autorisées une fois la maquette validée.
    TRANSITIONS_AUTORISEES = {
        (Statut.VALIDEE, Statut.ACTIVE),
        (Statut.VALIDEE, Statut.ARCHIVEE),
        (Statut.ACTIVE, Statut.ARCHIVEE),
    }

    def _verifier_immunabilite(self):
        """R4 : à partir du statut VALIDEE, le contenu pédagogique est gelé.

        Seules les transitions de statut du workflow (validation → activation
        → archivage) sont permises. Toute autre modification impose de créer
        une nouvelle version (clonage).
        """
        ancienne = Maquette.objects.filter(pk=self.pk).first()
        if ancienne is None or ancienne.statut not in self.STATUTS_VERROUILLES:
            return
        fk_att = (
            ('annee_academique', 'annee_academique_id'),
            ('ref_formation', 'ref_formation_id'),
            ('parcours', 'parcours_id'),
            ('niveau', 'niveau_id'),
        )
        modifiees = [
            nom for nom, att in fk_att
            if getattr(self, att) != getattr(ancienne, att)
        ] + [
            nom for nom in ('libelle', 'commentaire_validation', 'version')
            if getattr(self, nom) != getattr(ancienne, nom)
        ]
        if modifiees:
            raise ValidationError(
                f"Maquette {ancienne.get_statut_display().lower()} (v{ancienne.version}) "
                f"immuable : champs protégés modifiés ({', '.join(modifiees)}). "
                "Créez une nouvelle version par clonage."
            )
        if (ancienne.statut, self.statut) != (ancienne.statut, ancienne.statut) \
                and (ancienne.statut, self.statut) not in self.TRANSITIONS_AUTORISEES:
            raise ValidationError(
                f"Transition de statut non autorisée : {ancienne.statut} → {self.statut}."
            )

    def save(self, *args, **kwargs):
        self._verifier_immunabilite()
        super().save(*args, **kwargs)

    def __str__(self):
        base = self.libelle or f'{self.ref_formation} / {self.niveau}'
        return f'{base} – {self.annee_academique} (v{self.version})'

    @property
    def credits_total(self):
        return sum(ue.credits for ue in self.unites_enseignement.all())

    # ── Lot L1 — contrôles de cohérence LMD ───────────────────────────────────
    @property
    def volume_horaire_total(self):
        """Volume horaire total calculé (somme CM + TD + TP de toutes les ECUE)."""
        return sum(
            ecue.volume_total
            for ue in self.unites_enseignement.all()
            for ecue in ue.ecues.all()
        )

    def verifier_coherence(self):
        """Contrôles de cohérence — retourne la liste des problèmes (vide = cohérente)."""
        problemes = []
        ues = list(
            self.unites_enseignement.select_related('semestre').prefetch_related('ecues')
        )
        if not ues:
            problemes.append("Maquette incomplète : aucune unité d'enseignement.")
            return problemes
        ref_modules_vus = {}
        for ue in ues:
            ecues = list(ue.ecues.all())
            if not ecues:
                problemes.append(f"UE {ue.code} : maquette incomplète (aucune ECUE).")
            if ue.credits <= 0:
                problemes.append(f"UE {ue.code} : crédits ECTS non renseignés.")
            if ecues:
                somme_ecue = sum(e.credits for e in ecues)
                if somme_ecue != ue.credits:
                    problemes.append(
                        f"UE {ue.code} : la somme des crédits ECUE ({somme_ecue}) "
                        f"ne correspond pas aux crédits de l'UE ({ue.credits})."
                    )
            for ecue in ecues:
                if ecue.credits <= 0:
                    problemes.append(f"ECUE {ecue.code} : crédits ECTS non renseignés.")
                if ecue.coefficient <= 0:
                    problemes.append(f"ECUE {ecue.code} : coefficient invalide.")
                if ecue.archive:
                    problemes.append(
                        f"ECUE {ecue.code} archivée : une ECUE archivée ne peut pas "
                        "figurer dans une maquette applicable."
                    )
                if ecue.ref_module_id:
                    deja_vu = ref_modules_vus.get(ecue.ref_module_id)
                    if deja_vu:
                        problemes.append(
                            f"Module {ecue.ref_module_id} rattaché deux fois dans la "
                            f"maquette (ECUE {deja_vu} et {ecue.code})."
                        )
                    else:
                        ref_modules_vus[ecue.ref_module_id] = ecue.code
        return problemes

    # ── Lot L1 — clonage de version (correctif d'une maquette aboutie) ────────
    def cloner(self, utilisateur=None):
        """Crée une nouvelle version BROUILLON copiée de cette maquette.

        Les instances UE/ECUE ne sont jamais réutilisées : chaque ligne est
        recopiée. Les ECUE archivées ne sont pas copiées (elles ne peuvent pas
        entrer dans une nouvelle maquette). Les inscriptions pédagogiques
        existantes restent rattachées à cette version (ECUE en PROTECT).
        """
        derniere = (
            Maquette.objects.filter(
                annee_academique=self.annee_academique,
                ref_formation=self.ref_formation,
                parcours=self.parcours,
                niveau=self.niveau,
            ).order_by('-version').values_list('version', flat=True).first()
            or 0
        )
        clone = Maquette.objects.create(
            annee_academique=self.annee_academique,
            ref_formation=self.ref_formation,
            parcours=self.parcours,
            niveau=self.niveau,
            version=derniere + 1,
            statut=self.Statut.BROUILLON,
            libelle=self.libelle,
        )
        for ue in self.unites_enseignement.prefetch_related('ecues'):
            nouvelle_ue = UE.objects.create(
                maquette=clone,
                semestre=ue.semestre,
                code=ue.code,
                intitule=ue.intitule,
                credits=ue.credits,
                caractere=ue.caractere,
                ordre=ue.ordre,
            )
            for ecue in ue.ecues.all():
                if ecue.archive:
                    continue
                ECUE.objects.create(
                    ue=nouvelle_ue,
                    code=ecue.code,
                    intitule=ecue.intitule,
                    credits=ecue.credits,
                    coefficient=ecue.coefficient,
                    volume_cm=ecue.volume_cm,
                    volume_td=ecue.volume_td,
                    volume_tp=ecue.volume_tp,
                    ref_module=ecue.ref_module,
                    ordre=ecue.ordre,
                )
        MaquetteJournal.objects.create(
            maquette=clone,
            action=MaquetteJournal.Action.CLONAGE,
            utilisateur=utilisateur,
            detail={'source_id': self.pk, 'source_version': self.version},
        )
        return clone


class UE(models.Model):
    """Unité d'enseignement d'une maquette, rattachée à un semestre."""

    class Caractere(models.TextChoices):
        OBLIGATOIRE = 'OBLIGATOIRE', 'Obligatoire'
        OPTIONNELLE = 'OPTIONNELLE', 'Optionnelle'
        LIBRE = 'LIBRE', 'Libre'

    maquette = models.ForeignKey(
        Maquette, on_delete=models.CASCADE, related_name='unites_enseignement',
    )
    semestre = models.ForeignKey(Semestre, on_delete=models.PROTECT, related_name='unites_enseignement')
    code = models.CharField(max_length=30)
    intitule = models.CharField(max_length=255)
    credits = models.PositiveSmallIntegerField(default=0, verbose_name='Crédits ECTS')
    caractere = models.CharField(max_length=20, choices=Caractere.choices, default=Caractere.OBLIGATOIRE)
    ordre = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering = ['semestre__numero', 'ordre', 'code']
        verbose_name = "LMD – Unité d'enseignement"
        verbose_name_plural = "LMD – Unités d'enseignement"
        constraints = [
            models.UniqueConstraint('maquette', Lower('code'), name='uniq_ue_maquette_code_ci'),
        ]

    def __str__(self):
        return f'{self.code} – {self.intitule}'

    # ── Lot L1 — R4 : une UE suit l'immutabilité de sa maquette ──
    def _verifier_maquette_modifiable(self):
        if self.maquette_id and self.maquette.statut in Maquette.STATUTS_VERROUILLES:
            raise ValidationError(
                f"Maquette {self.maquette.statut.lower()} (v{self.maquette.version}) "
                f"immuable : l'UE {self.code} ne peut plus être modifiée. "
                "Créez une nouvelle version de la maquette (clonage)."
            )

    def save(self, *args, **kwargs):
        self._verifier_maquette_modifiable()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        self._verifier_maquette_modifiable()
        return super().delete(*args, **kwargs)


class ECUE(models.Model):
    """Élément constitutif d'une UE. Passerelle possible vers un RefModule opérationnel."""

    ue = models.ForeignKey(UE, on_delete=models.CASCADE, related_name='ecues')
    code = models.CharField(max_length=30)
    intitule = models.CharField(max_length=255)
    credits = models.PositiveSmallIntegerField(default=0, verbose_name='Crédits ECTS')
    coefficient = models.DecimalField(max_digits=5, decimal_places=2, default=1)
    volume_cm = models.DecimalField(max_digits=6, decimal_places=2, default=0, verbose_name='Volume CM (h)')
    volume_td = models.DecimalField(max_digits=6, decimal_places=2, default=0, verbose_name='Volume TD (h)')
    volume_tp = models.DecimalField(max_digits=6, decimal_places=2, default=0, verbose_name='Volume TP (h)')
    ref_module = models.ForeignKey(
        'formations.RefModule',
        on_delete=models.SET_NULL,
        related_name='ecues',
        null=True,
        blank=True,
        help_text=(
            "Module opérationnel correspondant. Ce lien permet de générer les inscriptions "
            "aux modules à partir des inscriptions pédagogiques."
        ),
    )
    # Lot L1 — une ECUE archivée ne peut pas entrer dans une nouvelle maquette
    archive = models.BooleanField(default=False, db_index=True)
    ordre = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering = ['ordre', 'code']
        verbose_name = 'LMD – ECUE'
        verbose_name_plural = 'LMD – ECUE'
        constraints = [
            models.UniqueConstraint('ue', Lower('code'), name='uniq_ecue_ue_code_ci'),
        ]

    def __str__(self):
        return f'{self.code} – {self.intitule}'

    @property
    def volume_total(self):
        return self.volume_cm + self.volume_td + self.volume_tp

    # ── Lot L1 — R4 : une ECUE suit l'immutabilité de sa maquette ──
    def _verifier_maquette_modifiable(self):
        statut = self.ue.maquette.statut if self.ue_id and self.ue.maquette_id else None
        if statut in Maquette.STATUTS_VERROUILLES:
            raise ValidationError(
                f"Maquette {statut.lower()} immuable : l'ECUE {self.code} ne peut "
                "plus être modifiée. Créez une nouvelle version de la maquette."
            )

    def save(self, *args, **kwargs):
        self._verifier_maquette_modifiable()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        self._verifier_maquette_modifiable()
        return super().delete(*args, **kwargs)


class MaquetteJournal(models.Model):
    """Lot L1 — historique des validations et changements d'état d'une maquette."""

    class Action(models.TextChoices):
        CREATION = 'CREATION', 'Création'
        MODIFICATION = 'MODIFICATION', 'Modification'
        VALIDATION = 'VALIDATION', 'Validation'
        ACTIVATION = 'ACTIVATION', 'Activation'
        ARCHIVAGE = 'ARCHIVAGE', 'Archivage'
        CLONAGE = 'CLONAGE', 'Clonage'

    maquette = models.ForeignKey(
        Maquette, on_delete=models.CASCADE, related_name='journal',
    )
    action = models.CharField(max_length=20, choices=Action.choices, db_index=True)
    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='actions_maquettes',
    )
    horodatage = models.DateTimeField(auto_now_add=True, db_index=True)
    detail = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ['-horodatage']
        verbose_name = 'LMD – Journal de maquette'
        verbose_name_plural = 'LMD – Journaux de maquette'
        indexes = [
            models.Index(fields=['maquette', 'horodatage'], name='maqjournal_maq_date_idx'),
        ]

    def __str__(self):
        return f'{self.action} – maquette #{self.maquette_id} @ {self.horodatage:%Y-%m-%d %H:%M}'


# ── Lot L3/L7 — charges pédagogiques des enseignants ─────────────────────────


class AffectationPedagogique(models.Model):
    """Charge pédagogique : enseignement confié à un enseignant pour une année.

    Rattachée à la hiérarchie LMD (année → formation → parcours → niveau →
    semestre → UE/ECUE → groupe) et au maquettage versionné : l'ECUE affectée
    doit appartenir à la maquette ACTIVE de l'année/formation/niveau.
    Ne touche ni Formateur (auquel elle se réfère par FK), ni la paie
    formateurs (FinanceSettings / FinanceAjustement).
    """

    class Statut(models.TextChoices):
        PROPOSEE = 'PROPOSEE', 'Proposée'
        VALIDEE = 'VALIDEE', 'Validée'
        PLANIFIEE = 'PLANIFIEE', 'Planifiée'
        REALISEE = 'REALISEE', 'Réalisée'
        ANNULEE = 'ANNULEE', 'Annulée'

    class TypeEnseignement(models.TextChoices):
        CM = 'CM', 'Cours magistral'
        TD = 'TD', 'Travaux dirigés'
        TP = 'TP', 'Travaux pratiques'
        STAGE = 'STAGE', 'Stage'
        AUTRE = 'AUTRE', 'Autre'

    annee_academique = models.ForeignKey(
        AnneeAcademique, on_delete=models.PROTECT, related_name='affectations_pedagogiques',
    )
    ref_formation = models.ForeignKey(
        'formations.RefFormation', on_delete=models.PROTECT, related_name='affectations_pedagogiques',
    )
    parcours = models.ForeignKey(
        Parcours, on_delete=models.PROTECT,
        related_name='affectations_pedagogiques', null=True, blank=True,
    )
    niveau = models.ForeignKey(Niveau, on_delete=models.PROTECT, related_name='affectations_pedagogiques')
    semestre = models.ForeignKey(Semestre, on_delete=models.PROTECT, related_name='affectations_pedagogiques')
    ue = models.ForeignKey(
        UE, on_delete=models.PROTECT, related_name='affectations_pedagogiques', null=True, blank=True,
    )
    ecue = models.ForeignKey(
        ECUE, on_delete=models.PROTECT, related_name='affectations_pedagogiques', null=True, blank=True,
    )
    groupe = models.ForeignKey(
        Groupe, on_delete=models.SET_NULL, related_name='affectations_pedagogiques', null=True, blank=True,
    )
    enseignant = models.ForeignKey(
        'formations.Formateur', on_delete=models.PROTECT, related_name='affectations_pedagogiques',
    )
    type_enseignement = models.CharField(
        max_length=10, choices=TypeEnseignement.choices, default=TypeEnseignement.CM,
    )
    volume_horaire = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    date_debut = models.DateField(null=True, blank=True)
    date_fin = models.DateField(null=True, blank=True)
    statut = models.CharField(max_length=15, choices=Statut.choices, default=Statut.PROPOSEE)
    observations = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['semestre__numero', 'ecue__ue__ordre', 'ecue__ordre']
        verbose_name = 'LMD – Affectation pédagogique'
        verbose_name_plural = 'LMD – Affectations pédagogiques'
        indexes = [
            models.Index(fields=['annee_academique', 'enseignant']),
            models.Index(fields=['ecue', 'statut']),
        ]

    def __str__(self):
        return f'{self.enseignant} – {self.ecue or self.ue} ({self.volume_horaire} h)'

    def _ecue_de_maquette_active(self):
        """Vrai si l'ECUE/UE affectée appartient à la maquette ACTIVE de l'année."""
        maquette = Maquette.objects.filter(
            annee_academique=self.annee_academique,
            ref_formation=self.ref_formation,
            niveau=self.niveau,
            statut=Maquette.Statut.ACTIVE,
        ).first()
        if maquette is None:
            return False
        if self.ecue_id:
            return self.ecue.ue.maquette_id == maquette.pk
        if self.ue_id:
            return self.ue.maquette_id == maquette.pk
        return False

    def clean(self):
        erreurs = {}
        # Double affectation : même ECUE/groupe/type déjà confiée à un autre
        # enseignant (affectation non annulée).
        if self.ecue_id and self.annee_academique_id:
            conflits = AffectationPedagogique.objects.filter(
                annee_academique=self.annee_academique,
                ecue=self.ecue,
                type_enseignement=self.type_enseignement,
            ).exclude(pk=self.pk).exclude(statut=self.Statut.ANNULEE)
            if self.groupe_id:
                conflits = conflits.filter(groupe=self.groupe)
            if conflits.exclude(enseignant=self.enseignant).exists():
                erreurs['ecue'] = (
                    'Double affectation : cet enseignement est déjà confié à un '
                    'autre enseignant.'
                )
        # Maquette incompatible : l'ECUE/UE doit appartenir à la maquette
        # ACTIVE de l'année/formation/niveau.
        if self.ecue_id or self.ue_id:
            if not self._ecue_de_maquette_active():
                erreurs['ecue'] = (
                    'Affectation incompatible : cet enseignement ne figure pas '
                    'dans la maquette ACTIVE de l’année/formation/niveau.'
                )
        # Conflit de disponibilité : période d'indisponibilité de l'enseignant.
        if self.enseignant_id and self.date_debut and self.date_fin:
            indispos = IndisponibiliteEnseignant.objects.filter(
                enseignant=self.enseignant,
                date_debut__lte=self.date_fin,
                date_fin__gte=self.date_debut,
            )
            if indispos.exists():
                erreurs['enseignant'] = (
                    'Conflit de disponibilité : l’enseignant est indisponible '
                    'sur cette période.'
                )
        if erreurs:
            raise ValidationError(erreurs)

    @classmethod
    def volumetrie(cls, enseignant, annee):
        """Charges d'un enseignant : affectée, validée, planifiée, réalisée."""
        affectations = cls.objects.filter(
            enseignant=enseignant, annee_academique=annee,
        ).exclude(statut=cls.Statut.ANNULEE)
        somme = lambda statut: sum(
            float(a.volume_horaire) for a in affectations if a.statut == statut
        )
        return {
            'affectee': sum(float(a.volume_horaire) for a in affectations),
            'validee': somme(cls.Statut.VALIDEE),
            'planifiee': somme(cls.Statut.PLANIFIEE),
            'realisee': somme(cls.Statut.REALISEE),
        }


class IndisponibiliteEnseignant(models.Model):
    """Période d'indisponibilité d'un enseignant (détection de conflits)."""

    enseignant = models.ForeignKey(
        'formations.Formateur', on_delete=models.CASCADE, related_name='indisponibilites',
    )
    date_debut = models.DateField()
    date_fin = models.DateField()
    motif = models.CharField(max_length=200, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date_debut']
        verbose_name = 'LMD – Indisponibilité d’enseignant'
        verbose_name_plural = 'LMD – Indisponibilités d’enseignants'

    def __str__(self):
        return f'{self.enseignant} : {self.date_debut} → {self.date_fin} ({self.motif})'

    def clean(self):
        if self.date_debut and self.date_fin and self.date_fin < self.date_debut:
            raise ValidationError(
                {'date_fin': 'La fin d’indisponibilité précède le début.'}
            )
        if self.enseignant_id and self.date_debut and self.date_fin:
            chevauche = IndisponibiliteEnseignant.objects.filter(
                enseignant=self.enseignant,
                date_debut__lte=self.date_fin,
                date_fin__gte=self.date_debut,
            ).exclude(pk=self.pk).exists()
            if chevauche:
                raise ValidationError(
                    {'date_debut': 'Une indisponibilité existe déjà sur cette période.'}
                )
        return f'{self.action} – maquette #{self.maquette_id} @ {self.horodatage:%Y-%m-%d %H:%M}'
