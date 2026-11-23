"""``PolitiqueSecurite`` : réglages modifiables sans redéploiement (singleton).

En U1, ces valeurs sont stockées et historisées (via le journal
d'habilitation) mais **aucun code d'authentification ne les applique
encore** : leur mise en œuvre (verrouillage, MFA, expiration…) relève des
unités U5/U6. Les valeurs par défaut sont volontairement non dérangeantes.
"""
from django.db import models


class PolitiqueQuerySet(models.QuerySet):
    def delete(self, *args, **kwargs):
        # La politique de sécurité ne se supprime pas, même en masse.
        raise models.ProtectedError(
            'La politique de sécurité ne peut pas être supprimée.',
            list(self),
        )


class PolitiqueSecurite(models.Model):
    """Une seule ligne, d'identifiant fixe (singleton ``pk=1``)."""

    objects = PolitiqueQuerySet.as_manager()

    # Mot de passe.
    longueur_min_mot_de_passe = models.PositiveSmallIntegerField(default=12)
    exige_majuscule = models.BooleanField(default=True)
    exige_minuscule = models.BooleanField(default=True)
    exige_chiffre = models.BooleanField(default=True)
    exige_caractere_special = models.BooleanField(default=True)
    duree_validite_mot_de_passe_jours = models.PositiveIntegerField(
        default=0, help_text="0 = pas d'expiration forcée.",
    )
    historique_mots_de_passe = models.PositiveSmallIntegerField(default=5)

    # Verrouillage de connexion.
    nombre_echecs_avant_verrouillage = models.PositiveSmallIntegerField(default=5)
    duree_verrouillage_minutes = models.PositiveIntegerField(default=15)

    # Sessions et inactivité.
    inactivite_session_minutes = models.PositiveIntegerField(default=30)
    inactivite_suspension_jours = models.PositiveIntegerField(
        default=180, help_text="Au-delà, proposition de suspension (jamais automatique en U1).",
    )

    # Dérogations et revues.
    duree_max_derogation_jours = models.PositiveIntegerField(default=90)
    periodicite_revue_jours = models.PositiveIntegerField(default=180)

    # U5 — cycle de vie et provisionnement événementiel.
    preavis_suspension_jours = models.PositiveIntegerField(
        default=15,
        help_text="Préavis notifié avant la proposition de suspension d'inactivité.",
    )
    delai_grace_fin_relation_jours = models.PositiveIntegerField(
        default=7,
        help_text="Délai de grâce après une fin de relation avant toute proposition.",
    )
    plafond_quotidien_propositions = models.PositiveIntegerField(
        default=50,
        help_text="Au-delà, les propositions excédentaires sont bloquées et une alerte est émise.",
    )
    echeance_notification_jours = models.PositiveIntegerField(
        default=7,
        help_text="Anticipation (jours) de la notification d'échéance des attributions.",
    )

    # Canaux / MFA par rôle : listes de codes de rôles en JSON.
    roles_mfa_obligatoire = models.JSONField(
        default=list, blank=True,
        help_text="Codes RoleMetier soumis au MFA quand le drapeau dédié est actif.",
    )
    canaux_par_role = models.JSONField(
        default=dict, blank=True,
        help_text="Dérogation de canal d'accès par code de rôle.",
    )

    date_modification = models.DateTimeField(auto_now=True)
    modifie_par = models.ForeignKey(
        'authentication.User', on_delete=models.SET_NULL, null=True,
        blank=True, related_name='politiques_modifiees',
    )

    class Meta:
        verbose_name = 'Politique de sécurité'
        verbose_name_plural = 'Politique de sécurité'

    def __str__(self):
        return 'Politique de sécurité des habilitations'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        # Le singleton ne se supprime pas.
        raise models.ProtectedError(
            'La politique de sécurité ne peut pas être supprimée.',
            [],
        )

    @classmethod
    def objet(cls):
        """Retourne le singleton, créé avec les valeurs par défaut sinon."""
        politique, _ = cls.objects.get_or_create(pk=1)
        return politique
