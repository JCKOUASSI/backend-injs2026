"""Services du lot L7 — Administration générale.

Toutes les transitions modifiant l'état d'un objet sont journalisées via
``scolarite.journaliser`` (best-effort, ne lève jamais).
"""
from django.utils import timezone

from scolarite.models import journaliser

from .models import Courrier, DocumentOfficiel, Mission, ReunionCommission, VersionDocument

# Actions de journal (harmonisées avec le socle)
ACTION_COURRIER_TRANSITION = 'ADMIN_COURRIER_TRANSITION'
ACTION_DOC_VERSION = 'ADMIN_DOC_VERSION'
ACTION_DOC_VALIDE = 'ADMIN_DOC_VALIDE'
ACTION_MISSION_VALIDEE = 'ADMIN_MISSION_VALIDEE'
ACTION_REUNION_PV = 'ADMIN_REUNION_PV'

COURRIER_TRANSITIONS = {
    Courrier.Statut.RECU: {Courrier.Statut.EN_COURS},
    Courrier.Statut.EN_COURS: {Courrier.Statut.REPONDU, Courrier.Statut.CLASSE},
    Courrier.Statut.REPONDU: {Courrier.Statut.CLASSE},
    Courrier.Statut.CLASSE: {Courrier.Statut.ARCHIVE},
    Courrier.Statut.ARCHIVE: set(),
}

DOCUMENT_TRANSITIONS = {
    DocumentOfficiel.Statut.BROUILLON: {DocumentOfficiel.Statut.EN_VALIDATION},
    DocumentOfficiel.Statut.EN_VALIDATION: {DocumentOfficiel.Statut.SIGNE, DocumentOfficiel.Statut.BROUILLON},
    DocumentOfficiel.Statut.SIGNE: {DocumentOfficiel.Statut.PUBLIE},
    DocumentOfficiel.Statut.PUBLIE: {DocumentOfficiel.Statut.ARCHIVE},
    DocumentOfficiel.Statut.ARCHIVE: set(),
}

REUNION_TRANSITIONS = {
    ReunionCommission.Statut.PLANIFIEE: {ReunionCommission.Statut.TENUE, ReunionCommission.Statut.ANNULEE},
    ReunionCommission.Statut.TENUE: {ReunionCommission.Statut.PV_EMIS},
    ReunionCommission.Statut.PV_EMIS: set(),
    ReunionCommission.Statut.ANNULEE: set(),
}

MISSION_TRANSITIONS = {
    Mission.Statut.PROPOSEE: {Mission.Statut.VALIDEE, Mission.Statut.REFUSEE, Mission.Statut.ANNULEE},
    Mission.Statut.VALIDEE: {Mission.Statut.EN_COURS, Mission.Statut.ANNULEE},
    Mission.Statut.EN_COURS: {Mission.Statut.TERMINEE},
    Mission.Statut.REFUSEE: set(),
    Mission.Statut.TERMINEE: set(),
    Mission.Statut.ANNULEE: set(),
}


def transitionner_courrier(courrier, statut, acteur=None):
    autorise = COURRIER_TRANSITIONS.get(courrier.statut, set())
    if statut not in autorise:
        raise ValueError(
            f"Transition {courrier.statut} → {statut} non autorisée pour un courrier."
        )
    courrier.statut = statut
    courrier.save(update_fields=['statut', 'updated_at'])
    journaliser(
        ACTION_COURRIER_TRANSITION,
        objet=courrier,
        acteur=acteur,
        ancienne_valeur=courrier.get_statut_display(),
        nouvelle_valeur=statut,
        commentaire=f'Courrier {courrier.reference}',
    )
    return courrier


def creer_version_document(document, contenu='', acteur=None):
    """Ajoute une version append-only au document (départ version 1)."""
    dernières = document.versions.order_by('-numero_version').first()
    numero = (dernières.numero_version + 1) if dernières else 1
    v = VersionDocument.objects.create(
        document=document, numero_version=numero, contenu=contenu, cree_par=acteur,
    )
    document.contenu = contenu
    document.save(update_fields=['contenu', 'updated_at'])
    journaliser(
        ACTION_DOC_VERSION,
        objet=document,
        acteur=acteur,
        commentaire=f'Version {numero}',
    )
    return v


def valider_document(document, acteur=None):
    """Signe un document (transition EN_VALIDATION → SIGNE)."""
    if document.statut != DocumentOfficiel.Statut.EN_VALIDATION:
        raise ValueError('Le document doit être en EN_VALIDATION pour être signé.')
    document.statut = DocumentOfficiel.Statut.SIGNE
    document.signe_par = acteur
    document.date_signature = timezone.now()
    document.save(update_fields=['statut', 'signe_par', 'date_signature', 'updated_at'])
    journaliser(
        ACTION_DOC_VALIDE,
        objet=document,
        acteur=acteur,
        commentaire=f'Signé par {acteur}',
    )
    return document


def transitionner_document(document, statut, acteur=None):
    autorise = DOCUMENT_TRANSITIONS.get(document.statut, set())
    if statut not in autorise:
        raise ValueError(
            f"Transition {document.statut} → {statut} non autorisée pour un document."
        )
    document.statut = statut
    document.save(update_fields=['statut', 'updated_at'])
    return document


def transitionner_reunion(reunion, statut, acteur=None):
    autorise = REUNION_TRANSITIONS.get(reunion.statut, set())
    if statut not in autorise:
        raise ValueError(
            f"Transition {reunion.statut} → {statut} non autorisée pour une réunion."
        )
    reunion.statut = statut
    reunion.save(update_fields=['statut', 'updated_at'])
    if statut == ReunionCommission.Statut.PV_EMIS:
        journaliser(ACTION_REUNION_PV, objet=reunion, acteur=acteur)
    return reunion


def transitionner_mission(mission, statut, acteur=None, motif_refus=''):
    autorise = MISSION_TRANSITIONS.get(mission.statut, set())
    if statut not in autorise:
        raise ValueError(f"Transition {mission.statut} → {statut} non autorisée pour une mission.")
    if statut == Mission.Statut.REFUSEE and not motif_refus.strip():
        raise ValueError('Un motif de refus est obligatoire.')
    mission.statut = statut
    if statut == Mission.Statut.REFUSEE:
        mission.motif_refus = motif_refus
    if statut == Mission.Statut.VALIDEE:
        mission.valide_par = acteur
    mission.save(update_fields=['statut', 'motif_refus', 'valide_par', 'updated_at'])
    journaliser(
        ACTION_MISSION_VALIDEE if statut == Mission.Statut.VALIDEE else 'ADMIN_MISSION_TRANSITION',
        objet=mission,
        acteur=acteur,
        ancienne_valeur='',
        nouvelle_valeur=statut,
        commentaire=motif_refus or '',
    )
    return mission