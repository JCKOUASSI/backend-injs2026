"""Sérialisation des scénarios de simulation."""

from __future__ import annotations

import datetime
import math
from typing import Any


def _serialize_value(value: Any) -> Any:
    if isinstance(value, datetime.date):
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [_serialize_value(v) for v in value]
    return value


def serialize_formset_payload(cleaned_rows: list[dict]) -> list[dict]:
    """Convertit les cleaned_data du formset en JSON stockable."""
    out: list[dict] = []
    for row in cleaned_rows:
        serialized = {k: _serialize_value(v) for k, v in row.items()}
        if serialized.get("jours_semaine"):
            serialized["jours_semaine"] = [str(j) for j in serialized["jours_semaine"]]
        out.append(serialized)
    return out


def _normaliser_ligne_scenario(row: dict) -> dict:
    """Compatibilité scénarios enregistrés avant le passage « auditeurs par groupe »."""
    initial = dict(row)
    if "nb_groupes" not in initial and initial.get("nb_auditeurs") is not None:
        cap = max(1, int(initial.get("capacite_groupe") or 25))
        total = max(1, int(initial["nb_auditeurs"]))
        initial["nb_groupes"] = max(1, math.ceil(total / cap))
        if initial["nb_groupes"] == 1:
            initial["capacite_groupe"] = total
    initial.pop("nb_auditeurs", None)
    return initial


def deserialize_formset_initial(payload: list[dict]) -> list[dict]:
    """Reconstruit les initial data pour SimulationFormationFormSet."""
    initials: list[dict] = []
    for row in payload:
        initial = _normaliser_ligne_scenario(row)
        for key in ("date_debut", "date_fin"):
            if initial.get(key):
                initial[key] = datetime.date.fromisoformat(str(initial[key]))
        if initial.get("jours_semaine"):
            initial["jours_semaine"] = [str(j) for j in initial["jours_semaine"]]
        initials.append(initial)
    return initials
