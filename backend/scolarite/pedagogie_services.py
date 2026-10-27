"""Génération et gestion des inscriptions pédagogiques.

Deux modes coexistent : la génération automatique depuis la maquette
pédagogique, qui couvre le cas courant, et l'ajout ou le retrait manuel
d'une ECUE, toujours historisé.
"""

from django.core.exceptions import ValidationError
from django.db import transaction

from .models import (
    ECUE,
    InscriptionAdministrative,
    InscriptionPedagogique,
    JournalScolarite,
    Maquette,
    journaliser,
)


class PedagogieImpossible(ValidationError):
    """L'opération demandée est incompatible avec l'état du dossier."""


def maquette_applicable(inscription):
    """Maquette active correspondant à l'inscription, ou None.

    On privilégie la maquette du parcours ; à défaut, celle définie au niveau
    de la formation seule. La version la plus récente l'emporte.
    """
    base = Maquette.objects.filter(
        annee_academique=inscription.annee_academique,
        ref_formation=inscription.ref_formation,
        niveau=inscription.niveau,
        statut=Maquette.Statut.ACTIVE,
    )
    if inscription.parcours_id:
        avec_parcours = base.filter(parcours=inscription.parcours).order_by('-version').first()
        if avec_parcours is not None:
            return avec_parcours
    return base.filter(parcours__isnull=True).order_by('-version').first()


def _type_enseignement_dominant(ecue):
    """Déduit le type d'enseignement principal d'une ECUE à partir de ses volumes."""
    volumes = {
        InscriptionPedagogique.TypeEnseignement.CM: ecue.volume_cm,
        InscriptionPedagogique.TypeEnseignement.TD: ecue.volume_td,
        InscriptionPedagogique.TypeEnseignement.TP: ecue.volume_tp,
    }
    dominant = max(volumes, key=lambda cle: volumes[cle])
    if volumes[dominant] <= 0:
        return InscriptionPedagogique.TypeEnseignement.AUTRE
    return dominant


@transaction.atomic
def generer_inscriptions_pedagogiques(inscription, semestre=None, groupe=None, acteur=None):
    """Crée les inscriptions pédagogiques d'une inscription administrative validée.

    Idempotent : les ECUE déjà rattachées ne sont ni recréées ni modifiées, ce
    qui permet de relancer la génération après une évolution de la maquette.
    """
    if not inscription.est_valide:
        raise PedagogieImpossible(
            'Les inscriptions pédagogiques nécessitent une inscription administrative validée. '
            f'Statut actuel : « {inscription.get_statut_display()} ».'
        )

    maquette = maquette_applicable(inscription)
    if maquette is None:
        raise PedagogieImpossible(
            'Aucune maquette active ne correspond à cette formation, ce niveau '
            'et cette année académique.'
        )

    ecues = ECUE.objects.filter(ue__maquette=maquette).select_related('ue', 'ue__semestre')
    if semestre is not None:
        ecues = ecues.filter(ue__semestre=semestre)
    if not ecues.exists():
        raise PedagogieImpossible('La maquette ne comporte aucune ECUE pour ce périmètre.')

    deja_inscrites = set(
        inscription.inscriptions_pedagogiques.values_list('ecue_id', flat=True)
    )

    creees = []
    for ecue in ecues:
        if ecue.id in deja_inscrites:
            continue
        ligne = InscriptionPedagogique(
            inscription=inscription,
            ecue=ecue,
            semestre=ecue.ue.semestre,
            groupe=groupe,
            type_enseignement=_type_enseignement_dominant(ecue),
            credits=ecue.credits,
            volume_horaire=ecue.volume_total,
            origine=InscriptionPedagogique.Origine.AUTOMATIQUE,
        )
        ligne.full_clean()
        creees.append(ligne)

    if creees:
        InscriptionPedagogique.objects.bulk_create(creees)

    journaliser(
        JournalScolarite.Action.INSCRIPTION_PEDAGOGIQUE_GENEREE,
        objet=inscription,
        acteur=acteur,
        nouvelle_valeur=str(len(creees)),
        extra={
            'maquette_id': maquette.id,
            'semestre_id': getattr(semestre, 'id', None),
            'groupe_id': getattr(groupe, 'id', None),
            'deja_presentes': len(deja_inscrites),
        },
    )
    return creees


@transaction.atomic
def ajouter_ecue(inscription, ecue, groupe=None, acteur=None, motif=''):
    """Ajoute manuellement une ECUE, en contrôlant son appartenance à la maquette."""
    if not inscription.est_valide:
        raise PedagogieImpossible(
            "L'inscription administrative doit être validée."
        )
    if inscription.inscriptions_pedagogiques.filter(ecue=ecue).exists():
        raise PedagogieImpossible(f'L’ECUE {ecue.code} est déjà rattachée à cette inscription.')

    maquette = maquette_applicable(inscription)
    if maquette is None or ecue.ue.maquette_id != maquette.id:
        raise PedagogieImpossible(
            f'L’ECUE {ecue.code} n’appartient pas à la maquette de cette inscription.'
        )

    ligne = InscriptionPedagogique(
        inscription=inscription,
        ecue=ecue,
        semestre=ecue.ue.semestre,
        groupe=groupe,
        type_enseignement=_type_enseignement_dominant(ecue),
        credits=ecue.credits,
        volume_horaire=ecue.volume_total,
        origine=InscriptionPedagogique.Origine.MANUELLE,
    )
    ligne.full_clean()
    ligne.save()

    journaliser(
        JournalScolarite.Action.INSCRIPTION_PEDAGOGIQUE_MANUELLE,
        objet=ligne,
        acteur=acteur,
        nouvelle_valeur=f'AJOUT {ecue.code}',
        commentaire=motif,
    )
    return ligne


@transaction.atomic
def retirer_ecue(ligne, acteur=None, motif=''):
    """Retire une ECUE d'une inscription pédagogique, avec traçabilité."""
    reference = f'{ligne.inscription.etudiant.matricule} / {ligne.ecue.code}'
    journaliser(
        JournalScolarite.Action.INSCRIPTION_PEDAGOGIQUE_MANUELLE,
        objet=ligne.inscription,
        acteur=acteur,
        ancienne_valeur=ligne.ecue.code,
        nouvelle_valeur=f'RETRAIT {ligne.ecue.code}',
        commentaire=motif,
        extra={'reference': reference, 'origine': ligne.origine},
    )
    ligne.delete()


def recapitulatif(inscription):
    """Synthèse par semestre : nombre d'ECUE, crédits et volume horaire."""
    lignes = inscription.inscriptions_pedagogiques.select_related('semestre', 'ecue')
    par_semestre = {}
    for ligne in lignes:
        entree = par_semestre.setdefault(ligne.semestre.libelle, {
            'semestre_id': ligne.semestre_id,
            'nb_ecues': 0,
            'credits': 0,
            'volume_horaire': 0,
        })
        entree['nb_ecues'] += 1
        entree['credits'] += ligne.credits
        entree['volume_horaire'] += float(ligne.volume_horaire)
    return {
        'total_ecues': lignes.count(),
        'total_credits': sum(e['credits'] for e in par_semestre.values()),
        'par_semestre': par_semestre,
    }
