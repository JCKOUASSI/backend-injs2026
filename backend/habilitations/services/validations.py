"""Contrôles purs et non bloquants des habilitations (socle U1).

Ces fonctions ne prennent AUCUNE décision d'accès : elles calculent et
signalent des violations, en préparation du moteur ``est_autorise`` d'U2 et
du mode observation. Elles sont déterministes et faciles à tester.
"""
from datetime import timedelta

from django.apps import apps as django_apps
from django.db import transaction
from django.utils import timezone


def controle_duree_derogation(date_debut, date_fin, politique=None):
    """Retourne un code d'anomalie si la dérogation OCTROI dépasse le maximum.

    ``None`` signifie « durée conforme ». Une dérogation OCTROI est toujours
    temporaire et doit porter une date de fin.
    """
    from ..models.politique import PolitiqueSecurite
    politique = politique or PolitiqueSecurite.objet()
    if date_fin is None:
        return 'DEROGATION_SANS_DATE_FIN'
    debut = date_debut or timezone.localdate()
    maximum = politique.duree_max_derogation_jours
    if date_fin > debut + timedelta(days=maximum):
        return 'DEROGATION_TROP_LONGUE'
    if date_fin < debut:
        return 'DEROGATION_PERIODE_INCOHERENTE'
    return None


@transaction.atomic
def declarer_incompatibilite(role_a, role_b):
    """Déclare une incompatibilité dans les deux sens (séparation des tâches)."""
    role_a.incompatible_avec.add(role_b)
    role_b.incompatible_avec.add(role_a)


def mettre_a_jour_disponibilite_roles():
    """Marque chaque rôle DISPONIBLE/INDISPONIBLE selon son module requis.

    Un module absent ne provoque jamais d'erreur : le rôle est simplement
    marqué indisponible (règle d'activation conditionnelle du prompt).
    Retourne ``(disponibles, indisponibles)`` sous forme de codes.
    """
    from ..models.role import RoleMetier
    disponibles, indisponibles = [], []
    for role in RoleMetier.objects.all():
        installe = role.module_est_installe()
        if role.disponible != installe:
            RoleMetier.objects.filter(pk=role.pk).update(disponible=installe)
            role.disponible = installe
        (disponibles if installe else indisponibles).append(role.code)
    return disponibles, indisponibles


def modules_installes():
    """Ensemble des noms d'applications Django effectivement présentes."""
    return {app.label for app in django_apps.get_app_configs()}
