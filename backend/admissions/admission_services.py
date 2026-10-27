"""Services métier des admissions : création depuis une candidature et décisions.

L'admission est une entité distincte de la candidature : elle porte la décision
officielle et ses conditions (référence, date limite d'inscription, catégorie,
grade), et c'est elle qui autorise ou non la création d'une inscription.
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from scolarite.models import JournalScolarite, journaliser

from . import workflow
from .models import Admission, Candidature

# Décision d'admission → statut de candidature correspondant.
DECISION_VERS_STATUT_CANDIDATURE = {
    Admission.Decision.ADMIS: Candidature.Statut.ADMIS,
    Admission.Decision.ADMIS_SOUS_RESERVE: Candidature.Statut.ADMIS_SOUS_RESERVE,
    Admission.Decision.REFUSEE: Candidature.Statut.REFUSE,
    Admission.Decision.EN_ATTENTE: Candidature.Statut.LISTE_ATTENTE,
    Admission.Decision.ANNULEE: Candidature.Statut.ANNULE,
}

# Une admission ne peut être ouverte que depuis ces statuts de candidature.
STATUTS_CANDIDATURE_ELIGIBLES = {
    Candidature.Statut.EN_ETUDE,
    Candidature.Statut.ADMISSIBLE,
    Candidature.Statut.LISTE_ATTENTE,
}


class AdmissionImpossible(ValidationError):
    """L'opération demandée est incompatible avec l'état du dossier."""


def verifier_eligibilite(candidature):
    """Vérifie qu'une candidature peut donner lieu à une admission."""
    if hasattr(candidature, 'admission'):
        raise AdmissionImpossible('Une admission existe déjà pour cette candidature.')
    if candidature.statut not in STATUTS_CANDIDATURE_ELIGIBLES:
        raise AdmissionImpossible(
            f'Une admission ne peut être ouverte que depuis les statuts '
            f'{", ".join(sorted(STATUTS_CANDIDATURE_ELIGIBLES))}. '
            f'Statut actuel : « {candidature.get_statut_display()} ».'
        )


@transaction.atomic
def creer_admission(candidature, acteur=None, **champs):
    """Ouvre une admission à partir d'une candidature éligible.

    Les caractéristiques académiques sont reprises de la candidature et peuvent
    être surchargées (un candidat peut être admis à un niveau différent de celui
    demandé).
    """
    verifier_eligibilite(candidature)

    defaut = {
        'candidat': candidature.candidat,
        'annee_academique': candidature.annee_academique,
        'ref_formation': candidature.ref_formation,
        'parcours': candidature.parcours,
        'niveau': candidature.niveau,
        'vague': candidature.vague,
        'voie_acces': candidature.voie_acces,
    }
    defaut.update({cle: valeur for cle, valeur in champs.items() if valeur is not None})

    admission = Admission(candidature=candidature, **defaut)
    admission.full_clean(exclude=['date_decision'])
    admission.save()

    journaliser(
        JournalScolarite.Action.ADMISSION_CREEE,
        objet=admission,
        acteur=acteur,
        nouvelle_valeur=admission.decision,
        extra={'candidature': candidature.numero},
    )
    return admission


@transaction.atomic
def prononcer_decision(admission, decision, acteur=None, reference='', date_limite=None,
                       observations='', forcer_dossier=False):
    """Enregistre la décision d'admission et aligne le statut de la candidature.

    L'alignement passe par la machine à états de la candidature : si la
    transition est interdite, la décision est refusée dans son ensemble.
    """
    if decision not in Admission.Decision.values:
        raise AdmissionImpossible(f'Décision inconnue : {decision}.')
    if admission.decision == decision:
        raise AdmissionImpossible(
            f'L\'admission porte déjà la décision « {admission.get_decision_display()} ».'
        )

    ancienne = admission.decision
    admission.decision = decision
    admission.date_decision = timezone.now()
    admission.decide_par = acteur if getattr(acteur, 'pk', None) else None
    if reference:
        admission.reference_decision = reference
    if date_limite is not None:
        admission.date_limite_inscription = date_limite
    if observations:
        admission.observations = observations
    admission.full_clean()
    admission.save()

    statut_cible = DECISION_VERS_STATUT_CANDIDATURE[decision]
    candidature = admission.candidature
    if candidature.statut != statut_cible:
        workflow.appliquer_transition(
            candidature,
            statut_cible,
            acteur=acteur,
            commentaire=f'Décision d’admission : {admission.get_decision_display()}.',
            forcer_dossier=forcer_dossier,
        )

    journaliser(
        JournalScolarite.Action.ADMISSION_DECISION,
        objet=admission,
        acteur=acteur,
        ancienne_valeur=ancienne,
        nouvelle_valeur=decision,
        commentaire=observations,
        extra={'reference': admission.reference_decision},
    )
    return admission


@transaction.atomic
def annuler_admission(admission, acteur=None, motif=''):
    """Annule une admission et la candidature associée."""
    if admission.decision == Admission.Decision.ANNULEE:
        raise AdmissionImpossible('Cette admission est déjà annulée.')

    ancienne = admission.decision
    admission.decision = Admission.Decision.ANNULEE
    admission.date_decision = timezone.now()
    admission.decide_par = acteur if getattr(acteur, 'pk', None) else None
    admission.observations = motif or admission.observations
    admission.save()

    candidature = admission.candidature
    if candidature.statut != Candidature.Statut.ANNULE:
        workflow.appliquer_transition(
            candidature, Candidature.Statut.ANNULE, acteur=acteur,
            commentaire=motif or 'Annulation de l’admission.',
        )

    journaliser(
        JournalScolarite.Action.ADMISSION_ANNULEE,
        objet=admission,
        acteur=acteur,
        ancienne_valeur=ancienne,
        nouvelle_valeur=Admission.Decision.ANNULEE,
        commentaire=motif,
    )
    return admission
