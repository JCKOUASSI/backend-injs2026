"""Tests du module planning.diagnostics."""

from __future__ import annotations

from collections import Counter

import pytest

from apps.seances.planning import diagnostics


@pytest.mark.parametrize(
    "diag,expected_fragment",
    [
        (Counter({"pas_de_salle_matin": 5, "pas_de_salle_soir": 3}), "pas_de_salle_matin_et_soir=8"),
        (Counter({"pas_formateur_matin": 2}), "pas_formateur_matin_et_soir=2"),
    ],
)
def test_raison_planning_avec_diag_agrege(diag, expected_fragment):
    out = diagnostics.raison_planning_avec_diag("cause initiale", diag)
    assert "cause initiale" in out
    assert expected_fragment in out


def test_diag_dominant_salles():
    diag = Counter({"pas_de_salle_matin": 10, "pas_formateur_matin": 2})
    max_val, at_max, buckets = diagnostics.diag_dominant_planning(diag)
    assert max_val == 10
    assert "salles" in at_max
    assert buckets["ps"] == 10


def test_raison_echec_aucune_minute_salles():
    diag = Counter({"pas_de_salle_matin": 5, "pas_de_salle_soir": 5})
    msg = diagnostics.raison_echec_planning_aucune_minute_placee(diag, ["S1"], None)
    assert "aucune salle libre" in msg
