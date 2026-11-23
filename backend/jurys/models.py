"""Modèles du module Jurys (lot L3 — Prompt 13).

Conception validée :
  - SessionJury : session de délibération liée à une maquette versionnée
    **verrouillée** (ACTIVE) d'une formation / parcours / niveau ;
  - workflow à 9 états : PREPARATION → CONTROLE → CALCUL → DELIBERATION →
    DECISION → PV_GENERE → VALIDE → VERROUILLE → PUBLIE (transitions
    contrôlées par le service, pas par édition libre) ;
  - PropositionJury : résultats du moteur ECTS (append-only, reproductibles) ;
  - DecisionJury : décision officielle (justification obligatoire si manuelle) ;
  - PVJury : PV PDF reportlab, hashé, verrouillé après publication ;
  - toutes les délibérations sont journalisées via scolarite.JournalScolarite
    (append-only) avec les actions JURY_*.

Zéro doublon avec suiviEvaluation.DecisionPedagogique : celle-ci porte la
décision opérationnelle formation×participant ; le jury produit la décision
officielle LMD (référencée à l'inscription administrative et à la maquette).
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from scolarite.models import (
    AnneeAcademique,
    InscriptionAdministrative,
    Maquette,
    Niveau,
    Parcours,
    Semestre,
)


class SessionJury(models.Model):
    """Session de délibération d'un jury LMD."""

    class Statut(models.TextChoices):
        PREPARATION = 'PREPARATION', 'Préparation'
        CONTROLE = 'CONTROLE', 'Contrôle'
        CALCUL = 'CALCUL', 'Calcul'
        DELIBERATION = 'DELIBERATION', 'Délibération'
        DECISION = 'DECISION', 'Décision'
        PV_GENERE = 'PV_GENERE', 'PV généré'
        VALIDE = 'VALIDE', 'Validé'
        VERROUILLE = 'VERROUILLE', 'Verrouillé'
        PUBLIE = 'PUBLIE', 'Publié'

    class TypeSession(models.TextChoices):
        NORMALE = 'NORMALE', 'Session normale'
        RATTRAPAGE = 'RATTRAPAGE', 'Rattrapage'
        RECTIFICATION = 'RECTIFICATION', 'Rectification'

    annee_academique = models.ForeignKey(
        AnneeAcademique, on_delete=models.PROTECT, related_name='sessions_jury',
    )
    ref_formation = models.ForeignKey(
        'formations.RefFormation', on_delete=models.PROTECT, related_name='sessions_jury',
    )
    parcours = models.ForeignKey(
        Parcours, on_delete=models.PROTECT, related_name='sessions_jury',
        null=True, blank=True,
    )
    niveau = models.ForeignKey(Niveau, on_delete=models.PROTECT, related_name='sessions_jury')
    semestre = models.ForeignKey(
        Semestre, on_delete=models.PROTECT, related_name='sessions_jury',
        null=True, blank=True,
        help_text='Null = jury annuel.',
    )
    maquette = models.ForeignKey(
        Maquette, on_delete=models.PROTECT, related_name='sessions_jury',
        help_text='Version de maquette verrouillée (VALIDEE/ACTIVE) supportant la délibération.',
    )
    type_session = models.CharField(
        max_length=15, choices=TypeSession.choices, default=TypeSession.NORMALE,
    )
    statut = models.CharField(
        max_length=15, choices=Statut.choices, default=Statut.PREPARATION,
    )
    libelle = models.CharField(max_length=255, blank=True, default='')
    creee_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='sessions_jury_creees',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-annee_academique__libelle', 'niveau__ordre', 'type_session']
        verbose_name = 'LMD – Session de jury'
        verbose_name_plural = 'LMD – Sessions de jury'
        constraints = [
            models.UniqueConstraint(
                fields=['annee_academique', 'ref_formation', 'parcours', 'niveau', 'type_session'],
                name='uniq_session_jury_par_session',
            ),
        ]


    # Chaîne de transitions contrôlées (aucun saut, aucun retour libre).
    TRANSITIONS = {
        Statut.PREPARATION: Statut.CONTROLE,
        Statut.CONTROLE: Statut.CALCUL,
        Statut.CALCUL: Statut.DELIBERATION,
        Statut.DELIBERATION: Statut.DECISION,
        Statut.DECISION: Statut.PV_GENERE,
        Statut.PV_GENERE: Statut.VALIDE,
        Statut.VALIDE: Statut.VERROUILLE,
        Statut.VERROUILLE: Statut.PUBLIE,
    }
    # À partir de VERROUILLE : plus aucune modification libre des décisions ;
    # toute rectification passe par une session de type RECTIFICATION.
    STATUTS_VERROUILLES = (Statut.VERROUILLE, Statut.PUBLIE)

    def clean(self):
        erreurs = {}
        # La maquette supportant la délibération doit être verrouillée (R4)
        # et correspondre exactement à la session.
        if self.maquette_id:
            if self.maquette.statut not in Maquette.STATUTS_VERROUILLES:
                erreurs['maquette'] = (
                    'La maquette doit être validée ou active (version verrouillée).'
                )
            if self.annee_academique_id and self.maquette.annee_academique_id != self.annee_academique_id:
                erreurs['maquette'] = "La maquette n'appartient pas à cette année académique."
            if self.ref_formation_id and self.maquette.ref_formation_id != self.ref_formation_id:
                erreurs['maquette'] = "La maquette n'appartient pas à cette formation."
            if self.niveau_id and self.maquette.niveau_id != self.niveau_id:
                erreurs['maquette'] = "La maquette ne correspond pas au niveau de la session."
        if self.semestre_id and self.niveau_id and self.semestre.niveau_id != self.niveau_id:
            erreurs['semestre'] = "Le semestre ne correspond pas au niveau de la session."
        if erreurs:
            raise ValidationError(erreurs)

    @property
    def verrouillee(self):
        return self.statut in self.STATUTS_VERROUILLES

    def __str__(self):
        base = self.libelle or f'{self.ref_formation} / {self.niveau} – {self.annee_academique}'
        return f'Jury {base} ({self.get_type_session_display()})'


class MembreJury(models.Model):
    """Membre d'un jury pour une session (historisé)."""

    class Fonction(models.TextChoices):
        PRESIDENT = 'PRESIDENT', 'Président'
        SECRETAIRE = 'SECRETAIRE', 'Secrétaire'
        MEMBRE = 'MEMBRE', 'Membre'

    session = models.ForeignKey(
        SessionJury, on_delete=models.CASCADE, related_name='membres',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='membres_jury',
    )
    fonction = models.CharField(
        max_length=12, choices=Fonction.choices, default=Fonction.MEMBRE,
    )
    ajoute_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='membres_jury_ajoutes',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['session', 'fonction', 'user']
        verbose_name = 'LMD – Membre de jury'
        verbose_name_plural = 'LMD – Membres de jury'
        unique_together = ('session', 'user')

    def __str__(self):
        return f'{self.user} – {self.get_fonction_display()} ({self.session})'


class PropositionJury(models.Model):
    """Résultat calculé par le moteur ECTS — APPEND-ONLY.

    À chaque recalcul (action CALCUL de la session), une nouvelle proposition
    est créée ; la plus récente par (session, inscription) est la proposition
    courante. L'empreinte SHA-256 du résultat garantit la reproductibilité.
    """

    session = models.ForeignKey(
        SessionJury, on_delete=models.CASCADE, related_name='propositions',
    )
    inscription = models.ForeignKey(
        InscriptionAdministrative, on_delete=models.PROTECT, related_name='propositions_jury',
    )
    participant = models.ForeignKey(
        'formations.Participant', on_delete=models.PROTECT, related_name='propositions_jury',
    )
    resultat = models.JSONField(help_text='Structure complète produite par le moteur ECTS.')
    empreinte = models.CharField(max_length=64, help_text='SHA-256 du résultat (reproductibilité).')
    decision_proposee = models.CharField(max_length=12, blank=True, default='')
    credits_acquis = models.PositiveSmallIntegerField(default=0)
    calcule_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='propositions_jury_calculees',
    )
    calcule_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['session', 'participant', '-calcule_le']
        verbose_name = 'LMD – Proposition de jury'
        verbose_name_plural = 'LMD – Propositions de jury'
        indexes = [
            models.Index(fields=['session', 'participant']),
            models.Index(fields=['empreinte']),
        ]

    def __str__(self):
        return (
            f'{self.participant} – {self.decision_proposee} '
            f'({self.credits_acquis} cr.) [{self.empreinte[:8]}]'
        )


class DecisionJury(models.Model):
    """Décision officielle du jury pour un étudiant (une par session)."""

    class Decision(models.TextChoices):
        # `EXCLUSION` est une décision officielle INJS : elle n'est JAMAIS
        # convertie en AJOURNE. Elle est produite par le moteur LMD lorsque la
        # moyenne d'une UE passe sous le seuil éliminatoire paramétré
        # (`RegleValidationLMD.seuil_elim`), qui existe déjà dans le
        # référentiel LMD officiel.
        ADMIS = 'ADMIS', 'Admis'
        AJOURNE = 'AJOURNE', 'Ajourné'
        ADMIS_AVEC_RESERVES = 'ADMIS_RESERVES', 'Admis avec réserves'
        EXCLUSION = 'EXCLUSION', 'Exclu'

    session = models.ForeignKey(
        SessionJury, on_delete=models.CASCADE, related_name='decisions',
    )
    inscription = models.ForeignKey(
        InscriptionAdministrative, on_delete=models.PROTECT, related_name='decisions_jury',
    )
    participant = models.ForeignKey(
        'formations.Participant', on_delete=models.PROTECT, related_name='decisions_jury',
    )
    decision = models.CharField(max_length=20, choices=Decision.choices)
    credits_acquis = models.PositiveSmallIntegerField(default=0)
    moyenne_generale = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
    )
    mention = models.CharField(max_length=20, blank=True, default='')
    decision_manuelle = models.BooleanField(
        default=False,
        help_text='True si la décision diverge de la proposition du moteur.',
    )
    justification = models.TextField(
        blank=True, default='',
        help_text='Obligatoire pour toute décision manuelle.',
    )
    decide_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='decisions_jury',
    )
    decide_le = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['session', 'participant__nom', 'participant__prenom']
        verbose_name = 'LMD – Décision de jury'
        verbose_name_plural = 'LMD – Décisions de jury'
        unique_together = ('session', 'inscription')

    def clean(self):
        if self.decision_manuelle and not (self.justification or '').strip():
            raise ValidationError(
                {'justification': 'Toute décision manuelle doit être justifiée.'}
            )

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.participant} – {self.get_decision_display()} ({self.session})'


class PVJury(models.Model):
    """Procès-verbal PDF du jury (reportlab), hashé, verrouillé à la publication."""

    session = models.OneToOneField(
        SessionJury, on_delete=models.CASCADE, related_name='pv',
    )
    fichier = models.FileField(upload_to='jurys/pv/', max_length=300)
    sha256 = models.CharField(max_length=64)
    genere_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='pv_jury_generes',
    )
    genere_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'LMD – PV de jury'
        verbose_name_plural = 'LMD – PV de jury'

    def __str__(self):
        return f'PV {self.session}'


class NotificationJury(models.Model):
    """Notification in-app (publication d'un jury) — pattern NotificationModificationNote."""

    destinataire = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='notifications_jury',
    )
    session = models.ForeignKey(
        SessionJury, on_delete=models.CASCADE, related_name='notifications',
    )
    message = models.TextField()
    lu = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'LMD – Notification de jury'
        verbose_name_plural = 'LMD – Notifications de jury'

    def __str__(self):
        return f'{self.message[:60]}… → {self.destinataire}'