"""``CompteUtilisateur`` : extension OneToOne du compte d'authentification.

Aucun second modèle utilisateur n'est créé : le compte de connexion reste
``authentication.User`` (note de conception U1, décision 2). Ce profil porte
les données du cycle de vie du compte au sens du Module 18. Il est lui-même
optionnel : un compte technique peut n'avoir ni profil ni :class:`Personne`,
et les comptes existants continuent de fonctionner sans profil tant que la
migration de comptes (U8) ne les a pas rattachés.
"""
from django.conf import settings
from django.db import models
from django.utils import timezone

from .enums import CanalAcces


class CompteUtilisateur(models.Model):
    class Statut(models.TextChoices):
        INVITE = 'INVITE', 'Invité'
        ACTIF = 'ACTIF', 'Actif'
        SUSPENDU = 'SUSPENDU', 'Suspendu'
        DESACTIVE = 'DESACTIVE', 'Désactivé'
        VERROUILLE = 'VERROUILLE', 'Verrouillé'
        EXPIRE = 'EXPIRE', 'Expiré'

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='profil_habilitation',
    )
    personne = models.ForeignKey(
        'habilitations.Personne', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='comptes',
    )

    # Rattachements organisationnels (complétion module Utilisateurs, 2026-09) :
    # ce sont des affiliations administratives, distinctes des périmètres CURP
    # qui bornent les permissions (les périmètres DIRECTION/SERVICE y porteront
    # ces mêmes entités — note J2). M2M additifs, vides par défaut : aucun
    # compte existant n'est modifié.
    departements = models.ManyToManyField(
        'administrations.Departement', blank=True, related_name='comptes',
        help_text='Départements dont le compte est rattaché.',
    )
    services = models.ManyToManyField(
        'ressources_humaines.Service', blank=True, related_name='comptes',
        help_text='Services dont le compte est rattaché.',
    )

    statut = models.CharField(
        max_length=12, choices=Statut.choices, default=Statut.ACTIF,
        db_index=True,
    )
    motif_statut = models.TextField(blank=True, default='')
    canal = models.CharField(
        max_length=10, choices=CanalAcces.choices, default=CanalAcces.LES_DEUX,
    )

    date_creation = models.DateTimeField(auto_now_add=True)
    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        blank=True, related_name='comptes_habilitation_crees',
    )
    date_activation = models.DateTimeField(null=True, blank=True)
    date_expiration = models.DateTimeField(null=True, blank=True)
    date_suspension = models.DateTimeField(null=True, blank=True)
    date_verrouillage = models.DateTimeField(null=True, blank=True)

    # Le User.last_login existe mais n'est pas alimenté par le flux JWT
    # (écart E11 d'U0) : ce champ sera rempli par le dispositif CURP (U6).
    derniere_connexion = models.DateTimeField(null=True, blank=True)
    derniere_activite = models.DateTimeField(null=True, blank=True)

    echecs_consecutifs = models.PositiveIntegerField(default=0)

    # U5 — réversibilité des imports en masse et exemption d'inactivité.
    import_execution = models.ForeignKey(
        'habilitations.ExecutionImport', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='comptes_crees',
    )
    exempt_inactivite = models.BooleanField(
        default=False,
        help_text="Exempte le compte de la suspension pour inactivité (congé longue durée…).",
    )
    date_preavis_inactivite = models.DateField(null=True, blank=True)

    mfa_actif = models.BooleanField(default=False)
    mfa_secret = models.CharField(
        max_length=64, blank=True, default='',
        help_text='Secret TOTP (base32) du MFA ; vide tant que le MFA n’est pas armé.',
    )
    langue = models.CharField(max_length=8, default='fr')
    notes = models.TextField(blank=True, default='')

    class Meta:
        verbose_name = 'Compte utilisateur (habilitation)'
        verbose_name_plural = 'Comptes utilisateur (habilitations)'
        ordering = ('-date_creation',)

    def __str__(self):
        return f'Compte de {self.user.get_username()} [{self.statut}]'

    @property
    def est_actif(self):
        return self.statut == self.Statut.ACTIF

    def est_en_cours_validite(self, maintenant=None):
        """Vrai si la date d'expiration (optionnelle) n'est pas atteinte."""
        if not self.date_expiration:
            return True
        maintenant = maintenant or timezone.now()
        return maintenant < self.date_expiration

    def peut_acceder_au_canal(self, canal_demande):
        """Le canal WEB n'est pas accordé à un compte MOBILE (et inversement)."""
        if self.canal == CanalAcces.LES_DEUX:
            return True
        return self.canal == canal_demande
