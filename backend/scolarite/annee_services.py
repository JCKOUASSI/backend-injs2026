"""Lot L1/L3 — workflow de clôture et de réouverture des années académiques.

Clôturer une année : plus aucune nouvelle inscription (garde au niveau du
modèle), l'année perd son statut « courante ». Rouvrir : l'année redevient
courante (unicité de l'année courante préservée). Toutes les opérations
sont journalisées via JournalScolarite.
"""
from django.db import transaction
from django.utils import timezone

from scolarite.models import JournalScolarite, journaliser

from .models import AnneeAcademique


@transaction.atomic
def cloturer_annee(annee, acteur=None, commentaire=''):
    """Clôture une année académique : elle perd son statut courante."""
    if annee.cloturee:
        raise ValidationError(f'L’année {annee.libelle} est déjà clôturée.')
    annee.cloturee = True
    annee.date_cloture = timezone.localdate()
    if annee.courante:
        annee.courante = False
    annee.save(update_fields=['cloturee', 'date_cloture', 'courante'])
    journaliser(
        JournalScolarite.Action.EVENEMENT_SCOLARITE,
        objet=annee,
        acteur=acteur,
        ancienne_valeur='ouverte',
        nouvelle_valeur='clôturée',
        commentaire=commentaire or 'Clôture de l’année académique',
    )
    return annee


@transaction.atomic
def rouvrir_annee(annee, acteur=None, commentaire=''):
    """Réouvre une année clôturée : elle redevient l'année courante.

    L'unicité de l'année courante est préservée : l'éventuelle année
    courante existante perd son statut (tracé au journal).
    """
    if not annee.cloturee:
        raise ValidationError(f'L’année {annee.libelle} n’est pas clôturée.')
    precedente_courante = AnneeAcademique.objects.filter(courante=True).exclude(pk=annee.pk).first()
    if precedente_courante:
        precedente_courante.courante = False
        precedente_courante.save(update_fields=['courante'])
        journaliser(
            JournalScolarite.Action.EVENEMENT_SCOLARITE,
            objet=precedente_courante,
            acteur=acteur,
            ancienne_valeur='courante',
            nouvelle_valeur='non courante',
            commentaire=f'Devient non courante : réouverture de {annee.libelle}',
        )
    annee.cloturee = False
    annee.date_cloture = None
    annee.courante = True
    annee.save(update_fields=['cloturee', 'date_cloture', 'courante'])
    journaliser(
        JournalScolarite.Action.EVENEMENT_SCOLARITE,
        objet=annee,
        acteur=acteur,
        ancienne_valeur='clôturée',
        nouvelle_valeur='ouverte (courante)',
        commentaire=commentaire or 'Réouverture de l’année académique',
    )
    return annee
