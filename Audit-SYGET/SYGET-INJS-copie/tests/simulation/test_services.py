"""
Tests du service de simulation : cœur de calcul pur + extraction depuis formation (DB).
"""

import datetime
import math

import pytest

from apps.simulation.services import (
    SimulationInput,
    compter_jours_ouvres,
    estimer_date_fin,
    jours_ouvres_minimum_requis,
    simuler,
)


def _inputs_par_defaut(**overrides) -> SimulationInput:
    """Construit un input « confortable » par défaut (statut OK)."""
    base = dict(
        nb_groupes=4,
        capacite_groupe=50,
        nb_modules=5,
        heures_par_module=40,
        nb_salles=6,
        capacite_salle_moyenne=60,
        tolerance_capacite_pct=0,
        jours_ouvres=90,
        creneaux_par_jour=2,
        duree_creneau_heures=4,
        max_salles_simultanees_module=5,
    )
    base.update(overrides)
    return SimulationInput(**base)


def test_simuler_cas_confortable_renvoie_statut_ok():
    """Dimensionnement large : tout doit passer en OK."""
    result = simuler(_inputs_par_defaut())

    assert result.statut == "ok"
    assert result.nb_groupes_requis == 4  # ceil(200/50)
    assert result.creneaux_par_module_par_groupe == 10  # ceil(40/4)
    assert result.creneaux_demandes_total == 4 * 5 * 10
    assert result.groupe_tient_dans_salle is True
    assert result.module_tient_dans_periode is True
    assert all(d.niveau == "ok" for d in result.diagnostics)
    assert result.recommandations == []


def test_simuler_groupe_trop_grand_pour_salle_genere_ko_et_reco():
    """Capacité de groupe > capacité salle effective → diagnostic KO + recos."""
    result = simuler(
        _inputs_par_defaut(
            capacite_groupe=70,
            capacite_salle_moyenne=60,
            tolerance_capacite_pct=0,
        )
    )

    assert result.statut == "ko"
    assert result.groupe_tient_dans_salle is False
    capacite_diag = next(d for d in result.diagnostics if d.titre == "Capacité des salles")
    assert capacite_diag.niveau == "ko"
    assert any("Réduisez la capacité d'un groupe" in r for r in result.recommandations)


def test_simuler_tolerance_capacite_recupere_le_cas():
    """Avec une tolérance suffisante, un groupe légèrement trop grand passe en OK."""
    result = simuler(
        _inputs_par_defaut(
            capacite_groupe=63,
            capacite_salle_moyenne=60,
            tolerance_capacite_pct=10,
        )
    )

    assert result.groupe_tient_dans_salle is True
    capacite_diag = next(d for d in result.diagnostics if d.titre == "Capacité des salles")
    assert capacite_diag.niveau == "ok"


def test_simuler_parallelisme_module_insuffisant_genere_ko():
    """Trop peu de salles simultanées pour un module → diagnostic KO + recos."""
    # On force le parallélisme à 1 alors qu'il faudrait beaucoup plus.
    result = simuler(
        _inputs_par_defaut(
            nb_groupes=20,
            capacite_groupe=50,
            heures_par_module=80,
            jours_ouvres=30,
            max_salles_simultanees_module=1,
        )
    )

    assert result.module_tient_dans_periode is False
    module_diag = next(d for d in result.diagnostics if d.titre == "Planification module par module")
    assert module_diag.niveau == "ko"
    assert result.statut == "ko"
    assert any("parallélisme" in r.lower() or "salle" in r.lower() for r in result.recommandations)


def test_simuler_taux_occupation_eleve_renvoie_warning():
    """Occupation entre 80 % et 100 % → diagnostic warning + reco buffer."""
    # On dimensionne pour avoir ~90 % d'occupation : demande = 0.9 × offre.
    # Offre = 30 jours × 2 × 4 salles = 240. Demande visée ≈ 216.
    # 2 groupes × 4 modules × 27 créneaux = 216.
    result = simuler(
        _inputs_par_defaut(
            nb_groupes=2,
            capacite_groupe=50,
            nb_modules=4,
            heures_par_module=108,
            nb_salles=4,
            jours_ouvres=30,
            creneaux_par_jour=2,
            duree_creneau_heures=4,
            max_salles_simultanees_module=4,
        )
    )

    assert 0.80 <= result.taux_occupation < 1.0
    occ_diag = next(d for d in result.diagnostics if d.titre == "Occupation globale")
    assert occ_diag.niveau == "warning"
    assert result.statut == "warning"
    assert any("buffer" in r.lower() for r in result.recommandations)


def test_simuler_demande_superieure_offre_renvoie_ko_et_recos_jours_salles():
    """Plus de créneaux demandés que offerts → diagnostic KO + recommandations chiffrées."""
    result = simuler(
        _inputs_par_defaut(
            nb_groupes=40,
            jours_ouvres=10,
            nb_salles=2,
            max_salles_simultanees_module=2,
        )
    )

    assert result.taux_occupation > 1.0
    occ_diag = next(d for d in result.diagnostics if d.titre == "Occupation globale")
    assert occ_diag.niveau == "ko"
    assert result.statut == "ko"
    assert any("jour" in r.lower() for r in result.recommandations)
    assert any("salle" in r.lower() for r in result.recommandations)


def test_simulation_input_refuse_valeurs_invalides():
    """Le DTO d'entrée doit lever ValueError sur des chiffres aberrants."""
    with pytest.raises(ValueError):
        _inputs_par_defaut(nb_groupes=0)
    with pytest.raises(ValueError):
        _inputs_par_defaut(creneaux_par_jour=3)
    with pytest.raises(ValueError):
        _inputs_par_defaut(tolerance_capacite_pct=-5)


def test_simulation_borne_parallelisme_au_nombre_de_salles():
    """Si max_salles_simultanees_module > nb_salles, on est borné par nb_salles."""
    result_borne = simuler(
        _inputs_par_defaut(
            nb_salles=3,
            max_salles_simultanees_module=99,
        )
    )
    result_ref = simuler(
        _inputs_par_defaut(
            nb_salles=3,
            max_salles_simultanees_module=3,
        )
    )

    assert result_borne.creneaux_offerts_par_module == result_ref.creneaux_offerts_par_module


# ── compter_jours_ouvres ────────────────────────────────────────────────────


def test_compter_jours_ouvres_semaine_complete_lun_ven():
    """Une semaine du lundi au dimanche = 5 jours ouvrés par défaut (lun-ven)."""
    debut = datetime.date(2026, 1, 5)  # lundi
    fin = datetime.date(2026, 1, 11)  # dimanche
    assert compter_jours_ouvres(debut, fin) == 5


def test_compter_jours_ouvres_exclut_les_feries():
    """Les jours fériés actifs dans l'intervalle sont retranchés."""
    debut = datetime.date(2026, 1, 5)
    fin = datetime.date(2026, 1, 11)
    feries = {datetime.date(2026, 1, 7)}  # mercredi férié
    assert compter_jours_ouvres(debut, fin, jours_feries=feries) == 4


def test_compter_jours_ouvres_indices_personnalises():
    """Avec un planning lundi-mardi seulement, on retombe sur 2 jours."""
    debut = datetime.date(2026, 1, 5)
    fin = datetime.date(2026, 1, 11)
    assert compter_jours_ouvres(debut, fin, jours_ouvres_indices=[0, 1]) == 2


def test_compter_jours_ouvres_dates_inversees_retourne_zero():
    """date_fin < date_debut : retourne 0, pas d'erreur."""
    assert compter_jours_ouvres(datetime.date(2026, 2, 1), datetime.date(2026, 1, 1)) == 0


# ── extraire_chiffres_formation (DB) ────────────────────────────────────────


@pytest.fixture
def formation_avec_modules_et_salles(db, formation, module_referentiel):
    """Formation avec 3 modules (20h/30h/40h) + 4 salles actives de capacités variées."""
    from apps.formations.models import FormationModule
    from apps.parametrage.models import Salle
    from apps.referentiels.models import Module

    FormationModule.objects.create(formation=formation, module=module_referentiel, volume_horaire=20)
    autre_module = Module.objects.create(titre="Module B", specialite=module_referentiel.specialite)
    FormationModule.objects.create(formation=formation, module=autre_module, volume_horaire=30)
    autre_module2 = Module.objects.create(titre="Module C", specialite=module_referentiel.specialite)
    FormationModule.objects.create(formation=formation, module=autre_module2, volume_horaire=40)

    for nom, cap, actif in [("S1", 40, True), ("S2", 60, True), ("S3", 80, True), ("S4", 100, False)]:
        Salle.objects.create(nom=nom, capacite_max=cap, actif=actif)

    return formation


def test_extraire_chiffres_formation_remplit_avec_valeurs_reelles(
    formation_avec_modules_et_salles, auditeur, parametres
):
    """Les chiffres extraits doivent refléter la formation (modules, salles, période)."""
    from apps.formations.models import Inscription
    from apps.simulation.services import extraire_chiffres_formation

    formation = formation_avec_modules_et_salles
    for fm in formation.modules.all():
        Inscription.objects.create(formation=formation, formation_module=fm, auditeur=auditeur)

    chiffres = extraire_chiffres_formation(formation.pk)

    assert chiffres["nb_groupes"] == 1
    assert chiffres["capacite_groupe"] == 1
    assert chiffres["nb_modules"] == 3
    assert chiffres["heures_par_module"] == 40
    assert chiffres["nb_salles"] == 3
    assert chiffres["capacite_salle_moyenne"] == 60
    assert "jours_ouvres" not in chiffres
    assert chiffres["date_debut"] is not None
    assert chiffres["date_fin"] is not None
    assert chiffres["max_salles_simultanees_module"] == parametres.max_salles_simultanees_module
    assert chiffres["formation_ids"] == str(formation.pk)
    overrides = chiffres["_simulation_overrides"]
    duree = chiffres["duree_creneau_heures"]
    assert overrides["creneaux_demandes_total"] == sum(math.ceil(h / duree) for h in (20, 30, 40))


def test_agreger_chiffres_formations_somme_les_besoins(db, formation, module_referentiel, parametres):
    """Deux formations simultanées : séances additionnées, salles en union."""
    from apps.formations.models import FormationModule
    from apps.formations.repositories import FormationModuleRepository, FormationRepository
    from apps.formations.services import FormationService
    from apps.parametrage.models import Salle
    from apps.referentiels.models import Module
    from apps.simulation.services import agreger_chiffres_formations, simuler, SimulationInput

    for nom, cap in [("S1", 40), ("S2", 60), ("S3", 80)]:
        Salle.objects.create(nom=nom, capacite_max=cap, actif=True)

    service = FormationService(FormationRepository(), FormationModuleRepository())
    f2 = service.creer(
        type_formation_id=formation.type_formation_id,
        intitule="Formation B",
        vague="Vague 2",
        date_debut=datetime.date(2025, 2, 1),
        date_fin=datetime.date(2025, 4, 30),
    )

    FormationModule.objects.create(formation=formation, module=module_referentiel, volume_horaire=40)
    autre = Module.objects.create(titre="Module B2", specialite=module_referentiel.specialite)
    FormationModule.objects.create(formation=f2, module=autre, volume_horaire=20)

    chiffres = agreger_chiffres_formations([formation.pk, f2.pk])
    overrides = chiffres["_simulation_overrides"]

    assert chiffres["nb_groupes"] == 2
    assert chiffres["nb_modules"] == 2
    assert chiffres["nb_salles"] == 3
    assert chiffres["date_debut"] == formation.date_debut
    assert chiffres["date_fin"] == f2.date_fin
    assert len(overrides["formations_detail"]) == 2

    duree = chiffres["duree_creneau_heures"]
    creneaux_attendus = math.ceil(40 / duree) + math.ceil(20 / duree)
    assert overrides["creneaux_demandes_total"] == creneaux_attendus

    inputs = SimulationInput(
        nb_groupes=chiffres["nb_groupes"],
        capacite_groupe=chiffres["capacite_groupe"],
        nb_modules=chiffres["nb_modules"],
        heures_par_module=chiffres["heures_par_module"],
        nb_salles=chiffres["nb_salles"],
        capacite_salle_moyenne=chiffres["capacite_salle_moyenne"],
        tolerance_capacite_pct=0,
        jours_ouvres=90,
        creneaux_par_jour=chiffres["creneaux_par_jour"],
        duree_creneau_heures=duree,
        max_salles_simultanees_module=chiffres["max_salles_simultanees_module"],
    )
    result = simuler(
        inputs,
        creneaux_demandes_total_override=overrides["creneaux_demandes_total"],
        creneaux_par_module_total_override=overrides["creneaux_par_module_total"],
        nb_groupes_requis_override=overrides["nb_groupes_requis"],
        formations_detail=overrides["formations_detail"],
        nb_formations=2,
    )
    assert result.creneaux_demandes_total == creneaux_attendus
    assert result.nb_formations == 2
    assert len(result.formations_detail) == 2


def test_extraire_chiffres_formation_garantit_minimum_safe(db, formation, parametres):
    """Une formation sans module / sans salle doit quand même produire un dict valide."""
    from apps.simulation.services import extraire_chiffres_formation

    chiffres = extraire_chiffres_formation(formation.pk)

    assert chiffres["nb_groupes"] >= 1
    assert chiffres["nb_modules"] >= 1
    assert chiffres["heures_par_module"] >= 1
    assert chiffres["nb_salles"] >= 1
    assert chiffres["capacite_salle_moyenne"] >= 1
    # jours_ouvres n'est plus retourné : les dates sont fournies, le calcul se fait en vue.
    assert "jours_ouvres" not in chiffres


# ── Pré-remplissage par défaut depuis le paramétrage (vue) ──────────────────


def test_initial_depuis_parametres_lit_les_salles_et_jours(db, parametres):
    """À l'ouverture, le formulaire doit déjà refléter le paramétrage plateforme."""
    from apps.parametrage.models import Salle
    from apps.simulation.views import _initial_depuis_parametres

    Salle.objects.create(nom="A1", capacite_max=40, actif=True)
    Salle.objects.create(nom="A2", capacite_max=80, actif=True)
    Salle.objects.create(nom="A3", capacite_max=99, actif=False)  # ignorée

    parametres.jours_defaut = [0, 1, 2, 3, 4]
    parametres.save()

    initial = _initial_depuis_parametres()

    assert initial["nb_salles"] == 2
    assert initial["capacite_salle_moyenne"] == 60  # moyenne(40,80)
    # jours_ouvres N'est PAS pré-rempli pour suggérer le mode calcul auto.
    assert "jours_ouvres" not in initial
    # jours_semaine est pré-coché depuis le paramétrage.
    assert initial["jours_semaine"] == ["0", "1", "2", "3", "4"]
    assert initial["capacite_groupe"] == parametres.max_auditeurs_groupe_defaut
    assert initial["max_salles_simultanees_module"] == parametres.max_salles_simultanees_module


# ── jours_ouvres_minimum & date de fin estimée ─────────────────────────────


def test_simuler_calcule_jours_ouvres_minimum_global_et_module():
    """jours_ouvres_minimum doit être le max entre contrainte globale et contrainte module."""
    result = simuler(_inputs_par_defaut())

    # Cas confortable : 4 groupes × 5 modules × 10 créneaux = 200 demandés
    # Capacité globale = 2 × 6 = 12 / jour → 17 jours min globaux
    # Capacité module  = 2 × 5 = 10 / jour, créneaux/module = 4 × 10 = 40 → 4 jours min
    assert result.jours_ouvres_minimum == 17


def test_simuler_avec_date_debut_calcule_date_fin_estimee():
    """Si date_debut + paramétrage fournis, la date de fin est calculée."""
    debut = datetime.date(2026, 1, 5)  # lundi
    result = simuler(
        _inputs_par_defaut(),
        date_debut=debut,
        jours_ouvres_indices=[0, 1, 2, 3, 4],
        jours_feries=set(),
    )

    assert result.date_debut == debut
    assert result.date_fin_estimee is not None
    assert result.jours_ouvres_minimum == 17
    # 17 jours ouvrés à partir du 5/1/2026 (lundi, sans fériés, lun-ven) :
    # semaine 1 (5-9), semaine 2 (12-16), semaine 3 (19-23), 2 jours en semaine 4 (26-27)
    assert result.date_fin_estimee == datetime.date(2026, 1, 27)
    assert result.jours_calendaires_estimes == 23


def test_simuler_sans_date_debut_renvoie_date_fin_none():
    """Sans date_debut, date_fin_estimee reste None."""
    result = simuler(_inputs_par_defaut())
    assert result.date_debut is None
    assert result.date_fin_estimee is None
    assert result.jours_calendaires_estimes is None


def test_simuler_date_fin_respecte_jours_feries():
    """Les jours fériés actifs dans la période sont sautés et reportent la fin."""
    debut = datetime.date(2026, 1, 5)  # lundi
    feries = {datetime.date(2026, 1, 7), datetime.date(2026, 1, 8)}  # mer + jeu
    result = simuler(
        _inputs_par_defaut(),
        date_debut=debut,
        jours_ouvres_indices=[0, 1, 2, 3, 4],
        jours_feries=feries,
    )

    # 17 jours ouvrés - les fériés mer/jeu sont sautés donc la fin est reportée de 2 jours.
    assert result.date_fin_estimee == datetime.date(2026, 1, 29)


def test_estimer_date_fin_retourne_date_debut_si_aucun_jour_requis():
    """jours_ouvres_requis = 0 → on retourne directement la date de début."""
    debut = datetime.date(2026, 1, 5)
    assert estimer_date_fin(debut, 0) == debut


def test_estimer_date_fin_retourne_none_si_aucun_jour_ouvre():
    """Aucun jour de la semaine actif → on ne peut pas estimer."""
    debut = datetime.date(2026, 1, 5)
    assert estimer_date_fin(debut, 5, jours_ouvres_indices=[]) is None


def test_initial_depuis_parametres_sans_salle_garde_valeurs_safe(db, parametres):
    """Aucune salle active configurée : on retombe sur des valeurs sûres (≥ 1)."""
    from apps.simulation.views import _initial_depuis_parametres

    parametres.jours_defaut = []
    parametres.save()

    initial = _initial_depuis_parametres()

    assert initial["nb_salles"] >= 1
    assert initial["capacite_salle_moyenne"] >= 1
    # Pas de jours_defaut → on retombe sur lundi-vendredi.
    assert initial["jours_semaine"] == ["0", "1", "2", "3", "4"]
    assert "jours_ouvres" not in initial


# ── Mode « calcul automatique » : jours_ouvres déduit du minimum requis ─────


def test_jours_ouvres_minimum_requis_est_pure_et_independant_de_jours_ouvres():
    """La fonction calcule la durée min sans avoir besoin de connaître jours_ouvres."""
    minimum = jours_ouvres_minimum_requis(
        nb_groupes=4,
        nb_modules=5,
        heures_par_module=40,
        nb_salles=6,
        creneaux_par_jour=2,
        duree_creneau_heures=4,
        max_salles_simultanees_module=5,
    )
    # Cf. test_simuler_calcule_jours_ouvres_minimum_global_et_module : 17 jours.
    assert minimum == 17


def test_simuler_mode_auto_neutralise_le_diagnostic_doccupation():
    """En mode auto, le diag « Occupation globale » est omis (sinon faux warning)."""
    inputs = _inputs_par_defaut(jours_ouvres=17)  # = minimum requis pour ce cas
    result = simuler(inputs, mode_auto=True)

    titres = [d.titre for d in result.diagnostics]
    assert "Occupation globale" not in titres
    assert result.statut == "ok"
    assert not any("buffer" in r.lower() for r in result.recommandations)


def test_simuler_sans_mode_auto_conserve_le_diagnostic_doccupation():
    """Sans mode auto, le diag « Occupation globale » est toujours présent."""
    inputs = _inputs_par_defaut(jours_ouvres=17)
    result = simuler(inputs, mode_auto=False)

    titres = [d.titre for d in result.diagnostics]
    assert "Occupation globale" in titres


def test_jours_ouvres_minimum_requis_borne_au_parallelisme_nb_salles():
    """Si max_salles_simultanees_module > nb_salles, on est borné par nb_salles."""
    # Avec 1 seule salle, on est forcément limité même si max=99.
    minimum = jours_ouvres_minimum_requis(
        nb_groupes=4,
        nb_modules=3,
        heures_par_module=20,
        nb_salles=1,
        creneaux_par_jour=2,
        duree_creneau_heures=4,
        max_salles_simultanees_module=99,
    )
    # 4 groupes × 3 modules × 5 créneaux = 60 demandés, 1 salle × 2 créneaux/jour
    # → ⌈60/2⌉ = 30 jours globaux ; module : 4×5 = 20 créneaux, ⌈20/2⌉ = 10 jours
    assert minimum == 30
