"""Lecture conservatrice d'un calendrier académique daté (phase 2).

Ce module n'est pas raccordé à la génération ancienne. Ne planifie jamais
sans période COURS/EXAMENS validée, sourcée et fiable.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable


@dataclass(frozen=True)
class DecisionCalendrier:
    autorise: bool
    code: str
    semaine: int | None


def semaine_academique(annee, jour: date) -> int:
    """Blocs de 7 jours à partir du début de l'année (pas des semaines ISO)."""
    if not annee.date_debut or not annee.date_fin or not annee.date_debut <= jour <= annee.date_fin:
        raise ValueError('Date hors des bornes de l’année académique.')
    return 1 + (jour - annee.date_debut).days // 7


def dates_semaine(annee, numero: int) -> tuple[date, date]:
    """Renvoie la période inclusive, éventuellement incomplète à la fin."""
    if numero < 1:
        raise ValueError('Numéro de semaine invalide.')
    debut = annee.date_debut + timedelta(days=7 * (numero - 1))
    if debut > annee.date_fin:
        raise ValueError('Semaine au-delà de la fin de l’année.')
    return debut, min(debut + timedelta(days=6), annee.date_fin)


def _concerne(periode, groupe) -> bool:
    """Une période ciblée ne s'étend jamais silencieusement à d'autres groupes."""
    if periode.portee == 'GLOBAL':
        return True
    if groupe is None:
        return False
    return {
        'FORMATION': periode.formation_id == groupe.ref_formation_id,
        'NIVEAU': periode.niveau_id == groupe.niveau_id,
        'GROUPE': periode.groupe_id == groupe.pk,
    }.get(periode.portee, False)


def evaluer_periodes(annee, groupe, jour: date, nature: str,
                     periodes: Iterable, *, revision_numero: int) -> DecisionCalendrier:
    """Évalue des périodes préchargées ; aucune requête ou écriture SQL ici.

    Toute période pertinente non validée bloque conservativement le placement.
    Les jours fériés/fermetures validés priment sur toute ouverture.
    """
    try:
        semaine = semaine_academique(annee, jour)
    except ValueError:
        return DecisionCalendrier(False, 'DATE_HORS_ANNEE', None)
    if groupe is not None and groupe.annee_academique_id != annee.pk:
        return DecisionCalendrier(False, 'GROUPE_HORS_ANNEE', semaine)
    applicables = [p for p in periodes if p.actif and p.annee_academique_id == annee.pk
                   and p.revision.numero == revision_numero
                   and p.date_debut <= jour <= p.date_fin and _concerne(p, groupe)]
    if any(p.statut_validation != 'VALIDEE' or p.fiabilite != 'OFFICIEL'
           or not p.source_document.strip() for p in applicables):
        return DecisionCalendrier(False, 'CALENDRIER_NON_VALIDE', semaine)
    types = {p.type for p in applicables}
    if 'FERIE' in types or 'FERMETURE' in types:
        return DecisionCalendrier(False, 'JOUR_FERME', semaine)
    # Une exception VACANCES peut se superposer à COURS (elle bloque les
    # cours) ; si les deux ont même portée/cible, les données se contredisent.
    for p in applicables:
        if p.type in ('COURS', 'EXAMENS') and any(
            q.type == 'VACANCES' and q.portee == p.portee and
            q.formation_id == p.formation_id and q.niveau_id == p.niveau_id and
            q.groupe_id == p.groupe_id for q in applicables
        ):
            return DecisionCalendrier(False, 'CALENDRIER_AMBIGU', semaine)
    if 'VACANCES' in types:
        return DecisionCalendrier(False, 'VACANCES', semaine)
    if 'EXAMENS' in types:
        if 'COURS' in types:
            return DecisionCalendrier(False, 'CALENDRIER_AMBIGU', semaine)
        return DecisionCalendrier(nature == 'EVALUATION',
                                  'EXAMENS' if nature == 'EVALUATION' else 'PERIODE_EXAMENS',
                                  semaine)
    if 'COURS' in types:
        return DecisionCalendrier(nature != 'EVALUATION',
                                  'COURS' if nature != 'EVALUATION' else 'HORS_EXAMENS',
                                  semaine)
    return DecisionCalendrier(False, 'AUCUNE_PERIODE_VALIDEE', semaine)


def charger_periodes(annee_id: int, revision_numero: int, *, chunk_size: int = 256):
    """Lecture par lots depuis la version demandée ; rien n'est activé seul."""
    from edts.models import PeriodeAcademique

    queryset = (PeriodeAcademique.objects
                .filter(annee_academique_id=annee_id, revision__numero=revision_numero,
                        revision__annee_academique_id=annee_id)
                .select_related('revision').order_by('date_debut', 'pk'))
    return queryset.iterator(chunk_size=chunk_size)
