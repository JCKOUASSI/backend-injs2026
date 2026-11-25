"""Contraintes temporelles pour la génération de planning."""

from __future__ import annotations

import datetime
from typing import Optional

from apps.seances.models import Seance


def formations_periodes_se_chevauchent(
    a_debut: datetime.date,
    a_fin: datetime.date,
    b_debut: datetime.date,
    b_fin: datetime.date,
) -> bool:
    return a_debut <= b_fin and b_debut <= a_fin


def planning_not_before_datetime(formation_id: int) -> Optional[datetime.datetime]:
    """
    Instant strict après lequel la première séance peut commencer : fin de la
    dernière séance existante parmi les formations prioritaires dont la période
    chevauche celle de la formation courante. None si aucune contrainte.
    """
    from apps.formations.models import Formation

    formation = Formation.objects.filter(pk=formation_id).only("date_debut", "date_fin", "pk").first()
    if formation is None:
        return None
    cle_tri = (formation.date_debut, formation.pk)

    overlapping_ids: list[int] = []
    for autre in Formation.objects.exclude(pk=formation_id).only("date_debut", "date_fin", "pk"):
        if (autre.date_debut, autre.pk) >= cle_tri:
            continue
        if not formations_periodes_se_chevauchent(
            formation.date_debut,
            formation.date_fin,
            autre.date_debut,
            autre.date_fin,
        ):
            continue
        overlapping_ids.append(autre.pk)

    if not overlapping_ids:
        return None

    fins: list[datetime.datetime] = []
    seen: set[int] = set()
    seances = (
        Seance.objects.filter(groupe__formation_id__in=overlapping_ids)
        .select_related("groupe")
        .order_by("groupe__formation_id", "-date", "-heure_fin", "-heure_debut", "-pk")
    )
    for seance in seances:
        fid = seance.groupe.formation_id
        if fid in seen:
            continue
        seen.add(fid)
        fins.append(datetime.datetime.combine(seance.date, seance.heure_fin))
    return max(fins) if fins else None
