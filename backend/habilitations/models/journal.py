"""``JournalHabilitation`` : registre append-only et CHAÎNÉ par empreintes.

Chaque événement sensible du module (création/activation/suspension d'un
compte, attribution ou révocation, dérogation, délégation, politique,
tentative d'auto-élévation ou de connexion interdite…) est une ligne
strictement immuable. L'immutabilité est garantie :

* au niveau ORM (``save`` refuse la mise à jour, ``delete`` est interdit, le
  queryset refuse les opérations en masse) ;
* en base PostgreSQL (prod / CI) par des déclencheurs ``BEFORE UPDATE/DELETE``
  posés par migration (SQLite ne fait que du développement ; l'ORM y
  pourvoit).

Le chaînage reprend l'empreinte de la ligne précédente dans le calcul
SHA-256 de la ligne courante : toute insertion, modification ou suppression
d'une ligne casse la chaîne et est détectée par
:func:`habilitations.services.journalisation.verifier_chaine`.
"""
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone


class JournalImmuableError(RuntimeError):
    """Levée à toute tentative de modification ou de suppression d'une trace."""


class JournalQuerySet(models.QuerySet):
    def delete(self, *args, **kwargs):
        raise JournalImmuableError(
            'Le journal des habilitations est append-only : suppression interdite.'
        )

    def update(self, *args, **kwargs):
        raise JournalImmuableError(
            'Le journal des habilitations est append-only : mise à jour interdite.'
        )


class JournalHabilitation(models.Model):

    class TypeEvenement(models.TextChoices):
        COMPTE_CREE = 'COMPTE_CREE', 'Création de compte'
        COMPTE_ACTIVE = 'COMPTE_ACTIVE', 'Activation de compte'
        COMPTE_SUSPENDU = 'COMPTE_SUSPENDU', 'Suspension de compte'
        COMPTE_DESACTIVE = 'COMPTE_DESACTIVE', 'Désactivation de compte'
        COMPTE_VERROUILLE = 'COMPTE_VERROUILLE', 'Verrouillage de compte'
        COMPTE_DEVERROUILLE = 'COMPTE_DEVERROUILLE', 'Déverrouillage de compte'
        COMPTE_EXPIRE = 'COMPTE_EXPIRE', 'Expiration de compte'
        MOT_DE_PASSE_REINITIALISE = 'MOT_DE_PASSE_REINITIALISE', 'Réinitialisation de mot de passe'
        ROLE_ATTRIBUE = 'ROLE_ATTRIBUE', 'Attribution de rôle'
        ROLE_REVOQUE = 'ROLE_REVOQUE', 'Révocation de rôle'
        PERMISSION_OCTROYEE = 'PERMISSION_OCTROYEE', 'Octroi de permission'
        PERMISSION_RETIREE = 'PERMISSION_RETIREE', 'Retrait de permission'
        DELEGATION_CREE = 'DELEGATION_CREE', 'Création de délégation'
        DELEGATION_REVOQUEE = 'DELEGATION_REVOQUEE', 'Révocation de délégation'
        POLITIQUE_MODIFIEE = 'POLITIQUE_MODIFIEE', 'Modification de politique'
        CONNEXION = 'CONNEXION', 'Connexion'
        CONNEXION_ECHOUEE = 'CONNEXION_ECHOUEE', 'Échec de connexion'
        CONNEXION_REFUSEE_VERROUILLEE = 'CONNEXION_REFUSEE_VERROUILLEE', \
            'Connexion refusée : compte verrouillé'
        MFA_ETAPSE_DEMANDEE = 'MFA_ETAPSE_DEMANDEE', 'Étape MFA demandée à la connexion'
        MFA_ACTIVE = 'MFA_ACTIVE', 'Activation du MFA (TOTP)'
        MFA_DESACTIVE = 'MFA_DESACTIVE', 'Désactivation du MFA (TOTP)'
        DECONNEXION = 'DECONNEXION', 'Déconnexion'
        SESSION_REVOQUEE = 'SESSION_REVOQUEE', 'Révocation de session'
        APPAREIL_REVOQUE = 'APPAREIL_REVOQUE', 'Révocation d’appareil'
        ACCES_REFUSE = 'ACCES_REFUSE', 'Accès refusé sur ressource sensible'
        AUTO_ELEVATION_TENTEE = 'AUTO_ELEVATION_TENTEE', 'Tentative d’auto-élévation'
        # U5 — cycle de vie, provisionnement, imports et délégation.
        TRANSITION_REFUSEE = 'TRANSITION_REFUSEE', 'Transition de statut refusée'
        PROPOSITION_DEPOSEE = 'PROPOSITION_DEPOSEE', 'Proposition de provisionnement déposée'
        PROPOSITION_APPROUVEE = 'PROPOSITION_APPROUVEE', 'Proposition approuvée'
        PROPOSITION_REJETEE = 'PROPOSITION_REJETEE', 'Proposition rejetée'
        IMPORT_EXECUTE = 'IMPORT_EXECUTE', 'Exécution d’import en masse'
        IMPORTA_ANNULE = 'IMPORTA_ANNULE', 'Annulation d’import en masse'
        EXPIRATION_AUTO = 'EXPIRATION_AUTO', 'Expiration automatique à terme'
        DELEGATION_ACTIVEE = 'DELEGATION_ACTIVEE', 'Activation de délégation'
        ACTION_DELEGUEE = 'ACTION_DELEGUEE', 'Action exercée par délégation'
        # LOT 3 — organisation administrative (directions/départements/services).
        ORGANISATION_MODIFIEE = 'ORGANISATION_MODIFIEE', \
            'Modification de l’organisation (direction, département, service, rattachement)'
        # Lot A refonte — organigramme unifié (création/désactivation d'unité).
        ORGANISATION_CREEE = 'ORGANISATION_CREEE', 'Création d’une unité d’organigramme'
        ORGANISATION_DESACTIVEE = 'ORGANISATION_DESACTIVEE', 'Désactivation d’une unité d’organigramme'
        # Lot B — versionnement et restauration des rôles métier.
        ROLE_VERSIONNE = 'ROLE_VERSIONNE', 'Versionnement de rôle'
        ROLE_RESTAURE = 'ROLE_RESTAURE', 'Restauration d’une version de rôle'
        # Lot C — workflow générique de demandes d'accès.
        DEMANDE_ACCES_CREEE = 'DEMANDE_ACCES_CREEE', 'Création d’une demande d’accès'
        DEMANDE_ACCES_SOUMISE = 'DEMANDE_ACCES_SOUMISE', 'Soumission d’une demande d’accès'
        DEMANDE_ACCES_EN_REVUE = 'DEMANDE_ACCES_EN_REVUE', 'Demande d’accès placée en revue'
        DEMANDE_ACCES_APPROUVEE = 'DEMANDE_ACCES_APPROUVEE', 'Demande d’accès approuvée'
        DEMANDE_ACCES_REFUSEE = 'DEMANDE_ACCES_REFUSEE', 'Demande d’accès refusée'
        DEMANDE_ACCES_ANNULEE = 'DEMANDE_ACCES_ANNULEE', 'Demande d’accès annulée'
        AUTRE = 'AUTRE', 'Autre événement'

    #: Numéro de séquence, continue et dans l'ordre du chaînage.
    numero = models.PositiveBigIntegerField(unique=True, db_index=True)
    horodatage = models.DateTimeField(default=timezone.now, db_index=True)

    acteur = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        blank=True, related_name='journal_habilitation_actes',
    )
    acteur_label = models.CharField(max_length=150, blank=True, default='')
    compte_concerne = models.ForeignKey(
        'habilitations.CompteUtilisateur', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='journal',
    )
    personne_concernee = models.ForeignKey(
        'habilitations.Personne', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='journal',
    )

    type_evenement = models.CharField(
        max_length=40, choices=TypeEvenement.choices, db_index=True,
    )

    # Cible polymorphe optionnelle (rôle, attribution, délégation, objet métier…).
    content_type = models.ForeignKey(
        ContentType, on_delete=models.SET_NULL, null=True, blank=True,
    )
    object_id = models.CharField(max_length=64, blank=True, default='', db_index=True)
    cible = GenericForeignKey('content_type', 'object_id')
    objet_type = models.CharField(max_length=100, blank=True, default='')
    objet_libelle = models.CharField(max_length=255, blank=True, default='')

    ancienne_valeur = models.JSONField(default=dict, blank=True)
    nouvelle_valeur = models.JSONField(default=dict, blank=True)
    motif = models.TextField(blank=True, default='')

    adresse_ip = models.GenericIPAddressField(null=True, blank=True)
    agent_utilisateur = models.CharField(max_length=250, blank=True, default='')
    correlation_id = models.CharField(max_length=64, blank=True, default='', db_index=True)

    empreinte_precedente = models.CharField(max_length=64, blank=True, default='', db_index=True)
    empreinte = models.CharField(max_length=64, unique=True, db_index=True)

    # U5 — quand l'action a été exercée EN VERTU d'une délégation, on porte
    # sa référence (la mention du délégant figure dans nouvelle_valeur).
    delegation_source = models.ForeignKey(
        'habilitations.DelegationHabilitation', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='actions_journalisees',
    )

    objects = JournalQuerySet.as_manager()

    class Meta:
        verbose_name = 'Événement d’habilitation'
        verbose_name_plural = 'Journal des habilitations'
        ordering = ('numero',)
        # Consultatif uniquement ; l'écriture passe par le service.
        default_permissions = ('view',)

    def __str__(self):
        return f'HAB-{self.numero:07d} · {self.type_evenement}'

    # ── Immutabilité au niveau ORM ───────────────────────────────────────
    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise JournalImmuableError(
                f'L’événement {self} est immuable : créez un nouvel événement.'
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise JournalImmuableError(
            f'L’événement {self} est immuable : suppression interdite.'
        )
