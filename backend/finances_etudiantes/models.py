from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from django.core.validators import MinValueValidator
from decimal import Decimal
import uuid

NATURE_FRAIS = [
    ('DOSSIER', 'Frais de dossier'),
    ('INSCRIPTION', "Frais d'inscription"),
    ('SCOLARITE', 'Frais de scolarité'),
    ('EXAMEN', 'Frais d\'examen'),
    ('DOCUMENT', 'Frais de document'),
]

MODE_PAIEMENT = [
    ('CAISSE', 'Caisse'),
    ('VIREMENT', 'Virement'),
    ('ELEPHANT_MONEY', 'Orange Money'),
    ('MTN_MONEY', 'MTN Mobile Money'),
    ('MOOV_MONEY', 'Moov Money'),
    ('CARTE_BANCAIRE', 'Carte bancaire'),
]

STATUT_PAIEMENT = [
    ('INITIE', 'Initialisé'),
    ('EN_ATTENTE', 'En attente'),
    ('CONFIRME', 'Confirmé'),
    ('ECHOUE', 'Échoué'),
    ('ANNULE', 'Annulé'),
    ('REMBOSSE', 'Remboursé'),
    ('RAPPROCHE', 'Rapproché'),
]


class Tarification(models.Model):
    """Tarification des frais par formation/parcours/niveau/année."""
    formation = models.ForeignKey(
        'formations.RefFormation',
        on_delete=models.PROTECT,
        related_name='+'
    )
    parcours = models.ForeignKey(
        'scolarite.Parcours',
        on_delete=models.SET_NULL,
        related_name='+',
        null=True,
        blank=True
    )
    niveau = models.ForeignKey(
        'scolarite.Niveau',
        on_delete=models.PROTECT,
        related_name='+',
        null=True,
        blank=True
    )
    annee_academique = models.ForeignKey(
        'scolarite.AnneeAcademique',
        on_delete=models.PROTECT,
        related_name='+'
    )
    nature = models.CharField(max_length=50, choices=NATURE_FRAIS)
    montant_base = models.DecimalField(max_digits=10, decimal_places=2)
    devise = models.CharField(max_length=3, default='XOF')
    actif = models.BooleanField(default=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['formation', 'parcours', 'niveau', 'annee_academique', 'nature']
        ordering = ['-date_creation']

    def __str__(self):
                return f"{self.get_nature_display()} - {self.montant_base.to_eng_string()} {self.devise}"


class Echeancier(models.Model):
    """Échéancier de paiement pour un étudiant."""
    etudiant = models.ForeignKey(
        'scolarite.DossierEtudiant',
        on_delete=models.CASCADE,
        related_name='+'
    )
    annee_academique = models.ForeignKey(
        'scolarite.AnneeAcademique',
        on_delete=models.PROTECT,
        related_name='+'
    )
    lignes = models.ManyToManyField('LigneEcheancier', related_name='+')

    @property
    def statut_global(self):
        """Statut global de l'échéancier."""
        total = sum(l.montant for l in self.lignes.all())
        paye = sum(l.montant for l in self.lignes.filter(statut='PAYE'))
        if total == 0:
            return 'COMPLETE'
        taux = (paye / total) * 100
        if taux == 0:
            return 'IMPAYE'
        elif taux < 100:
            return 'PARTIELLEMENT_PAYE'
        else:
            return 'COMPLETE'

    def __str__(self):
        return f"Échéancier {self.etudiant.id} - {self.annee_academique}"


class LigneEcheancier(models.Model):
    """Ligne d'échéancier individuelle."""
    echeancier = models.ForeignKey(
        'Echeancier',
        on_delete=models.CASCADE,
        related_name='+'
    )
    nature = models.CharField(max_length=50, choices=NATURE_FRAIS)
    montant = models.DecimalField(
        max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    date_echeance = models.DateField()
    statut = models.CharField(
        max_length=30,
        choices=[
            ('IMPAYE', 'Impayé'),
            ('PAYE', 'Payé'),
            ('PARTIELLEMENT_PAYE', 'Partiellement payé'),
        ],
        default='IMPAYE'
    )

    def __str__(self):
        return f"{self.get_nature_display()} - {self.montant} {self.statut}"


class Facture(models.Model):
    """Facture générée à partir d'un échéancier."""
    echeancier = models.ForeignKey(
        'Echeancier',
        on_delete=models.CASCADE,
        related_name='+'
    )
    numero = models.CharField(max_length=100, unique=True)
    lignes = models.ManyToManyField('LigneEcheancier', related_name='+')
    total = models.DecimalField(max_digits=12, decimal_places=2)
    date_emission = models.DateField(default=timezone.now)
    statut = models.CharField(
        max_length=20,
        choices=[
            ('BROUILLON', 'Brouillon'),
            ('EMISE', 'Émise'),
            ('PAYEE', 'Payée'),
            ('ANNULEE', 'Annulée'),
        ],
        default='BROUILLON'
    )

    def __str__(self):
        return f"Facture {self.numero} - {self.statut}"


class Paiement(models.Model):
    """Paiement effectué par un étudiant ou candidat."""
    # Source polymorphe (Candidat ou DossierEtudiant)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    source = GenericForeignKey('content_type', 'object_id')

    # Alias pratiques pour les deux types connus
    etudiant = models.ForeignKey(
        'scolarite.DossierEtudiant',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+'
    )
    candidat = models.ForeignKey(
        'admissions.Candidat',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+'
    )

    nature = models.CharField(max_length=50, choices=NATURE_FRAIS)
    montant = models.DecimalField(
        max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    devise = models.CharField(max_length=3, default='XOF')
    date = models.DateTimeField(default=timezone.now)
    mode = models.CharField(max_length=30, choices=MODE_PAIEMENT)
    statut = models.CharField(max_length=20, choices=STATUT_PAIEMENT, default='INITIE')
    preuve = models.FileField(
        upload_to='finances_proofs/',
        null=True,
        blank=True,
        help_text="Pièce justificative du paiement (obligatoire pour CONFIRME)"
    )
    utilisateur = models.ForeignKey(
        'authentication.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+'
    )
    # Anti-doublon : transaction externe unique
    transaction_externe = models.CharField(
        max_length=200,
        unique=True,
        null=True,
        blank=True,
        help_text="Identifiant unique de transaction externe (anti-doublon)"
    )
    date_rapprochement = models.DateTimeField(null=True, blank=True)
    # Audit trail complet
    audit_trail = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"Paiement {self.montant} {self.devise} ({self.get_statut_display()})"

    @property
    def source_type(self):
        if self.etudiant_id:
            return 'ETUDIANT'
        return 'CANDIDAT'

    def save(self, *args, **kwargs):
        # Initialisation de l'audit trail
        if not self.audit_trail:
            self.audit_trail = {
                'created_at': timezone.now().isoformat(),
                'created_by': str(self.utilisateur.id) if self.utilisateur else None,
            }
        super().save(*args, **kwargs)


class Quittance(models.Model):
    """Quittance de paiement."""
    paiement = models.OneToOneField(
        'Paiement',
        on_delete=models.CASCADE,
        related_name='+'
    )
    numero = models.CharField(max_length=100, unique=True, default=uuid.uuid4)
    date_echeance = models.DateField()

    def __str__(self):
        return f"Quittance {self.numero}"


class Remboursement(models.Model):
    """Remboursement d'un paiement."""
    paiement_original = models.ForeignKey(
        'Paiement',
        on_delete=models.CASCADE,
        related_name='+'
    )
    montant = models.DecimalField(
        max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    devise = models.CharField(max_length=3, default='XOF')
    motif = models.TextField()
    statut = models.CharField(max_length=20, choices=STATUT_PAIEMENT, default='INITIE')
    transaction_externe = models.CharField(max_length=200, null=True, blank=True)
    date = models.DateTimeField(default=timezone.now)
    utilisateur = models.ForeignKey(
        'authentication.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+'
    )

    def __str__(self):
        return f"Remboursement {self.montant} {self.devise} - {self.get_statut_display()}"


class Relance(models.Model):
    """Relance pour un échéancier impayé."""
    echeancier = models.ForeignKey(
        'Echeancier',
        on_delete=models.CASCADE,
        related_name='+'
    )
    type_relance = models.CharField(
        max_length=20,
        choices=[
            ('EMAIL', 'Email'),
            ('SMS', 'SMS'),
            ('LETTRE', 'Lettre'),
        ]
    )
    message = models.TextField()
    date_creation = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Relance {self.get_type_relance_display()} - {self.echeancier}"


class RapprochementComptable(models.Model):
    """Rapprochement comptable des paiements."""
    transactions = models.ManyToManyField('Paiement', related_name='+')
    date_periode = models.DateField()
    solde = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    commentaire = models.TextField(blank=True)

    def __str__(self):
        return f"Rapprochement {self.date_periode} - Solde: {self.solde}"