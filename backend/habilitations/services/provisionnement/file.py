"""File de validation humaine du provisionnement (C3, L2).

Les sondes déposent des propositions ; :func:`mettre_en_file` est
idempotent (clé de déduplication par fait), respecte le **plafond
quotidien** de créations (qui émet une alerte au lieu d'inonder la file) et
notifie les administrateurs qu'une proposition attend une décision.
Aucune proposition n'est jamais appliquée automatiquement.
"""
from django.db.models import Count
from django.utils import timezone

from ...models import (
    CompteUtilisateur,
    NotificationHabilitation,
    PolitiqueSecurite,
    PropositionProvisionnement,
)
from ..drapeaux import sonde_active
from ..journalisation import journaliser
from ..notifications import notifier_admins
from .sondes import SONDES


def _cle_existe_deja(cle):
    """Une proposition vivante (en attente/approuvée/appliquée) existe déjà."""
    return PropositionProvisionnement.objects.filter(
        cle_dedoublonnage=cle,
    ).exclude(
        statut__in=[
            PropositionProvisionnement.Statut.REJETEE,
            PropositionProvisionnement.Statut.ANNULEE,
        ],
    ).exists()


def propositions_du_jour():
    aujourd_hui = timezone.localdate()
    return PropositionProvisionnement.objects.filter(
        cree_le__date=aujourd_hui,
    )


def _plafond_atteint():
    politique = PolitiqueSecurite.objet()
    return propositions_du_jour().count() >= politique.plafond_quotidien_propositions


def _alerte_plafond_deja_emise():
    return NotificationHabilitation.objects.filter(
        categorie=NotificationHabilitation.Categorie.ALERTE_PLAFOND,
        date_creation__date=timezone.localdate(),
    ).exists()


def mettre_en_file(fait, acteur=None):
    """Dépose une proposition pour le :class:`Fait`, ou ``None`` si doublon."""
    cle = fait.cle()
    if _cle_existe_deja(cle):
        return None
    if _plafond_atteint():
        # Plafond quotidien franchi : on bloque les nouveaux dépôts et on
        # alerte UNE fois par jour (reprise de données, sonde fautive…).
        if not _alerte_plafond_deja_emise():
            notifier_admins(
                NotificationHabilitation.Categorie.ALERTE_PLAFOND,
                'Plafond de propositions de provisionnement atteint',
                "Le nombre maximal de propositions automatiques du jour est "
                "atteint ; les nouveaux faits ne sont pas mis en file tant que "
                "la file n'est pas instruite. Vérifiez les déclencheurs.",
                {'declencheur': fait.declencheur},
            )
        return None

    compte_cible = None
    if fait.username_cible:
        compte_cible = (
            CompteUtilisateur.objects
            .filter(user__username=fait.username_cible)
            .first()
        )

    proposition = PropositionProvisionnement.objects.create(
        declencheur=fait.declencheur,
        action_proposee=fait.action,
        source_app=fait.source_app,
        source_modele=fait.source_modele,
        source_objet_id=str(fait.source_objet_id),
        source_libelle=fait.source_libelle[:255],
        proposition=fait.proposition,
        cle_dedoublonnage=cle,
        compte_cible=compte_cible,
        motif=(fait.proposition.get('motif', '') or '')[:4000],
    )
    journaliser(
        'PROPOSITION_DEPOSEE', acteur=acteur, compte=compte_cible,
        cible=proposition,
        nouvelle_valeur={
            'declencheur': proposition.declencheur,
            'action': proposition.action_proposee,
            'source': f'{fait.source_app}.{fait.source_modele}#{fait.source_objet_id}',
        },
        motif=proposition.motif or 'Proposition automatique en attente de validation.',
    )
    return proposition


def scanner(declencheurs=None, acteur=None):
    """Parcourt les sondes ACTIVÉES (maître + drapeau dédié) et alimente la file.

    Retourne ``{declencheur: nombre_nouveau}``. Une sonde éteinte n'est même
    pas lue : extinction immédiate sans redéploiement.
    """
    bilan = {}
    for code, sonde in SONDES.items():
        if declencheurs is not None and code not in declencheurs:
            continue
        if not sonde_active(code, acteur):
            continue
        # FIN_RELATION tient compte du délai de grâce paramétrable.
        politique = PolitiqueSecurite.objet()
        faits = (
            sonde(politique.delai_grace_fin_relation_jours)
            if code == 'FIN_RELATION' else sonde()
        )
        nouveau = 0
        for fait in faits:
            if mettre_en_file(fait, acteur=acteur) is not None:
                nouveau += 1
        bilan[code] = nouveau
    return bilan
