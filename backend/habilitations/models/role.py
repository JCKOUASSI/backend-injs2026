"""Référentiel paramétrable des rôles métier (``RoleMetier``).

En U1, le référentiel est une coquille **vide** prête à être peuplée : le
chargement des 33 rôles de l'annexe A1 est explicitement reporté à l'unité
U3 (migration de données idempotente). Aucun code ne doit figer la liste en
dur ; les rôles sont des données configurables sans redéploiement.

Les incompatibilités de séparation des tâches sont une relation réflexive
symétrique (la réciproque est créée par le service, pas automatiquement par
Django car la relation est déclarée non symétrique).
"""
from django.conf import settings
from django.apps import apps as django_apps
from django.db import models

from .enums import CanalAcces, DomaineMetier, NiveauAcces
from .perimetre import Perimetre


class RoleMetier(models.Model):
    code = models.CharField(
        max_length=60, unique=True, db_index=True,
        help_text="Code technique stable en majuscules, ex. AGENT_CANDIDATURE.",
    )
    libelle = models.CharField(max_length=150)
    libelle_court = models.CharField(max_length=80, blank=True, default='')
    description = models.TextField(
        blank=True, default='',
        help_text="Description fonctionnelle rédigée pour un non-informaticien.",
    )

    domaine = models.CharField(max_length=30, choices=DomaineMetier.choices,
                               db_index=True)
    niveau_defaut = models.CharField(
        max_length=2, choices=NiveauAcces.choices, default=NiveauAcces.N1,
    )
    perimetre_defaut = models.CharField(
        max_length=20, choices=Perimetre.Type.choices,
        default=Perimetre.Type.INJS_ENTIER,
    )

    #: Nom d'application Django requise (null = rôle toujours disponible).
    module_requis = models.CharField(max_length=60, blank=True, default='')
    disponible = models.BooleanField(
        default=True,
        help_text="Calculé au démarrage par inspection d'INSTALLED_APPS (U3).",
    )

    sensible = models.BooleanField(
        default=False, help_text="Un rôle sensible impose le MFA et la double validation.",
    )
    cumulable = models.BooleanField(
        default=True, help_text="Ce rôle peut-il être combiné à d'autres rôles ?",
    )
    incompatible_avec = models.ManyToManyField(
        'self', symmetrical=False, blank=True,
        related_name='incompatibilite_inverse',
        help_text="Rôles inconciliables (séparation des tâches).",
    )

    # Matrice rôle → permissions (U2 : structure nécessaire au moteur ;
    # la table est VIDE jusqu'à la migration de données U3, qui charge les
    # 33 rôles et leurs permissions).
    permissions = models.ManyToManyField(
        'habilitations.PermissionMetier', blank=True,
        related_name='roles_octroyants',
        help_text="Permissions canoniques octroyées par ce rôle (matrice U3).",
    )

    canal_impose = models.CharField(
        max_length=10, choices=CanalAcces.choices, blank=True, default='',
        help_text="Canal d'accès imposé, le cas échéant (ex. MOBILE).",
    )

    ordre = models.PositiveIntegerField(default=100)
    actif = models.BooleanField(default=True)

    auteur = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        blank=True, related_name='roles_metier_crees',
    )
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Rôle métier'
        verbose_name_plural = 'Rôles métier'
        ordering = ('domaine', 'ordre', 'libelle')

    def __str__(self):
        return f'{self.libelle} ({self.code})'

    def module_est_installe(self):
        """Vrai si l'application requise est présente dans INSTALLED_APPS."""
        if not self.module_requis:
            return True
        try:
            django_apps.get_app_config(self.module_requis)
        except LookupError:
            return False
        return True

    def rendre_disponibilite(self, enregistrer=False):
        """Met à jour ``disponible`` selon la présence du module requis."""
        etat = self.module_est_installe()
        if enregistrer and self.disponible != etat:
            RoleMetier.objects.filter(pk=self.pk).update(disponible=etat)
            self.disponible = etat
        return etat
