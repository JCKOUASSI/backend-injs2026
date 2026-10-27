"""Machine d'états des demandes d'accès (Lot C, additif).

Transitions légitimes uniquement :

    BROUILLON → SOUMISE → EN_REVUE → APPROUVEE / REFUSEE
    BROUILLON | SOUMISE | EN_REVUE → ANNULEE

Sécurité :
- séparation demandeur / approbateur (auto-approbation interdite) ;
- justification obligatoire à la création ;
- motif de décision obligatoire au refus ;
- l'approbation d'une demande d'attribution de rôle alimente la file de
  provisionnement EXISTANTE (PropositionProvisionnement EN_ATTENTE) — elle
  ne provisionne jamais directement ;
- chaque transition est journalisée (journal immuable).
"""
from django.db import transaction
from django.utils import timezone

from ..models import DemandeAcces
from .journalisation import journaliser

#: Transitions légitimes : {état courant: {états accessibles}}.
TRANSITIONS = {
    DemandeAcces.Statut.BROUILLON: {
        DemandeAcces.Statut.SOUMISE,
        DemandeAcces.Statut.ANNULEE,
    },
    DemandeAcces.Statut.SOUMISE: {
        DemandeAcces.Statut.EN_REVUE,
        DemandeAcces.Statut.APPROUVEE,
        DemandeAcces.Statut.REFUSEE,
        DemandeAcces.Statut.ANNULEE,
    },
    DemandeAcces.Statut.EN_REVUE: {
        DemandeAcces.Statut.APPROUVEE,
        DemandeAcces.Statut.REFUSEE,
        DemandeAcces.Statut.ANNULEE,
    },
    # États terminaux : aucune transition.
    DemandeAcces.Statut.APPROUVEE: set(),
    DemandeAcces.Statut.REFUSEE: set(),
    DemandeAcces.Statut.ANNULEE: set(),
}

#: Type d'événement de journal associé à chaque état d'arrivée.
EVENEMENTS = {
    DemandeAcces.Statut.SOUMISE: 'DEMANDE_ACCES_SOUMISE',
    DemandeAcces.Statut.EN_REVUE: 'DEMANDE_ACCES_EN_REVUE',
    DemandeAcces.Statut.APPROUVEE: 'DEMANDE_ACCES_APPROUVEE',
    DemandeAcces.Statut.REFUSEE: 'DEMANDE_ACCES_REFUSEE',
    DemandeAcces.Statut.ANNULEE: 'DEMANDE_ACCES_ANNULEE',
}


class TransitionIllegale(ValueError):
    """Transition non permise par la machine d'états."""


def creer_demande(demandeur, *, type_demande, justification,
                  compte_cible=None, role=None, permission=None):
    """Crée une demande en BROUILLON (justification obligatoire)."""
    if not (justification or '').strip():
        raise ValueError('La justification est obligatoire.')
    if type_demande == DemandeAcces.Type.ATTRIBUTION_ROLE and role is None:
        raise ValueError('Une demande de rôle doit désigner le rôle visé.')
    if (
        type_demande == DemandeAcces.Type.PERMISSION_DIRECTE
        and permission is None
    ):
        raise ValueError(
            'Une demande de permission directe doit désigner la permission.'
        )
    demande = DemandeAcces.objects.create(
        demandeur=demandeur if (demandeur and demandeur.is_authenticated) else None,
        compte_cible=compte_cible,
        type_demande=type_demande,
        role=role,
        permission=permission,
        justification=justification.strip(),
    )
    journaliser(
        'DEMANDE_ACCES_CREEE',
        acteur=demandeur if (demandeur and demandeur.is_authenticated) else None,
        compte=compte_cible,
        cible=demande,
        nouvelle_valeur={'type': type_demande, 'statut': demande.statut},
        motif=justification,
    )
    return demande


def appliquer_transition(demande, vers, *, acteur, motif_decision=''):
    """Applique une transition contrôlée et journalise. Toute re-transition
    d'un état terminal est refusée (idempotence par refus explicite)."""
    vers = DemandeAcces.Statut(vers) if isinstance(vers, str) else vers
    if vers not in TRANSITIONS.get(demande.statut, set()):
        raise TransitionIllegale(
            f'Transition interdite : {demande.statut} → {vers}.'
        )
    acteur_reel = acteur if (acteur and acteur.is_authenticated) else None
    ancien_statut = demande.statut

    if vers in (DemandeAcces.Statut.APPROUVEE, DemandeAcces.Statut.REFUSEE):
        # Séparation des responsabilités : jamais soi-même.
        if acteur_reel and demande.demandeur_id == acteur_reel.pk:
            raise ValueError(
                'Un demandeur ne peut pas décider sa propre demande.'
            )
        demande.approbateur = acteur_reel
        demande.date_decision = timezone.now()
        demande.motif_decision = (motif_decision or '').strip()
        if vers == DemandeAcces.Statut.REFUSEE and not demande.motif_decision:
            raise ValueError('Un motif de décision est obligatoire au refus.')

    if vers == DemandeAcces.Statut.SOUMISE:
        demande.date_soumission = timezone.now()

    demande.statut = vers
    with transaction.atomic():
        demande.save()
        if vers == DemandeAcces.Statut.APPROUVEE:
            _alimenter_provisionnement(demande)
    journaliser(
        EVENEMENTS[vers],
        acteur=acteur_reel,
        compte=demande.compte_cible,
        cible=demande,
        ancienne_valeur={'statut': ancien_statut},
        nouvelle_valeur={
            'statut': vers,
            'provisionnement': demande.proposition_id,
        },
        motif=motif_decision or demande.justification,
    )
    return demande


def _alimenter_provisionnement(demande):
    """Approbation → file de provisionnement EXISTANTE (jamais d'exécution)."""
    from ..models import PropositionProvisionnement

    if (
        demande.type_demande != DemandeAcces.Type.ATTRIBUTION_ROLE
        or demande.role is None
        or demande.compte_cible is None
        or demande.proposition_id
    ):
        return
    proposition = PropositionProvisionnement.objects.create(
        declencheur=PropositionProvisionnement.Declencheur.RECRUTEMENT,
        action_proposee=PropositionProvisionnement.Action.ATTRIBUER_ROLE,
        source_app='habilitations',
        source_modele='DemandeAcces',
        source_objet_id=str(demande.pk),
        source_libelle=f'Demande d’accès #{demande.pk} — {demande.role.code}',
        proposition={
            'role': demande.role.code,
            'demande_acces': demande.pk,
            'origine': 'DEMANDE_ACCES',
        },
        statut=PropositionProvisionnement.Statut.EN_ATTENTE,
        cle_dedoublonnage=f'demande-acces-{demande.pk}',
        compte_cible=demande.compte_cible,
        motif=demande.justification,
    )
    DemandeAcces.objects.filter(pk=demande.pk).update(proposition=proposition)
    demande.proposition = proposition
