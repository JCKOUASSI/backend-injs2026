"""
Service de simulation (dimensionnement).

Cœur de calcul (`simuler`) en pur Python sans accès base : verdict de faisabilité
à partir des chiffres saisis + recommandations correctives en cas de goulot.

`extraire_chiffres_formation` réutilise une `Formation` existante pour pré-remplir
le formulaire avec des valeurs réelles (auditeurs, modules, salles, période).
"""

from __future__ import annotations

import datetime
import math
from dataclasses import dataclass, field
from typing import Literal

DiagnosticNiveau = Literal["ok", "warning", "ko"]
Statut = Literal["ok", "warning", "ko"]
_STATUT_PIRE = {"ok": 0, "warning": 1, "ko": 2}


@dataclass(frozen=True)
class SimulationInput:
    """Chiffres de dimensionnement saisis par l'utilisateur."""

    nb_groupes: int
    capacite_groupe: int
    nb_modules: int
    heures_par_module: int
    nb_salles: int
    capacite_salle_moyenne: int
    tolerance_capacite_pct: int
    jours_ouvres: int
    creneaux_par_jour: int
    duree_creneau_heures: int
    max_salles_simultanees_module: int

    def __post_init__(self) -> None:
        for nom, val in self._champs_positifs():
            if val <= 0:
                raise ValueError(f"{nom} doit être strictement positif (reçu {val}).")
        if self.tolerance_capacite_pct < 0:
            raise ValueError("La tolérance de capacité ne peut pas être négative.")
        if self.creneaux_par_jour not in (1, 2):
            raise ValueError("Le nombre de créneaux par jour doit être 1 ou 2.")
        if self.max_salles_simultanees_module > self.nb_salles:
            # Garde-fou silencieux : la valeur effective sera bornée par nb_salles.
            pass

    def _champs_positifs(self):
        return [
            ("nb_groupes", self.nb_groupes),
            ("capacite_groupe", self.capacite_groupe),
            ("nb_modules", self.nb_modules),
            ("heures_par_module", self.heures_par_module),
            ("nb_salles", self.nb_salles),
            ("capacite_salle_moyenne", self.capacite_salle_moyenne),
            ("jours_ouvres", self.jours_ouvres),
            ("duree_creneau_heures", self.duree_creneau_heures),
            ("max_salles_simultanees_module", self.max_salles_simultanees_module),
        ]


@dataclass(frozen=True)
class Diagnostic:
    """Un contrôle de faisabilité."""

    titre: str
    niveau: DiagnosticNiveau
    message: str


@dataclass(frozen=True)
class FormationSimulationDetail:
    """Détail des besoins pour une formation dans une simulation multi-formations."""

    formation_id: int
    intitule: str
    nb_auditeurs: int
    nb_groupes: int
    nb_modules: int
    creneaux_demandes: int
    creneaux_par_module_total_max: int


@dataclass(frozen=True)
class SimulationResult:
    """Résultat brut + diagnostic + recommandations."""

    inputs: SimulationInput
    # KPI principaux
    nb_groupes_requis: int
    creneaux_par_module_par_groupe: int
    creneaux_demandes_total: int
    creneaux_offerts_total: int
    taux_occupation: float
    # Capacité salle
    capacite_salle_effective: int
    groupe_tient_dans_salle: bool
    # Parallélisme module
    creneaux_par_module_total: int
    creneaux_offerts_par_module: int
    module_tient_dans_periode: bool
    # Estimation temporelle (toujours calculée)
    jours_ouvres_minimum: int
    # Minimum recommandé = plancher strict × 1,2 (marge pour contraintes réelles :
    # salles partagées entre groupes, formateurs, rythme mensuel, périodes de module…).
    # C'est la valeur à utiliser comme « Jours de cours disponibles » pour qu'une
    # génération réelle aboutisse.
    jours_ouvres_recommandes: int
    # Estimation calendaire (calculée seulement si une date de début + paramétrage fournis)
    date_debut: datetime.date | None = None
    date_fin_estimee: datetime.date | None = None
    jours_calendaires_estimes: int | None = None
    nb_formations: int = 1
    formations_detail: list[FormationSimulationDetail] = field(default_factory=list)
    # Verdict
    statut: Statut = "ok"
    diagnostics: list[Diagnostic] = field(default_factory=list)
    recommandations: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SimulationLigneResultat:
    """Résultat de simulation pour une formation (paramètres propres)."""

    intitule: str
    formation_id: int | None
    resultat: SimulationResult
    mode_auto: bool
    jours_ouvres_periode: int | None
    periode_suffisante: bool | None
    date_fin_proposee: datetime.date | None
    nb_jours_semaine: int
    semaines_recommandees: float | None


@dataclass(frozen=True)
class SimulationSynthese:
    """Vue d'ensemble lorsque plusieurs formations sont simulées en parallèle."""

    statut: Statut
    nb_formations: int
    nb_ok: int
    nb_warning: int
    nb_ko: int
    creneaux_demandes_total: int
    nb_salles_partagees: int | None = None
    taux_occupation_salles_partagees: float | None = None
    message_salles_partagees: str | None = None


def _pire_statut(a: Statut, b: Statut) -> Statut:
    return a if _STATUT_PIRE[a] >= _STATUT_PIRE[b] else b


def synthese_simulations(lignes: list[SimulationLigneResultat]) -> SimulationSynthese | None:
    """Construit la synthèse multi-formations (verdict global + salles partagées)."""
    if not lignes:
        return None
    if len(lignes) == 1:
        r = lignes[0].resultat
        return SimulationSynthese(
            statut=r.statut,
            nb_formations=1,
            nb_ok=1 if r.statut == "ok" else 0,
            nb_warning=1 if r.statut == "warning" else 0,
            nb_ko=1 if r.statut == "ko" else 0,
            creneaux_demandes_total=r.creneaux_demandes_total,
        )

    statut: Statut = "ok"
    nb_ok = nb_warning = nb_ko = 0
    creneaux_total = 0
    formation_ids: list[int] = []
    for ligne in lignes:
        statut = _pire_statut(statut, ligne.resultat.statut)
        creneaux_total += ligne.resultat.creneaux_demandes_total
        if ligne.resultat.statut == "ok":
            nb_ok += 1
        elif ligne.resultat.statut == "warning":
            nb_warning += 1
        else:
            nb_ko += 1
        if ligne.formation_id:
            formation_ids.append(ligne.formation_id)

    nb_salles_partagees = None
    taux_partage = None
    message = None
    if formation_ids:
        from apps.formations.models import Formation

        formations = list(Formation.objects.filter(pk__in=formation_ids).prefetch_related("modules__module"))
        if formations:
            nb_salles_partagees, _ = _pool_salles_union_formations(formations)
            jours_min = min((ligne.resultat.jours_ouvres_minimum for ligne in lignes), default=1)
            creneaux_par_jour = max((ligne.resultat.inputs.creneaux_par_jour for ligne in lignes), default=2)
            offre = max(1, jours_min * creneaux_par_jour * nb_salles_partagees)
            taux_partage = creneaux_total / offre
            if taux_partage >= _SEUIL_OCC_KO:
                statut = _pire_statut(statut, "ko")
                message = (
                    f"Les {len(lignes)} formations mobilisent {creneaux_total} séances cumulées "
                    f"sur un pool partagé de {nb_salles_partagees} salle(s) "
                    f"(occupation estimée {taux_partage:.0%} — capacité insuffisante)."
                )
            elif taux_partage >= _SEUIL_OCC_WARNING:
                statut = _pire_statut(statut, "warning")
                message = (
                    f"Pool de salles partagé très sollicité ({taux_partage:.0%}) " f"entre les formations simultanées."
                )

    return SimulationSynthese(
        statut=statut,
        nb_formations=len(lignes),
        nb_ok=nb_ok,
        nb_warning=nb_warning,
        nb_ko=nb_ko,
        creneaux_demandes_total=creneaux_total,
        nb_salles_partagees=nb_salles_partagees,
        taux_occupation_salles_partagees=taux_partage,
        message_salles_partagees=message,
    )


# Seuils pour le diagnostic d'occupation globale.
_SEUIL_OCC_WARNING = 0.80
_SEUIL_OCC_KO = 1.0


def simuler(
    inputs: SimulationInput,
    *,
    date_debut: datetime.date | None = None,
    jours_ouvres_indices: list[int] | tuple[int, ...] | None = None,
    jours_feries: set[datetime.date] | None = None,
    mode_auto: bool = False,
    marge_pct: int = 20,
    creneaux_demandes_total_override: int | None = None,
    creneaux_par_module_total_override: int | None = None,
    nb_groupes_requis_override: int | None = None,
    creneaux_par_module_par_groupe_override: int | None = None,
    formations_detail: list[FormationSimulationDetail] | None = None,
    nb_formations: int = 1,
) -> SimulationResult:
    """Calcule les indicateurs de faisabilité + recommandations.

    Si `date_debut` est fourni, calcule en plus la date de fin estimée
    correspondant aux `jours_ouvres_minimum` requis, en respectant les jours
    ouvrés (`jours_ouvres_indices`) et les jours fériés (`jours_feries`).

    Si `mode_auto=True` (l'utilisateur n'a pas saisi de plage temporelle et
    on a retenu le minimum requis comme `jours_ouvres`), le diagnostic
    d'occupation globale est neutralisé : par construction la demande colle
    à l'offre, donc le taux est mécaniquement proche de 100 % et n'a pas de
    valeur informative.

    `marge_pct` (défaut 20) : pourcentage de marge ajouté au plancher théorique
    pour obtenir le minimum recommandé. Configurable via ParametreGeneral.
    """
    nb_groupes_requis = nb_groupes_requis_override if nb_groupes_requis_override is not None else inputs.nb_groupes
    creneaux_par_module_par_groupe = (
        creneaux_par_module_par_groupe_override
        if creneaux_par_module_par_groupe_override is not None
        else math.ceil(inputs.heures_par_module / inputs.duree_creneau_heures)
    )
    if creneaux_demandes_total_override is not None:
        creneaux_demandes_total = creneaux_demandes_total_override
    else:
        creneaux_demandes_total = nb_groupes_requis * inputs.nb_modules * creneaux_par_module_par_groupe
    creneaux_offerts_total = inputs.jours_ouvres * inputs.creneaux_par_jour * inputs.nb_salles
    taux_occupation = creneaux_demandes_total / creneaux_offerts_total if creneaux_offerts_total > 0 else float("inf")

    capacite_salle_effective = int(round(inputs.capacite_salle_moyenne * (1 + inputs.tolerance_capacite_pct / 100)))
    groupe_tient_dans_salle = inputs.capacite_groupe <= capacite_salle_effective

    if creneaux_par_module_total_override is not None:
        creneaux_par_module_total = creneaux_par_module_total_override
    else:
        creneaux_par_module_total = nb_groupes_requis * creneaux_par_module_par_groupe
    salles_simultanees_effectives = min(inputs.max_salles_simultanees_module, inputs.nb_salles)
    creneaux_offerts_par_module = inputs.jours_ouvres * inputs.creneaux_par_jour * salles_simultanees_effectives
    module_tient_dans_periode = creneaux_par_module_total <= creneaux_offerts_par_module

    diagnostics, recommandations, statut = _diagnostiquer(
        inputs=inputs,
        nb_groupes_requis=nb_groupes_requis,
        creneaux_par_module_par_groupe=creneaux_par_module_par_groupe,
        creneaux_demandes_total=creneaux_demandes_total,
        creneaux_offerts_total=creneaux_offerts_total,
        taux_occupation=taux_occupation,
        capacite_salle_effective=capacite_salle_effective,
        groupe_tient_dans_salle=groupe_tient_dans_salle,
        creneaux_par_module_total=creneaux_par_module_total,
        creneaux_offerts_par_module=creneaux_offerts_par_module,
        module_tient_dans_periode=module_tient_dans_periode,
        salles_simultanees_effectives=salles_simultanees_effectives,
        mode_auto=mode_auto,
    )

    jours_ouvres_minimum = jours_ouvres_minimum_requis(
        nb_groupes=nb_groupes_requis,
        nb_modules=inputs.nb_modules,
        heures_par_module=inputs.heures_par_module,
        nb_salles=inputs.nb_salles,
        creneaux_par_jour=inputs.creneaux_par_jour,
        duree_creneau_heures=inputs.duree_creneau_heures,
        max_salles_simultanees_module=inputs.max_salles_simultanees_module,
        creneaux_demandes_total=creneaux_demandes_total_override,
        creneaux_par_module_total=creneaux_par_module_total_override,
    )
    # Minimum recommandé : plancher théorique + marge_pct % pour absorber les contraintes
    # réelles non modélisées (salles figées après 1er choix, rythme mensuel, fenêtres module,
    # formations concurrentes sur les mêmes salles, jours fériés imprévus…).
    # La marge est configurable dans ParametreGeneral.marge_simulation_pct (défaut 20 %).
    # Avec un nb_salles correctement calculé par site/module, 5–10 % suffisent souvent.
    marge_effective = max(0, int(marge_pct))
    jours_ouvres_recommandes = math.ceil(jours_ouvres_minimum * (1 + marge_effective / 100))

    # En mode auto on a simulé avec jours_ouvres_recommandes (passé depuis la vue)
    # donc la date de fin estimée doit correspondre à cette valeur, pas au plancher strict.
    jours_pour_date_fin = jours_ouvres_recommandes if mode_auto else jours_ouvres_minimum

    date_fin = None
    jours_calendaires = None
    if date_debut is not None:
        date_fin = estimer_date_fin(date_debut, jours_pour_date_fin, jours_ouvres_indices, jours_feries)
        if date_fin is not None:
            jours_calendaires = (date_fin - date_debut).days + 1

    return SimulationResult(
        inputs=inputs,
        nb_formations=nb_formations,
        formations_detail=list(formations_detail or ()),
        nb_groupes_requis=nb_groupes_requis,
        creneaux_par_module_par_groupe=creneaux_par_module_par_groupe,
        creneaux_demandes_total=creneaux_demandes_total,
        creneaux_offerts_total=creneaux_offerts_total,
        taux_occupation=taux_occupation,
        capacite_salle_effective=capacite_salle_effective,
        groupe_tient_dans_salle=groupe_tient_dans_salle,
        creneaux_par_module_total=creneaux_par_module_total,
        creneaux_offerts_par_module=creneaux_offerts_par_module,
        module_tient_dans_periode=module_tient_dans_periode,
        jours_ouvres_minimum=jours_ouvres_minimum,
        jours_ouvres_recommandes=jours_ouvres_recommandes,
        date_debut=date_debut,
        date_fin_estimee=date_fin,
        jours_calendaires_estimes=jours_calendaires,
        statut=statut,
        diagnostics=diagnostics,
        recommandations=recommandations,
    )


def _diagnostiquer(
    *,
    inputs: SimulationInput,
    nb_groupes_requis: int,
    creneaux_par_module_par_groupe: int,
    creneaux_demandes_total: int,
    creneaux_offerts_total: int,
    taux_occupation: float,
    capacite_salle_effective: int,
    groupe_tient_dans_salle: bool,
    creneaux_par_module_total: int,
    creneaux_offerts_par_module: int,
    module_tient_dans_periode: bool,
    salles_simultanees_effectives: int,
    mode_auto: bool = False,
) -> tuple[list[Diagnostic], list[str], Statut]:
    """Construit la liste des contrôles et la liste de recommandations."""
    diagnostics: list[Diagnostic] = []
    recommandations: list[str] = []

    if groupe_tient_dans_salle:
        diagnostics.append(
            Diagnostic(
                titre="Capacité des salles",
                niveau="ok",
                message=(
                    f"Un groupe de {inputs.capacite_groupe} auditeurs tient dans une salle "
                    f"de {inputs.capacite_salle_moyenne} (+{inputs.tolerance_capacite_pct}\u00a0% "
                    f"= {capacite_salle_effective})."
                ),
            )
        )
    else:
        manque = inputs.capacite_groupe - capacite_salle_effective
        diagnostics.append(
            Diagnostic(
                titre="Capacité des salles",
                niveau="ko",
                message=(
                    f"Un groupe de {inputs.capacite_groupe} dépasse la capacité salle "
                    f"de {manque} auditeur(s) "
                    f"(capacité effective\u00a0: {capacite_salle_effective})."
                ),
            )
        )
        capacite_cible = capacite_salle_effective
        recommandations.append(f"Réduisez la capacité d'un groupe à {capacite_cible} auditeurs ou moins.")
        recommandations.append(f"Ou choisissez des salles d'au moins {inputs.capacite_groupe} places.")
        tolerance_necessaire = (
            math.ceil((inputs.capacite_groupe / inputs.capacite_salle_moyenne - 1) * 100)
            if inputs.capacite_salle_moyenne > 0
            else 0
        )
        if 0 < tolerance_necessaire <= 30:
            recommandations.append(
                f"Ou augmentez la tolérance de capacité salle à {tolerance_necessaire}\u00a0% "
                "(à utiliser avec prudence)."
            )

    if module_tient_dans_periode:
        marge = creneaux_offerts_par_module - creneaux_par_module_total
        diagnostics.append(
            Diagnostic(
                titre="Planification module par module",
                niveau="ok",
                message=(
                    f"Chaque module a {creneaux_offerts_par_module} créneaux disponibles "
                    f"pour {creneaux_par_module_total} demandés (marge\u00a0: {marge})."
                ),
            )
        )
    else:
        manque = creneaux_par_module_total - creneaux_offerts_par_module
        diagnostics.append(
            Diagnostic(
                titre="Planification module par module",
                niveau="ko",
                message=(
                    f"Un module demande {creneaux_par_module_total} créneaux mais seulement "
                    f"{creneaux_offerts_par_module} sont disponibles "
                    f"(parallélisme limité à {salles_simultanees_effectives} salles). "
                    f"Manque\u00a0: {manque} créneaux."
                ),
            )
        )
        jours_a_ajouter = math.ceil(manque / (inputs.creneaux_par_jour * salles_simultanees_effectives))
        recommandations.append(f"Allongez la période de {jours_a_ajouter} jour(s) ouvré(s) supplémentaire(s).")
        if salles_simultanees_effectives < inputs.nb_salles:
            recommandations.append(
                f"Ou augmentez le parallélisme module de {salles_simultanees_effectives} "
                f"à {inputs.nb_salles} salles simultanées (paramètre "
                f"\u00ab\u00a0max_salles_simultanees_module\u00a0\u00bb)."
            )
        else:
            salles_a_ajouter = math.ceil(manque / (inputs.jours_ouvres * inputs.creneaux_par_jour))
            recommandations.append(f"Ou ajoutez {salles_a_ajouter} salle(s) supplémentaire(s).")

    # En mode calcul automatique, l'utilisateur n'a pas saisi de plage
    # temporelle : on a retenu le minimum strict requis comme `jours_ouvres`.
    # La demande colle alors par construction à l'offre (taux ~100 %), donc
    # ce diagnostic n'apporterait aucune information utile et serait même
    # trompeur (warning systématique « Faisable mais tendue »). On le saute.
    if mode_auto:
        pass
    elif taux_occupation < _SEUIL_OCC_WARNING:
        diagnostics.append(
            Diagnostic(
                titre="Occupation globale",
                niveau="ok",
                message=(
                    f"Taux d'occupation\u00a0: {taux_occupation:.0%} "
                    f"({creneaux_demandes_total} créneaux demandés / "
                    f"{creneaux_offerts_total} offerts)."
                ),
            )
        )
    elif taux_occupation < _SEUIL_OCC_KO:
        diagnostics.append(
            Diagnostic(
                titre="Occupation globale",
                niveau="warning",
                message=(
                    f"Taux d'occupation élevé\u00a0: {taux_occupation:.0%}. "
                    "Très peu de marge en cas d'imprévu (absence formateur, salle indisponible)."
                ),
            )
        )
        recommandations.append("Prévoyez un buffer de 10 à 20\u00a0% (jours ou salles) pour absorber les imprévus.")
    else:
        depassement = (
            (creneaux_demandes_total - creneaux_offerts_total)
            if math.isfinite(taux_occupation)
            else creneaux_demandes_total
        )
        diagnostics.append(
            Diagnostic(
                titre="Occupation globale",
                niveau="ko",
                message=(
                    f"Demande supérieure à l'offre\u00a0: {taux_occupation:.0%} " f"(manque {depassement} créneau(x))."
                ),
            )
        )
        if inputs.jours_ouvres > 0:
            jours_supp = math.ceil(depassement / (inputs.creneaux_par_jour * inputs.nb_salles))
            recommandations.append(f"Allongez globalement la période de {jours_supp} jour(s) ouvré(s).")
        salles_supp = math.ceil(depassement / max(1, inputs.jours_ouvres * inputs.creneaux_par_jour))
        recommandations.append(f"Ou ajoutez {salles_supp} salle(s) au pool.")
        if inputs.creneaux_par_jour == 1:
            recommandations.append("Ou activez le second créneau (matin\u00a0+\u00a0soir) si l'organisation le permet.")

    if any(d.niveau == "ko" for d in diagnostics):
        statut: Statut = "ko"
    elif any(d.niveau == "warning" for d in diagnostics):
        statut = "warning"
    else:
        statut = "ok"

    return diagnostics, recommandations, statut


_JOURS_OUVRES_DEFAUT = (0, 1, 2, 3, 4)


def jours_ouvres_minimum_requis(
    *,
    nb_groupes: int,
    nb_modules: int,
    heures_par_module: int,
    nb_salles: int,
    creneaux_par_jour: int,
    duree_creneau_heures: int,
    max_salles_simultanees_module: int,
    creneaux_demandes_total: int | None = None,
    creneaux_par_module_total: int | None = None,
) -> int:
    """Plus petit nombre de jours ouvrés permettant de tout planifier.

    Respecte les deux contraintes : occupation globale (toutes salles) ET
    parallélisme module (au plus `max_salles_simultanees_module` salles
    travaillant simultanément sur un même module).

    Pure fonction sans dépendance à `jours_ouvres` : utilisée pour le mode
    « calcul automatique » de la simulation, où l'utilisateur ne saisit pas
    la durée disponible et veut que le système la déduise.
    """
    salles_sim = min(max_salles_simultanees_module, nb_salles)
    capacite_jour_globale = max(1, creneaux_par_jour * nb_salles)
    capacite_jour_module = max(1, creneaux_par_jour * salles_sim)

    if creneaux_demandes_total is None:
        creneaux_par_module = math.ceil(heures_par_module / duree_creneau_heures)
        creneaux_demandes_total = nb_groupes * nb_modules * creneaux_par_module
    if creneaux_par_module_total is None:
        creneaux_par_module = math.ceil(heures_par_module / duree_creneau_heures)
        creneaux_par_module_total = nb_groupes * creneaux_par_module

    jours_min_global = math.ceil(creneaux_demandes_total / capacite_jour_globale)
    jours_min_module = math.ceil(creneaux_par_module_total / capacite_jour_module)
    return max(jours_min_global, jours_min_module)


def compter_jours_ouvres(
    date_debut: datetime.date,
    date_fin: datetime.date,
    jours_ouvres_indices: list[int] | tuple[int, ...] | None = None,
    jours_feries: set[datetime.date] | None = None,
) -> int:
    """Compte les jours ouvrables entre deux dates (bornes incluses).

    `jours_ouvres_indices` suit la convention `weekday()` : 0=lundi … 6=dimanche.
    """
    if date_fin < date_debut:
        return 0
    indices = tuple(jours_ouvres_indices) if jours_ouvres_indices else _JOURS_OUVRES_DEFAUT
    feries = jours_feries or set()
    cur = date_debut
    nb = 0
    one_day = datetime.timedelta(days=1)
    while cur <= date_fin:
        if cur.weekday() in indices and cur not in feries:
            nb += 1
        cur += one_day
    return nb


# Garde-fou : si aucun jour de la semaine n'est ouvré, on évite la boucle infinie.
_MAX_JOURS_RECHERCHE = 365 * 10  # 10 ans


def estimer_date_fin(
    date_debut: datetime.date,
    jours_ouvres_requis: int,
    jours_ouvres_indices: list[int] | tuple[int, ...] | None = None,
    jours_feries: set[datetime.date] | None = None,
) -> datetime.date | None:
    """Retourne la dernière date à atteindre pour totaliser `jours_ouvres_requis`.

    Si `jours_ouvres_requis <= 0`, retourne `date_debut`.
    Si `jours_ouvres_indices` est explicitement vide (configuration absurde où
    aucun jour de la semaine n'est ouvré), retourne None plutôt que de boucler.
    Si `jours_ouvres_indices is None`, on retombe sur lundi-vendredi par défaut.
    """
    if jours_ouvres_requis <= 0:
        return date_debut
    if jours_ouvres_indices is None:
        indices: tuple[int, ...] = _JOURS_OUVRES_DEFAUT
    else:
        indices = tuple(jours_ouvres_indices)
    if not indices:
        return None
    feries = jours_feries or set()
    cur = date_debut
    compte = 0
    one_day = datetime.timedelta(days=1)
    for _ in range(_MAX_JOURS_RECHERCHE):
        if cur.weekday() in indices and cur not in feries:
            compte += 1
            if compte >= jours_ouvres_requis:
                return cur
        cur += one_day
    return None


def _volume_horaire_formation_module(fm, type_formation_id: int | None) -> int:
    """Volume horaire effectif d'un module de formation (heures)."""
    from apps.parametrage.models import ModuleTypeFormation

    if fm.volume_horaire is not None:
        return int(fm.volume_horaire)
    if type_formation_id:
        mtf_vols = list(
            ModuleTypeFormation.objects.filter(
                module_id=fm.module_id,
                type_formation_id=type_formation_id,
            ).values_list("volume_horaire_defaut", flat=True)
        )
        if mtf_vols:
            return max(mtf_vols)
    return 20


def _salles_ids_pour_formation_module(fm, salles_globales_ids: list[int]) -> list[int]:
    """Identifiants des salles actives mobilisables pour un module."""
    from apps.parametrage.models import Salle

    site_nom = (fm.site_nom or "").strip()
    batiment_nom = (fm.batiment_nom or "").strip()
    if site_nom:
        qs = Salle.objects.filter(actif=True, batiment__site__nom__iexact=site_nom)
        if batiment_nom:
            qs = qs.filter(batiment__nom__iexact=batiment_nom)
        return list(qs.values_list("pk", flat=True))
    return salles_globales_ids


def _pool_salles_union_formations(formations) -> tuple[int, int]:
    """Union des salles mobilisées par plusieurs formations simultanées."""
    from apps.parametrage.models import Salle

    salles_globales_ids = list(Salle.objects.filter(actif=True).values_list("pk", flat=True))
    salle_ids: set[int] = set()
    for formation in formations:
        for fm in formation.modules.all():
            salle_ids.update(_salles_ids_pour_formation_module(fm, salles_globales_ids))

    if salle_ids:
        caps = list(Salle.objects.filter(pk__in=salle_ids, actif=True).values_list("capacite_max", flat=True))
    else:
        caps = list(Salle.objects.filter(actif=True).values_list("capacite_max", flat=True))

    nb_salles = len(caps) or 1
    capacite_moyenne = max(1, round(sum(caps) / len(caps))) if caps else 25
    return nb_salles, capacite_moyenne


def _groupes_effectifs_formation(formation, capacite_groupe: int) -> tuple[int, int]:
    """Retourne (nb_groupes, auditeurs_par_groupe) pour une formation.

    Si des groupes pédagogiques existent, on reprend leur nombre et l'effectif
    le plus contraignant (membres réels, sinon plafond du groupe).
    Sinon, on déduit nb_groupes et auditeurs_par_groupe depuis les inscrits.
    """
    from django.db.models import Count

    from apps.groupes.models import Groupe

    groupes = list(Groupe.objects.filter(formation_id=formation.pk).annotate(_nb_membres=Count("membres")))
    if groupes:
        effectifs = []
        for g in groupes:
            n = g._nb_membres
            effectifs.append(n if n > 0 else g.max_auditeurs)
        return len(groupes), max(effectifs)

    nb_inscrits = formation.nb_inscrits or 1
    cap = max(1, capacite_groupe)
    nb_groupes = max(1, math.ceil(nb_inscrits / cap))
    auditeurs_par_groupe = nb_inscrits if nb_groupes == 1 else cap
    return nb_groupes, auditeurs_par_groupe


def _besoins_creneaux_formation(
    formation,
    capacite_groupe: int,
    duree_creneau_heures: int,
) -> FormationSimulationDetail:
    """Calcule les besoins en créneaux pour une formation (volumes réels par module)."""
    nb_groupes, auditeurs_par_groupe = _groupes_effectifs_formation(formation, capacite_groupe)
    nb_auditeurs = nb_groupes * auditeurs_par_groupe
    creneaux_demandes = 0
    creneaux_par_module_total_max = 0
    heures_max = 1

    for fm in formation.modules.all():
        heures = _volume_horaire_formation_module(fm, formation.type_formation_id)
        heures_max = max(heures_max, heures)
        creneaux_module = math.ceil(heures / duree_creneau_heures)
        creneaux_module_total = nb_groupes * creneaux_module
        creneaux_demandes += creneaux_module_total
        creneaux_par_module_total_max = max(creneaux_par_module_total_max, creneaux_module_total)

    nb_modules = formation.modules.count()
    if nb_modules == 0:
        creneaux_module = math.ceil(heures_max / duree_creneau_heures)
        creneaux_demandes = nb_groupes * creneaux_module
        creneaux_par_module_total_max = creneaux_demandes
        nb_modules = 1

    return FormationSimulationDetail(
        formation_id=formation.pk,
        intitule=formation.intitule,
        nb_auditeurs=nb_auditeurs,
        nb_groupes=nb_groupes,
        nb_modules=max(1, nb_modules),
        creneaux_demandes=creneaux_demandes,
        creneaux_par_module_total_max=creneaux_par_module_total_max,
    )


def calculer_besoins_formations(
    formation_ids: list[int],
    capacite_groupe: int,
    duree_creneau_heures: int,
) -> tuple[list[FormationSimulationDetail], int, int, int]:
    """Agrège les besoins en créneaux pour plusieurs formations simultanées.

    Retourne (détails par formation, créneaux total, max créneaux/module, nb groupes total).
    """
    from apps.formations.models import Formation

    formations = list(
        Formation.objects.filter(pk__in=formation_ids)
        .prefetch_related("modules__module")
        .select_related("type_formation")
        .order_by("date_debut", "intitule")
    )
    if len(formations) != len(set(formation_ids)):
        raise Formation.DoesNotExist

    details: list[FormationSimulationDetail] = []
    creneaux_total = 0
    creneaux_module_max = 0
    nb_groupes_total = 0
    for formation in formations:
        if capacite_groupe is None or duree_creneau_heures is None:
            from apps.parametrage.models import get_parametres_pour_formation

            params = get_parametres_pour_formation(formation.pk)
            cap = capacite_groupe if capacite_groupe is not None else params.max_auditeurs_groupe_defaut
            duree = (
                duree_creneau_heures
                if duree_creneau_heures is not None
                else max(1, (params.duree_seance_defaut_minutes or 240) // 60)
            )
        else:
            cap = capacite_groupe
            duree = duree_creneau_heures
        detail = _besoins_creneaux_formation(formation, cap, duree)
        details.append(detail)
        creneaux_total += detail.creneaux_demandes
        creneaux_module_max = max(creneaux_module_max, detail.creneaux_par_module_total_max)
        nb_groupes_total += detail.nb_groupes

    return details, creneaux_total, creneaux_module_max, nb_groupes_total


def agreger_chiffres_formations(formation_ids: list[int]) -> dict:
    """Construit les initials du formulaire pour plusieurs formations en parallèle."""
    from apps.formations.models import Formation
    from apps.parametrage.models import get_parametres_pour_formation

    ids_uniques = list(dict.fromkeys(int(i) for i in formation_ids))
    if not ids_uniques:
        raise ValueError("Au moins une formation est requise.")
    if len(ids_uniques) == 1:
        chiffres = extraire_chiffres_formation(ids_uniques[0])
        chiffres["formation_ids"] = str(ids_uniques[0])
        return chiffres

    formations = list(
        Formation.objects.filter(pk__in=ids_uniques)
        .prefetch_related("modules__module")
        .select_related("type_formation")
        .order_by("date_debut", "intitule")
    )
    if len(formations) != len(ids_uniques):
        raise Formation.DoesNotExist

    params = get_parametres_pour_formation(ids_uniques[0])
    capacite_groupe = params.max_auditeurs_groupe_defaut
    duree_creneau = max(1, (params.duree_seance_defaut_minutes or 240) // 60)

    details, creneaux_total, creneaux_module_max, nb_groupes_total = calculer_besoins_formations(
        ids_uniques, None, None
    )

    nb_groupes = sum(d.nb_groupes for d in details)
    auditeurs_par_groupe = max(
        (d.nb_auditeurs // d.nb_groupes if d.nb_groupes else 1 for d in details),
        default=capacite_groupe,
    )
    nb_modules = sum(d.nb_modules for d in details)
    heures_par_module = 1
    for formation in formations:
        for fm in formation.modules.all():
            heures_par_module = max(
                heures_par_module,
                _volume_horaire_formation_module(fm, formation.type_formation_id),
            )

    nb_salles, capacite_salle_moyenne = _pool_salles_union_formations(formations)
    dates_debut = [f.date_debut for f in formations if f.date_debut]
    dates_fin = [f.date_fin for f in formations if f.date_fin]
    jours_indices = params.jours_defaut if params.jours_defaut else list(_JOURS_OUVRES_DEFAUT)

    return {
        "formation_ids": ",".join(str(i) for i in ids_uniques),
        "nb_groupes": max(1, nb_groupes),
        "capacite_groupe": auditeurs_par_groupe,
        "nb_modules": max(1, nb_modules),
        "heures_par_module": heures_par_module,
        "nb_salles": nb_salles,
        "capacite_salle_moyenne": capacite_salle_moyenne,
        "tolerance_capacite_pct": params.tolerance_capacite_salle or 0,
        "creneaux_par_jour": params.max_seances_par_jour_defaut or 2,
        "duree_creneau_heures": duree_creneau,
        "max_salles_simultanees_module": params.max_salles_simultanees_module,
        "date_debut": min(dates_debut) if dates_debut else None,
        "date_fin": max(dates_fin) if dates_fin else None,
        "jours_semaine": [str(j) for j in jours_indices],
        "_simulation_overrides": {
            "creneaux_demandes_total": creneaux_total,
            "creneaux_par_module_total": creneaux_module_max,
            "nb_groupes_requis": nb_groupes_total,
            "formations_detail": details,
            "nb_formations": len(formations),
        },
    }


def extraire_chiffres_formation(formation_id: int) -> dict:
    """Construit un dict d'initials prêt à pré-remplir `SimulationForm` depuis une `Formation`.

    Touche la base (lit `Formation`, `Salle`, `ParametreGeneral`).

    `heures_par_module` reflète le **maximum** des volumes horaires effectifs (cas le plus
    contraignant).  Pour les modules sans volume fixé sur le FormationModule, on consulte
    toutes les lignes ``ModuleTypeFormation`` correspondantes et on retient leur maximum :
    cela garantit que le module avec le plus grand volume-grade (ex. Culture Civique A3 = 32h)
    est pris en compte, même si `volume_horaire` est NULL sur le FormationModule.
    """
    from apps.formations.models import Formation
    from apps.parametrage.models import get_parametres_pour_formation, Salle

    formation = (
        Formation.objects.prefetch_related("modules__module").select_related("type_formation").get(pk=formation_id)
    )
    params = get_parametres_pour_formation(formation_id)

    volumes: list[int] = []
    for fm in formation.modules.all():
        volumes.append(_volume_horaire_formation_module(fm, formation.type_formation_id))

    heures_par_module = max(volumes) if volumes else 20

    salles_actives_global = list(Salle.objects.filter(actif=True).values_list("pk", flat=True))

    nb_salles_par_module: list[int] = []
    capacites_par_module: list[list[int]] = []
    for fm in formation.modules.all():
        salle_ids = _salles_ids_pour_formation_module(fm, salles_actives_global)
        if salle_ids:
            from apps.parametrage.models import Salle as SalleModel

            caps = list(SalleModel.objects.filter(pk__in=salle_ids).values_list("capacite_max", flat=True))
        else:
            caps = list(Salle.objects.filter(actif=True).values_list("capacite_max", flat=True))
        if caps:
            nb_salles_par_module.append(len(caps))
            capacites_par_module.append(caps)

    if nb_salles_par_module:
        idx_min = nb_salles_par_module.index(min(nb_salles_par_module))
        nb_salles = nb_salles_par_module[idx_min]
        salles_pour_moyenne = capacites_par_module[idx_min]
    else:
        caps_global = list(Salle.objects.filter(actif=True).values_list("capacite_max", flat=True))
        nb_salles = len(caps_global) or 1
        salles_pour_moyenne = caps_global

    capacite_salle_moyenne = (
        max(1, round(sum(salles_pour_moyenne) / len(salles_pour_moyenne))) if salles_pour_moyenne else 25
    )

    jours_indices = params.jours_defaut if params.jours_defaut else list(_JOURS_OUVRES_DEFAUT)
    duree_min = params.duree_seance_defaut_minutes or 240
    duree_creneau = max(1, duree_min // 60)
    detail = _besoins_creneaux_formation(formation, params.max_auditeurs_groupe_defaut, duree_creneau)
    nb_groupes, auditeurs_par_groupe = _groupes_effectifs_formation(formation, params.max_auditeurs_groupe_defaut)

    return {
        "formation_ids": str(formation_id),
        "nb_groupes": nb_groupes,
        "capacite_groupe": auditeurs_par_groupe,
        "nb_modules": max(1, formation.modules.count()),
        "heures_par_module": heures_par_module,
        "nb_salles": nb_salles,
        "capacite_salle_moyenne": capacite_salle_moyenne,
        "tolerance_capacite_pct": params.tolerance_capacite_salle or 0,
        "creneaux_par_jour": params.max_seances_par_jour_defaut or 2,
        "duree_creneau_heures": duree_creneau,
        "max_salles_simultanees_module": params.max_salles_simultanees_module,
        "date_debut": formation.date_debut,
        "date_fin": formation.date_fin,
        "jours_semaine": [str(j) for j in jours_indices],
        "_simulation_overrides": {
            "creneaux_demandes_total": detail.creneaux_demandes,
            "creneaux_par_module_total": detail.creneaux_par_module_total_max,
            "nb_groupes_requis": detail.nb_groupes,
            "formations_detail": [detail],
            "nb_formations": 1,
        },
    }
