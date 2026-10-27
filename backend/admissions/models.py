"""Candidatures, pièces justificatives et admissions.

Couche additive : aucun modèle existant n'est modifié. Le rattachement à
l'étudiant opérationnel (``formations.Participant``) est facultatif et n'est
renseigné qu'au moment de la conversion en inscription.
"""

import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


def piece_upload_path(instance, filename):
    """Range les pièces par candidature. Le dossier media n'est pas servi publiquement."""
    return f'candidatures/{instance.candidature.numero}/{filename}'


class TypeCandidature(models.Model):
    """Type de recrutement (concours externe, interne, sur titre…)."""

    code = models.CharField(max_length=30, unique=True)
    libelle = models.CharField(max_length=150)
    actif = models.BooleanField(default=True)

    class Meta:
        ordering = ['libelle']
        verbose_name = 'Admission – Type de candidature'
        verbose_name_plural = 'Admission – Types de candidature'

    def __str__(self):
        return self.libelle


class VoieAcces(models.Model):
    """Voie d'accès à la formation (concours, validation des acquis, transfert…)."""

    code = models.CharField(max_length=30, unique=True)
    libelle = models.CharField(max_length=150)
    actif = models.BooleanField(default=True)

    class Meta:
        ordering = ['libelle']
        verbose_name = "Admission – Voie d'accès"
        verbose_name_plural = "Admission – Voies d'accès"

    def __str__(self):
        return self.libelle


class TypePiece(models.Model):
    """Type de pièce justificative attendue dans un dossier de candidature."""

    code = models.CharField(max_length=30, unique=True)
    libelle = models.CharField(max_length=150)
    obligatoire_par_defaut = models.BooleanField(default=True)
    avec_date_expiration = models.BooleanField(
        default=False,
        help_text="La pièce a une date de validité (ex: certificat médical).",
    )
    actif = models.BooleanField(default=True)

    class Meta:
        ordering = ['libelle']
        verbose_name = 'Admission – Type de pièce'
        verbose_name_plural = 'Admission – Types de pièce'

    def __str__(self):
        return self.libelle


class ReglePiece(models.Model):
    """Rend une pièce obligatoire ou facultative pour une formation ou un type de formation."""

    type_piece = models.ForeignKey(TypePiece, on_delete=models.CASCADE, related_name='regles')
    type_formation = models.ForeignKey(
        'scolarite.TypeFormation', on_delete=models.CASCADE, related_name='regles_pieces',
        null=True, blank=True,
    )
    ref_formation = models.ForeignKey(
        'formations.RefFormation', on_delete=models.CASCADE, related_name='regles_pieces',
        null=True, blank=True, verbose_name='Formation (cycle)',
    )
    obligatoire = models.BooleanField(default=True)

    class Meta:
        ordering = ['type_piece__libelle']
        verbose_name = 'Admission – Règle de pièce'
        verbose_name_plural = 'Admission – Règles de pièces'
        unique_together = ('type_piece', 'type_formation', 'ref_formation')

    def clean(self):
        if not self.type_formation_id and not self.ref_formation_id:
            raise ValidationError(
                'Renseignez au moins un type de formation ou un cycle de formation.'
            )

    def __str__(self):
        cible = self.ref_formation or self.type_formation
        return f'{self.type_piece} → {cible}'


class Candidat(models.Model):
    """Personne candidatant à une formation. Indépendant du dossier étudiant."""

    class Sexe(models.TextChoices):
        MASCULIN = 'M', 'Masculin'
        FEMININ = 'F', 'Féminin'

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    nom = models.CharField(max_length=150)
    prenom = models.CharField(max_length=150)
    sexe = models.CharField(max_length=1, choices=Sexe.choices, blank=True)
    date_naissance = models.DateField(null=True, blank=True)
    lieu_naissance = models.CharField(max_length=150, blank=True)
    nationalite = models.CharField(max_length=100, blank=True)
    email = models.EmailField(blank=True)
    telephone = models.CharField(max_length=30, blank=True)
    telephone2 = models.CharField(max_length=30, blank=True)
    adresse = models.TextField(blank=True)
    participant = models.OneToOneField(
        'formations.Participant', on_delete=models.SET_NULL,
        related_name='candidat', null=True, blank=True,
        help_text="Renseigné lors de la conversion en étudiant inscrit.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['nom', 'prenom']
        verbose_name = 'Admission – Candidat'
        verbose_name_plural = 'Admission – Candidats'
        indexes = [
            models.Index(fields=['nom', 'prenom']),
        ]

    def __str__(self):
        return f'{self.nom} {self.prenom}'

    @property
    def nom_complet(self):
        return f'{self.nom} {self.prenom}'.strip()


class Candidature(models.Model):
    """Dossier de candidature à une formation pour une année académique."""

    class Statut(models.TextChoices):
        BROUILLON = 'BROUILLON', 'Brouillon'
        SOUMISE = 'SOUMISE', 'Soumise'
        EN_ATTENTE_DE_VERIFICATION = 'EN_ATTENTE_DE_VERIFICATION', 'En attente de vérification'
        PIECES_INCOMPLETES = 'PIECES_INCOMPLETES', 'Pièces incomplètes'
        PIECES_VALIDEES = 'PIECES_VALIDEES', 'Pièces validées'
        EN_ETUDE = 'EN_ETUDE', 'En étude'
        ADMISSIBLE = 'ADMISSIBLE', 'Admissible'
        ADMIS = 'ADMIS', 'Admis'
        ADMIS_SOUS_RESERVE = 'ADMIS_SOUS_RESERVE', 'Admis sous réserve'
        LISTE_ATTENTE = 'LISTE_ATTENTE', "Liste d'attente"
        REFUSE = 'REFUSE', 'Refusé'
        ANNULE = 'ANNULE', 'Annulé'

    numero = models.CharField(max_length=30, unique=True, editable=False)
    candidat = models.ForeignKey(Candidat, on_delete=models.CASCADE, related_name='candidatures')
    annee_academique = models.ForeignKey(
        'scolarite.AnneeAcademique', on_delete=models.PROTECT, related_name='candidatures',
    )
    ref_formation = models.ForeignKey(
        'formations.RefFormation', on_delete=models.PROTECT, related_name='candidatures',
        verbose_name='Formation (cycle) demandée',
    )
    parcours = models.ForeignKey(
        'scolarite.Parcours', on_delete=models.PROTECT, related_name='candidatures',
        null=True, blank=True,
    )
    niveau = models.ForeignKey(
        'scolarite.Niveau', on_delete=models.PROTECT, related_name='candidatures',
        verbose_name='Niveau demandé',
    )
    type_candidature = models.ForeignKey(
        TypeCandidature, on_delete=models.PROTECT, related_name='candidatures',
        null=True, blank=True,
    )
    voie_acces = models.ForeignKey(
        VoieAcces, on_delete=models.PROTECT, related_name='candidatures', null=True, blank=True,
    )
    regime = models.ForeignKey(
        'scolarite.RegimeEtudes', on_delete=models.PROTECT, related_name='candidatures',
        null=True, blank=True,
    )
    vague = models.ForeignKey(
        'formations.RefVague', on_delete=models.SET_NULL, related_name='candidatures',
        null=True, blank=True,
    )
    date_candidature = models.DateField(default=timezone.localdate)
    statut = models.CharField(max_length=30, choices=Statut.choices, default=Statut.BROUILLON)
    # Lot L2 — campagne d'admission (nullable : dossiers hors campagne tolérés)
    campagne = models.ForeignKey(
        'CampagneAdmission', on_delete=models.SET_NULL,
        related_name='candidatures', null=True, blank=True,
        help_text="Campagne d'admission de rattachement. Une campagne clôturée "
                  "n'accepte plus de candidature.",
    )
    score = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    observations = models.TextField(blank=True)
    date_decision = models.DateTimeField(null=True, blank=True)
    decide_par = models.ForeignKey(
        'authentication.User', on_delete=models.SET_NULL, related_name='candidatures_decidees',
        null=True, blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date_candidature', '-id']
        verbose_name = 'Admission – Candidature'
        verbose_name_plural = 'Admission – Candidatures'
        constraints = [
            models.UniqueConstraint(
                fields=['candidat', 'annee_academique', 'ref_formation', 'niveau'],
                condition=~models.Q(statut='ANNULE'),
                name='uniq_candidature_active_par_candidat_formation_niveau',
            ),
        ]
        indexes = [
            models.Index(fields=['statut', 'annee_academique']),
        ]

    def __str__(self):
        return f'{self.numero} – {self.candidat}'

    def save(self, *args, **kwargs):
        if not self.numero:
            self.numero = self._generer_numero()
        super().save(*args, **kwargs)

    def _generer_numero(self):
        """Numéro séquentiel par année académique : CAND-2026-2027-0001."""
        prefixe = f'CAND-{self.annee_academique.libelle}-'
        dernier = (
            Candidature.objects.filter(numero__startswith=prefixe)
            .order_by('-numero')
            .values_list('numero', flat=True)
            .first()
        )
        sequence = int(dernier.rsplit('-', 1)[1]) + 1 if dernier else 1
        return f'{prefixe}{sequence:04d}'

    def clean(self):
        if self.parcours_id and self.ref_formation_id and self.parcours.ref_formation_id != self.ref_formation_id:
            raise ValidationError({'parcours': "Le parcours n'appartient pas à cette formation."})
        # Lot L2 — cohérence campagne : la formation demandée doit correspondre,
        # et une campagne non ouverte (ou clôturée) n'accepte pas de candidature.
        if self.campagne_id:
            campagne = self.campagne
            if campagne.ref_formation_id != self.ref_formation_id:
                raise ValidationError(
                    {'campagne': "La campagne ne correspond pas à la formation demandée."}
                )
            campagne.verifier_ouverture_candidature()

    # ── Complétude du dossier ───────────────────────────────────────────────

    @property
    def pieces_obligatoires(self):
        return self.pieces.filter(obligatoire=True)

    @property
    def completude(self):
        """Retourne (nb_pièces_validées, nb_pièces_obligatoires)."""
        obligatoires = list(self.pieces_obligatoires)
        validees = [p for p in obligatoires if p.statut == PieceCandidature.Statut.VALIDEE]
        return len(validees), len(obligatoires)

    @property
    def dossier_complet(self):
        validees, total = self.completude
        return total > 0 and validees == total

    @property
    def taux_completude(self):
        validees, total = self.completude
        return round(validees * 100 / total) if total else 0


class PieceCandidature(models.Model):
    """Pièce justificative déposée dans un dossier de candidature."""

    class Statut(models.TextChoices):
        MANQUANTE = 'MANQUANTE', 'Manquante'
        FOURNIE = 'FOURNIE', 'Fournie'
        EN_VERIFICATION = 'EN_VERIFICATION', 'En vérification'
        VALIDEE = 'VALIDEE', 'Validée'
        REFUSEE = 'REFUSEE', 'Refusée'
        EXPIREE = 'EXPIREE', 'Expirée'

    candidature = models.ForeignKey(Candidature, on_delete=models.CASCADE, related_name='pieces')
    type_piece = models.ForeignKey(TypePiece, on_delete=models.PROTECT, related_name='pieces')
    obligatoire = models.BooleanField(default=True)
    fichier = models.FileField(upload_to=piece_upload_path, null=True, blank=True)
    numero_document = models.CharField(max_length=100, blank=True)
    date_delivrance = models.DateField(null=True, blank=True)
    date_expiration = models.DateField(null=True, blank=True)
    statut = models.CharField(max_length=20, choices=Statut.choices, default=Statut.MANQUANTE)
    commentaire = models.TextField(blank=True)
    verifie_par = models.ForeignKey(
        'authentication.User', on_delete=models.SET_NULL, related_name='pieces_verifiees',
        null=True, blank=True,
    )
    verifie_le = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['type_piece__libelle']
        verbose_name = 'Admission – Pièce de candidature'
        verbose_name_plural = 'Admission – Pièces de candidature'
        constraints = [
            models.UniqueConstraint(
                'candidature', 'type_piece', name='uniq_piece_par_candidature_et_type',
            ),
        ]

    def __str__(self):
        return f'{self.type_piece} – {self.candidature.numero}'

    @property
    def est_expiree(self):
        return bool(self.date_expiration and self.date_expiration < timezone.localdate())


class Admission(models.Model):
    """Décision d'admission issue d'une candidature. Entité distincte de la candidature."""

    class Decision(models.TextChoices):
        ADMIS = 'ADMIS', 'Admis'
        ADMIS_SOUS_RESERVE = 'ADMIS_SOUS_RESERVE', 'Admis sous réserve'
        EN_ATTENTE = 'EN_ATTENTE', 'En attente'
        REFUSEE = 'REFUSEE', 'Refusée'
        ANNULEE = 'ANNULEE', 'Annulée'

    candidature = models.OneToOneField(
        Candidature, on_delete=models.CASCADE, related_name='admission',
    )
    candidat = models.ForeignKey(Candidat, on_delete=models.CASCADE, related_name='admissions')
    annee_academique = models.ForeignKey(
        'scolarite.AnneeAcademique', on_delete=models.PROTECT, related_name='admissions',
    )
    ref_formation = models.ForeignKey(
        'formations.RefFormation', on_delete=models.PROTECT, related_name='admissions',
        verbose_name='Formation (cycle)',
    )
    parcours = models.ForeignKey(
        'scolarite.Parcours', on_delete=models.PROTECT, related_name='admissions',
        null=True, blank=True,
    )
    niveau = models.ForeignKey(
        'scolarite.Niveau', on_delete=models.PROTECT, related_name='admissions',
        verbose_name="Niveau d'entrée",
    )
    vague = models.ForeignKey(
        'formations.RefVague', on_delete=models.SET_NULL, related_name='admissions',
        null=True, blank=True,
    )
    categorie = models.ForeignKey(
        'formations.RefCategorie', on_delete=models.SET_NULL, related_name='admissions',
        null=True, blank=True,
    )
    grade = models.ForeignKey(
        'formations.RefGrade', on_delete=models.SET_NULL, related_name='admissions',
        null=True, blank=True,
    )
    voie_acces = models.ForeignKey(
        VoieAcces, on_delete=models.PROTECT, related_name='admissions', null=True, blank=True,
    )
    decision = models.CharField(max_length=30, choices=Decision.choices, default=Decision.EN_ATTENTE)
    date_decision = models.DateTimeField(null=True, blank=True)
    reference_decision = models.CharField(max_length=100, blank=True)
    date_limite_inscription = models.DateField(
        null=True, blank=True,
        help_text="Au-delà de cette date, l'admission ne permet plus de créer une inscription.",
    )
    observations = models.TextField(blank=True)
    decide_par = models.ForeignKey(
        'authentication.User', on_delete=models.SET_NULL, related_name='admissions_decidees',
        null=True, blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Admission – Admission'
        verbose_name_plural = 'Admission – Admissions'
        indexes = [
            models.Index(fields=['decision', 'annee_academique']),
        ]

    def __str__(self):
        return f'{self.candidat} – {self.get_decision_display()}'

    def clean(self):
        if self.grade_id and self.categorie_id and self.grade.categorie_id != self.categorie_id:
            raise ValidationError({'grade': "Le grade n'appartient pas à cette catégorie."})

    @property
    def est_expiree(self):
        return bool(
            self.date_limite_inscription
            and self.date_limite_inscription < timezone.localdate()
        )

    @property
    def permet_inscription(self):
        return (
            self.decision in (self.Decision.ADMIS, self.Decision.ADMIS_SOUS_RESERVE)
            and not self.est_expiree
        )


# ── Lot L2 — Campagnes et concours/sélection ─────────────────────────────────


class CampagneAdmission(models.Model):
    """Campagne d'admission : fenêtre de candidature par formation/parcours.

    Workflow : BROUILLON → PLANIFIEE → OUVERTE ⇄ SUSPENDUE → CLOTUREE →
    ARCHIVEE (PLANIFIEE/OUVERTE/SUSPENDUE → ANNULEE). Une campagne clôturée
    (ou non ouverte) n'accepte plus de candidature.
    """

    class Statut(models.TextChoices):
        BROUILLON = 'BROUILLON', 'Brouillon'
        PLANIFIEE = 'PLANIFIEE', 'Planifiée'
        OUVERTE = 'OUVERTE', 'Ouverte'
        SUSPENDUE = 'SUSPENDUE', 'Suspendue'
        CLOTUREE = 'CLOTUREE', 'Clôturée'
        ANNULEE = 'ANNULEE', 'Annulée'
        ARCHIVEE = 'ARCHIVEE', 'Archivée'

    libelle = models.CharField(max_length=200)
    annee_academique = models.ForeignKey(
        'scolarite.AnneeAcademique', on_delete=models.PROTECT, related_name='campagnes',
    )
    ref_formation = models.ForeignKey(
        'formations.RefFormation', on_delete=models.PROTECT, related_name='campagnes',
    )
    parcours = models.ForeignKey(
        'scolarite.Parcours', on_delete=models.PROTECT,
        related_name='campagnes', null=True, blank=True,
    )
    date_ouverture = models.DateField(null=True, blank=True)
    date_fermeture = models.DateField(null=True, blank=True)
    quota_admissibles = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="Nombre de candidats déclarés admissibles.",
    )
    quota_admis = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="Nombre d'admis au terme de la sélection.",
    )
    statut = models.CharField(max_length=20, choices=Statut.choices, default=Statut.BROUILLON)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-annee_academique__libelle', 'ref_formation__intitule']
        verbose_name = 'Admission – Campagne'
        verbose_name_plural = 'Admission – Campagnes'
        constraints = [
            models.UniqueConstraint(
                fields=['annee_academique', 'ref_formation', 'parcours'],
                name='uniq_campagne_par_annee_formation_parcours',
            ),
        ]

    def __str__(self):
        return f'{self.libelle} – {self.ref_formation} ({self.annee_academique})'

    def clean(self):
        erreurs = {}
        if self.date_ouverture and self.date_fermeture and self.date_fermeture < self.date_ouverture:
            erreurs['date_fermeture'] = 'La date de fermeture précède la date d’ouverture.'
        if self.parcours_id and self.ref_formation_id and self.parcours.ref_formation_id != self.ref_formation_id:
            erreurs['parcours'] = "Le parcours n'appartient pas à cette formation."
        if erreurs:
            raise ValidationError(erreurs)

    # ── Workflow (machine à états déclarée dans concours_services) ──
    def verifier_ouverture_candidature(self):
        """Règle L2 : seule une campagne OUVERTE dans ses dates accepte une candidature."""
        from datetime import date as _date

        def _as_date(valeur):
            return _date.fromisoformat(valeur) if isinstance(valeur, str) else valeur

        aujourd_hui = timezone.localdate()
        if self.statut != self.Statut.OUVERTE:
            raise ValidationError(
                f"La campagne « {self.libelle} » n'est pas ouverte "
                f"(statut : {self.get_statut_display()}) : candidature refusée."
            )
        date_ouverture = _as_date(self.date_ouverture)
        date_fermeture = _as_date(self.date_fermeture)
        if date_ouverture and aujourd_hui < date_ouverture:
            raise ValidationError(
                f"La campagne « {self.libelle} » ouvre le {date_ouverture.strftime('%d/%m/%Y')}."
            )
        if date_fermeture and aujourd_hui > date_fermeture:
            raise ValidationError(
                f"La campagne « {self.libelle} » a fermé le {date_fermeture.strftime('%d/%m/%Y')}."
            )

    @property
    def permet_inscription(self):
        return (
            self.decision in (self.Decision.ADMIS, self.Decision.ADMIS_SOUS_RESERVE)
            and not self.est_expiree
        )


class Epreuve(models.Model):
    """Épreuve de concours/sélection rattachée à une campagne.

    Types : écrit, oral, pratique, physique. Le verrouillage fige toutes les
    notes de l'épreuve (résultats verrouillés non modifiables).
    """

    class Type(models.TextChoices):
        ECRIT = 'ECRIT', 'Écrit'
        ORAL = 'ORAL', 'Oral'
        PRATIQUE = 'PRATIQUE', 'Pratique'
        PHYSIQUE = 'PHYSIQUE', 'Physique'

    campagne = models.ForeignKey(
        CampagneAdmission, on_delete=models.CASCADE, related_name='epreuves',
    )
    type = models.CharField(max_length=10, choices=Type.choices)
    intitule = models.CharField(max_length=200)
    date = models.DateField()
    heure_debut = models.TimeField()
    duree_minutes = models.PositiveSmallIntegerField(default=60)
    centre = models.ForeignKey(
        'formations.RefSite', on_delete=models.SET_NULL,
        related_name='epreuves', null=True, blank=True,
        verbose_name='Centre (site)',
    )
    salle = models.ForeignKey(
        'formations.RefSalle', on_delete=models.SET_NULL,
        related_name='epreuves', null=True, blank=True,
    )
    coefficient = models.DecimalField(max_digits=4, decimal_places=2, default=1)
    verrouillee = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['date', 'heure_debut']
        verbose_name = 'Admission – Épreuve'
        verbose_name_plural = 'Admission – Épreuves'

    def __str__(self):
        return f'{self.intitule} ({self.get_type_display()}) – {self.date}'

    @property
    def fin(self):
        from datetime import timedelta
        return self.debut + timedelta(minutes=self.duree_minutes)

    @property
    def debut(self):
        from datetime import date as _date, datetime, time as _time
        jour = self.date
        if isinstance(jour, str):
            jour = _date.fromisoformat(jour)
        heure = self.heure_debut
        if isinstance(heure, str):
            heure = _time.fromisoformat(heure)
        return datetime.combine(jour, heure)

    def chevauche(self, autre):
        """Vrai si deux épreuves se déroulent au même moment."""
        return (
            self.debut.date() == autre.debut.date()
            and self.debut < autre.fin
            and autre.debut < self.fin
        )


class SurveillanceEpreuve(models.Model):
    """Affectation d'un surveillant à une épreuve.

    Règle : un surveillant ne peut pas être affecté à deux épreuves
    simultanées.
    """

    epreuve = models.ForeignKey(
        Epreuve, on_delete=models.CASCADE, related_name='surveillances',
    )
    surveillant = models.ForeignKey(
        'authentication.User', on_delete=models.PROTECT, related_name='surveillances',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Admission – Surveillance d’épreuve'
        verbose_name_plural = 'Admission – Surveillances d’épreuve'
        constraints = [
            models.UniqueConstraint(
                fields=['epreuve', 'surveillant'], name='uniq_surveillance_par_epreuve',
            ),
        ]

    def __str__(self):
        return f'{self.surveillant} – {self.epreuve}'

    def clean(self):
        if not (self.epreuve_id and self.surveillant_id):
            return
        conflits = [
            s for s in SurveillanceEpreuve.objects.filter(
                surveillant=self.surveillant,
                epreuve__date=self.epreuve.date,
            ).exclude(pk=self.pk).select_related('epreuve')
            if self.epreuve.chevauche(s.epreuve)
        ]
        if conflits:
            raise ValidationError(
                {'surveillant': f"Ce surveillant est déjà affecté à l'épreuve "
                                f"« {conflits[0].epreuve} » au même moment."}
            )


class ConvocationEpreuve(models.Model):
    """Convocation d'une candidature à une épreuve + présence le jour J.

    Règle : la salle de l'épreuve ne peut pas dépasser sa capacité.
    """

    epreuve = models.ForeignKey(
        Epreuve, on_delete=models.CASCADE, related_name='convocations',
    )
    candidature = models.ForeignKey(
        Candidature, on_delete=models.CASCADE, related_name='convocations',
    )
    presente = models.BooleanField(default=False)
    convoque_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Admission – Convocation'
        verbose_name_plural = 'Admission – Convocations'
        constraints = [
            models.UniqueConstraint(
                fields=['epreuve', 'candidature'], name='uniq_convocation_par_epreuve',
            ),
        ]

    def __str__(self):
        return f'{self.candidature.numero} – {self.epreuve}'

    def clean(self):
        if not self.epreuve_id:
            return
        campagne = self.epreuve.campagne
        if campagne.statut in (campagne.Statut.CLOTUREE, campagne.Statut.ANNULEE, campagne.Statut.ARCHIVEE):
            raise ValidationError('Campagne clôturée : convocations impossible.')
        salle = self.epreuve.salle
        if salle and salle.capacite:
            deja_convoques = ConvocationEpreuve.objects.filter(
                epreuve=self.epreuve,
            ).exclude(pk=self.pk).count()
            if deja_convoques + 1 > salle.capacite:
                raise ValidationError(
                    f'Capacité de la salle « {salle.nom} » atteinte '
                    f'({salle.capacite} places) : convocation refusée.'
                )


class NoteConcours(models.Model):
    """Note d'une candidature à une épreuve. Verrouillage au niveau épreuve.

    Toute correction est historisée (NoteConcoursHistorique) avec l'ancienne
    et la nouvelle valeur.
    """

    epreuve = models.ForeignKey(
        Epreuve, on_delete=models.CASCADE, related_name='notes',
    )
    candidature = models.ForeignKey(
        Candidature, on_delete=models.CASCADE, related_name='notes_concours',
    )
    note = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text='Note obtenue (null = non noté).',
    )
    absent = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Admission – Note de concours'
        verbose_name_plural = 'Admission – Notes de concours'
        constraints = [
            models.UniqueConstraint(
                fields=['epreuve', 'candidature'], name='uniq_note_par_epreuve',
            ),
        ]

    def __str__(self):
        return f'{self.candidature.numero} – {self.epreuve} : {self.note if self.note is not None else "—"}'

    @property
    def est_verrouillee(self):
        return self.epreuve.verrouillee

    def save(self, *args, **kwargs):
        ancienne = NoteConcours.objects.filter(pk=self.pk).first()
        if ancienne and self.epreuve.verrouillee:
            raise ValidationError(
                f'Épreuve « {self.epreuve} » verrouillée : les résultats ne sont '
                'plus modifiables.'
            )
        super().save(*args, **kwargs)
        if ancienne and ancienne.note != self.note:
            NoteConcoursHistorique.objects.create(
                note=self,
                ancienne_valeur=ancienne.note,
                nouvelle_valeur=self.note,
            )


class NoteConcoursHistorique(models.Model):
    """Lot L2 — conservation ancienne/nouvelle valeur à chaque correction."""

    note = models.ForeignKey(
        NoteConcours, on_delete=models.CASCADE, related_name='historique',
    )
    ancienne_valeur = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    nouvelle_valeur = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    modifie_par = models.ForeignKey(
        'authentication.User', on_delete=models.SET_NULL,
        related_name='corrections_notes_concours', null=True, blank=True,
    )
    horodatage = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-horodatage']
        verbose_name = 'Admission – Historique de note'
        verbose_name_plural = 'Admission – Historiques de note'

    def __str__(self):
        return f'{self.note} : {self.ancienne_valeur} → {self.nouvelle_valeur}'


class ClassementConcours(models.Model):
    """Rang et liste d'une candidature à l'issue d'une campagne.

    Calcul reproductible (voir concours_services.calculer_classement) :
    le recalcul régénère les lignes et trace l'opération via
    JournalScolarite. Le résultat publié n'est plus recalculable.
    """

    class Liste(models.TextChoices):
        ADMISSIBLE = 'ADMISSIBLE', 'Admissible'
        LISTE_ATTENTE = 'LISTE_ATTENTE', "Liste d'attente"
        NON_ADMIS = 'NON_ADMIS', 'Non admis'

    campagne = models.ForeignKey(
        CampagneAdmission, on_delete=models.CASCADE, related_name='classements',
    )
    candidature = models.ForeignKey(
        Candidature, on_delete=models.CASCADE, related_name='classements',
    )
    rang = models.PositiveSmallIntegerField()
    score_total = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    liste = models.CharField(max_length=20, choices=Liste.choices)
    publie = models.BooleanField(default=False)
    genere_par = models.ForeignKey(
        'authentication.User', on_delete=models.SET_NULL,
        related_name='classements_generes', null=True, blank=True,
    )
    genere_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['campagne', 'rang']
        verbose_name = 'Admission – Classement'
        verbose_name_plural = 'Admission – Classements'
        constraints = [
            models.UniqueConstraint(
                fields=['campagne', 'candidature'], name='uniq_classement_par_campagne',
            ),
            models.UniqueConstraint(
                fields=['campagne', 'rang'], name='uniq_rang_par_campagne',
            ),
        ]

    def __str__(self):
        return f'{self.campagne.libelle} : #{self.rang} {self.candidature.numero} ({self.liste})'
