"""Modèles du cycle de vie U5 (prompt C3).

Trois objets nouveaux, tous additifs et sans effet sur les anciens écrans :

* :class:`PropositionProvisionnement` — file de validation HUMAINE alimentée
  par les sondes événementielles ; rien n'est créé sans approbation ;
* :class:`ExecutionImport` — exécution d'un import en masse en une
  transaction, réversible par référence d'exécution (annulation =
  désactivation, jamais de suppression physique, règle S5) ;
* :class:`NotificationHabilitation` — support traçable des préavis,
  échéances et alertes (le canal d'envoi SMTP/SMS reste hors périmètre démo).
"""
from django.conf import settings
from django.db import models
from django.utils import timezone


class PropositionProvisionnement(models.Model):
    """Proposition en attente de validation humaine (jamais appliquée seule)."""

    class Declencheur(models.TextChoices):
        ADMISSION = 'ADMISSION', 'Admission d’un candidat validée'
        INSCRIPTION = 'INSCRIPTION', 'Inscription administrative validée'
        RECRUTEMENT = 'RECRUTEMENT', 'Recrutement d’un agent enregistré en RH'
        AFFECTATION_ENSEIGNANT = 'AFFECTATION_ENSEIGNANT', 'Affectation pédagogique d’un enseignant'
        FIN_RELATION = 'FIN_RELATION', 'Fin d’inscription, départ ou fin de contrat'
        JURY = 'JURY', 'Désignation d’un membre de jury'
        INACTIVITE = 'INACTIVITE', 'Compte inactif au-delà de la durée admise'

    class Action(models.TextChoices):
        CREER_COMPTE = 'CREER_COMPTE', 'Créer un compte'
        ACTIVER_COMPTE = 'ACTIVER_COMPTE', 'Activer un compte'
        ATTRIBUER_ROLE = 'ATTRIBUER_ROLE', 'Attribuer un rôle'
        SUSPENDRE_COMPTE = 'SUSPENDRE_COMPTE', 'Suspendre un compte'
        DESACTIVER_COMPTE = 'DESACTIVER_COMPTE', 'Désactiver un compte'

    class Statut(models.TextChoices):
        EN_ATTENTE = 'EN_ATTENTE', 'En attente'
        APPROUVEE = 'APPROUVEE', 'Approuvée'
        APPLIQUEE = 'APPLIQUEE', 'Appliquée'
        REJETEE = 'REJETEE', 'Rejetée'
        ANNULEE = 'ANNULEE', 'Annulée'

    declencheur = models.CharField(max_length=24, choices=Declencheur.choices, db_index=True)
    action_proposee = models.CharField(max_length=20, choices=Action.choices)

    # Référence DÉCOUPLÉE de l'objet métier source (pas de FK vers les apps
    # métier : le dispositif d'habilitation reste autonome).
    source_app = models.CharField(max_length=60)
    source_modele = models.CharField(max_length=80)
    source_objet_id = models.CharField(max_length=64)
    source_libelle = models.CharField(max_length=255, blank=True, default='')

    # Charge utile normalisée (identifiant suggéré, personne, rôles, legacy…).
    proposition = models.JSONField(default=dict, blank=True)
    # Résultat d'application (identifiants créés, statut obtenu…).
    resultat = models.JSONField(default=dict, blank=True)

    statut = models.CharField(
        max_length=12, choices=Statut.choices, default=Statut.EN_ATTENTE, db_index=True,
    )
    cle_dedoublonnage = models.CharField(max_length=180, unique=True)

    compte_cible = models.ForeignKey(
        'habilitations.CompteUtilisateur', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='propositions',
    )
    motif = models.TextField(blank=True, default='')
    motif_rejet = models.TextField(blank=True, default='')

    cree_le = models.DateTimeField(auto_now_add=True)
    approuve_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        blank=True, related_name='propositions_approuvees',
    )
    traite_le = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Proposition de provisionnement'
        verbose_name_plural = 'Propositions de provisionnement'
        ordering = ('-cree_le',)
        indexes = [
            models.Index(fields=['declencheur', 'statut']),
            models.Index(fields=['source_app', 'source_modele', 'source_objet_id']),
        ]

    def __str__(self):
        return f'{self.get_declencheur_display()} · {self.action_proposee} [{self.statut}]'


class ExecutionImport(models.Model):
    """Une exécution d'import en masse, avec son rapport et son annulation."""

    class Statut(models.TextChoices):
        EN_COURS = 'EN_COURS', 'En cours'
        TERMINE = 'TERMINE', 'Terminé'
        ECHEC = 'ECHEC', 'Échec (aucune écriture)'
        ANNULE = 'ANNULE', 'Annulé (comptes désactivés)'

    reference = models.CharField(max_length=30, unique=True, db_index=True)
    statut = models.CharField(
        max_length=10, choices=Statut.choices, default=Statut.EN_COURS, db_index=True,
    )
    nom_fichier = models.CharField(max_length=255, blank=True, default='')
    total = models.PositiveIntegerField(default=0)
    crees = models.PositiveIntegerField(default=0)
    erreurs = models.PositiveIntegerField(default=0)
    rapport = models.JSONField(default=dict, blank=True)
    rapport_annulation = models.JSONField(default=dict, blank=True)

    lance_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        blank=True, related_name='imports_lances',
    )
    date_execution = models.DateTimeField(auto_now_add=True)
    annule_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        blank=True, related_name='imports_annules',
    )
    date_annulation = models.DateTimeField(null=True, blank=True)
    motif_annulation = models.TextField(blank=True, default='')

    class Meta:
        verbose_name = 'Exécution d’import en masse'
        verbose_name_plural = 'Exécutions d’import en masse'
        ordering = ('-date_execution',)

    def __str__(self):
        return f'{self.reference} [{self.statut}]'


class NotificationHabilitation(models.Model):
    """Notification interne au dispositif (préavis, échéance, alerte, file)."""

    class Categorie(models.TextChoices):
        PREAVIS_SUSPENSION = 'PREAVIS_SUSPENSION', 'Préavis de suspension pour inactivité'
        ECHEANCE_ATTRIBUTION = 'ECHEANCE_ATTRIBUTION', 'Échéance d’attribution'
        ECHEANCE_DEROGATION = 'ECHEANCE_DEROGATION', 'Échéance de dérogation'
        ECHEANCE_DELEGATION = 'ECHEANCE_DELEGATION', 'Échéance de délégation'
        ECHEANCE_COMPTE = 'ECHEANCE_COMPTE', "Échéance du compte"
        EXPIRATION_INVITATION = 'EXPIRATION_INVITATION', 'Invitation expirée'
        ALERTE_PLAFOND = 'ALERTE_PLAFOND', 'Plafond quotidien de propositions atteint'
        PROPOSITION = 'PROPOSITION', 'Proposition de provisionnement à instruire'
        AUTRE = 'AUTRE', 'Autre notification'

    destinataire = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='notifications_habilitation',
    )
    compte = models.ForeignKey(
        'habilitations.CompteUtilisateur', on_delete=models.CASCADE,
        null=True, blank=True, related_name='notifications',
    )
    categorie = models.CharField(max_length=24, choices=Categorie.choices, db_index=True)
    titre = models.CharField(max_length=200)
    message = models.TextField(blank=True, default='')
    metadonnees = models.JSONField(default=dict, blank=True)
    lu = models.BooleanField(default=False, db_index=True)
    date_lecture = models.DateTimeField(null=True, blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Notification d’habilitation'
        verbose_name_plural = 'Notifications d’habilitation'
        ordering = ('-date_creation',)
        indexes = [models.Index(fields=['destinataire', 'lu'])]

    def __str__(self):
        return f'{self.get_categorie_display()} → {self.destinataire_id}'
