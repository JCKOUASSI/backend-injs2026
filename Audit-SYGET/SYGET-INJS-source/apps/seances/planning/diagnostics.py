"""Messages d'échec et diagnostics de la génération de planning."""

from __future__ import annotations

import datetime
import logging
from collections import Counter
from typing import Optional

logger = logging.getLogger("apps.seances")


def log_echec_planning_module(
    *,
    contexte: str,
    groupe_id: int,
    groupe_nom: str,
    formation_id: int,
    module_id: int,
    module_titre: str,
    module_date_debut: datetime.date,
    module_date_fin: datetime.date,
    grade_principal: str,
    minutes_initial: int,
    minutes_restants: int,
    reason: str,
    diag: Counter[str],
    salles_module: list[str],
    not_before_dt: Optional[datetime.datetime],
    niveau: int = logging.ERROR,
) -> None:
    """Journalise le détail d'un module non entièrement planifié."""
    logger.log(
        niveau,
        "[%s] échec planning module groupe_id=%s groupe=%r formation_id=%s module_id=%s module=%r "
        "fenêtre=%s–%s grade=%s minutes_initial=%s minutes_restants=%s reason=%r diag=%s "
        "salles_candidats(nb=%s)=%s not_before_dt=%s",
        contexte,
        groupe_id,
        groupe_nom,
        formation_id,
        module_id,
        module_titre,
        module_date_debut.isoformat(),
        module_date_fin.isoformat(),
        grade_principal or "—",
        minutes_initial,
        minutes_restants,
        reason,
        dict(diag),
        len(salles_module),
        salles_module[:20],
        not_before_dt.isoformat() if not_before_dt else None,
    )


def raison_planning_avec_diag(reason: str, diag: Counter[str]) -> str:
    """Ajoute aux messages d'échec les compteurs de rejets."""
    if not diag:
        return reason
    rows: list[tuple[int, str]] = []
    skip: set[str] = set()

    pm = int(diag.get("pas_de_salle_matin", 0))
    ps = int(diag.get("pas_de_salle_soir", 0))
    if pm > 0 or ps > 0:
        total_s = pm + ps
        if pm > 0 and ps > 0:
            lab = f"pas_de_salle_matin_et_soir={total_s} (matin={pm}, soir={ps})"
        elif pm > 0:
            lab = f"pas_de_salle_matin_et_soir={total_s} (matin={pm})"
        else:
            lab = f"pas_de_salle_matin_et_soir={total_s} (soir={ps})"
        rows.append((total_s, lab))
        skip.update({"pas_de_salle_matin", "pas_de_salle_soir"})

    pfm = int(diag.get("pas_formateur_matin", 0))
    pfs = int(diag.get("pas_formateur_soir", 0))
    if pfm > 0 or pfs > 0:
        total_f = pfm + pfs
        if pfm > 0 and pfs > 0:
            lab = f"pas_formateur_matin_et_soir={total_f} (matin={pfm}, soir={pfs})"
        elif pfm > 0:
            lab = f"pas_formateur_matin_et_soir={total_f} (matin={pfm})"
        else:
            lab = f"pas_formateur_matin_et_soir={total_f} (soir={pfs})"
        rows.append((total_f, lab))
        skip.update({"pas_formateur_matin", "pas_formateur_soir"})

    plm = int(diag.get("plancher_bloque_matin", 0))
    pls = int(diag.get("plancher_bloque_soir", 0))
    if plm > 0 or pls > 0:
        total_p = plm + pls
        if plm > 0 and pls > 0:
            lab = f"plancher_bloque_matin_et_soir={total_p} (matin={plm}, soir={pls})"
        elif plm > 0:
            lab = f"plancher_bloque_matin_et_soir={total_p} (matin={plm})"
        else:
            lab = f"plancher_bloque_matin_et_soir={total_p} (soir={pls})"
        rows.append((total_p, lab))
        skip.update({"plancher_bloque_matin", "plancher_bloque_soir"})

    for k, v in diag.items():
        if v > 0 and k not in skip:
            rows.append((v, f"{k}={v}"))

    rows.sort(key=lambda item: (-item[0], item[1]))
    parts = [lab for _, lab in rows[:20]]
    if not parts:
        return reason
    return f"{reason} Détail des rejets sur la période : {' ; '.join(parts)}."


def diag_dominant_planning(diag: Counter[str]) -> tuple[int, frozenset[str], dict[str, int]]:
    """Agrège les compteurs de diagnostic en familles et retourne le(s) rejet(s) dominant(s)."""
    pf = int(diag.get("pas_formateur_matin", 0)) + int(diag.get("pas_formateur_soir", 0))
    ps = int(diag.get("pas_de_salle_matin", 0)) + int(diag.get("pas_de_salle_soir", 0))
    am = int(diag.get("autre_module_deja_ce_jour", 0))
    mo = int(diag.get("inter_groupes_pool_module_epuise_ce_jour", 0))
    pl = int(diag.get("plancher_bloque_matin", 0)) + int(diag.get("plancher_bloque_soir", 0))
    jh = int(diag.get("jour_hors_jours_actifs", 0))
    jf = int(diag.get("jour_ferie", 0))
    dmap: dict[str, int] = {
        "formateurs": pf,
        "salles": ps,
        "autre_module_jour": am,
        "module_occupe": mo,
        "plancher": pl,
        "hors_jours": jh,
        "ferie": jf,
    }
    max_val = max(dmap.values())
    at_max = frozenset(k for k, v in dmap.items() if v == max_val)
    return max_val, at_max, {"pf": pf, "ps": ps, "am": am, "mo": mo, "pl": pl, "jh": jh, "jf": jf}


def raison_echec_planning_aucune_minute_placee(
    diag: Counter[str],
    salles_module: list[str],
    not_before_dt: Optional[datetime.datetime],
) -> str:
    """Libellé principal lorsque aucune minute n'a été placée."""
    max_val, at_max, b = diag_dominant_planning(diag)
    pf, ps = b["pf"], b["ps"]
    if max_val == 0:
        return (
            "aucun créneau exploitable sur la période ; vérifiez la configuration du groupe "
            "(jours de cours, fenêtre de dates du module) et le référentiel des lieux."
        )

    if len(at_max) > 1:
        if at_max == frozenset({"formateurs", "salles"}) and pf == ps and pf > 0:
            return (
                "à chaque date candidate, une salle du pool peut manquer ou un formateur éligible "
                "(spécialité du module, affectations au groupe, disponibilité) ; "
                "vérifiez salles actives, effectif, pool formateurs et spécialité du module."
            )
        return (
            "plusieurs contraintes excluent les créneaux au même niveau (voir les compteurs de rejets) : "
            "salles, formateurs, un module par jour, priorité entre formations ou jours."
        )

    only = next(iter(at_max))

    if only == "formateurs":
        if len(salles_module) == 0:
            return (
                "aucun formateur éligible et en plus aucune salle candidate sur le module ; "
                "configurez le site / les salles actives et les formateurs avec la bonne spécialité."
            )
        return (
            "aucun formateur disponible avec la spécialité requise pour ce module sur les créneaux "
            "où une salle du pool était libre ; vérifiez les affectations formateurs au groupe, "
            "le référentiel formateurs (spécialités) et la spécialité du module."
        )

    if only == "salles":
        return (
            "aucune salle libre dans le pool du module sur les dates et créneaux utiles "
            "(capacité, occupations croisées) ; vérifiez le site, les salles actives et l'effectif du groupe."
        )

    if only == "autre_module_jour":
        return (
            "la règle « un seul module par jour pour ce groupe » empêche de placer ce module : "
            "chaque jour utile est déjà réservé à un autre module du programme sur la période."
        )

    if only == "module_occupe":
        return (
            "ce même module référentiel est déjà planifié le même jour pour un autre groupe de cette "
            "formation dans chaque salle utile du pool (ou une séance sans salle bloque tout le jour) ; "
            "élargissez les salles du module ou les sites, ou réordonnez les groupes."
        )

    if only == "plancher":
        if not_before_dt:
            return (
                "contrainte de priorité entre formations : aucun créneau ne peut commencer avant "
                f"{not_before_dt:%d/%m/%Y %H:%M} (planning d'une formation prioritaire) ; "
                "élargir les dates ou l'ordre des formations si besoin."
            )
        return "créneaux repoussés par une contrainte de date minimale liée à d'autres formations sur la période."

    if only == "hors_jours":
        return (
            "les dates de la fenêtre ne recoupent pas les jours de cours configurés pour le groupe ; "
            "vérifiez les jours actifs du groupe et les dates du module."
        )

    if only == "ferie":
        return "les jours de cours utiles dans la fenêtre coïncident avec des jours fériés paramétrés."

    return (
        "aucun créneau planifiable sur la période (salle, formateur, ou autre contrainte du programme) ; "
        "voir le détail des compteurs ci-dessous."
    )


def raison_echec_planning_partielle_reliquat(
    diag: Counter[str],
    salles_module: list[str],
    not_before_dt: Optional[datetime.datetime],
) -> str:
    """Libellé principal lorsque le volume est partiellement planifié."""
    prefix = "volume horaire du module partiellement planifié"
    max_val, at_max, b = diag_dominant_planning(diag)
    pf, ps = b["pf"], b["ps"]
    if max_val == 0:
        return (
            f"{prefix} : sur les jours restants, aucun rejet n'a été comptabilisé ; élargissez la fenêtre "
            "de dates ou vérifiez la configuration du groupe et du module."
        )

    if len(at_max) > 1:
        if at_max == frozenset({"formateurs", "salles"}) and pf == ps and pf > 0:
            return (
                f"{prefix} : pour le reliquat, à chaque date candidate une salle du pool peut manquer ou "
                "un formateur éligible (spécialité, affectations, disponibilité) ; vérifiez salles actives, "
                "effectif et pool formateurs."
            )
        return (
            f"{prefix} : le reliquat bute sur plusieurs contraintes au même niveau (voir compteurs) : "
            "salles, formateurs, un module par jour, saturation du pool module entre groupes, "
            "ou priorité entre formations."
        )

    only = next(iter(at_max))

    if only == "formateurs":
        if len(salles_module) == 0:
            return (
                f"{prefix} : le reliquat coïncide surtout avec l'absence de formateur éligible et "
                "aucune salle candidate sur le module ; complétez site, salles actives et formateurs."
            )
        return (
            f"{prefix} : le reliquat coïncide surtout avec l'absence de formateur disponible avec la "
            "spécialité requise sur les créneaux où une salle du pool était encore libre ; vérifiez "
            "affectations au groupe et référentiel formateurs."
        )

    if only == "salles":
        return (
            f"{prefix} : le reliquat coïncide surtout avec l'absence de salle libre dans le pool du module "
            "sur les dates et créneaux utiles (capacité, occupations croisées) ; vérifiez le site, "
            "les salles actives et l'effectif du groupe."
        )

    if only == "autre_module_jour":
        return (
            f"{prefix} : le reliquat bute sur la règle « un seul module par jour pour ce groupe » "
            "(un autre module occupe déjà le jour sur les dates encore utiles)."
        )

    if only == "module_occupe":
        return (
            f"{prefix} : le reliquat bute surtout sur des jours où chaque salle candidate est déjà "
            "utilisée pour ce module par un autre groupe de la formation (ou une séance sans salle "
            "renseignée occupe le jour) ; ajoutez des salles au pool du module ou décalez des volumes."
        )

    if only == "plancher":
        if not_before_dt:
            return (
                f"{prefix} : contrainte de priorité entre formations — le reliquat ne trouve pas de créneau "
                f"commençant au plus tôt le {not_before_dt:%d/%m/%Y %H:%M} ; élargissez les dates si besoin."
            )
        return (
            f"{prefix} : le reliquat est repoussé par une contrainte de date minimale liée à d'autres "
            "formations sur la période."
        )

    if only == "hors_jours":
        return (
            f"{prefix} : les dates encore nécessaires pour le reliquat ne recoupent pas les jours de cours "
            "du groupe ; vérifiez jours actifs et fenêtre du module."
        )

    if only == "ferie":
        return (
            f"{prefix} : les jours de cours utiles pour placer le reliquat coïncident avec des jours fériés "
            "paramétrés."
        )

    return (
        f"{prefix} : le reliquat ne trouve pas de créneau (salle, formateur ou autre contrainte) ; "
        "voir le détail des compteurs ci-dessous."
    )
