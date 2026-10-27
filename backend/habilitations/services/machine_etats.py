"""Machine à états stricte du compte (annexe A5) — U5, livrable L1.

Le graphe ci-dessous reprend EXACTEMENT les flèches de l'annexe A5 :

    (création) → INVITÉ ──1re connexion + changement MDP→ ACTIF
    INVITÉ ──invitation expirée→ EXPIRE
    ACTIF ──→ SUSPENDU (décision admin, durée bornée)
    ACTIF ──→ VERROUILLÉ (échecs répétés, automatique)
    ACTIF ──→ DÉSACTIVÉ (départ, fin de relation, décision)
    ACTIF ──→ EXPIRE (date d'expiration atteinte)
    SUSPENDU ──réactivation motivée→ ACTIF
    VERROUILLÉ ──déverrouillage auto ou admin→ ACTIF
    DÉSACTIVÉ ──réactivation exceptionnelle motivée→ ACTIF

Toute transition non prévue depuis le statut courant est refusée
(:class:`TransitionIllegale`) et journalisée comme tentative par le
service :func:`habilitations.services.comptes_admin.changer_statut`.
"""
from ..models import CompteUtilisateur, JournalHabilitation


class TransitionIllegale(Exception):
    """Transition non prévue par le graphe A5 pour le statut courant."""

    def __init__(self, transition, statut_source):
        self.transition = transition
        self.statut_source = statut_source
        super().__init__(
            f"La transition « {transition} » n'est pas autorisée depuis le statut "
            f"« {statut_source} » (machine à états A5)."
        )


#: Graphe des transitions : nom → (statut cible, états sources légaux,
#: événement de journal, compte de connexion actif après transition).
TRANSITIONS = {
    'activer': (
        CompteUtilisateur.Statut.ACTIF,
        {
            CompteUtilisateur.Statut.INVITE,
            CompteUtilisateur.Statut.SUSPENDU,
            CompteUtilisateur.Statut.VERROUILLE,
            CompteUtilisateur.Statut.DESACTIVE,
        },
        JournalHabilitation.TypeEvenement.COMPTE_ACTIVE,
        True,
    ),
    'suspendre': (
        CompteUtilisateur.Statut.SUSPENDU,
        {CompteUtilisateur.Statut.ACTIF},
        JournalHabilitation.TypeEvenement.COMPTE_SUSPENDU,
        False,
    ),
    'desactiver': (
        CompteUtilisateur.Statut.DESACTIVE,
        {CompteUtilisateur.Statut.ACTIF},
        JournalHabilitation.TypeEvenement.COMPTE_DESACTIVE,
        False,
    ),
    'verrouiller': (
        CompteUtilisateur.Statut.VERROUILLE,
        {CompteUtilisateur.Statut.ACTIF},
        JournalHabilitation.TypeEvenement.COMPTE_VERROUILLE,
        False,
    ),
    'deverrouiller': (
        CompteUtilisateur.Statut.ACTIF,
        {CompteUtilisateur.Statut.VERROUILLE},
        JournalHabilitation.TypeEvenement.COMPTE_DEVERROUILLE,
        True,
    ),
    'expirer': (
        CompteUtilisateur.Statut.EXPIRE,
        {
            CompteUtilisateur.Statut.INVITE,
            CompteUtilisateur.Statut.ACTIF,
        },
        JournalHabilitation.TypeEvenement.COMPTE_EXPIRE,
        False,
    ),
}


def transition_legale(statut_source, transition):
    """Vrai si la transition est prévue depuis ``statut_source``."""
    regle = TRANSITIONS.get(transition)
    return bool(regle) and statut_source in regle[1]


def decrire_transition(transition):
    """Retourne ``(cible, evenement, compte_actif)`` ou lève KeyError."""
    cible, _sources, evenement, actif = TRANSITIONS[transition]
    return cible, evenement, actif


def transitions_possibles(statut_source):
    """Noms des transitions licites depuis un statut donné (pour l'UI)."""
    return sorted(
        nom for nom, (_cible, sources, _evt, _actif) in TRANSITIONS.items()
        if statut_source in sources
    )
