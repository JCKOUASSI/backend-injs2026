"""Tests de l'orchestrateur de planification groupe."""

import datetime

import pytest

from apps.formations.models import FormationModule
from apps.groupes.models import ConfigGroupe, Groupe, JourCours
from apps.seances.repositories import SeanceRepository
from apps.seances.planning.orchestrator import GroupePlanningOrchestrator
from apps.seances.services import PlanningService


def _creer_groupe_configure(formation, nom: str, jours: list[int]) -> Groupe:
    groupe = Groupe.objects.create(formation=formation, nom=nom, max_auditeurs=25)
    ConfigGroupe.objects.create(
        groupe=groupe,
        matin_actif=True,
        matin_heure_debut=datetime.time(8, 0),
        matin_heure_fin=datetime.time(12, 0),
        soir_actif=False,
        soir_heure_debut=datetime.time(13, 0),
        soir_heure_fin=datetime.time(17, 0),
    )
    for jour in jours:
        JourCours.objects.create(groupe=groupe, jour=jour)
    return groupe


@pytest.mark.django_db
def test_orchestrator_delegation_generer_pour_groupe(formation, module_referentiel, formateur_general_planning):
    """L'orchestrateur produit le même résultat que generer_pour_groupe via le service."""
    groupe = _creer_groupe_configure(formation, "ORCH-G1", jours=[0])
    FormationModule.objects.create(
        formation=formation,
        module=module_referentiel,
        volume_horaire=4,
        site_nom="Site A",
        batiment_nom="Bat A",
        salle_nom="Salle 101",
    )

    service = PlanningService(SeanceRepository())
    via_service = service.generer_pour_groupe(groupe.pk, dry_run=True)

    service2 = PlanningService(SeanceRepository())
    via_orchestrator = GroupePlanningOrchestrator(service2).executer(groupe.pk, dry_run=True, for_preview=False)

    assert len(via_orchestrator.seances) == len(via_service)
    assert via_orchestrator.preview_report is None
    assert via_orchestrator.echecs_modules == []
    assert via_orchestrator.seances[0].module_id == via_service[0].module_id
    assert via_orchestrator.seances[0].date == via_service[0].date


@pytest.mark.django_db
def test_orchestrator_preview_retourne_rapport(formation, module_referentiel, formateur_general_planning):
    """En mode preview, l'orchestrateur retourne un rapport diagnostic par module."""
    groupe = _creer_groupe_configure(formation, "ORCH-PREV", jours=[0])
    FormationModule.objects.create(
        formation=formation,
        module=module_referentiel,
        volume_horaire=4,
        site_nom="",
        batiment_nom="",
        salle_nom="",
        salle_nombre=0,
        date_debut=formation.date_debut,
        date_fin=formation.date_debut,
    )

    service = PlanningService(SeanceRepository())
    result = GroupePlanningOrchestrator(service).executer(groupe.pk, dry_run=True, for_preview=True)

    assert result.preview_report is not None
    assert len(result.preview_report) == 1
    assert result.preview_report[0]["heures_restantes"] > 0
    assert "aucune salle candidate" in (result.preview_report[0]["reason"] or "")
    assert result.echecs_modules == []

    seances_svc, report_svc = service.previsualiser_pour_groupe(groupe.pk)
    assert len(result.seances) == len(seances_svc)
    assert result.preview_report[0]["couverture"] == report_svc[0]["couverture"]
