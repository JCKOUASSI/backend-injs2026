"""Calculs de durée canoniques — source unique de vérité (règle SYGEP).

Règle métier :
- Toute durée de présence est bornée au créneau planifié de la séance
  (``heure_debut_prevue`` / ``heure_fin_prevue``).
- Un pointage sans sortie compte jusqu'à maintenant, borné de la même façon.
- Une durée n'est jamais négative.

Utilisé par ``Pointage.calculer_duree()``, le badgeage (``presences/views.py``),
les exports (``exports/views.py``) et la finance (``formations/api_views.py``).
La règle équivalente côté séance est ``formations.volume_horaire._session_realise_minutes``.
"""
from datetime import datetime, timedelta

from django.utils import timezone


def clamp_to_seance(ts, seance):
    """Borne un timestamp aux heures prévues de la séance.

    - Si ts est avant heure_debut_prevue → retourne heure_debut_prevue
    - Si ts est après heure_fin_prevue   → retourne heure_fin_prevue
    - Sinon retourne ts tel quel.
    """
    if ts is None or seance is None:
        return ts
    local_ts = timezone.localtime(ts)
    date = local_ts.date()
    tz = local_ts.tzinfo
    if seance.heure_debut_prevue and local_ts.time() < seance.heure_debut_prevue:
        return timezone.make_aware(datetime.combine(date, seance.heure_debut_prevue), tz)
    if seance.heure_fin_prevue and local_ts.time() > seance.heure_fin_prevue:
        return timezone.make_aware(datetime.combine(date, seance.heure_fin_prevue), tz)
    return ts


def pointage_bornes_clampees(pointage, *, now=None):
    """Retourne ``(entree, sortie, en_cours)`` clampées au créneau de la séance liée.

    Si le pointage est encore ouvert, la sortie vaut ``now`` (clampé).
    """
    seance = pointage.session
    entree = clamp_to_seance(pointage.timestamp_entree, seance)
    en_cours = pointage.timestamp_sortie is None
    sortie_raw = pointage.timestamp_sortie or now or timezone.now()
    sortie = clamp_to_seance(sortie_raw, seance)
    return entree, sortie, en_cours


def pointage_minutes_clampees(pointage, *, now=None):
    """Durée de présence (minutes) clampée au créneau planifié, jamais négative."""
    if not pointage.timestamp_entree:
        return 0.0
    entree, sortie, _ = pointage_bornes_clampees(pointage, now=now)
    return max(round((sortie - entree).total_seconds() / 60, 2), 0.0)


def rattrapage_creneau_timestamps(seance, *, offset_seconds=0):
    """Horodatages entrée/sortie pour présence forcée : durée planifiée de la séance.

    Règle métier : présence forcée = présent pour toute la durée de la séance
    (``heure_debut_prevue`` → ``heure_fin_prevue`` sur cette séance uniquement,
    pas le volume horaire total du module/cours).
    Aligné sur ``formations.volume_horaire._session_prevu_minutes``.
    """
    from formations.volume_horaire import _session_prevu_minutes

    tz = timezone.get_current_timezone()
    day = seance.date_journee

    if day and seance.heure_debut_prevue and seance.heure_fin_prevue:
        entree = timezone.make_aware(
            datetime.combine(day, seance.heure_debut_prevue), tz,
        ) + timedelta(seconds=offset_seconds)
        sortie = timezone.make_aware(
            datetime.combine(day, seance.heure_fin_prevue), tz,
        )
        return entree, sortie

    if seance.demarree_le and seance.terminee_le:
        entree = seance.demarree_le + timedelta(seconds=offset_seconds)
        return entree, seance.terminee_le

    entree = (seance.demarree_le or timezone.now()) + timedelta(seconds=offset_seconds)
    prevu_min = _session_prevu_minutes(seance)
    if prevu_min > 0:
        sortie = entree + timedelta(minutes=prevu_min)
    else:
        sortie = entree + timedelta(hours=4)
    return entree, sortie


def duree_minutes_effective(pointage, *, now=None):
    """Durée pour affichage / stats : recalcule depuis les timestamps (règle canonique).

    Utilisé quand ``duree_presence_minutes`` n'a pas été persistée (données historiques,
    clôtures partielles). Les absents forcés (``ABSENT_NON_BADGE``) restent à 0.
    """
    if not pointage.timestamp_entree:
        return 0.0
    if getattr(pointage, 'statut', None) == 'ABSENT_NON_BADGE':
        return 0.0
    return pointage_minutes_clampees(pointage, now=now)
