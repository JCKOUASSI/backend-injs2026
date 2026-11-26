"""
Tests du service de génération du planning.
"""

import datetime

import pytest

from apps.formations.models import FormationModule
from apps.groupes.models import ConfigGroupe, Groupe, GroupeAuditeur, JourCours
from apps.referentiels.models import Module
from apps.seances.models import Seance
from apps.seances.repositories import SeanceRepository
from apps.seances.services import PlanningService


def _creer_groupe_configure(formation, nom: str, jours: list[int]) -> Groupe:
    """Crée un groupe avec une configuration horaire simple et les jours actifs demandés."""
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
class TestPlanningServiceDatesModules:
    """Vérifie la logique de dates module vs formation."""

    def test_module_sans_dates_utilise_fenetre_formation(
        self, formation, module_referentiel, formateur_general_planning
    ):
        """
        Si le module n'a pas de date début/fin, la fenêtre de la formation est utilisée.
        """
        groupe = _creer_groupe_configure(formation, "G1", jours=[0])  # lundi
        FormationModule.objects.create(
            formation=formation,
            module=module_referentiel,
            volume_horaire=4,
            site_nom="Site A",
            batiment_nom="Bat A",
            salle_nom="Salle 101",
            date_debut=None,
            date_fin=None,
        )

        seances = PlanningService(SeanceRepository()).generer_pour_groupe(groupe.pk)

        assert len(seances) == 1
        assert seances[0].date == formation.date_debut

    def test_module_avec_dates_priorise_fenetre_module(self, formation, module_referentiel, formateur_general_planning):
        """
        Si le module a des dates définies, elles sont utilisées à la place de celles de la formation.
        """
        from tests.conftest import configurer_periode_principale

        groupe = _creer_groupe_configure(formation, "G2", jours=[0, 2])  # lundi + mercredi
        date_module = datetime.date(2025, 1, 8)  # mercredi

        configurer_periode_principale(formation, date_debut=date_module, date_fin=date_module)
        FormationModule.objects.create(
            formation=formation,
            module=module_referentiel,
            volume_horaire=4,
            site_nom="Site A",
            batiment_nom="Bat A",
            salle_nom="Salle 101",
        )

        seances = PlanningService(SeanceRepository()).generer_pour_groupe(groupe.pk)

        assert len(seances) == 1
        assert seances[0].date == date_module

    def test_module_grade_cible_filtre_selon_grade_du_groupe(
        self, formation, auditeur, specialite_generale, formateur_general_planning
    ):
        """
        Seuls les modules dont le grade_cible correspond au grade principal du groupe
        sont planifiés.
        """
        groupe = _creer_groupe_configure(formation, "G3", jours=[0])  # lundi
        GroupeAuditeur.objects.create(groupe=groupe, auditeur=auditeur)  # grade A3

        module_a3 = Module.objects.create(titre="Module A3", specialite=specialite_generale)
        module_b = Module.objects.create(titre="Module B", specialite=specialite_generale)

        FormationModule.objects.create(
            formation=formation,
            module=module_a3,
            volume_horaire=4,
            grade_cible="A3",
            site_nom="Site A",
            batiment_nom="Bat A",
            salle_nom="Salle 101",
        )
        FormationModule.objects.create(
            formation=formation,
            module=module_b,
            volume_horaire=4,
            grade_cible="B",
            site_nom="Site A",
            batiment_nom="Bat A",
            salle_nom="Salle 101",
        )

        seances = PlanningService(SeanceRepository()).generer_pour_groupe(groupe.pk)

        assert len(seances) == 1
        assert seances[0].module.titre == "Module A3"

    def test_module_grade_parent_couvre_grade_detail_groupe(
        self, formation, specialite_generale, formateur_general_planning
    ):
        """Un module ciblé sur B doit s'appliquer à un groupe de grade B3."""
        from apps.auditeurs.models import Auditeur

        groupe = _creer_groupe_configure(formation, "G4", jours=[0])  # lundi
        auditeur_b3 = Auditeur.objects.create(
            nom="TEST",
            prenom="B3",
            matricule="PLNB30001",
            grade="B3",
            genre="M",
            categorie="B",
        )
        GroupeAuditeur.objects.create(groupe=groupe, auditeur=auditeur_b3)

        module_b = Module.objects.create(titre="Module B Parent", specialite=specialite_generale)
        FormationModule.objects.create(
            formation=formation,
            module=module_b,
            volume_horaire=4,
            grade_cible="B",
            site_nom="Site A",
            batiment_nom="Bat A",
            salle_nom="Salle 101",
        )

        seances = PlanningService(SeanceRepository()).generer_pour_groupe(groupe.pk)

        assert len(seances) == 1
        assert seances[0].module.titre == "Module B Parent"

    def test_module_sans_batiment_salle_dispatch_choisit_salle_par_site(
        self, formation, module_referentiel, formateur_general_planning
    ):
        """Sans bâtiment/salle explicites, le planning prend toutes les salles actives du site.
        Le bâtiment N'EST PAS réécrit sur le FormationModule pour ne pas réduire le pool
        lors des regénérations suivantes."""
        from apps.parametrage.models import Batiment, Salle, Site

        groupe = _creer_groupe_configure(formation, "G-SITE", jours=[0])  # lundi
        site_ok = Site.objects.create(nom="SITE-OK", actif=True)
        bat_ok = Batiment.objects.create(site=site_ok, nom="BAT-OK", actif=True)
        Salle.objects.create(batiment=bat_ok, nom="SALLE-OK", capacite_max=30, actif=True)
        # Salle hors site (ne doit pas être choisie).
        site_other = Site.objects.create(nom="SITE-OTHER", actif=True)
        bat_other = Batiment.objects.create(site=site_other, nom="BAT-OTHER", actif=True)
        Salle.objects.create(batiment=bat_other, nom="SALLE-OTHER", capacite_max=30, actif=True)

        FormationModule.objects.create(
            formation=formation,
            module=module_referentiel,
            volume_horaire=4,
            site_nom="SITE-OK",
            batiment_nom="",
            salle_nom="",
            date_debut=formation.date_debut,
            date_fin=formation.date_debut,
        )

        seances = PlanningService(SeanceRepository()).generer_pour_groupe(groupe.pk)
        assert len(seances) == 1
        assert seances[0].salle_nom == "SALLE-OK"
        fm = FormationModule.objects.get(formation=formation, module=module_referentiel)
        # Le bâtiment et la salle ne sont pas réécrits sur le FormationModule
        # afin de préserver le pool complet du site lors des regénérations.
        assert not (fm.batiment_nom or "").strip()
        assert not (fm.salle_nom or "").strip()
        assert fm.salle_nombre == 0

    def test_site_disponible_uniquement_dans_periodes_configurees(
        self, formation, module_referentiel, formateur_general_planning
    ):
        """Les salles d'un site ne sont planifiables que dans ses périodes de disponibilité."""
        from apps.parametrage.models import Batiment, PeriodeDisponibiliteSite, Salle, Site

        groupe = _creer_groupe_configure(formation, "G-PERIODE-SITE", jours=[0])
        site = Site.objects.create(nom="SITE-PER", actif=True)
        bat = Batiment.objects.create(site=site, nom="BAT-PER", actif=True)
        Salle.objects.create(batiment=bat, nom="SALLE-PER", capacite_max=30, actif=True)

        PeriodeDisponibiliteSite.objects.create(
            site=site,
            date_debut=datetime.date(2025, 3, 1),
            date_fin=datetime.date(2025, 3, 31),
        )

        from tests.conftest import configurer_periode_principale

        configurer_periode_principale(
            formation,
            date_debut=formation.date_debut,
            date_fin=formation.date_debut,
        )
        FormationModule.objects.create(
            formation=formation,
            module=module_referentiel,
            volume_horaire=4,
            site_nom="SITE-PER",
            batiment_nom="",
            salle_nom="",
        )

        _, report_hors_periode = PlanningService(SeanceRepository()).previsualiser_pour_groupe(groupe.pk)
        assert len(report_hors_periode) == 1
        assert report_hors_periode[0]["heures_restantes"] > 0

        PeriodeDisponibiliteSite.objects.create(
            site=site,
            date_debut=formation.date_debut,
            date_fin=formation.date_debut,
        )

        seances = PlanningService(SeanceRepository()).generer_pour_groupe(groupe.pk)
        assert len(seances) == 1
        assert seances[0].salle_nom == "SALLE-PER"

    def test_site_sans_periode_reste_toujours_disponible(
        self, formation, module_referentiel, formateur_general_planning
    ):
        from apps.parametrage.models import Batiment, Salle, Site

        groupe = _creer_groupe_configure(formation, "G-SITE-SANS-PERIODE", jours=[0])
        site = Site.objects.create(nom="SITE-LIBRE", actif=True)
        bat = Batiment.objects.create(site=site, nom="BAT-LIBRE", actif=True)
        Salle.objects.create(batiment=bat, nom="SALLE-LIBRE", capacite_max=30, actif=True)

        FormationModule.objects.create(
            formation=formation,
            module=module_referentiel,
            volume_horaire=4,
            site_nom="SITE-LIBRE",
            batiment_nom="",
            salle_nom="",
            date_debut=formation.date_debut,
            date_fin=formation.date_debut,
        )

        seances = PlanningService(SeanceRepository()).generer_pour_groupe(groupe.pk)
        assert len(seances) == 1
        assert seances[0].salle_nom == "SALLE-LIBRE"

    def test_dispatch_salle_explicite_refusee_si_site_referentiel_hors_module(
        self, formation, module_referentiel, formateur_general_planning
    ):
        """Salle présente au référentiel mais sur un autre site que le module : exclue du dispatch."""
        from apps.parametrage.models import Batiment, Salle, Site

        groupe = _creer_groupe_configure(formation, "G-DISPATCH-SITE", jours=[0])
        site_a = Site.objects.create(nom="REF-SITE-A", actif=True)
        bat_a = Batiment.objects.create(site=site_a, nom="REF-BAT-A", actif=True)
        Salle.objects.create(batiment=bat_a, nom="SALLE-REF-A", capacite_max=30, actif=True)

        FormationModule.objects.create(
            formation=formation,
            module=module_referentiel,
            volume_horaire=4,
            site_nom="AUTRE-SITE",
            batiment_nom="",
            salle_nom="SALLE-REF-A",
            date_debut=formation.date_debut,
            date_fin=formation.date_debut,
        )

        with pytest.raises(ValueError, match="incompatibles site"):
            PlanningService(SeanceRepository()).generer_pour_groupe(groupe.pk)

    def test_dispatch_salles_explicites_melange_ne_retient_que_les_coherentes(
        self, formation, module_referentiel, formateur_general_planning
    ):
        """Plusieurs salles explicites : celles hors site module sont ignorées, les cohérentes restent."""
        from apps.parametrage.models import Batiment, Salle, Site

        groupe = _creer_groupe_configure(formation, "G-DISPATCH-MIX", jours=[0])
        site_ok = Site.objects.create(nom="SITE-MIX", actif=True)
        bat_ok = Batiment.objects.create(site=site_ok, nom="BAT-MIX", actif=True)
        Salle.objects.create(batiment=bat_ok, nom="SALLE-OK-MIX", capacite_max=30, actif=True)
        site_other = Site.objects.create(nom="SITE-OTHER-MIX", actif=True)
        bat_other = Batiment.objects.create(site=site_other, nom="BAT-OTHER", actif=True)
        Salle.objects.create(batiment=bat_other, nom="SALLE-WRONG-MIX", capacite_max=30, actif=True)

        FormationModule.objects.create(
            formation=formation,
            module=module_referentiel,
            volume_horaire=4,
            site_nom="SITE-MIX",
            batiment_nom="",
            salle_nom="SALLE-WRONG-MIX, SALLE-OK-MIX",
            date_debut=formation.date_debut,
            date_fin=formation.date_debut,
        )

        seances = PlanningService(SeanceRepository()).generer_pour_groupe(groupe.pk)
        assert len(seances) == 1
        assert seances[0].salle_nom == "SALLE-OK-MIX"

    def test_dispatch_salle_explicite_refusee_si_batiment_hors_module(
        self, formation, module_referentiel, formateur_general_planning
    ):
        """Salle sur le bon site mais mauvais bâtiment lorsque le module restreint les bâtiments."""
        from apps.parametrage.models import Batiment, Salle, Site

        groupe = _creer_groupe_configure(formation, "G-DISPATCH-BAT", jours=[0])
        site = Site.objects.create(nom="SITE-BAT-TEST", actif=True)
        bat1 = Batiment.objects.create(site=site, nom="BAT-UN", actif=True)
        bat2 = Batiment.objects.create(site=site, nom="BAT-DEUX", actif=True)
        Salle.objects.create(batiment=bat1, nom="SALLE-BAT1", capacite_max=25, actif=True)
        Salle.objects.create(batiment=bat2, nom="SALLE-BAT2", capacite_max=25, actif=True)

        FormationModule.objects.create(
            formation=formation,
            module=module_referentiel,
            volume_horaire=4,
            site_nom="SITE-BAT-TEST",
            batiment_nom="BAT-UN",
            salle_nom="SALLE-BAT2",
            date_debut=formation.date_debut,
            date_fin=formation.date_debut,
        )

        with pytest.raises(ValueError, match="incompatibles site"):
            PlanningService(SeanceRepository()).generer_pour_groupe(groupe.pk)

    def test_module_multi_grades_couvre_grade_groupe(
        self, formation, auditeur, specialite_generale, formateur_general_planning
    ):
        """Un module avec plusieurs grades cibles doit matcher le grade du groupe."""
        groupe = _creer_groupe_configure(formation, "G4bis", jours=[0])  # lundi
        GroupeAuditeur.objects.create(groupe=groupe, auditeur=auditeur)  # grade A3
        module_multi = Module.objects.create(titre="Module Multi Grades", specialite=specialite_generale)
        FormationModule.objects.create(
            formation=formation,
            module=module_multi,
            volume_horaire=4,
            grade_cible="A2, A3",
            site_nom="Site A",
            batiment_nom="Bat A",
            salle_nom="Salle 101",
        )

        seances = PlanningService(SeanceRepository()).generer_pour_groupe(groupe.pk)
        assert len(seances) == 1
        assert seances[0].module.titre == "Module Multi Grades"

    def test_dry_run_ne_persiste_pas_les_seances(self, formation, module_referentiel, formateur_general_planning):
        """Le mode dry_run calcule les séances sans écrire en base."""
        groupe = _creer_groupe_configure(formation, "G5", jours=[0])  # lundi
        FormationModule.objects.create(
            formation=formation,
            module=module_referentiel,
            volume_horaire=4,
            site_nom="Site A",
            batiment_nom="Bat A",
            salle_nom="Salle 101",
            date_debut=formation.date_debut,
            date_fin=formation.date_debut,
        )

        # Séance existante: elle ne doit pas être supprimée en dry_run.
        Seance.objects.create(
            groupe=groupe,
            module=module_referentiel,
            date=formation.date_debut,
            heure_debut=datetime.time(8, 0),
            heure_fin=datetime.time(10, 0),
            duree_minutes=120,
            salle_nom="Salle 999",
        )

        generees = PlanningService(SeanceRepository()).generer_pour_groupe(groupe.pk, dry_run=True)

        assert len(generees) == 1
        assert Seance.objects.filter(groupe=groupe).count() == 1

    def test_generation_respecte_mode_module_matin_uniquement(
        self, formation, module_referentiel, formateur_general_planning
    ):
        """Avec creneau_mode=matin sur le module, aucune séance ne doit être placée le soir."""
        groupe = _creer_groupe_configure(formation, "G-MATIN", jours=[0, 1])  # lun + mar
        groupe.config.soir_actif = True
        groupe.config.save(update_fields=["soir_actif"])
        FormationModule.objects.create(
            formation=formation,
            module=module_referentiel,
            volume_horaire=8,
            creneau_mode="matin",
            site_nom="Site A",
            batiment_nom="Bat A",
            salle_nom="Salle 101",
            date_debut=formation.date_debut,
            date_fin=formation.date_debut + datetime.timedelta(days=1),
        )

        seances = PlanningService(SeanceRepository()).generer_pour_groupe(groupe.pk)

        assert len(seances) == 2
        assert all(s.heure_debut == datetime.time(8, 0) for s in seances)

    def test_generation_respecte_mode_module_soir_uniquement(
        self, formation, module_referentiel, formateur_general_planning
    ):
        """Avec creneau_mode=soir sur le module, une séance est planifiée sur le créneau soir."""
        groupe = _creer_groupe_configure(formation, "G-SOIR", jours=[0])  # lundi
        groupe.config.soir_actif = True
        groupe.config.save(update_fields=["soir_actif"])
        FormationModule.objects.create(
            formation=formation,
            module=module_referentiel,
            volume_horaire=4,
            creneau_mode="soir",
            site_nom="Site A",
            batiment_nom="Bat A",
            salle_nom="Salle 101",
            date_debut=formation.date_debut,
            date_fin=formation.date_debut,
        )

        seances = PlanningService(SeanceRepository()).generer_pour_groupe(groupe.pk)

        assert len(seances) == 1
        assert seances[0].heure_debut == datetime.time(13, 0)

    def test_generation_respecte_rythme_mensuel_une_semaine(
        self, formation, module_referentiel, formateur_general_planning
    ):
        """Avec rythme mensuel 1, seules les séances de la première semaine du mois sont autorisées."""
        from tests.conftest import configurer_periode_principale

        configurer_periode_principale(
            formation,
            date_debut=datetime.date(2025, 1, 1),
            date_fin=datetime.date(2025, 1, 31),
            rythme_mensuel="1",
        )
        groupe = _creer_groupe_configure(formation, "G-RYTHME-1", jours=[0])  # lundi
        groupe.config.soir_actif = False
        groupe.config.save(update_fields=["soir_actif"])
        FormationModule.objects.create(
            formation=formation,
            module=module_referentiel,
            volume_horaire=4,
            creneau_mode="matin",
            site_nom="Site A",
            batiment_nom="Bat A",
            salle_nom="Salle 101",
        )

        seances = PlanningService(SeanceRepository()).generer_pour_groupe(groupe.pk)

        assert len(seances) == 1
        assert seances[0].date == datetime.date(2025, 1, 6)

    def test_generation_respecte_rythme_mensuel_par_periode(
        self, type_formation, module_referentiel, formateur_general_planning
    ):
        """Chaque module utilise le rythme de sa période (ici 1re semaine vs tout le mois)."""
        from apps.parametrage.models import ModuleTypeFormation
        from apps.referentiels.models import Module

        from apps.formations.repositories import FormationModuleRepository, FormationRepository
        from apps.formations.services import FormationService
        from tests.conftest import configurer_periode_principale

        service = FormationService(FormationRepository(), FormationModuleRepository())
        formation = service.creer(
            type_formation_id=type_formation.pk,
            intitule="Formation rythme par période",
            vague="",
            date_debut=datetime.date(2025, 1, 1),
            date_fin=datetime.date(2025, 2, 28),
        )
        configurer_periode_principale(
            formation,
            date_debut=datetime.date(2025, 1, 1),
            date_fin=datetime.date(2025, 1, 31),
            rythme_mensuel="1",
        )
        p2 = service.ajouter_periode(
            formation.pk,
            "Février",
            datetime.date(2025, 2, 1),
            datetime.date(2025, 2, 28),
            rythme_mensuel="4",
        )
        module_fev = Module.objects.create(titre="Module février", specialite=module_referentiel.specialite)
        for mod in (module_referentiel, module_fev):
            ModuleTypeFormation.objects.create(
                module=mod,
                type_formation=type_formation,
                volume_horaire_defaut=4,
            )
        service.ajouter_module(
            formation.pk,
            module_referentiel.pk,
            periode_id=formation.periodes.order_by("ordre").first().pk,
            site_noms=["Site A"],
            batiment_noms=["Bat A"],
            salle_noms=["Salle 101"],
        )
        service.ajouter_module(
            formation.pk,
            module_fev.pk,
            periode_id=p2.pk,
            volume_horaire=8,
            site_noms=["Site A"],
            batiment_noms=["Bat A"],
            salle_noms=["Salle 102"],
        )
        groupe = _creer_groupe_configure(formation, "G-RYTHME-PERIODE", jours=[0])
        groupe.config.soir_actif = False
        groupe.config.save(update_fields=["soir_actif"])

        seances = PlanningService(SeanceRepository()).generer_pour_groupe(groupe.pk)

        janv = [s for s in seances if s.date.month == 1]
        fev = [s for s in seances if s.date.month == 2]
        assert len(janv) == 1
        assert janv[0].date == datetime.date(2025, 1, 6)
        assert len(fev) >= 2
        assert any(s.date.day > 7 for s in fev)

    def test_generation_respecte_rythme_mensuel_du_groupe(
        self, formation, module_referentiel, formateur_general_planning
    ):
        """Le rythme mensuel défini sur un groupe restreint son planning indépendamment de la formation."""
        from tests.conftest import configurer_periode_principale

        configurer_periode_principale(
            formation,
            date_debut=datetime.date(2025, 1, 1),
            date_fin=datetime.date(2025, 1, 31),
            rythme_mensuel="4",
        )
        groupe = _creer_groupe_configure(formation, "G-RYTHME-GR-1", jours=[0])  # lundi
        groupe.rythme_mensuel = "1"  # 1re semaine du mois seulement, par groupe
        groupe.save(update_fields=["rythme_mensuel"])
        groupe.config.soir_actif = False
        groupe.config.save(update_fields=["soir_actif"])
        FormationModule.objects.create(
            formation=formation,
            module=module_referentiel,
            volume_horaire=4,
            creneau_mode="matin",
            site_nom="Site A",
            batiment_nom="Bat A",
            salle_nom="Salle 101",
        )

        seances = PlanningService(SeanceRepository()).generer_pour_groupe(groupe.pk)

        assert len(seances) == 1
        assert seances[0].date == datetime.date(2025, 1, 6)

    def test_generation_override_rythme_groupe_remplace_celui_de_la_formation(
        self, formation, module_referentiel, formateur_general_planning
    ):
        """Quand le groupe a un rythme défini, il remplace (override) celui de la formation.

        Formation=1 (1re semaine seulement), Groupe=3 (1re, 2e et 3e semaines) → le groupe
        override : 3 semaines disponibles malgré la restriction de la formation.
        """
        from tests.conftest import configurer_periode_principale

        configurer_periode_principale(
            formation,
            date_debut=datetime.date(2025, 1, 1),
            date_fin=datetime.date(2025, 1, 31),
            rythme_mensuel="1",
        )
        groupe = _creer_groupe_configure(formation, "G-RYTHME-OVERRIDE", jours=[0])  # lundi
        groupe.rythme_mensuel = "3"
        groupe.save(update_fields=["rythme_mensuel"])
        groupe.config.soir_actif = False
        groupe.config.save(update_fields=["soir_actif"])
        FormationModule.objects.create(
            formation=formation,
            module=module_referentiel,
            volume_horaire=8,  # 2 séances de 4h sur la période disponible
            creneau_mode="matin",
            site_nom="Site A",
            batiment_nom="Bat A",
            salle_nom="Salle 101",
        )

        seances = PlanningService(SeanceRepository()).generer_pour_groupe(groupe.pk)

        # Avec override "3", les lundis valides en janvier 2025 sont 6, 13, 20 (semaines 1-3).
        for s in seances:
            assert s.date.day <= 21, f"Séance {s.date} hors override rythme groupe(3) = 3 premières semaines"
        dates = sorted(s.date for s in seances)
        assert dates == [datetime.date(2025, 1, 6), datetime.date(2025, 1, 13)]

    def test_module_inactif_n_est_pas_planifie(self, formation, module_referentiel, formateur_general_planning):
        """Un Module marqué inactif est ignoré par l'algorithme (avec log info)."""
        module_referentiel.actif = False
        module_referentiel.save(update_fields=["actif"])
        groupe = _creer_groupe_configure(formation, "G-INACTIF", jours=[0])  # lundi
        FormationModule.objects.create(
            formation=formation,
            module=module_referentiel,
            volume_horaire=4,
            creneau_mode="matin",
            site_nom="Site A",
            batiment_nom="Bat A",
            salle_nom="Salle 101",
            date_debut=datetime.date(2025, 1, 1),
            date_fin=datetime.date(2025, 1, 31),
        )

        with pytest.raises(ValueError, match="Aucun module planifiable"):
            PlanningService(SeanceRepository()).generer_pour_groupe(groupe.pk)

    def test_veto_capacite_salle_strict_par_defaut(
        self, formation, module_referentiel, formateur_general_planning, parametres
    ):
        """Avec tolérance=0 (défaut), une salle plus petite que l'effectif est rejetée."""
        from apps.auditeurs.models import Auditeur
        from apps.formations.models import Inscription
        from apps.parametrage.models import Batiment, Salle, Site

        parametres.tolerance_capacite_salle = 0
        parametres.save(update_fields=["tolerance_capacite_salle"])

        site = Site.objects.create(nom="SITE-VETO", actif=True)
        bat = Batiment.objects.create(site=site, nom="BAT-VETO", actif=True)
        Salle.objects.create(batiment=bat, nom="PETITE", capacite_max=2, actif=True)
        Salle.objects.create(batiment=bat, nom="GRANDE", capacite_max=50, actif=True)

        groupe = _creer_groupe_configure(formation, "G-VETO", jours=[0])  # lundi
        for i in range(5):  # 5 auditeurs
            a = Auditeur.objects.create(nom=f"AUD{i}", prenom="X", matricule=f"VETO{i}", grade="A3")
            Inscription.objects.create(formation=formation, auditeur=a)
            GroupeAuditeur.objects.create(groupe=groupe, auditeur=a)

        FormationModule.objects.create(
            formation=formation,
            module=module_referentiel,
            volume_horaire=4,
            creneau_mode="matin",
            site_nom="SITE-VETO",
            salle_nom="",  # pool implicite
            date_debut=datetime.date(2025, 1, 1),
            date_fin=datetime.date(2025, 1, 31),
        )

        seances = PlanningService(SeanceRepository()).generer_pour_groupe(groupe.pk)

        assert len(seances) == 1
        assert seances[0].salle_nom == "GRANDE"  # PETITE rejetée car capacité 2 < effectif 5

    def test_veto_capacite_salle_avec_tolerance(
        self, formation, module_referentiel, formateur_general_planning, parametres
    ):
        """Avec tolérance=3, une salle de capacité = effectif - 3 reste candidate."""
        from apps.auditeurs.models import Auditeur
        from apps.formations.models import Inscription
        from apps.parametrage.models import Batiment, Salle, Site

        parametres.tolerance_capacite_salle = 3
        parametres.save(update_fields=["tolerance_capacite_salle"])

        site = Site.objects.create(nom="SITE-TOL", actif=True)
        bat = Batiment.objects.create(site=site, nom="BAT-TOL", actif=True)
        # Capacité=2 → seuil = 5-3 = 2 → 2 ≥ 2 OK, salle conservée
        Salle.objects.create(batiment=bat, nom="LIMITE", capacite_max=2, actif=True)

        groupe = _creer_groupe_configure(formation, "G-TOL", jours=[0])  # lundi
        for i in range(5):
            a = Auditeur.objects.create(nom=f"TOL{i}", prenom="X", matricule=f"TOL{i}", grade="A3")
            Inscription.objects.create(formation=formation, auditeur=a)
            GroupeAuditeur.objects.create(groupe=groupe, auditeur=a)

        FormationModule.objects.create(
            formation=formation,
            module=module_referentiel,
            volume_horaire=4,
            creneau_mode="matin",
            site_nom="SITE-TOL",
            salle_nom="",
            date_debut=datetime.date(2025, 1, 1),
            date_fin=datetime.date(2025, 1, 31),
        )

        seances = PlanningService(SeanceRepository()).generer_pour_groupe(groupe.pk)

        assert len(seances) == 1
        assert seances[0].salle_nom == "LIMITE"  # acceptée grâce à la tolérance

    def test_generation_groupe_sans_rythme_herite_de_la_formation(
        self, formation, module_referentiel, formateur_general_planning
    ):
        """Sans cadence sur le groupe (champ vide), la cadence de la période du module est appliquée."""
        from tests.conftest import configurer_periode_principale

        configurer_periode_principale(
            formation,
            date_debut=datetime.date(2025, 1, 1),
            date_fin=datetime.date(2025, 1, 31),
            rythme_mensuel="1",
        )
        groupe = _creer_groupe_configure(formation, "G-RYTHME-HERITE", jours=[0])  # lundi
        # rythme_mensuel reste vide par défaut → hérite
        assert groupe.rythme_mensuel == ""
        groupe.config.soir_actif = False
        groupe.config.save(update_fields=["soir_actif"])
        FormationModule.objects.create(
            formation=formation,
            module=module_referentiel,
            volume_horaire=4,
            creneau_mode="matin",
            site_nom="Site A",
            batiment_nom="Bat A",
            salle_nom="Salle 101",
        )

        seances = PlanningService(SeanceRepository()).generer_pour_groupe(groupe.pk)

        assert len(seances) == 1
        assert seances[0].date == datetime.date(2025, 1, 6)

    def test_generation_strict_periode_module_invalide_ne_supprime_pas_l_existant(
        self, formation, module_referentiel, formateur_general_planning
    ):
        """En strict, une période pédagogique invalide doit échouer et annuler la suppression préalable."""
        from apps.formations.models import FormationPeriode

        groupe = _creer_groupe_configure(formation, "G5B", jours=[0])  # lundi
        periode = formation.periodes.order_by("ordre", "date_debut").first()
        FormationPeriode.objects.filter(pk=periode.pk).update(
            date_debut=formation.date_fin,
            date_fin=formation.date_debut,
        )
        FormationModule.objects.create(
            formation=formation,
            module=module_referentiel,
            volume_horaire=4,
            site_nom="Site A",
            batiment_nom="Bat A",
            salle_nom="Salle 101",
        )
        seance_existante = Seance.objects.create(
            groupe=groupe,
            module=module_referentiel,
            date=formation.date_debut,
            heure_debut=datetime.time(8, 0),
            heure_fin=datetime.time(10, 0),
            duree_minutes=120,
            salle_nom="Salle 999",
        )

        with pytest.raises(ValueError, match="période invalide"):
            PlanningService(SeanceRepository()).generer_pour_groupe(groupe.pk)

        assert Seance.objects.filter(pk=seance_existante.pk).exists()
        assert Seance.objects.filter(groupe=groupe).count() == 1

    def test_previsualisation_retourne_raison_non_couverture(
        self, formation, module_referentiel, formateur_general_planning
    ):
        """La prévisualisation expose la cause quand un module n'est pas totalement planifiable."""
        groupe = _creer_groupe_configure(formation, "G6", jours=[0])  # lundi
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

        _, report = PlanningService(SeanceRepository()).previsualiser_pour_groupe(groupe.pk)

        assert len(report) == 1
        assert report[0]["heures_restantes"] > 0
        assert "aucune salle candidate" in (report[0]["reason"] or "")

    def test_occupations_modules_limitees_a_la_formation_courante(
        self, formation, module_referentiel, formateur_general_planning
    ):
        """
        L'occupation inter-groupes (même formation) pour un même module le même jour est portée
        par salle : une séance d'une autre formation ne bloque pas ; une séance sans salle bloque
        le jour entier pour ce module (conservateur).
        """
        import datetime

        from apps.formations.repositories import FormationModuleRepository, FormationRepository
        from apps.formations.services import FormationService
        from apps.seances.models import Seance
        from apps.seances.services import PlanningService

        service = FormationService(FormationRepository(), FormationModuleRepository())
        f2 = service.creer(
            type_formation_id=formation.type_formation_id,
            intitule="Formation parallele",
            vague="Vague 1",
            date_debut=formation.date_debut,
            date_fin=formation.date_fin,
        )

        g_f1 = _creer_groupe_configure(formation, "G-PLAN-F1", jours=[0])
        g_f2 = _creer_groupe_configure(f2, "G-PLAN-F2", jours=[0])

        d = formation.date_debut
        Seance.objects.create(
            groupe=g_f1,
            module=module_referentiel,
            date=d,
            heure_debut=datetime.time(8, 0),
            heure_fin=datetime.time(12, 0),
            duree_minutes=240,
            salle_nom="Salle 101",
            site_nom="Site A",
            batiment_nom="Bat A",
            formateur_nom="POOL",
            formateur_prenom="GENERAL",
            formateur_numero="+2250999999001",
        )

        occ_f2 = PlanningService._charger_occupations_modules_existantes(g_f2.pk, f2.pk)
        quadruples_f2, sans_salle_f2 = occ_f2
        assert (d, module_referentiel.pk, "SITE A", "SALLE 101") not in quadruples_f2
        assert (d, module_referentiel.pk) not in sans_salle_f2

        g_f1_bis = _creer_groupe_configure(formation, "G-PLAN-F1-BIS", jours=[0])
        occ_f1_bis = PlanningService._charger_occupations_modules_existantes(g_f1_bis.pk, formation.pk)
        quadruples_f1, sans_salle_f1 = occ_f1_bis
        assert (d, module_referentiel.pk, "SITE A", "SALLE 101") in quadruples_f1
        assert (d, module_referentiel.pk) not in sans_salle_f1

    def test_generation_limite_un_seul_module_par_jour_pour_le_groupe(
        self, formation, module_referentiel, parametres, specialite_generale, formateur_general_planning
    ):
        """
        Un groupe ne doit avoir qu'un seul module par date.
        """
        parametres.max_seances_par_jour_defaut = 2
        parametres.save(update_fields=["max_seances_par_jour_defaut"])

        groupe = Groupe.objects.create(formation=formation, nom="G-MAX-GLOBAL", max_auditeurs=25)
        ConfigGroupe.objects.create(
            groupe=groupe,
            matin_actif=True,
            matin_heure_debut=datetime.time(8, 0),
            matin_heure_fin=datetime.time(12, 0),
            soir_actif=True,
            soir_heure_debut=datetime.time(13, 0),
            soir_heure_fin=datetime.time(17, 0),
        )
        JourCours.objects.create(groupe=groupe, jour=0)  # lundi
        JourCours.objects.create(groupe=groupe, jour=1)  # mardi

        module_2 = Module.objects.create(titre="Module max global 2", specialite=specialite_generale)
        date_debut = datetime.date(2025, 1, 6)
        date_fin = datetime.date(2025, 1, 7)
        FormationModule.objects.create(
            formation=formation,
            module=module_referentiel,
            volume_horaire=8,  # 2 séances de 4h
            site_nom="Site A",
            salle_nom="SALLE-A",
            date_debut=date_debut,
            date_fin=date_fin,
        )
        FormationModule.objects.create(
            formation=formation,
            module=module_2,
            volume_horaire=8,  # 2 séances de 4h
            site_nom="Site A",
            salle_nom="SALLE-B",
            date_debut=date_debut,
            date_fin=date_fin,
        )

        seances = PlanningService(SeanceRepository()).generer_pour_groupe(groupe.pk)

        modules_par_date = {}
        for seance in seances:
            modules_par_date.setdefault(seance.date, set()).add(seance.module_id)
        assert seances
        assert all(len(modules) == 1 for modules in modules_par_date.values())

    def test_generation_repartit_sur_plusieurs_jours_quand_module_salle_depasse_max(
        self, formation, module_referentiel, parametres, formateur_general_planning
    ):
        """
        Un même module dans une même salle est limité à 2 séances/jour:
        4 séances doivent donc être réparties sur 2 jours.
        """
        parametres.max_seances_par_jour_defaut = 2
        parametres.save(update_fields=["max_seances_par_jour_defaut"])

        groupe = Groupe.objects.create(formation=formation, nom="G-MOD-SALLE", max_auditeurs=25)
        ConfigGroupe.objects.create(
            groupe=groupe,
            matin_actif=True,
            matin_heure_debut=datetime.time(8, 0),
            matin_heure_fin=datetime.time(12, 0),
            soir_actif=True,
            soir_heure_debut=datetime.time(13, 0),
            soir_heure_fin=datetime.time(17, 0),
        )
        JourCours.objects.create(groupe=groupe, jour=0)  # lundi
        JourCours.objects.create(groupe=groupe, jour=1)  # mardi

        # Deux entrées du même module/salle pour simuler un volume total élevé.
        FormationModule.objects.create(
            formation=formation,
            module=module_referentiel,
            volume_horaire=8,
            site_nom="Site A",
            salle_nom="SALLE-UNIQUE",
            date_debut=datetime.date(2025, 1, 6),
            date_fin=datetime.date(2025, 1, 7),
        )
        FormationModule.objects.create(
            formation=formation,
            module=module_referentiel,
            volume_horaire=8,
            site_nom="Site A",
            salle_nom="SALLE-UNIQUE",
            date_debut=datetime.date(2025, 1, 6),
            date_fin=datetime.date(2025, 1, 7),
        )

        seances = PlanningService(SeanceRepository()).generer_pour_groupe(groupe.pk)

        compte = {}
        for seance in seances:
            cle = (seance.date, seance.module_id, (seance.salle_nom or "").strip().upper())
            compte[cle] = compte.get(cle, 0) + 1

        assert len(seances) == 4
        assert all(valeur <= 2 for valeur in compte.values())

    def test_generation_ne_planifie_pas_meme_module_meme_jour_sur_groupes_differents(
        self, formation, module_referentiel, parametres, formateur_general_planning
    ):
        """
        Un même module ne doit pas être planifié le même jour sur deux groupes différents.
        """
        parametres.max_seances_par_jour_defaut = 2
        parametres.save(update_fields=["max_seances_par_jour_defaut"])

        groupe1 = _creer_groupe_configure(formation, "G-MOD-1", jours=[0, 1])  # lundi, mardi
        groupe2 = _creer_groupe_configure(formation, "G-MOD-2", jours=[0, 1])

        FormationModule.objects.create(
            formation=formation,
            module=module_referentiel,
            volume_horaire=4,
            site_nom="Site A",
            salle_nom="SALLE-1",
            date_debut=datetime.date(2025, 1, 6),
            date_fin=datetime.date(2025, 1, 7),
        )

        # Groupe 1 déjà planifié sur le lundi pour ce module.
        Seance.objects.create(
            groupe=groupe1,
            module=module_referentiel,
            date=datetime.date(2025, 1, 6),
            heure_debut=datetime.time(8, 0),
            heure_fin=datetime.time(12, 0),
            duree_minutes=240,
            salle_nom="SALLE-1",
        )

        seances_g2 = PlanningService(SeanceRepository()).generer_pour_groupe(groupe2.pk)

        assert len(seances_g2) == 1
        assert seances_g2[0].date == datetime.date(2025, 1, 7)

    def test_generation_respecte_max_salles_simultanees_par_module(
        self, formation, module_referentiel, parametres, formateur_general_planning
    ):
        """
        Si la limite est à 1 salle simultanée pour un module, un second groupe doit être décalé
        au jour suivant même si une autre salle est disponible.
        """
        from apps.parametrage.models import Batiment, Salle, Site

        parametres.max_salles_simultanees_module = 1
        parametres.save(update_fields=["max_salles_simultanees_module"])

        site = Site.objects.create(nom="SITE-SIM", actif=True)
        bat = Batiment.objects.create(site=site, nom="BAT-SIM", actif=True)
        Salle.objects.create(batiment=bat, nom="SALLE-SIM-1", capacite_max=25, actif=True)
        Salle.objects.create(batiment=bat, nom="SALLE-SIM-2", capacite_max=25, actif=True)

        groupe1 = _creer_groupe_configure(formation, "G-SIM-1", jours=[0, 1])  # lundi, mardi
        groupe2 = _creer_groupe_configure(formation, "G-SIM-2", jours=[0, 1])

        FormationModule.objects.create(
            formation=formation,
            module=module_referentiel,
            volume_horaire=4,
            site_nom="SITE-SIM",
            salle_nom="",
            salle_nombre=2,
            date_debut=datetime.date(2025, 1, 6),
            date_fin=datetime.date(2025, 1, 7),
        )

        Seance.objects.create(
            groupe=groupe1,
            module=module_referentiel,
            date=datetime.date(2025, 1, 6),
            heure_debut=datetime.time(8, 0),
            heure_fin=datetime.time(12, 0),
            duree_minutes=240,
            site_nom="SITE-SIM",
            salle_nom="SALLE-SIM-1",
        )

        seances_g2 = PlanningService(SeanceRepository()).generer_pour_groupe(groupe2.pk)

        assert len(seances_g2) == 1
        assert seances_g2[0].date == datetime.date(2025, 1, 7)

    def test_generation_respecte_contraintes_cumulees(
        self, formation, module_referentiel, parametres, formateur_general_planning
    ):
        """
        Vérifie le cumul des contraintes :
        - rythme mensuel de la période du module (1re semaine),
        - créneau du module (soir),
        - max salles simultanées par module (1).
        """
        from apps.parametrage.models import Batiment, Salle, Site
        from tests.conftest import configurer_periode_principale

        configurer_periode_principale(
            formation,
            date_debut=datetime.date(2025, 1, 1),
            date_fin=datetime.date(2025, 1, 31),
            rythme_mensuel="1",
        )
        parametres.max_salles_simultanees_module = 1
        parametres.save(update_fields=["max_salles_simultanees_module"])

        site = Site.objects.create(nom="SITE-CUMUL", actif=True)
        bat = Batiment.objects.create(site=site, nom="BAT-CUMUL", actif=True)
        Salle.objects.create(batiment=bat, nom="SALLE-CUMUL-1", capacite_max=25, actif=True)
        Salle.objects.create(batiment=bat, nom="SALLE-CUMUL-2", capacite_max=25, actif=True)

        groupe1 = _creer_groupe_configure(formation, "G-CUMUL-1", jours=[0, 1])  # lundi, mardi
        groupe2 = _creer_groupe_configure(formation, "G-CUMUL-2", jours=[0, 1])
        for g in (groupe1, groupe2):
            g.config.soir_actif = True
            g.config.save(update_fields=["soir_actif"])

        FormationModule.objects.create(
            formation=formation,
            module=module_referentiel,
            volume_horaire=4,
            creneau_mode="soir",
            site_nom="SITE-CUMUL",
            salle_nom="",
            salle_nombre=2,
        )

        # Groupe 1 occupe déjà une salle lundi soir pour ce module.
        Seance.objects.create(
            groupe=groupe1,
            module=module_referentiel,
            date=datetime.date(2025, 1, 6),
            heure_debut=datetime.time(13, 0),
            heure_fin=datetime.time(17, 0),
            duree_minutes=240,
            site_nom="SITE-CUMUL",
            salle_nom="SALLE-CUMUL-1",
        )

        seances_g2 = PlanningService(SeanceRepository()).generer_pour_groupe(groupe2.pk)

        assert len(seances_g2) == 1
        # Lundi bloqué (max salles simultanées atteint), report au mardi de la 1re semaine.
        assert seances_g2[0].date == datetime.date(2025, 1, 7)
        assert seances_g2[0].heure_debut == datetime.time(13, 0)

    def test_generation_choisit_salle_capacite_la_plus_proche(
        self, formation, module_referentiel, auditeur, formateur_general_planning
    ):
        """Le choix de salle privilégie la capacité la plus proche de l'effectif du groupe."""
        from apps.parametrage.models import Batiment, Salle, Site

        groupe = _creer_groupe_configure(formation, "G-CAP", jours=[0])  # lundi
        GroupeAuditeur.objects.create(groupe=groupe, auditeur=auditeur)

        site = Site.objects.create(nom="SITE-CAP", actif=True)
        bat = Batiment.objects.create(site=site, nom="BAT-CAP", actif=True)
        Salle.objects.create(batiment=bat, nom="SALLE-CAP-100", capacite_max=100, actif=True)
        Salle.objects.create(batiment=bat, nom="SALLE-CAP-030", capacite_max=30, actif=True)

        FormationModule.objects.create(
            formation=formation,
            module=module_referentiel,
            volume_horaire=4,
            site_nom="SITE-CAP",
            batiment_nom="",
            salle_nom="",
            salle_nombre=2,
            date_debut=formation.date_debut,
            date_fin=formation.date_debut,
        )

        seances = PlanningService(SeanceRepository()).generer_pour_groupe(groupe.pk)

        assert len(seances) == 1
        assert seances[0].salle_nom == "SALLE-CAP-030"

    def test_generation_rotation_multi_salles_pour_un_meme_module(
        self, formation, module_referentiel, auditeur, parametres, formateur_general_planning
    ):
        """Pour un même module, toutes les séances du groupe utilisent la même salle (première retenue)."""
        from apps.parametrage.models import Batiment, Salle, Site

        parametres.max_seances_par_jour_defaut = 2
        parametres.save(update_fields=["max_seances_par_jour_defaut"])

        groupe = Groupe.objects.create(formation=formation, nom="G-ROT", max_auditeurs=25)
        ConfigGroupe.objects.create(
            groupe=groupe,
            matin_actif=True,
            matin_heure_debut=datetime.time(8, 0),
            matin_heure_fin=datetime.time(12, 0),
            soir_actif=True,
            soir_heure_debut=datetime.time(13, 0),
            soir_heure_fin=datetime.time(17, 0),
        )
        JourCours.objects.create(groupe=groupe, jour=0)  # lundi
        GroupeAuditeur.objects.create(groupe=groupe, auditeur=auditeur)

        site = Site.objects.create(nom="SITE-ROT", actif=True)
        bat = Batiment.objects.create(site=site, nom="BAT-ROT", actif=True)
        Salle.objects.create(batiment=bat, nom="SALLE-ROT-A", capacite_max=30, actif=True)
        Salle.objects.create(batiment=bat, nom="SALLE-ROT-B", capacite_max=30, actif=True)

        FormationModule.objects.create(
            formation=formation,
            module=module_referentiel,
            volume_horaire=8,  # 2 séances de 4h
            site_nom="SITE-ROT",
            batiment_nom="",
            salle_nom="",
            salle_nombre=2,
            date_debut=formation.date_debut,
            date_fin=formation.date_debut,
        )

        seances = sorted(
            PlanningService(SeanceRepository()).generer_pour_groupe(groupe.pk),
            key=lambda s: s.heure_debut,
        )

        assert len(seances) == 2
        assert len({s.salle_nom for s in seances}) == 1

    def test_generation_respecte_poids_scoring_parametrage(
        self, formation, module_referentiel, auditeur, parametres, formateur_general_planning
    ):
        """Les poids de scoring orientent le premier choix ; les séances suivantes restent dans la même salle."""
        from apps.parametrage.models import Batiment, Salle, Site

        parametres.max_seances_par_jour_defaut = 2
        parametres.poids_score_ecart_capacite = 1
        parametres.poids_score_rotation_module = 30
        parametres.poids_score_equilibrage_global = 1
        parametres.save(
            update_fields=[
                "max_seances_par_jour_defaut",
                "poids_score_ecart_capacite",
                "poids_score_rotation_module",
                "poids_score_equilibrage_global",
            ]
        )

        groupe = Groupe.objects.create(formation=formation, nom="G-POIDS", max_auditeurs=25)
        ConfigGroupe.objects.create(
            groupe=groupe,
            matin_actif=True,
            matin_heure_debut=datetime.time(8, 0),
            matin_heure_fin=datetime.time(12, 0),
            soir_actif=True,
            soir_heure_debut=datetime.time(13, 0),
            soir_heure_fin=datetime.time(17, 0),
        )
        JourCours.objects.create(groupe=groupe, jour=0)  # lundi
        GroupeAuditeur.objects.create(groupe=groupe, auditeur=auditeur)  # effectif = 1

        site = Site.objects.create(nom="SITE-POIDS", actif=True)
        bat = Batiment.objects.create(site=site, nom="BAT-POIDS", actif=True)
        Salle.objects.create(batiment=bat, nom="SALLE-POIDS-A", capacite_max=3, actif=True)
        Salle.objects.create(batiment=bat, nom="SALLE-POIDS-B", capacite_max=5, actif=True)

        FormationModule.objects.create(
            formation=formation,
            module=module_referentiel,
            volume_horaire=8,  # 2 séances
            site_nom="SITE-POIDS",
            batiment_nom="",
            salle_nom="",
            salle_nombre=2,
            date_debut=formation.date_debut,
            date_fin=formation.date_debut,
        )

        seances = sorted(
            PlanningService(SeanceRepository()).generer_pour_groupe(groupe.pk),
            key=lambda s: s.heure_debut,
        )

        assert len(seances) == 2
        assert seances[0].salle_nom == seances[1].salle_nom

    def test_generation_assigne_formateur_importe_sur_les_seances(
        self, formation, module_referentiel, specialite_generale
    ):
        """Chaque séance générée récupère un formateur importé du module."""
        from apps.formations.models import AffectationFormateurGroupe, Formateur

        groupe = _creer_groupe_configure(formation, "G-FORM", jours=[0])  # lundi
        FormationModule.objects.create(
            formation=formation,
            module=module_referentiel,
            volume_horaire=4,
            site_nom="Site A",
            salle_nom="SALLE-F1",
            date_debut=formation.date_debut,
            date_fin=formation.date_debut,
        )
        formateur = Formateur.objects.create(
            numero="+2250102030405",
            nom="FORMATEUR TEST",
            prenom="UN",
            email="formateur.test@example.com",
            telephone="+2252721223344",
            organisation="CPFAE",
        )
        formateur.specialites.add(specialite_generale)
        AffectationFormateurGroupe.objects.create(
            groupe=groupe,
            module=module_referentiel,
            formateur=formateur,
        )

        seances = PlanningService(SeanceRepository()).generer_pour_groupe(groupe.pk)

        assert len(seances) == 1
        assert seances[0].formateur_nom == "FORMATEUR TEST"

    def test_generation_module_avec_specialite_choisit_formateur_du_referentiel(self, formation, module_referentiel):
        """Le module indique une spécialité ; le planning prend un formateur qui l’a sur le modèle Formateur."""
        from apps.formations.models import Formateur
        from apps.referentiels.models import Specialite

        spec = Specialite.objects.create(code="FIN", libelle="Finance")
        module_referentiel.specialite = spec
        module_referentiel.save(update_fields=["specialite"])

        groupe = _creer_groupe_configure(formation, "G-SPEC", jours=[0])
        FormationModule.objects.create(
            formation=formation,
            module=module_referentiel,
            volume_horaire=4,
            site_nom="Site A",
            salle_nom="SALLE-SPEC",
            date_debut=formation.date_debut,
            date_fin=formation.date_debut,
        )
        f_ok = Formateur.objects.create(
            numero="+2250111111111",
            nom="ALPHA",
            prenom="Spec",
            email="a@example.com",
            telephone="010101",
            organisation="ORG",
        )
        f_ok.specialites.add(spec)

        seances = PlanningService(SeanceRepository()).generer_pour_groupe(groupe.pk)

        assert len(seances) == 1
        assert seances[0].formateur_nom == "ALPHA"

    def test_generation_affectation_exclusive_meme_si_specialite_module_differente(self, formation, module_referentiel):
        """Affectation prioritaire : même sans spécialité métier exacte, seul le formateur affecté est retenu."""
        from apps.formations.models import AffectationFormateurGroupe, Formateur
        from apps.referentiels.models import Specialite

        spec = Specialite.objects.create(code="DROIT", libelle="Droit")
        module_referentiel.specialite = spec
        module_referentiel.save(update_fields=["specialite"])

        groupe = _creer_groupe_configure(formation, "G-SPEC2", jours=[0])
        FormationModule.objects.create(
            formation=formation,
            module=module_referentiel,
            volume_horaire=4,
            site_nom="Site A",
            salle_nom="SALLE-SPEC2",
            date_debut=formation.date_debut,
            date_fin=formation.date_debut,
        )
        f_mauvais = Formateur.objects.create(
            numero="+2250999999999",
            nom="MAUVAIS",
            prenom="",
            email="bad@example.com",
            telephone="",
            organisation="",
        )
        f_mauvais.specialites.add(Specialite.objects.get(code="GENERAL"))
        AffectationFormateurGroupe.objects.create(
            groupe=groupe,
            module=module_referentiel,
            formateur=f_mauvais,
        )

        seances = PlanningService(SeanceRepository()).generer_pour_groupe(groupe.pk)

        assert len(seances) == 1
        assert seances[0].formateur_nom == "MAUVAIS"

    def test_generation_limite_formateur_a_deux_seances_par_jour(self, formation, parametres, auditeur):
        """Si le formateur unique est déjà à quota sur un jour, le planning place quand même la séance sans formateur."""
        from apps.formations.models import AffectationFormateurGroupe, Formateur
        from apps.referentiels.models import Specialite

        # Spécialité dédiée : sinon le pool GENERAL du référentiel satisferait le lundi à la place du formateur affecté.
        spec_lim = Specialite.objects.create(code="LIMTEST01", libelle="Test limite jour")
        module_g2 = Module.objects.create(titre="Module Formateur Cible", specialite=spec_lim)
        module_occ_1 = Module.objects.create(titre="Module Occupation 1", specialite=spec_lim)
        module_occ_2 = Module.objects.create(titre="Module Occupation 2", specialite=spec_lim)
        groupe1 = _creer_groupe_configure(formation, "G-FORM-1", jours=[0, 1])  # lundi, mardi
        groupe2 = _creer_groupe_configure(formation, "G-FORM-2", jours=[0, 1])
        GroupeAuditeur.objects.create(groupe=groupe2, auditeur=auditeur)

        FormationModule.objects.create(
            formation=formation,
            module=module_g2,
            volume_horaire=4,
            site_nom="Site A",
            salle_nom="SALLE-F2",
            date_debut=formation.date_debut,
            date_fin=formation.date_fin,
        )
        formateur = Formateur.objects.create(
            numero="+225000000001",
            nom="FORMATEUR UNIQUE",
            prenom="",
            email="formateur.unique@example.com",
            telephone="",
            organisation="",
        )
        formateur.specialites.add(spec_lim)
        AffectationFormateurGroupe.objects.create(
            groupe=groupe2,
            module=module_g2,
            formateur=formateur,
        )

        # Deux séances existantes sur le lundi pour saturer le formateur.
        Seance.objects.create(
            groupe=groupe1,
            module=module_occ_1,
            formateur_nom="FORMATEUR UNIQUE",
            date=datetime.date(2025, 1, 6),
            heure_debut=datetime.time(8, 0),
            heure_fin=datetime.time(12, 0),
            duree_minutes=240,
            salle_nom="SALLE-X",
        )
        Seance.objects.create(
            groupe=groupe1,
            module=module_occ_2,
            formateur_nom="FORMATEUR UNIQUE",
            date=datetime.date(2025, 1, 6),
            heure_debut=datetime.time(13, 0),
            heure_fin=datetime.time(17, 0),
            duree_minutes=240,
            salle_nom="SALLE-Y",
        )

        seances_g2 = PlanningService(SeanceRepository()).generer_pour_groupe(groupe2.pk)

        assert len(seances_g2) == 1
        assert seances_g2[0].date == datetime.date(2025, 1, 6)
        assert seances_g2[0].formateur_nom == ""


@pytest.mark.django_db
def test_deuxieme_formation_chevauchante_planifie_apres_derniere_seance_premiere(
    type_formation, module_referentiel, auditeur, formateur_general_planning
):
    """Ordre (date_debut formation, id) : la 2e formation ne commence pas avant la fin de la dernière séance de la 1re."""
    from apps.formations.repositories import FormationModuleRepository, FormationRepository
    from apps.formations.services import FormationService
    from apps.parametrage.models import Batiment, ModuleTypeFormation, Salle, Site

    svc = FormationService(FormationRepository(), FormationModuleRepository())
    d0 = datetime.date(2025, 1, 6)
    d1 = datetime.date(2025, 3, 28)
    f1 = svc.creer(
        type_formation_id=type_formation.pk,
        intitule="Formation première",
        vague="V1",
        date_debut=d0,
        date_fin=d1,
    )
    f2 = svc.creer(
        type_formation_id=type_formation.pk,
        intitule="Formation deuxième",
        vague="V2",
        date_debut=d0,
        date_fin=d1,
    )

    site = Site.objects.create(nom="SITE-ORD", actif=True)
    bat = Batiment.objects.create(site=site, nom="BAT-ORD", actif=True)
    Salle.objects.create(batiment=bat, nom="SALLE-ORD", capacite_max=30, actif=True)

    mtf, _ = ModuleTypeFormation.objects.get_or_create(
        module=module_referentiel,
        type_formation=type_formation,
        defaults={"volume_horaire_defaut": 4},
    )
    if mtf.volume_horaire_defaut != 4:
        mtf.volume_horaire_defaut = 4
        mtf.save(update_fields=["volume_horaire_defaut"])

    for f in (f1, f2):
        FormationModule.objects.create(
            formation=f,
            module=module_referentiel,
            volume_horaire=4,
            grade_cible="",
            site_nom=site.nom,
            batiment_nom=bat.nom,
            salle_nom="SALLE-ORD",
            site_nombre=1,
            batiment_nombre=1,
            salle_nombre=1,
            date_debut=d0,
            date_fin=d1,
        )

    g1 = _creer_groupe_configure(f1, "G-F1-ORD", jours=[0])
    g2 = _creer_groupe_configure(f2, "G-F2-ORD", jours=[0])
    GroupeAuditeur.objects.create(groupe=g1, auditeur=auditeur)
    GroupeAuditeur.objects.create(groupe=g2, auditeur=auditeur)

    ps = PlanningService(SeanceRepository())
    seances1 = ps.generer_pour_groupe(g1.pk)
    assert len(seances1) == 1
    fin_premiere = datetime.datetime.combine(seances1[0].date, seances1[0].heure_fin)

    seances2 = ps.generer_pour_groupe(g2.pk)
    assert len(seances2) == 1
    debut_seconde = datetime.datetime.combine(seances2[0].date, seances2[0].heure_debut)
    assert debut_seconde > fin_premiere
    assert seances2[0].date == datetime.date(2025, 1, 13)


@pytest.mark.django_db
def test_planning_volume_null_resolu_par_type_module_grade(
    formation, module_referentiel, auditeur, formateur_general_planning
):
    """Sans volume stocké, le planning utilise le paramétrage (type × module × grade du groupe)."""
    from apps.parametrage.models import ModuleTypeFormation

    ModuleTypeFormation.objects.update_or_create(
        module=module_referentiel,
        type_formation=formation.type_formation,
        grade_cible="A3",
        defaults={"volume_horaire_defaut": 4},
    )
    ModuleTypeFormation.objects.update_or_create(
        module=module_referentiel,
        type_formation=formation.type_formation,
        grade_cible="B",
        defaults={"volume_horaire_defaut": 8},
    )

    groupe = _creer_groupe_configure(formation, "G-VOL-PARAM", jours=[0])
    GroupeAuditeur.objects.create(groupe=groupe, auditeur=auditeur)

    FormationModule.objects.create(
        formation=formation,
        module=module_referentiel,
        volume_horaire=None,
        grade_cible="",
        site_nom="Site A",
        batiment_nom="Bat A",
        salle_nom="Salle 101",
        site_nombre=1,
        batiment_nombre=1,
        salle_nombre=1,
        date_debut=None,
        date_fin=None,
    )

    seances = PlanningService(SeanceRepository()).generer_pour_groupe(groupe.pk)
    assert len(seances) == 1
    assert seances[0].duree_minutes == 240


@pytest.mark.django_db
def test_dispatch_sans_ligne_grade_parametrage_refuse_volume_tous_grades(
    formation, module_referentiel, auditeur, formateur_general_planning
):
    """
    Si le groupe a un grade connu, le planning n'utilise pas le volume paramétré
    « tous grades » (grade_cible vide) : il faut une règle compatible avec ce grade.
    """
    from apps.parametrage.models import ModuleTypeFormation

    ModuleTypeFormation.objects.filter(
        module_id=module_referentiel.pk,
        type_formation_id=formation.type_formation_id,
    ).delete()
    ModuleTypeFormation.objects.create(
        module=module_referentiel,
        type_formation=formation.type_formation,
        grade_cible="",
        volume_horaire_defaut=4,
    )

    groupe = _creer_groupe_configure(formation, "G-VOL-TOUS-GRADES-SEUL", jours=[0])
    GroupeAuditeur.objects.create(groupe=groupe, auditeur=auditeur)

    FormationModule.objects.create(
        formation=formation,
        module=module_referentiel,
        volume_horaire=None,
        grade_cible="",
        site_nom="Site A",
        batiment_nom="Bat A",
        salle_nom="Salle 101",
        site_nombre=1,
        batiment_nombre=1,
        salle_nombre=1,
        date_debut=None,
        date_fin=None,
    )

    with pytest.raises(ValueError, match="Aucun module planifiable"):
        PlanningService(SeanceRepository()).generer_pour_groupe(groupe.pk)


@pytest.mark.django_db
def test_dispatch_volume_sur_fm_refuse_si_parametrage_uniquement_autre_grade(
    formation, module_referentiel, auditeur, formateur_general_planning
):
    """
    Un volume renseigné sur le module de formation ne doit pas forcer le dispatch
    si le paramétrage (type × module) ne définit le module que pour d'autres grades
    (ex. B3 seulement) et qu'aucune ligne « tous grades » n'existe.
    """
    from apps.parametrage.models import ModuleTypeFormation
    from apps.parametrage.services import volume_horaire_effectif_formation_module_pour_dispatch

    ModuleTypeFormation.objects.filter(
        module_id=module_referentiel.pk,
        type_formation_id=formation.type_formation_id,
    ).delete()
    ModuleTypeFormation.objects.create(
        module=module_referentiel,
        type_formation=formation.type_formation,
        grade_cible="B3",
        volume_horaire_defaut=20,
    )

    assert (
        volume_horaire_effectif_formation_module_pour_dispatch(
            module_referentiel.pk,
            20,
            formation.type_formation_id,
            "A3",
            module_referentiel.titre,
        )
        is None
    )
    assert (
        volume_horaire_effectif_formation_module_pour_dispatch(
            module_referentiel.pk,
            20,
            formation.type_formation_id,
            "B3",
            module_referentiel.titre,
        )
        == 20
    )

    groupe = _creer_groupe_configure(formation, "G-A3-VOL-FM-B3-ONLY", jours=[0])
    GroupeAuditeur.objects.create(groupe=groupe, auditeur=auditeur)

    FormationModule.objects.create(
        formation=formation,
        module=module_referentiel,
        volume_horaire=20,
        grade_cible="",
        site_nom="Site A",
        batiment_nom="Bat A",
        salle_nom="Salle 101",
        site_nombre=1,
        batiment_nombre=1,
        salle_nombre=1,
        date_debut=None,
        date_fin=None,
    )

    with pytest.raises(ValueError, match="Aucun module planifiable"):
        PlanningService(SeanceRepository()).generer_pour_groupe(groupe.pk)


@pytest.mark.django_db
class TestPlanningModeBestEffort:
    """Mode best_effort : ne lève pas au premier module en échec, continue avec les suivants."""

    def test_best_effort_continue_apres_module_non_planifiable(
        self, formation, module_referentiel, formateur_general_planning, specialite_generale
    ):
        """Un module à fenêtre invalide ne bloque pas les autres modules en best_effort."""
        groupe = _creer_groupe_configure(formation, "G-BE-1", jours=[0])  # lundi

        # Module OK : placera 4h le lundi 06/01/2025 (formation.date_debut)
        FormationModule.objects.create(
            formation=formation,
            module=module_referentiel,
            volume_horaire=4,
            site_nom="Site A",
            batiment_nom="Bat A",
            salle_nom="Salle 101",
            date_debut=None,
            date_fin=None,
        )
        # Module impossible : période d'un seul mardi (groupe actif uniquement le lundi).
        from apps.formations.models import FormationPeriode

        module_ko = Module.objects.create(titre="Module KO", specialite=specialite_generale)
        periode_ko = FormationPeriode.objects.create(
            formation=formation,
            libelle="Période KO",
            date_debut=datetime.date(2025, 1, 7),
            date_fin=datetime.date(2025, 1, 7),
            ordre=1,
        )
        FormationModule.objects.create(
            formation=formation,
            module=module_ko,
            periode=periode_ko,
            volume_horaire=4,
            site_nom="Site A",
            batiment_nom="Bat A",
            salle_nom="Salle 101",
        )

        service = PlanningService(SeanceRepository())
        seances = service.generer_pour_groupe(groupe.pk, mode="best_effort")

        assert len(seances) == 1
        assert seances[0].module_id == module_referentiel.pk
        assert len(service._derniers_echecs_modules) == 1
        echec = service._derniers_echecs_modules[0]
        assert echec["module_id"] == module_ko.pk
        assert echec["heures_restantes"] == 4
        assert "heures_placees" in echec
        assert "reason" in echec
        assert "message" in echec

    def test_strict_raise_au_premier_module_non_planifiable(
        self, formation, module_referentiel, formateur_general_planning
    ):
        """Le mode strict (défaut) conserve le comportement historique : raise."""
        from apps.formations.models import FormationPeriode

        groupe = _creer_groupe_configure(formation, "G-BE-2", jours=[0])

        periode_mardi = FormationPeriode.objects.create(
            formation=formation,
            libelle="Période mardi",
            date_debut=datetime.date(2025, 1, 7),
            date_fin=datetime.date(2025, 1, 7),
            ordre=1,
        )
        FormationModule.objects.create(
            formation=formation,
            module=module_referentiel,
            periode=periode_mardi,
            volume_horaire=4,
            site_nom="Site A",
            batiment_nom="Bat A",
            salle_nom="Salle 101",
        )

        with pytest.raises(ValueError, match="non planifiable"):
            PlanningService(SeanceRepository()).generer_pour_groupe(groupe.pk)


@pytest.mark.django_db
class TestPlanningOrdonnancementGroupes:
    """Ordonnancement des groupes par difficulté décroissante."""

    def test_ordre_par_effectif_decroissant(self, formation, auditeur, auditeur2):
        """Un groupe plus peuplé passe avant un groupe vide."""
        g_petit = _creer_groupe_configure(formation, "G-PETIT", jours=[0, 1, 2, 3, 4])
        g_grand = _creer_groupe_configure(formation, "G-GRAND", jours=[0, 1, 2, 3, 4])
        GroupeAuditeur.objects.create(groupe=g_grand, auditeur=auditeur)
        GroupeAuditeur.objects.create(groupe=g_grand, auditeur=auditeur2)

        ordre = PlanningService.ordonner_groupes_par_difficulte(formation.pk)

        assert ordre.index(g_grand.pk) < ordre.index(g_petit.pk)

    def test_ordre_penalise_peu_de_jours_actifs(self, formation):
        """À effectif égal, le groupe avec moins de jours actifs passe en premier."""
        g_5jours = _creer_groupe_configure(formation, "G-5J", jours=[0, 1, 2, 3, 4])
        g_2jours = _creer_groupe_configure(formation, "G-2J", jours=[0, 1])

        ordre = PlanningService.ordonner_groupes_par_difficulte(formation.pk)

        assert ordre.index(g_2jours.pk) < ordre.index(g_5jours.pk)


@pytest.mark.django_db
class TestPlanningRunPersistance:
    """Persistance PlanningRun par generer_pour_formation (spec §7.6)."""

    def test_planning_run_cree_termine_avec_synthese(self, formation, module_referentiel, formateur_general_planning):
        from apps.seances.models import PlanningRun

        _creer_groupe_configure(formation, "G-RUN-1", jours=[0])
        FormationModule.objects.create(
            formation=formation,
            module=module_referentiel,
            volume_horaire=4,
            site_nom="Site A",
            batiment_nom="Bat A",
            salle_nom="Salle 101",
            date_debut=None,
            date_fin=None,
        )

        rapport = PlanningService(SeanceRepository()).generer_pour_formation(formation.pk)

        assert rapport["planning_run_id"] is not None
        run = PlanningRun.objects.get(pk=rapport["planning_run_id"])
        assert run.statut == PlanningRun.Statut.TERMINE
        assert run.formation_id == formation.pk
        assert run.actor is None
        assert run.finished_at is not None
        assert run.synthese["nb_groupes"] == 1
        assert run.synthese["nb_seances_total"] >= 1
        assert isinstance(run.groupes, list)
        assert run.groupes[0]["status"] == "ok"

    def test_planning_run_serialise_dates_dans_echecs_modules(
        self, formation, module_referentiel, formateur_general_planning, specialite_generale
    ):
        """Les dates des modules en échec doivent être sérialisées en chaînes ISO dans le JSON."""
        from apps.seances.models import PlanningRun

        _creer_groupe_configure(formation, "G-RUN-2", jours=[0])
        # Module en échec : période invalide
        module_ko = Module.objects.create(titre="Module KO RUN", specialite=specialite_generale)
        FormationModule.objects.create(
            formation=formation,
            module=module_ko,
            volume_horaire=4,
            site_nom="Site A",
            batiment_nom="Bat A",
            salle_nom="Salle 101",
            date_debut=formation.date_fin,
            date_fin=formation.date_debut,  # période invalide
        )

        rapport = PlanningService(SeanceRepository()).generer_pour_formation(formation.pk)
        run = PlanningRun.objects.get(pk=rapport["planning_run_id"])

        # En base, on doit pouvoir relire le JSON sans erreur de désérialisation.
        run.refresh_from_db()
        assert any(g["status"] in {"partiel", "erreur"} for g in run.groupes) or run.groupes
        for g in run.groupes:
            for echec in g.get("echecs_modules", []):
                # JSONField : les dates doivent être des chaînes après sérialisation.
                if "module_date_debut" in echec:
                    assert isinstance(echec["module_date_debut"], str)
                if "module_date_fin" in echec:
                    assert isinstance(echec["module_date_fin"], str)

    def test_planning_run_actor_propage(
        self, formation, module_referentiel, formateur_general_planning, django_user_model
    ):
        from apps.seances.models import PlanningRun

        user = django_user_model.objects.create_user(username="planificateur", password="x")
        _creer_groupe_configure(formation, "G-RUN-3", jours=[0])
        FormationModule.objects.create(
            formation=formation,
            module=module_referentiel,
            volume_horaire=4,
            site_nom="Site A",
            batiment_nom="Bat A",
            salle_nom="Salle 101",
        )

        rapport = PlanningService(SeanceRepository()).generer_pour_formation(formation.pk, actor=user)
        run = PlanningRun.objects.get(pk=rapport["planning_run_id"])
        assert run.actor_id == user.pk

    def test_planning_run_skip_si_persister_run_false(self, formation, module_referentiel, formateur_general_planning):
        from apps.seances.models import PlanningRun

        _creer_groupe_configure(formation, "G-RUN-4", jours=[0])
        FormationModule.objects.create(
            formation=formation,
            module=module_referentiel,
            volume_horaire=4,
            site_nom="Site A",
            batiment_nom="Bat A",
            salle_nom="Salle 101",
        )

        avant = PlanningRun.objects.count()
        rapport = PlanningService(SeanceRepository()).generer_pour_formation(formation.pk, persister_run=False)
        assert rapport["planning_run_id"] is None
        assert PlanningRun.objects.count() == avant


@pytest.mark.django_db
class TestPlanningGenererPourFormation:
    """Orchestration multi-groupes au niveau d'une formation."""

    def test_rapport_contient_synthese_et_groupes(self, formation, module_referentiel, formateur_general_planning):
        """Le rapport agrège statut, séances et échecs par groupe."""
        g1 = _creer_groupe_configure(formation, "G-ALL-1", jours=[0])
        g2 = _creer_groupe_configure(formation, "G-ALL-2", jours=[0])

        FormationModule.objects.create(
            formation=formation,
            module=module_referentiel,
            volume_horaire=4,
            site_nom="Site A",
            batiment_nom="Bat A",
            salle_nom="Salle 101",
            date_debut=None,
            date_fin=None,
        )

        rapport = PlanningService(SeanceRepository()).generer_pour_formation(formation.pk, mode="best_effort")

        assert rapport["formation_id"] == formation.pk
        assert rapport["mode"] == "best_effort"
        assert set(rapport["ordre_groupes"]) == {g1.pk, g2.pk}
        assert rapport["synthese"]["nb_groupes"] == 2
        assert rapport["synthese"]["nb_groupes_ok"] >= 1
        statuts = {g["groupe_id"]: g["status"] for g in rapport["groupes"]}
        assert g1.pk in statuts
        assert g2.pk in statuts

    def test_best_effort_ne_remonte_pas_lerreur_dun_groupe(
        self, formation, module_referentiel, formateur_general_planning
    ):
        """Un groupe en échec total n'interrompt pas le traitement des autres."""
        g_ok = _creer_groupe_configure(formation, "G-OK", jours=[0])
        # Groupe sans JourCours -> ValueError "Le groupe n'est pas encore configuré"
        g_ko = Groupe.objects.create(formation=formation, nom="G-KO", max_auditeurs=25)
        ConfigGroupe.objects.create(
            groupe=g_ko,
            matin_actif=True,
            matin_heure_debut=datetime.time(8, 0),
            matin_heure_fin=datetime.time(12, 0),
            soir_actif=False,
            soir_heure_debut=datetime.time(13, 0),
            soir_heure_fin=datetime.time(17, 0),
        )

        FormationModule.objects.create(
            formation=formation,
            module=module_referentiel,
            volume_horaire=4,
            site_nom="Site A",
            batiment_nom="Bat A",
            salle_nom="Salle 101",
            date_debut=None,
            date_fin=None,
        )

        rapport = PlanningService(SeanceRepository()).generer_pour_formation(formation.pk, mode="best_effort")

        statuts = {g["groupe_id"]: g["status"] for g in rapport["groupes"]}
        assert statuts[g_ok.pk] == "ok"
        assert statuts[g_ko.pk] == "erreur"
        erreur_ko = next(g for g in rapport["groupes"] if g["groupe_id"] == g_ko.pk)
        assert erreur_ko["error"]
