"""
Modèles pour le module Paramètres.

Stocke les paramètres fonctionnels de l'application avec historisation.
"""

import json
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import models

from authentication.role_groups import get_user_roles

# Clés dont la modification exige une confirmation explicite (API + UI).
CLES_CRITIQUES = frozenset({
    'duree_session_heures',
    'qr_token_lifetime_hours',
    'seuil_absence_minutes',
})


class Parametre(models.Model):
    """
    Paramètres fonctionnels de l'application (singleton par clé).
    
    - Clé unique identifiant le paramètre
    - Typé (texte, entier, décimal, booléen, choix)
    - Categoriés (général, finance, présences, sécurité, interface)
    - Versionnés via ParametreHistorique
    - Contrôle d'accès par rôle
    """

    # Catégories disponibles
    CATEGORIE_CHOICES = [
        ('general', 'Général'),
        ('scolarite', 'Scolarité / LMD'),
        ('presences', 'Présences'),
        ('edt', 'EDT (import)'),
        ('notifications', 'Notifications'),
        ('securite', 'Sécurité'),
        ('interface', 'Interface'),
        ('finance', 'Finance'),
        # P00-08 : feature flags (interrupteurs de fonctionnalités, livrés éteints).
        ('flags', 'Fonctionnalités (feature flags)'),
    ]

    # Types de paramètres
    TYPE_CHOICES = [
        ('text', 'Texte libre'),
        ('email', 'Email'),
        ('integer', 'Nombre entier'),
        ('decimal', 'Décimal'),
        ('bool', 'Booléen'),
        ('choice', 'Liste déroulante'),
        ('date', 'Date'),
    ]

    # Identifiant unique (clé technique)
    cle = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
        help_text="Identifiant technique unique (ex: finance_prix_heure_realisee)",
    )

    # Affichage et organisation
    libelle = models.CharField(
        max_length=255,
        help_text="Libellé affiché à l'utilisateur",
    )
    description = models.TextField(
        blank=True,
        default='',
        help_text="Description complète ou aide contextuelle",
    )
    categorie = models.CharField(
        max_length=50,
        choices=CATEGORIE_CHOICES,
        db_index=True,
    )
    ordre = models.PositiveSmallIntegerField(
        default=100,
        help_text="Ordre d'affichage au sein de la catégorie (croissant)",
    )

    # Type et validation
    type = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
        default='text',
    )

    # Valeurs
    valeur = models.TextField(
        help_text="Valeur courante (stockée en JSON si nécessaire)",
    )
    valeur_defaut = models.TextField(
        help_text="Valeur par défaut (pour restauration)",
    )

    # Métadonnées pour types complexes
    choices_json = models.TextField(
        blank=True,
        default='',
        help_text='Pour type=choice: {"key": "Libellé", ...} en JSON',
    )
    regex_validation = models.CharField(
        max_length=500,
        blank=True,
        default='',
        help_text="Regex pour validation custom (optionnel)",
    )

    # Contrôle d'accès et modification
    modifiable = models.BooleanField(
        default=True,
        help_text="Si False, le paramètre ne peut pas être modifié",
    )
    modifiable_par_roles = models.TextField(
        default='["ADMIN", "CHEF_INJS_ADMIN", "INJS_ADMIN"]',
        help_text="Rôles autorisés à modifier (JSON array)",
    )
    lecturable_par_roles = models.TextField(
        default='["ADMIN", "CHEF_INJS_ADMIN", "INJS_ADMIN", "DIRECTION", "FINANCE"]',
        help_text="Rôles autorisés à consulter (JSON array)",
    )

    # État
    actif = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Paramètre actif/inactif",
    )

    # Audit
    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='parametres_crees',
    )
    cree_le = models.DateTimeField(auto_now_add=True)

    modifie_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='parametres_modifies',
    )
    modifie_le = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Paramètre'
        verbose_name_plural = 'Paramètres'
        ordering = ['categorie', 'ordre', 'libelle']
        indexes = [
            models.Index(fields=['categorie', 'actif'], name='param__categ_actif_idx'),
            models.Index(fields=['cle'], name='param__cle_idx'),
            models.Index(fields=['modifie_le'], name='param__modif_date_idx'),
        ]
        permissions = [
            ('view_parametres', 'Consulter les paramètres'),
            ('change_parametres', 'Modifier les paramètres'),
        ]

    def __str__(self):
        return f"{self.libelle} ({self.cle})"

    @property
    def est_critique(self):
        return self.cle in CLES_CRITIQUES

    def get_valeur_typed(self):
        """Retourne la valeur avec le bon type Python, ou None si vide/invalide."""
        if self.valeur is None or self.valeur == '':
            return None
        try:
            return self._coerce_valeur(self.valeur)
        except ValidationError:
            return None

    def _coerce_valeur(self, raw):
        """Normalise et valide une valeur brute selon le type du paramètre."""
        if raw is None:
            raise ValidationError({'valeur': 'Valeur obligatoire.'})
        text = str(raw).strip()

        if self.type == 'bool':
            lowered = text.lower()
            if lowered in ('true', '1', 'yes', 'oui'):
                return True
            if lowered in ('false', '0', 'no', 'non'):
                return False
            raise ValidationError({'valeur': 'Valeur booléenne attendue (oui/non).'})

        if self.type == 'integer':
            try:
                value = int(text)
            except (ValueError, TypeError):
                raise ValidationError({'valeur': 'Nombre entier attendu.'})
            if value < 0 or value > 100000:
                raise ValidationError({'valeur': 'Entier hors plage autorisée (0–100000).'})
            return value

        if self.type == 'decimal':
            try:
                value = Decimal(text)
            except (InvalidOperation, ValueError, TypeError):
                raise ValidationError({'valeur': 'Nombre décimal attendu.'})
            return value

        if self.type == 'email':
            try:
                validate_email(text)
            except ValidationError:
                raise ValidationError({'valeur': 'Adresse email invalide.'})
            return text

        if self.type == 'date':
            try:
                datetime.strptime(text, '%Y-%m-%d')
            except ValueError:
                raise ValidationError({'valeur': 'Date attendue au format AAAA-MM-JJ.'})
            return text

        if self.type == 'choice':
            try:
                choices = json.loads(self.choices_json or '{}')
            except json.JSONDecodeError:
                choices = {}
            if not isinstance(choices, dict) or text not in choices:
                raise ValidationError({'valeur': 'Valeur hors des choix autorisés.'})
            return text

        if self.regex_validation:
            try:
                if not re.fullmatch(self.regex_validation, text):
                    raise ValidationError({'valeur': 'Valeur incompatible avec le format attendu.'})
            except re.error:
                raise ValidationError({'valeur': 'Règle de validation interne invalide.'})
        return text

    def normalize_valeur(self, raw):
        """Retourne la valeur à stocker (texte) après validation de type."""
        typed = self._coerce_valeur(raw)
        if self.type == 'bool':
            return 'true' if typed else 'false'
        if self.type == 'decimal':
            return format(typed, 'f')
        return str(typed)

    def can_be_modified_by(self, user):
        if not self.modifiable or not self.actif:
            return False
        try:
            allowed = set(json.loads(self.modifiable_par_roles or '[]'))
        except (json.JSONDecodeError, TypeError):
            return False
        return bool(get_user_roles(user) & allowed)

    def can_be_read_by(self, user):
        try:
            allowed = set(json.loads(self.lecturable_par_roles or '[]'))
        except (json.JSONDecodeError, TypeError):
            return False
        return bool(get_user_roles(user) & allowed)

    @classmethod
    def get_by_cle(cls, cle, default=None):
        """
        Récupère un paramètre par sa clé.
        
        Args:
            cle (str): Clé technique du paramètre
            default: Valeur par défaut si non trouvé
            
        Returns:
            Parametre or default
        """
        try:
            return cls.objects.get(cle=cle)
        except cls.DoesNotExist:
            return default


class ParametreHistorique(models.Model):
    """
    Historique (audit) des modifications de paramètres.
    
    Modèle immuable (append-only) enregistrant chaque changement
    de valeur avec l'utilisateur, la date, et la raison.
    """

    parametre = models.ForeignKey(
        Parametre,
        on_delete=models.CASCADE,
        related_name='historiques',
        help_text="Paramètre concerné par cette modification",
    )

    ancienne_valeur = models.TextField(
        help_text="Valeur précédente du paramètre",
    )
    nouvelle_valeur = models.TextField(
        help_text="Nouvelle valeur du paramètre",
    )

    modifie_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='modifications_parametres',
    )
    modifie_le = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
    )

    motif_modification = models.TextField(
        blank=True,
        default='',
        help_text="Raison optionnelle de la modification",
    )

    adresse_ip = models.CharField(
        max_length=50,
        blank=True,
        default='',
        help_text="Adresse IP du client ayant effectué la modification",
    )

    class Meta:
        verbose_name = 'Historique paramètre'
        verbose_name_plural = 'Historique paramètres'
        ordering = ['-modifie_le']
        indexes = [
            models.Index(fields=['parametre', 'modifie_le'], name='hist__param_date_idx'),
            models.Index(fields=['modifie_le'], name='hist__modif_date_idx'),
        ]

    def __str__(self):
        param_cle = self.parametre.cle if self.parametre else 'unknown'
        date_str = self.modifie_le.strftime('%Y-%m-%d %H:%M:%S') if self.modifie_le else '?'
        return f"{param_cle} @ {date_str}"
