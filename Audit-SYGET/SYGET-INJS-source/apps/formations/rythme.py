"""Règles de rythme mensuel pour la planification des modules."""

from __future__ import annotations

from apps.formations.models import Formation, FormationModule
from apps.groupes.models import Groupe


def rythme_mensuel_effectif_pour_module(groupe: Groupe, formation_module: FormationModule) -> str:
    """
    Rythme appliqué à un module lors de la planification :
    override groupe > rythme de la période du module > rythme de la formation.
    """
    rythme_groupe = (getattr(groupe, "rythme_mensuel", "") or "").strip()
    if rythme_groupe:
        return rythme_groupe

    periode = getattr(formation_module, "periode", None)
    if periode is not None:
        rythme_periode = (periode.rythme_mensuel or "").strip()
        if rythme_periode:
            return rythme_periode

    formation = getattr(formation_module, "formation", None) or groupe.formation
    return (getattr(formation, "rythme_mensuel", "") or "").strip() or Formation.RythmeMensuel.TOUT_LE_MOIS
