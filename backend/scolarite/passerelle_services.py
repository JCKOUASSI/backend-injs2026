"""Passerelle entre les inscriptions pédagogiques LMD et les modules opérationnels.

Cette passerelle est strictement additive. Elle **crée** des lignes
``formations.ModuleParticipant``, exactement comme le ferait une inscription
manuelle depuis les écrans existants. Elle n'en supprime jamais, ne modifie
aucun module et ne touche ni aux présences, ni aux notes, ni à la finance.

Le rapprochement se fait par ``RefModule`` : une ECUE porte un ``ref_module``,
un Module opérationnel porte le même. Sans ce lien, aucun rapprochement n'est
tenté et l'ECUE est signalée comme non rapprochée.
"""

from django.core.exceptions import ValidationError
from django.db import transaction

from formations.models import Module, ModuleParticipant

from .models import InscriptionPedagogique, JournalScolarite, journaliser


class PasserelleImpossible(ValidationError):
    """Le rapprochement demandé ne peut pas être réalisé."""


def analyser(inscription, formation):
    """Simule la passerelle sans rien écrire.

    Retourne le détail de ce qui serait créé, de ce qui existe déjà et de ce
    qui ne peut pas être rapproché.
    """
    ref_formation = inscription.ref_formation
    lignes = list(
        inscription.inscriptions_pedagogiques
        .select_related('ecue', 'ecue__ref_module', 'ecue__ue__maquette')
        .exclude(statut=InscriptionPedagogique.Statut.ABANDONNEE)
    )
    if any(
        ligne.ecue.ue.maquette.ref_formation_id != ref_formation.id
        for ligne in lignes
    ):
        raise PasserelleImpossible(
            'Une inscription pédagogique ne relève pas de la formation de '
            f'référence « {ref_formation} » de l’inscription administrative.'
        )

    ref_modules_attendus = {
        ligne.ecue.ref_module_id
        for ligne in lignes
        if ligne.ecue.ref_module_id
    }
    if ref_modules_attendus and not Module.objects.filter(
        formation=formation,
        ref_module_id__in=ref_modules_attendus,
    ).exists():
        raise PasserelleImpossible(
            f'La formation opérationnelle « {formation} » ne contient aucun module '
            f'correspondant à la formation de référence « {ref_formation} ».'
        )

    modules_par_ref = {}
    for module in (
        Module.objects
        .filter(
            formation=formation,
            ref_module_id__in=ref_modules_attendus,
        )
        .order_by('id')
    ):
        modules_par_ref.setdefault(module.ref_module_id, []).append(module)

    participant = inscription.etudiant.participant
    module_participants = {
        module_participant.module_id: module_participant
        for module_participant in (
            ModuleParticipant.objects
            .filter(participant=participant, module__formation=formation)
            .order_by('id')
        )
    }

    a_creer, a_lier, existantes, non_rapprochees, ambiguites = [], [], [], [], []
    for ligne in lignes:
        if not ligne.ecue.ref_module_id:
            non_rapprochees.append({
                'ecue': ligne.ecue.code,
                'motif': "L'ECUE n'est reliée à aucun module du référentiel.",
            })
            continue

        modules = modules_par_ref.get(ligne.ecue.ref_module_id, [])
        if not modules:
            non_rapprochees.append({
                'ecue': ligne.ecue.code,
                'motif': f'Aucun module de « {formation} » ne correspond à ce référentiel.',
            })
            continue
        if len(modules) > 1:
            ambiguites.append({
                'ecue': ligne.ecue.code,
                'ref_module_id': ligne.ecue.ref_module_id,
                'motif': (
                    f'Plusieurs modules de « {formation} » correspondent au même '
                    'module du référentiel.'
                ),
                'modules': [
                    {'id': module.id, 'intitule': module.intitule}
                    for module in modules
                ],
            })
            continue

        module = modules[0]
        module_participant = module_participants.get(module.id)
        if module_participant is not None:
            existantes.append({'ecue': ligne.ecue.code, 'module': module.intitule})
            if ligne.module_participant_id != module_participant.id:
                a_lier.append((ligne, module_participant))
            continue
        a_creer.append((ligne, module))

    return {
        'a_creer': a_creer,
        'a_lier': a_lier,
        'existantes': existantes,
        'non_rapprochees': non_rapprochees,
        'ambiguites': ambiguites,
    }


@transaction.atomic
def synchroniser(inscription, formation, acteur=None):
    """Crée les inscriptions aux modules opérationnels manquantes.

    Idempotent : relancer la synchronisation ne produit aucun doublon.
    """
    if not inscription.est_valide:
        raise PasserelleImpossible(
            "L'inscription administrative doit être validée avant toute synchronisation."
        )

    analyse = analyser(inscription, formation)
    participant = inscription.etudiant.participant

    for ligne, module_participant in analyse['a_lier']:
        ligne.module_participant = module_participant
        ligne.save(update_fields=['module_participant', 'updated_at'])

    creees = []
    for ligne, module in analyse['a_creer']:
        module_participant, cree = ModuleParticipant.objects.get_or_create(
            module=module, participant=participant,
        )
        if ligne.module_participant_id != module_participant.id:
            ligne.module_participant = module_participant
            ligne.save(update_fields=['module_participant', 'updated_at'])
        if cree:
            creees.append(module_participant)

    journaliser(
        JournalScolarite.Action.SYNCHRONISATION_EDT,
        objet=inscription,
        acteur=acteur,
        nouvelle_valeur=str(len(creees)),
        commentaire=f'Passerelle vers la formation « {formation} ».',
        extra={
            'formation_id': formation.id,
            'creees': len(creees),
            'existantes': len(analyse['existantes']),
            'non_rapprochees': len(analyse['non_rapprochees']),
            'ambiguites': len(analyse['ambiguites']),
        },
    )

    return {
        'creees': len(creees),
        'existantes': len(analyse['existantes']),
        'non_rapprochees': analyse['non_rapprochees'],
        'ambiguites': analyse['ambiguites'],
    }


def synchroniser_lot(inscriptions, formation, acteur=None):
    """Synchronise plusieurs inscriptions. Un échec isolé n'interrompt pas le lot."""
    resultats = {
        'inscriptions': 0,
        'creees': 0,
        'existantes': 0,
        'ambiguites': [],
        'echecs': [],
    }
    for inscription in inscriptions:
        try:
            resultat = synchroniser(inscription, formation, acteur=acteur)
        except PasserelleImpossible as erreur:
            resultats['echecs'].append({
                'inscription_id': inscription.id,
                'motif': erreur.messages[0],
            })
            continue
        resultats['inscriptions'] += 1
        resultats['creees'] += resultat['creees']
        resultats['existantes'] += resultat['existantes']
        if resultat['ambiguites']:
            resultats['ambiguites'].append({
                'inscription_id': inscription.id,
                'details': resultat['ambiguites'],
            })
    return resultats
