"""Affectation aux groupes pédagogiques et réinscription d'une année sur l'autre."""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import (
    AffectationGroupe,
    EvenementScolarite,
    Groupe,
    InscriptionAdministrative,
    JournalScolarite,
    journaliser,
)


class AffectationImpossible(ValidationError):
    """Le groupe demandé est incompatible ou saturé."""


class ReinscriptionImpossible(ValidationError):
    """La réinscription demandée est incompatible avec le dossier."""


def effectif_groupe(groupe):
    """Nombre d'étudiants actuellement affectés au groupe."""
    return AffectationGroupe.objects.filter(groupe=groupe, active=True).count()


def places_restantes(groupe):
    """Places disponibles, ou None si le groupe n'a pas de capacité définie."""
    if groupe.capacite_max is None:
        return None
    return max(groupe.capacite_max - effectif_groupe(groupe), 0)


def verifier_compatibilite(inscription, groupe):
    """Contrôle que le groupe correspond bien au périmètre de l'inscription."""
    if groupe.annee_academique_id != inscription.annee_academique_id:
        raise AffectationImpossible(
            "Le groupe n'appartient pas à la même année académique que l'inscription."
        )
    if groupe.ref_formation_id != inscription.ref_formation_id:
        raise AffectationImpossible("Le groupe n'appartient pas à la même formation.")
    if groupe.niveau_id != inscription.niveau_id:
        raise AffectationImpossible("Le groupe ne correspond pas au niveau de l'inscription.")
    if groupe.parcours_id and inscription.parcours_id and groupe.parcours_id != inscription.parcours_id:
        raise AffectationImpossible("Le groupe ne correspond pas au parcours de l'inscription.")
    if not groupe.actif:
        raise AffectationImpossible('Ce groupe est désactivé.')


@transaction.atomic
def affecter_groupe(inscription, groupe, acteur=None, motif='', ignorer_capacite=False):
    """Affecte une inscription à un groupe, en clôturant l'affectation précédente."""
    if not inscription.est_valide:
        raise AffectationImpossible(
            "L'inscription administrative doit être validée avant toute affectation."
        )
    verifier_compatibilite(inscription, groupe)

    restantes = places_restantes(groupe)
    if restantes == 0 and not ignorer_capacite:
        raise AffectationImpossible(
            f'Le groupe {groupe.nom} est complet ({groupe.capacite_max} places).'
        )

    precedente = inscription.affectations.filter(active=True).select_related('groupe').first()
    if precedente is not None and precedente.groupe_id == groupe.id:
        raise AffectationImpossible(f'L’étudiant est déjà affecté au groupe {groupe.nom}.')

    ancien_nom = ''
    if precedente is not None:
        ancien_nom = precedente.groupe.nom
        precedente.active = False
        precedente.date_fin = timezone.localdate()
        precedente.save(update_fields=['active', 'date_fin'])

    affectation = AffectationGroupe.objects.create(
        inscription=inscription,
        groupe=groupe,
        motif=motif,
        affecte_par=acteur if getattr(acteur, 'pk', None) else None,
    )

    # Les inscriptions pédagogiques suivent le groupe de l'étudiant.
    inscription.inscriptions_pedagogiques.update(groupe=groupe)

    changement = precedente is not None
    if changement:
        EvenementScolarite.objects.create(
            etudiant=inscription.etudiant,
            inscription=inscription,
            type_evenement=EvenementScolarite.Type.CHANGEMENT_GROUPE,
            ancienne_valeur=ancien_nom,
            nouvelle_valeur=groupe.nom,
            commentaire=motif,
            enregistre_par=acteur if getattr(acteur, 'pk', None) else None,
        )

    journaliser(
        JournalScolarite.Action.GROUPE_CHANGEMENT if changement
        else JournalScolarite.Action.GROUPE_AFFECTATION,
        objet=inscription,
        acteur=acteur,
        ancienne_valeur=ancien_nom,
        nouvelle_valeur=groupe.nom,
        commentaire=motif,
    )
    return affectation


@transaction.atomic
def retirer_du_groupe(inscription, acteur=None, motif=''):
    """Clôture l'affectation active sans en créer de nouvelle."""
    affectation = inscription.affectations.filter(active=True).select_related('groupe').first()
    if affectation is None:
        raise AffectationImpossible("Cette inscription n'est affectée à aucun groupe.")
    affectation.active = False
    affectation.date_fin = timezone.localdate()
    affectation.save(update_fields=['active', 'date_fin'])
    inscription.inscriptions_pedagogiques.update(groupe=None)

    journaliser(
        JournalScolarite.Action.GROUPE_CHANGEMENT,
        objet=inscription,
        acteur=acteur,
        ancienne_valeur=affectation.groupe.nom,
        nouvelle_valeur='',
        commentaire=motif,
    )
    return affectation


def repartir_automatiquement(inscriptions, groupes, acteur=None):
    """Répartit des inscriptions sur des groupes, en remplissant le moins chargé d'abord.

    Retourne le couple (affectations réalisées, échecs détaillés).
    """
    realisees, echecs = [], []
    for inscription in inscriptions:
        candidats = [
            groupe for groupe in groupes
            if groupe.actif
            and groupe.annee_academique_id == inscription.annee_academique_id
            and groupe.ref_formation_id == inscription.ref_formation_id
            and groupe.niveau_id == inscription.niveau_id
            and (places_restantes(groupe) is None or places_restantes(groupe) > 0)
        ]
        if not candidats:
            echecs.append({
                'inscription_id': inscription.id,
                'motif': 'Aucun groupe compatible avec de la place disponible.',
            })
            continue
        cible = min(candidats, key=effectif_groupe)
        try:
            realisees.append(affecter_groupe(inscription, cible, acteur=acteur,
                                             motif='Répartition automatique'))
        except AffectationImpossible as erreur:
            echecs.append({'inscription_id': inscription.id, 'motif': erreur.messages[0]})
    return realisees, echecs


# ── Réinscription ───────────────────────────────────────────────────────────

# Type de réinscription → événement de scolarité correspondant.
TYPE_VERS_EVENEMENT = {
    InscriptionAdministrative.Type.REINSCRIPTION: EvenementScolarite.Type.PASSAGE,
    InscriptionAdministrative.Type.REDOUBLEMENT: EvenementScolarite.Type.REDOUBLEMENT,
    InscriptionAdministrative.Type.REPRISE: EvenementScolarite.Type.REPRISE,
    InscriptionAdministrative.Type.REORIENTATION: EvenementScolarite.Type.REORIENTATION,
    InscriptionAdministrative.Type.TRANSFERT: EvenementScolarite.Type.TRANSFERT,
}


@transaction.atomic
def reinscrire(etudiant, annee_academique, niveau, acteur=None,
               type_inscription=InscriptionAdministrative.Type.REINSCRIPTION,
               valider=False, **surcharges):
    """Réinscrit un étudiant existant pour une nouvelle année, sans recréer son dossier."""
    from . import inscription_services

    if etudiant.statut and etudiant.statut.bloque_inscription:
        raise ReinscriptionImpossible(
            f'Le statut « {etudiant.statut.libelle} » interdit toute nouvelle inscription.'
        )

    precedente = (
        etudiant.inscriptions
        .filter(statut=InscriptionAdministrative.Statut.VALIDEE)
        .select_related('ref_formation', 'parcours', 'niveau')
        .order_by('-annee_academique__libelle')
        .first()
    )
    if precedente is None:
        raise ReinscriptionImpossible(
            "Aucune inscription validée antérieure : utilisez une première inscription."
        )
    if etudiant.inscriptions.filter(
        annee_academique=annee_academique,
        statut=InscriptionAdministrative.Statut.VALIDEE,
    ).exists():
        raise ReinscriptionImpossible(
            f'Cet étudiant a déjà une inscription validée pour {annee_academique}.'
        )

    champs = {
        'etudiant': etudiant,
        'annee_academique': annee_academique,
        'ref_formation': precedente.ref_formation,
        'parcours': precedente.parcours,
        'niveau': niveau,
        'vague': precedente.vague,
        'categorie': precedente.categorie,
        'grade': precedente.grade,
        'regime': precedente.regime,
        'statut_etudiant': precedente.statut_etudiant,
        'type_inscription': type_inscription,
    }
    champs.update({cle: valeur for cle, valeur in surcharges.items() if valeur is not None})

    inscription = InscriptionAdministrative(**champs)
    inscription.full_clean(exclude=['date_validation'])
    inscription.save()

    EvenementScolarite.objects.create(
        etudiant=etudiant,
        inscription=inscription,
        type_evenement=TYPE_VERS_EVENEMENT.get(
            type_inscription, EvenementScolarite.Type.PASSAGE,
        ),
        ancienne_valeur=f'{precedente.annee_academique} / {precedente.niveau.code}',
        nouvelle_valeur=f'{annee_academique} / {niveau.code}',
        enregistre_par=acteur if getattr(acteur, 'pk', None) else None,
    )

    journaliser(
        JournalScolarite.Action.REINSCRIPTION,
        objet=inscription,
        acteur=acteur,
        ancienne_valeur=f'{precedente.annee_academique} / {precedente.niveau.code}',
        nouvelle_valeur=f'{annee_academique} / {niveau.code}',
        extra={'type_inscription': type_inscription},
    )

    if valider:
        for statut in (
            InscriptionAdministrative.Statut.EN_ATTENTE,
            InscriptionAdministrative.Statut.A_VALIDER,
            InscriptionAdministrative.Statut.VALIDEE,
        ):
            inscription_services.appliquer_transition(inscription, statut, acteur=acteur)

    return inscription


@transaction.atomic
def enregistrer_evenement(etudiant, type_evenement, acteur=None, inscription=None, **champs):
    """Enregistre un événement de scolarité et le journalise."""
    evenement = EvenementScolarite.objects.create(
        etudiant=etudiant,
        inscription=inscription,
        type_evenement=type_evenement,
        enregistre_par=acteur if getattr(acteur, 'pk', None) else None,
        **champs,
    )
    journaliser(
        JournalScolarite.Action.EVENEMENT_SCOLARITE,
        objet=evenement,
        acteur=acteur,
        nouvelle_valeur=type_evenement,
        commentaire=champs.get('commentaire', ''),
    )
    return evenement
