"""Services du lot L7 — Patrimoine.

Validation des réservations d'espaces, suivi des maintenances et
enregistrement des mouvements patrimoniaux (append-only).
"""
from scolarite.models import journaliser

from .models import Maintenance, MouvementPatrimonial, ReservationEspace

ACTION_MAINTENANCE = 'PATRIMOINE_MAINTENANCE'
ACTION_RESERVATION = 'PATRIMOINE_RESERVATION'
ACTION_MOUVEMENT = 'PATRIMOINE_MOUVEMENT'

RESERVATION_TRANSITIONS = {
    ReservationEspace.Statut.PROVISOIRE: {
        ReservationEspace.Statut.VALIDEE,
        ReservationEspace.Statut.REFUSEE,
        ReservationEspace.Statut.ANNULEE,
    },
    ReservationEspace.Statut.VALIDEE: {ReservationEspace.Statut.ANNULEE},
}

MAINTENANCE_TRANSITIONS = {
    Maintenance.Statut.PLANIFIEE: {Maintenance.Statut.EN_COURS, Maintenance.Statut.ANNULEE},
    Maintenance.Statut.EN_COURS: {Maintenance.Statut.TERMINEE, Maintenance.Statut.ANNULEE},
}


def valider_reservation(reservation, valide_par, statut=ReservationEspace.Statut.VALIDEE, acteur=None):
    """Valide ou refuse une réservation (validation obligatoire)."""
    if statut not in RESERVATION_TRANSITIONS.get(reservation.statut, set()):
        raise ValueError(f"Transition {reservation.statut} → {statut} non autorisée.")
    reservation.statut = statut
    reservation.valide_par = valide_par
    reservation.save(update_fields=['statut', 'valide_par', 'updated_at'])
    journaliser(
        ACTION_RESERVATION, objet=reservation, acteur=acteur,
        ancienne_valeur=reservation.get_statut_display(), nouvelle_valeur=statut,
    )
    return reservation


def transitionner_maintenance(maintenance, statut, acteur=None):
    if statut not in MAINTENANCE_TRANSITIONS.get(maintenance.statut, set()):
        raise ValueError(f"Transition {maintenance.statut} → {statut} non autorisée.")
    maintenance.statut = statut
    maintenance.save(update_fields=['statut', 'updated_at'])
    journaliser(
        ACTION_MAINTENANCE, objet=maintenance, acteur=acteur,
        nouvelle_valeur=statut,
    )
    return maintenance


def tracer_mouvement(type_mouvement, equipement=None, vehicule=None, acteur=None,
                     detail='', anciennev=None, nouvelle=None):
    """Enregistre un mouvement patrimonial (append-only)."""
    if equipement is None and vehicule is None:
        raise ValueError('Un équipement ou un véhicule est requis.')
    m = MouvementPatrimonial.objects.create(
        equipement=equipement, vehicule=vehicule, type_mouvement=type_mouvement,
        detail=detail, ancienne_valeur=anciennev or {}, nouvelle_valeur=nouvelle or {},
        acteur=acteur,
    )
    journaliser(ACTION_MOUVEMENT, objet=m, acteur=acteur, commentaire=detail)
    return m