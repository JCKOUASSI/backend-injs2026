"""Lot L1 — règles métier des présences.

Règle 1 : un étudiant ne peut être marqué présent que s'il est inscrit
dans le groupe (affectation LMD active) pour la séance considérée.

Principe de non-régression : la règle ne s'applique QUE lorsque la séance
est rattachée à la chaîne LMD (passerelle Module ↔ ECUE → maquette ACTIVE).
Les séances du socle opérationnel non rattachées restent inchangées.
"""
from scolarite.models import (
    AffectationGroupe,
    DossierEtudiant,
    ECUE,
    InscriptionAdministrative,
    Maquette,
)


def dossier_de_participant(participant):
    """Dossier étudiant LMD du participant (None si hors LMD)."""
    return DossierEtudiant.objects.filter(participant=participant).first()


def ecue_de_session(session):
    """ECUE LMD correspondant au module de la séance, via la passerelle."""
    ref_module = getattr(session.module, 'ref_module_id', None)
    if not ref_module:
        return None
    return ECUE.objects.filter(ref_module_id=ref_module).select_related('ue__maquette').first()


def maquette_active_pour_session(session, annee_academique):
    """Maquette ACTIVE couvrant la séance (année + formation + niveau)."""
    if not annee_academique:
        return None
    return Maquette.objects.filter(
        annee_academique=annee_academique,
        ref_formation=session.module.formation.ref_formation_id,
        niveau_id=session.module.niveau_id,
        statut=Maquette.Statut.ACTIVE,
    ).first()


def verifier_inscription_groupe(participant, session, groupe_lmd=None):
    """Règle 1 (lot L1) : présent seulement si inscrit dans le groupe.

    Retourne ``(True, '')`` si la présence est autorisée, ``(False, motif)``
    sinon. Ne s'applique que lorsque la chaîne LMD est identifiable :
    1. le module de la séance est rattaché à une ECUE (passerelle) dont la
       maquette est ACTIVE pour l'année ;
    2. l'étudiant a un dossier LMD et une inscription VALIDEE ;
    3. un groupe LMD est attendu (affectation active de l'étudiant) et la
       présence n'est pas prise dans ce groupe.
    """
    ecue = ecue_de_session(session)
    if ecue is None:
        return True, ''  # hors LMD : règle inapplicable, non bloquante

    dossier = dossier_de_participant(participant)
    if dossier is None:
        return False, 'Étudiant sans dossier LMD pour une séance LMD.'

    inscription = InscriptionAdministrative.objects.filter(
        etudiant=dossier,
        statut=InscriptionAdministrative.Statut.VALIDEE,
        annee_academique__courante=True,
    ).first()
    if inscription is None:
        return False, 'Aucune inscription validée pour l’année courante.'

    affectation = AffectationGroupe.objects.filter(
        inscription=inscription, active=True,
    ).select_related('groupe').first()

    if affectation is None:
        # Étudiant LMD sans groupe : présence tolérée (pas de groupe à
        # vérifier), à affiner au prompt 21 (réconciliation des groupes).
        return True, ''

    if groupe_lmd and affectation.groupe_id != groupe_lmd.pk:
        return False, (
            f'Étudiant affecté au groupe « {affectation.groupe.nom} » : '
            'présence hors groupe refusée.'
        )
    return True, ''