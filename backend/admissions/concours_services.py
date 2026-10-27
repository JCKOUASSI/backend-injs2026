"""Lot L2 — services métier des campagnes et du concours/sélection.

Toutes les décisions sont auditées via JournalScolarite (journaliser) et
toute correction de note conserve l'ancienne et la nouvelle valeur.
"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from scolarite.models import JournalScolarite, journaliser

from .models import (
    CampagneAdmission,
    Candidature,
    ClassementConcours,
    ConvocationEpreuve,
    Epreuve,
    NoteConcours,
)

S = CampagneAdmission.Statut

# Machine à états des campagnes.
TRANSITIONS_CAMPAGNE = {
    S.BROUILLON: {S.PLANIFIEE, S.ANNULEE},
    S.PLANIFIEE: {S.OUVERTE, S.ANNULEE},
    S.OUVERTE: {S.SUSPENDUE, S.CLOTUREE},
    S.SUSPENDUE: {S.OUVERTE, S.CLOTUREE},
    S.CLOTUREE: {S.ARCHIVEE},
    S.ANNULEE: set(),
    S.ARCHIVEE: set(),
}


class CampagneFermee(ValidationError):
    """La campagne n'accepte pas de candidature."""


def appliquer_transition_campagne(campagne, nouveau_statut, acteur=None, commentaire=''):
    """Applique une transition de statut de campagne validée, journalisée."""
    if nouveau_statut == campagne.statut:
        raise ValidationError(f'La campagne est déjà « {campagne.get_statut_display()} ».')
    autorises = TRANSITIONS_CAMPAGNE.get(campagne.statut, set())
    if nouveau_statut not in autorises:
        raise ValidationError(
            f'Transition interdite : « {campagne.get_statut_display()} » ne peut pas '
            f'passer à « {S(nouveau_statut).label} ».'
        )
    ancien = campagne.statut
    campagne.statut = nouveau_statut
    campagne.save(update_fields=['statut', 'updated_at'])
    journaliser(
        JournalScolarite.Action.CAMPAGNE_TRANSITION,
        objet=campagne,
        acteur=acteur,
        ancienne_valeur=ancien,
        nouvelle_valeur=nouveau_statut,
        commentaire=commentaire,
    )
    return campagne


def candidatures_convoquables(campagne):
    """Candidatures de la campagne dont le dossier est engagé (au-delà de la soumission)."""
    statuts_convoquables = {
        Candidature.Statut.EN_ATTENTE_DE_VERIFICATION,
        Candidature.Statut.PIECES_INCOMPLETES,
        Candidature.Statut.PIECES_VALIDEES,
        Candidature.Statut.EN_ETUDE,
        Candidature.Statut.ADMISSIBLE,
        Candidature.Statut.LISTE_ATTENTE,
    }
    return campagne.candidatures.filter(statut__in=statuts_convoquables).order_by('numero')


@transaction.atomic
def generer_convocations(epreuve, utilisateur=None):
    """Convoque les candidatures convoquables de la campagne pour une épreuve.

    Respecte la capacité de la salle (règle L2) ; retourne le nombre de
    convocations créées. Opération journalisée.
    """
    if epreuve.campagne.statut in (S.CLOTUREE, S.ANNULEE, S.ARCHIVEE):
        raise ValidationError('Campagne clôturée : convocations impossible.')
    deja = set(
        ConvocationEpreuve.objects.filter(epreuve=epreuve)
        .values_list('candidature_id', flat=True)
    )
    capacite = epreuve.salle.capacite if (epreuve.salle and epreuve.salle.capacite) else None
    crees = 0
    for candidature in candidatures_convoquables(epreuve.campagne):
        if candidature.pk in deja:
            continue
        if capacite is not None and len(deja) + crees >= capacite:
            break
        ConvocationEpreuve.objects.create(epreuve=epreuve, candidature=candidature)
        crees += 1
    journaliser(
        JournalScolarite.Action.CONCOURS_CONVOCATIONS,
        objet=epreuve,
        acteur=utilisateur,
        nouvelle_valeur=str(crees),
        extra={'campagne_id': epreuve.campagne_id, 'capacite': capacite},
    )
    return crees


def enregistrer_note(epreuve, candidature, utilisateur=None, note=None, absent=False):
    """Crée ou met à jour la note d'une candidature à une épreuve.

    Refuse toute écriture sur une épreuve verrouillée. Toute correction
    passe par NoteConcoursHistorique (ancienne + nouvelle valeur) et est
    journalisée.
    """
    if epreuve.verrouillee:
        raise ValidationError(
            f'Épreuve « {epreuve} » verrouillée : les résultats ne sont plus modifiables.'
        )
    if absent:
        note = None
    ancienne = NoteConcours.objects.filter(epreuve=epreuve, candidature=candidature).first()
    note_obj, _ = NoteConcours.objects.update_or_create(
        epreuve=epreuve, candidature=candidature,
        defaults={'note': note, 'absent': absent},
    )
    if ancienne and ancienne.note != note_obj.note:
        # L'historique est créé par NoteConcours.save() ; on journalise ici.
        historique = note_obj.historique.first()
        if historique:
            historique.modifie_par = utilisateur
            historique.save(update_fields=['modifie_par'])
        journaliser(
            JournalScolarite.Action.CONCOURS_NOTE_CORRIGEE,
            objet=note_obj,
            acteur=utilisateur,
            ancienne_valeur=str(ancienne.note),
            nouvelle_valeur=str(note_obj.note),
        )
    return note_obj


def verrouiller_epreuve(epreuve, utilisateur=None):
    """Verrouille les résultats d'une épreuve — irréversible."""
    epreuve.verrouillee = True
    epreuve.save(update_fields=['verrouillee', 'updated_at'])
    journaliser(
        JournalScolarite.Action.CONCOURS_EPREUVE_VERROUILLEE,
        objet=epreuve,
        acteur=utilisateur,
        nouvelle_valeur='verrouillée',
    )
    return epreuve


def calculer_classement(campagne, utilisateur=None):
    """Calcule et applique le classement d'une campagne — reproductible.

    Score = Σ (note × coefficient de l'épreuve). Rang par score décroissant ;
    listes : ADMISSIBLE (jusqu'au quota), LISTE_ATTENTE (jusqu'au cumul des
    quotas), sinon NON_ADMIS. Un classement déjà publié n'est pas recalculé.
    """
    if ClassementConcours.objects.filter(campagne=campagne, publie=True).exists():
        raise ValidationError(
            'Le classement de cette campagne est publié : recalcul impossible.'
        )
    epreuves = list(campagne.epreuves.all())
    if not epreuves:
        raise ValidationError('Aucune épreuve définie pour cette campagne.')

    scores = {}
    for candidature in campagne.candidatures.all():
        total = Decimal('0')
        notee = False
        for epreuve in epreuves:
            note = NoteConcours.objects.filter(
                epreuve=epreuve, candidature=candidature,
            ).first()
            if note and not note.absent and note.note is not None:
                total += note.note * epreuve.coefficient
                notee = True
        if notee:
            scores[candidature] = total

    ClassementConcours.objects.filter(campagne=campagne).delete()

    quota_admissibles = campagne.quota_admissibles
    quota_total = None
    if campagne.quota_admis is not None:
        quota_total = (quota_admissibles or 0) + campagne.quota_admis
    if quota_admissibles is None and quota_total is None:
        # Sans quotas : tous les candidats notés sont admissibles.
        quota_admissibles = len(scores)

    tries = sorted(scores.items(), key=lambda item: (-item[1], item[0].numero))
    lignes = []
    for rang, (candidature, total) in enumerate(tries, start=1):
        if quota_admissibles is not None and rang <= quota_admissibles:
            liste = ClassementConcours.Liste.ADMISSIBLE
        elif quota_total is not None and rang <= quota_total:
            liste = ClassementConcours.Liste.LISTE_ATTENTE
        else:
            liste = ClassementConcours.Liste.NON_ADMIS
        lignes.append(ClassementConcours(
            campagne=campagne, candidature=candidature, rang=rang,
            score_total=total, liste=liste, genere_par=utilisateur,
        ))
    ClassementConcours.objects.bulk_create(lignes)
    journaliser(
        JournalScolarite.Action.CONCOURS_CLASSEMENT_CALCULE,
        objet=campagne,
        acteur=utilisateur,
        nouvelle_valeur=str(len(lignes)),
        extra={'reproductible': True},
    )
    return list(
        ClassementConcours.objects.filter(campagne=campagne).select_related('candidature')
    )


def publier_classement(campagne, utilisateur=None):
    """Publie le classement (listes d'admissibilité) — plus de recalcul ensuite."""
    if not ClassementConcours.objects.filter(campagne=campagne).exists():
        raise ValidationError('Aucun classement calculé : calculez-le avant publication.')
    ClassementConcours.objects.filter(campagne=campagne).update(publie=True)
    journaliser(
        JournalScolarite.Action.CONCOURS_CLASSEMENT_PUBLIE,
        objet=campagne,
        acteur=utilisateur,
        nouvelle_valeur='publié',
    )
    return ClassementConcours.objects.filter(campagne=campagne).order_by('rang')
