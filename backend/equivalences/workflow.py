"""Machine à états des demandes d'équivalence/dispense (lot L5).

Workflow : BROUILLON → SOUMISE → EN_INSTRUCTION → A_COMPLETER →
AVIS_PEDAGOGIQUE → DECISION → VALIDEE ou REJETEE → APPLIQUEE.
(A_COMPLETER peut revenir à EN_INSTRUCTION après complétion des pièces.)
"""
from django.core.exceptions import ValidationError

from scolarite.models import JournalScolarite

from .models import DemandeEquivalenceDispense, HistoriqueEquivalence

S = DemandeEquivalenceDispense.Statut

TRANSITIONS = {
    S.BROUILLON: {S.SOUMISE},
    S.SOUMISE: {S.EN_INSTRUCTION, S.A_COMPLETER},
    S.EN_INSTRUCTION: {S.A_COMPLETER, S.AVIS_PEDAGOGIQUE, S.REJETEE},
    S.A_COMPLETER: {S.EN_INSTRUCTION, S.REJETEE},
    S.AVIS_PEDAGOGIQUE: {S.DECISION},
    S.DECISION: {S.VALIDEE, S.REJETEE},
    S.VALIDEE: {S.APPLIQUEE},
    S.REJETEE: set(),
    S.APPLIQUEE: set(),
}


class TransitionInterdite(ValidationError):
    """Transition non autorisée par la machine à états."""


def transitions_possibles(demande):
    return sorted(TRANSITIONS.get(demande.statut, set()))


def appliquer_transition(demande, nouveau_statut, utilisateur=None, commentaire=''):
    if nouveau_statut == demande.statut:
        raise TransitionInterdite(f'La demande est déjà « {demande.get_statut_display()} ».')
    if nouveau_statut not in TRANSITIONS.get(demande.statut, set()):
        raise TransitionInterdite(
            f'Transition interdite : « {demande.get_statut_display()} » ne peut pas '
            f'passer à « {S(nouveau_statut).label} ».'
        )
    ancien = demande.statut
    demande.statut = nouveau_statut
    demande.save(update_fields=['statut', 'updated_at'])
    demande.journaliser(
        JournalScolarite.Action.EVENEMENT_SCOLARITE, utilisateur,
        ancienne_valeur=ancien,
        nouvelle_valeur=nouveau_statut,
        commentaire=commentaire,
    )
    HistoriqueEquivalence.objects.create(
        demande=demande, statut=nouveau_statut,
        utilisateur=utilisateur if getattr(utilisateur, 'pk', None) else None,
        commentaire=commentaire,
    )
    return demande