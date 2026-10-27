"""Lot L5 — application des équivalences/dispenses et rectification.

Règles implémentées :
- aucune dispense/équivalence ne s'applique avant validation (statut VALIDEE) ;
- l'application alimente l'historique académique (EvenementScolarite de type
  EQUIVALENCE_DISPENSE) et JournalScolarite ;
- l'inscription pédagogique existante correspondante passe au statut
  DISPENSEE (statut déjà présent sur InscriptionPedagogique) ;
- les crédits reconnus sont tracés (le calcul ECTS des semestres reste au
  lot L3) ;
- une décision n'est jamais supprimée : toute modification après validation
  passe par ``rectifier`` (trace ancienne/nouvelle valeur).
"""
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from scolarite.models import (
    EvenementScolarite,
    InscriptionPedagogique,
    JournalScolarite,
    journaliser,
)

from .models import DemandeEquivalenceDispense


class ApplicationImpossible(ValidationError):
    """L'application de la dispense/équivalence est impossible."""


@transaction.atomic
def appliquer(demande, utilisateur=None, commentaire=''):
    """Applique une demande VALIDEE : effet académique + audit complet."""
    if demande.statut != DemandeEquivalenceDispense.Statut.VALIDEE:
        raise ApplicationImpossible(
            'Seule une demande VALIDEE peut être appliquée : aucune dispense '
            'ne s’applique avant validation.'
        )
    if demande.fin_validite and demande.fin_validite < timezone.localdate():
        raise ApplicationImpossible('La dispense/équivalence a expiré.')

    # 1) Inscriptions pédagogiques existantes correspondantes → DISPENSEE.
    lignes = InscriptionPedagogique.objects.filter(
        inscription__etudiant=demande.etudiant,
    ).select_related('inscription')
    if demande.ecue_id:
        lignes = lignes.filter(ecue=demande.ecue)
    elif demande.ue_id:
        lignes = lignes.filter(ecue__ue=demande.ue)
    for ligne in lignes:
        if ligne.statut != InscriptionPedagogique.Statut.DISPENSEE:
            ligne.statut = InscriptionPedagogique.Statut.DISPENSEE
            ligne.save(update_fields=['statut', 'updated_at'])

    # 2) Historique académique.
    EvenementScolarite.objects.create(
        etudiant=demande.etudiant,
        type_evenement=EvenementScolarite.Type.EQUIVALENCE_DISPENSE,
        ancienne_valeur='',
        nouvelle_valeur=(
            f'{demande.get_type_demande_display()} – '
            f'{demande.credits_reconnus or 0} crédit(s) reconnu(s)'
        ),
        commentaire=commentaire or demande.motif,
        enregistre_par=utilisateur,
    )

    # 3) Statut de la demande + audit.
    demande.statut = DemandeEquivalenceDispense.Statut.APPLIQUEE
    demande.appliquee_le = timezone.now()
    demande.appliquee_par = utilisateur
    demande.save(update_fields=['statut', 'appliquee_le', 'appliquee_par', 'updated_at'])
    journaliser(
        JournalScolarite.Action.EVENEMENT_SCOLARITE,
        objet=demande,
        acteur=utilisateur,
        nouvelle_valeur='APPLIQUEE',
        commentaire=commentaire,
        extra={
            'type_demande': demande.type_demande,
            'credits_reconnus': demande.credits_reconnus,
            'nb_ip_dispensees': len(lignes),
        },
    )
    return demande


@transaction.atomic
def rectifier(demande, utilisateur=None, motif='', **champs):
    """Procédure de rectification après validation (jamais de suppression).

    Conserve l'ancienne et la nouvelle décision, journalise la rectification.
    """
    if not demande.est_verrouillee:
        raise ApplicationImpossible(
            'La rectification ne concerne que les demandes validées/rejetées/appliquées.'
        )
    if demande.statut == DemandeEquivalenceDispense.Statut.APPLIQUEE:
        raise ApplicationImpossible(
            'Une demande déjà appliquée ne peut pas être rectifiée : créez une '
            'nouvelle demande (l’historique académique est engagé).'
        )
    ancienne_decision = demande.decision
    autorises = {'credits_reconnus', 'note_transferee', 'motif', 'autorite_validation'}
    for champ, valeur in champs.items():
        if champ in autorises:
            setattr(demande, champ, valeur)
    demande.decision_rectifiee = demande.decision
    demande.rectifiee_le = timezone.now()
    demande.motif_rectification = motif
    demande.save(update_fields=[
        'credits_reconnus', 'note_transferee', 'motif', 'autorite_validation',
        'decision_rectifiee', 'rectifiee_le', 'motif_rectification', 'updated_at',
    ])
    journaliser(
        JournalScolarite.Action.EVENEMENT_SCOLARITE,
        objet=demande,
        acteur=utilisateur,
        ancienne_valeur=ancienne_decision,
        nouvelle_valeur=demande.decision_rectifiee or demande.decision,
        commentaire=f'Rectification : {motif}',
    )
    return demande