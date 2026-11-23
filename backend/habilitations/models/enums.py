"""Énumérations partagées par les modèles du socle d'habilitation (U1).

Ces choix sont des constantes de référence du Module 18 du modèle
fonctionnel. Ils vivent dans le nouveau dispositif et n'interfèrent pas
avec les ``TextChoices`` du modèle ``authentication.User`` (les 12 rôles
existants restent intacts jusqu'à la migration de comptes d'U8).
"""
from django.db import models


class NiveauAcces(models.TextChoices):
    """Niveaux d'autorisation du modèle fonctionnel (N0 le plus bas)."""

    N0 = 'N0', 'N0 — consultation très limitée'
    N1 = 'N1', 'N1 — consultation'
    N2 = 'N2', 'N2 — saisie et traitement'
    N3 = 'N3', 'N3 — validation'
    N4 = 'N4', 'N4 — administration et décision'


class DomaineMetier(models.TextChoices):
    ADMINISTRATION = 'ADMINISTRATION', 'Administration'
    CANDIDATURES = 'CANDIDATURES', 'Candidatures'
    SCOLARITE = 'SCOLARITE', 'Scolarité'
    PEDAGOGIE = 'PEDAGOGIE', 'Pédagogie'
    ENSEIGNANTS = 'ENSEIGNANTS', 'Enseignants'
    EVALUATIONS = 'EVALUATIONS', 'Évaluations'
    DIPLOMATION = 'DIPLOMATION', 'Diplômation'
    FINANCE = 'FINANCE', 'Finance'
    STAGES = 'STAGES', 'Stages'
    RH = 'RH', 'Ressources humaines'
    PATRIMOINE = 'PATRIMOINE', 'Patrimoine'
    ADMINISTRATION_GENERALE = 'ADMINISTRATION_GENERALE', 'Administration générale'
    DESTINATAIRES = 'DESTINATAIRES', 'Destinataires du service'
    TECHNIQUE = 'TECHNIQUE', 'Technique'


class CanalAcces(models.TextChoices):
    WEB = 'WEB', 'Plateforme web'
    MOBILE = 'MOBILE', 'Application mobile / PWA'
    LES_DEUX = 'LES_DEUX', 'Web et mobile'


class SituationPersonne(models.TextChoices):
    INTERNE = 'INTERNE', 'Personnel interne'
    EXTERNE = 'EXTERNE', 'Personnel externe'
    VACATAIRE = 'VACATAIRE', 'Vacataire'
    PARTENAIRE = 'PARTENAIRE', 'Partenaire / tutelle'
