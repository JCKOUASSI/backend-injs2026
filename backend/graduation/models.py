"""Modèles du lot L4 — Diplômation et documents officiels.

Diplome est délivré UNIQUEMENT à partir d'une décision de jury officielle
(jurys.DecisionJury) et d'une inscription administrative VALIDEE. Le PDF
produit est hashé (sha256) et gelé dès VALIDATED : toute modification
ultérieure passe par une Réédition (append-only, motif obligatoire), sans
toucher au diplôme original. Le numéro UUID est public (vérification QR).
Le registre annuel atteste la conservation longue durée.
"""
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Diplome(models.Model):
    """Diplôme LMD délivré à un étudiant (trace officielle)."""

    class Statut(models.TextChoices):
        BROUILLON = 'BROUILLON', 'Brouillon'
        VALIDATION_PENDING = 'VALIDATION_PENDING', 'En attente de validation'
        VALIDATED = 'VALIDATED', 'Validé'
        REVOKED = 'REVOKED', 'Révoqué'

    etudiant = models.ForeignKey(
        'scolarite.DossierEtudiant', on_delete=models.PROTECT, related_name='diplomes',
    )
    annee_academique = models.ForeignKey(
        'scolarite.AnneeAcademique', on_delete=models.PROTECT, related_name='diplomes',
    )
    ref_formation = models.ForeignKey(
        'formations.RefFormation', on_delete=models.PROTECT, related_name='diplomes',
    )
    parcours = models.ForeignKey(
        'scolarite.Parcours', on_delete=models.PROTECT, related_name='diplomes',
        null=True, blank=True,
    )
    niveau = models.ForeignKey(
        'scolarite.Niveau', on_delete=models.PROTECT, related_name='diplomes',
    )
    session_jury = models.ForeignKey(
        'jurys.SessionJury', on_delete=models.PROTECT, related_name='diplomes',
        null=True, blank=True,
    )
    decision_jury = models.ForeignKey(
        'jurys.DecisionJury', on_delete=models.PROTECT, related_name='diplomes',
        null=True, blank=True,
    )
    numero_unique = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    mention = models.CharField(max_length=30, blank=True, default='')
    credits_acquis = models.PositiveSmallIntegerField(default=0)
    statut = models.CharField(max_length=20, choices=Statut.choices, default=Statut.BROUILLON)
    pdf_fichier = models.FileField(
        upload_to='graduation/diplomes/', max_length=300, null=True, blank=True,
    )
    empreinte_pdf = models.CharField(max_length=64, blank=True, default='')
    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='diplomes_crees',
    )
    valide_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='diplomes_valides',
    )
    revoque_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='diplomes_revoques',
    )
    motif_revocation = models.TextField(blank=True, default='')
    date_creation = models.DateTimeField(auto_now_add=True)
    date_validation = models.DateTimeField(null=True, blank=True)
    date_revocation = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-date_creation']
        verbose_name = "LMD – Diplôme"
        verbose_name_plural = "LMD – Diplômes"
        constraints = [
            models.UniqueConstraint(
                fields=['etudiant', 'ref_formation', 'niveau'],
                name='uniq_diplome_par_etudiant_formation_niveau',
                condition=models.Q(statut='VALIDATED'),
                violation_error_message=(
                    "Un même étudiant ne peut recevoir qu'un seul diplôme VALIDÉ "
                    "pour la même formation et le même niveau."
                ),
            ),
        ]

    def __str__(self):
        return f'{self.etudiant.matricule} – {self.ref_formation} ({self.get_statut_display()})'

    def clean(self):
        erreurs = {}
        if self.annee_academique_id and self.annee_academique.cloturee:
            erreurs['annee_academique'] = (
                "Impossible de délivrer un diplôme sur une année académique clôturée."
            )
        if self.parcours_id and self.ref_formation_id and \
                self.parcours.ref_formation_id != self.ref_formation_id:
            erreurs['parcours'] = "Le parcours n'appartient pas à cette formation."
        if self.statut == self.Statut.VALIDATED and not self.verifier_conditions_validation()[0]:
            erreurs['statut'] = (
                "Les conditions de validation (décision de jury + inscription VALIDEE) "
                "ne sont pas réunies."
            )
        if self.statut == self.Statut.REVOKED and not (self.motif_revocation or '').strip():
            erreurs['motif_revocation'] = "Toute révocation doit être motivée."
        if erreurs:
            raise ValidationError(erreurs)

    def save(self, *args, **kwargs):
        # Le PDF original est gelé dès VALIDATED ; toute modification ultérieure
        # passe par une Réédition (append-only) à motif obligatoire.
        self.clean()
        super().save(*args, **kwargs)

    def verifier_conditions_validation(self):
        """Vérifie les conditions de diplômation. Retourne (ok, raisons[]).

        1. Inscription administrative VALIDEE pour (etudiant, annee, formation, niveau).
        2. Décision de jury non NULL et statut de session VERROUILLE/PUBLIE.
        Hooks L5 (stages) et L6 (finances etudiantes) a brancher ulterieurement.
        """
        raisons = []
        from scolarite.models import InscriptionAdministrative
        inscription = InscriptionAdministrative.objects.filter(
            etudiant=self.etudiant, annee_academique=self.annee_academique,
            ref_formation=self.ref_formation, niveau=self.niveau,
            statut=InscriptionAdministrative.Statut.VALIDEE,
        ).first()
        if not inscription:
            raisons.append("Aucune inscription administrative VALIDEE pour ce périmètre.")
        if not self.decision_jury_id:
            raisons.append("Aucune décision de jury officielle associée.")
        elif self.decision_jury.session.statut not in self.decision_jury.session.STATUTS_VERROUILLES:
            raisons.append(
                "La session de jury doit être verrouillée ou publiée (décision officielle)."
            )
        return (not raisons, raisons)


class Reedition(models.Model):
    """Réédition (append-only) d'un diplôme déjà VALIDATED.

    Le PDF original reste gelé (empreinte_pdf invariante) ; chaque réédition
    produit un nouveau PDF horodaté, hashé, à motif obligatoire.
    """

    diplome = models.ForeignKey(
        Diplome, on_delete=models.PROTECT, related_name='reeditions',
    )
    motif = models.TextField(help_text="Motif obligatoire de la réédition.")
    pdf_fichier = models.FileField(
        upload_to='graduation/reeditions/', max_length=300, null=True, blank=True,
    )
    empreinte_pdf = models.CharField(max_length=64, blank=True, default='')
    par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='diplomes_reedits',
    )
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date']
        verbose_name = "LMD – Réédition de diplôme"
        verbose_name_plural = "LMD – Rééditions de diplôme"

    def __str__(self):
        return f'Réédition {self.diplome} – {self.date:%Y-%m-%d}'

    def clean(self):
        if not (self.motif or '').strip():
            raise ValidationError({'motif': "Le motif de réédition est obligatoire."})
        if not self.diplome_id:
            raise ValidationError({'diplome': "Diplôme requis."})
        if self.diplome.statut == Diplome.Statut.REVOKED:
            raise ValidationError(
                "Impossible de rééditer un diplôme révoqué — restaurez-le d'abord."
            )

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)


class RegistreDiplomes(models.Model):
    """Registre annuel des diplômes délivrés (conservation longue durée).

    Une fois clôturé, aucun ajout n'est possible — clause de conservation.
    """

    annee_academique = models.OneToOneField(
        'scolarite.AnneeAcademique', on_delete=models.PROTECT, related_name='registre_diplomes',
    )
    diplomes = models.ManyToManyField(Diplome, related_name='registres', blank=True)
    cloture = models.BooleanField(default=False)
    date_cloture = models.DateTimeField(null=True, blank=True)
    cloture_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='registres_clotures',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-annee_academique__libelle']
        verbose_name = "LMD – Registre des diplômes"
        verbose_name_plural = "LMD – Registres des diplômes"

    def __str__(self):
        return f'Registre {self.annee_academique}'

    def ajouter(self, diplome, user=None):
        if self.cloture:
            raise ValidationError("Registre clôturé : ajout impossible.")
        if diplome.statut != Diplome.Statut.VALIDATED:
            raise ValidationError("Seuls les diplômes VALIDATED peuvent être inscrits au registre.")
        self.diplomes.add(diplome)

    def clôturer(self, user=None):
        """Marque le registre comme clôturé (irréversible côté ajout)."""
        if self.cloture:
            return
        self.cloture = True
        self.date_cloture = timezone.now()
        self.cloture_par = user
        self.save()


class ModeleDocument(models.Model):
    """Gabarit de document officiel (diplôme, attestation, certificat, relevé).

    Un gabarit global (formation NULL) s'applique à toutes les formations ;
    un gabarit spécifique à une formation prévaut sur le global.
    """

    class Type(models.TextChoices):
        DIPLOME = 'DIPLOME', 'Diplôme'
        ATTESTATION = 'ATTESTATION', 'Attestation'
        CERTIFICAT = 'CERTIFICAT', 'Certificat'
        RELEVE_NOTES = 'RELEVE_NOTES', 'Relevé de notes'

    type = models.CharField(max_length=20, choices=Type.choices)
    formation = models.ForeignKey(
        'formations.RefFormation', on_delete=models.CASCADE, related_name='modeles_document',
        null=True, blank=True, help_text="NULL = gabarit global par défaut.",
    )
    libelle = models.CharField(max_length=255)
    modele_pdf = models.FileField(
        upload_to='graduation/modeles/', max_length=300, null=True, blank=True,
    )
    actif = models.BooleanField(default=True)
    date_modification = models.DateTimeField(auto_now=True)
    modifie_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='modeles_document_modifies',
    )

    class Meta:
        ordering = ['type', 'formation__intitule', '-date_modification']
        verbose_name = "LMD – Modèle de document"
        verbose_name_plural = "LMD – Modèles de document"
        constraints = [
            models.UniqueConstraint(
                fields=['type', 'formation'],
                name='uniq_modele_par_type_formation',
                condition=models.Q(actif=True),
            ),
            models.UniqueConstraint(
                fields=['type'],
                name='uniq_modele_global_par_type',
                condition=models.Q(formation__isnull=True, actif=True),
            ),
        ]

    def __str__(self):
        suffixe = f' ({self.formation})' if self.formation_id else ' (global)'
        return f'{self.get_type_display()}{suffixe}'


