"""Machine à états des candidatures.

Les transitions autorisées sont déclarées ici et nulle part ailleurs : ni les
vues, ni l'admin, ni le frontend ne doivent décider d'un enchaînement de
statuts. Toute transition passe par ``appliquer_transition``.
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from scolarite.models import JournalScolarite, journaliser

from .models import Candidature

S = Candidature.Statut

# Transitions autorisées : statut courant → statuts atteignables.
TRANSITIONS = {
    S.BROUILLON: {S.SOUMISE, S.ANNULE},
    S.SOUMISE: {S.EN_ATTENTE_DE_VERIFICATION, S.ANNULE},
    S.EN_ATTENTE_DE_VERIFICATION: {S.PIECES_INCOMPLETES, S.PIECES_VALIDEES, S.ANNULE},
    S.PIECES_INCOMPLETES: {S.EN_ATTENTE_DE_VERIFICATION, S.PIECES_VALIDEES, S.ANNULE},
    S.PIECES_VALIDEES: {S.EN_ETUDE, S.PIECES_INCOMPLETES, S.ANNULE},
    S.EN_ETUDE: {S.ADMISSIBLE, S.REFUSE, S.LISTE_ATTENTE, S.ANNULE},
    S.ADMISSIBLE: {S.ADMIS, S.ADMIS_SOUS_RESERVE, S.LISTE_ATTENTE, S.REFUSE, S.ANNULE},
    S.LISTE_ATTENTE: {S.ADMIS, S.ADMIS_SOUS_RESERVE, S.REFUSE, S.ANNULE},
    S.ADMIS: {S.ANNULE},
    S.ADMIS_SOUS_RESERVE: {S.ADMIS, S.ANNULE},
    S.REFUSE: {S.ANNULE},
    S.ANNULE: set(),
}

# Statuts de décision finale : horodatent la décision et son auteur.
STATUTS_DECISION = {S.ADMIS, S.ADMIS_SOUS_RESERVE, S.LISTE_ATTENTE, S.REFUSE}

# Statuts exigeant un dossier de pièces obligatoires complet.
STATUTS_EXIGEANT_DOSSIER_COMPLET = {S.PIECES_VALIDEES}


class TransitionInterdite(ValidationError):
    """Transition non autorisée par la machine à états."""


def transitions_possibles(candidature):
    return sorted(TRANSITIONS.get(candidature.statut, set()))


def verifier_transition(candidature, nouveau_statut, forcer_dossier=False):
    """Valide une transition sans l'appliquer. Lève ``TransitionInterdite`` si refusée."""
    if nouveau_statut == candidature.statut:
        raise TransitionInterdite(
            f'La candidature est déjà au statut « {candidature.get_statut_display()} ».'
        )
    autorises = TRANSITIONS.get(candidature.statut, set())
    if nouveau_statut not in autorises:
        raise TransitionInterdite(
            f'Transition interdite : « {candidature.get_statut_display()} » ne peut pas '
            f'passer à « {Candidature.Statut(nouveau_statut).label} ».'
        )
    if nouveau_statut in STATUTS_EXIGEANT_DOSSIER_COMPLET and not forcer_dossier:
        validees, total = candidature.completude
        if not candidature.dossier_complet:
            raise TransitionInterdite(
                f'Dossier incomplet : {validees}/{total} pièce(s) obligatoire(s) validée(s).'
            )


@transaction.atomic
def appliquer_transition(candidature, nouveau_statut, acteur=None, commentaire='', forcer_dossier=False):
    """Applique une transition validée, horodate la décision et journalise."""
    verifier_transition(candidature, nouveau_statut, forcer_dossier=forcer_dossier)

    ancien_statut = candidature.statut
    candidature.statut = nouveau_statut
    champs = ['statut', 'updated_at']

    if nouveau_statut in STATUTS_DECISION:
        candidature.date_decision = timezone.now()
        candidature.decide_par = acteur if getattr(acteur, 'pk', None) else None
        champs += ['date_decision', 'decide_par']

    candidature.save(update_fields=champs)

    journaliser(
        JournalScolarite.Action.CANDIDATURE_TRANSITION,
        objet=candidature,
        acteur=acteur,
        ancienne_valeur=ancien_statut,
        nouvelle_valeur=nouveau_statut,
        commentaire=commentaire,
        extra={'forcer_dossier': bool(forcer_dossier)},
    )
    return candidature
