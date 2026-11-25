"""Allocation et scoring des salles pour la génération de planning."""

from __future__ import annotations

import datetime
import logging
from typing import Optional

from .locations import (
    LocalisationMap,
    site_disponible_a_date,
    split_noms,
    split_noms_salles_uniques,
)
from .occupations import OccupationIndex, salle_disponible

logger = logging.getLogger("apps.seances")


def score_salle_candidate(
    salle_nom: str,
    effectif: int,
    localisations: LocalisationMap,
    module_id: int,
    salle_usage_counts: dict[str, int],
    module_salle_usage_counts: dict[tuple[int, str], int],
    score_weights: tuple[int, int, int],
) -> tuple[int, int, str]:
    """Score trié par ordre croissant (plus petit = meilleur)."""
    cle_salle = salle_nom.strip().upper()
    _site, _bat, capacite = localisations.get(cle_salle, ("", "", 0))
    capacite = int(capacite or 0)
    effectif = int(effectif or 0)

    if effectif > 0 and capacite > 0:
        sous_capacite = 1 if capacite < effectif else 0
        ecart_capacite = (effectif - capacite) if capacite < effectif else (capacite - effectif)
    else:
        sous_capacite = 0
        ecart_capacite = 0

    usage_module = module_salle_usage_counts.get((module_id, cle_salle), 0)
    usage_global = salle_usage_counts.get(cle_salle, 0)
    poids_ecart, poids_rotation, poids_equilibrage = score_weights
    score_pondere = (
        ecart_capacite * max(1, int(poids_ecart))
        + usage_module * max(1, int(poids_rotation))
        + usage_global * max(1, int(poids_equilibrage))
    )
    return (sous_capacite, score_pondere, cle_salle)


def filtrer_salles_explicites_dispatch_site_batiment(
    salles: list[str],
    sites_module: set[str],
    batiments_module: set[str],
    localisations: LocalisationMap,
    formation_module,
) -> list[str]:
    """Filtre les salles explicites selon site/bâtiment du module et le référentiel."""
    if not sites_module:
        logger.info(
            "planning dispatch fm_id=%s : salles explicites sans site sur le module ; "
            "filtrage site/bâtiment référentiel non appliqué",
            formation_module.pk,
        )
        return salles

    titre_module = ""
    mod = getattr(formation_module, "module", None)
    if mod is not None:
        titre_module = getattr(mod, "titre", "") or ""

    retenues: list[str] = []
    for brut in salles:
        name = brut.strip()
        if not name:
            continue
        cle = name.upper()
        loc = localisations.get(cle)
        if loc is None:
            logger.info(
                "planning dispatch fm_id=%s titre=%r salle=%r absente du référentiel salles actives "
                "(candidate conservée ; vérifiez orthographe et cohérence site/bâtiment)",
                formation_module.pk,
                titre_module,
                name,
            )
            retenues.append(name)
            continue
        site, batiment, _cap = loc
        site_u = (site or "").strip().upper()
        bat_u = (batiment or "").strip().upper()
        if site_u not in sites_module:
            logger.warning(
                "planning dispatch fm_id=%s titre=%r salle=%r exclue : site référentiel %r " "hors sites du module %s",
                formation_module.pk,
                titre_module,
                name,
                site or "",
                sorted(sites_module),
            )
            continue
        if batiments_module and bat_u not in batiments_module:
            logger.warning(
                "planning dispatch fm_id=%s titre=%r salle=%r exclue : bâtiment référentiel %r "
                "hors bâtiments du module %s",
                formation_module.pk,
                titre_module,
                name,
                batiment or "",
                sorted(batiments_module),
            )
            continue
        retenues.append(name)
    return retenues


def salles_candidates(
    formation_module,
    localisations: LocalisationMap,
    *,
    salles_par_site_batiment: Optional[dict[str, dict[str, list[str]]]] = None,
    union_sites_programme: Optional[frozenset[str]] = None,
) -> list[str]:
    """Retourne les salles candidates d'un module de formation."""
    salles = split_noms_salles_uniques(formation_module.salle_nom)
    sites_module = {s.strip().upper() for s in split_noms(formation_module.site_nom)}
    batiments_module = {b.strip().upper() for b in split_noms(formation_module.batiment_nom)}

    if salles:
        filtrees = filtrer_salles_explicites_dispatch_site_batiment(
            salles,
            sites_module,
            batiments_module,
            localisations,
            formation_module,
        )
        logger.info(
            "planning dispatch pool salles explicites fm_id=%s titre=%r nb_entree=%s nb_retenu=%s "
            "sites_module=%s batiments_module=%s",
            formation_module.pk,
            (getattr(getattr(formation_module, "module", None), "titre", None) or ""),
            len(salles),
            len(filtrees),
            sorted(sites_module),
            sorted(batiments_module) if batiments_module else [],
        )
        return filtrees

    if not sites_module:
        return []

    nombre = int(formation_module.salle_nombre or 0)
    sites_pool: set[str] = set(sites_module)
    if union_sites_programme:
        sites_pool |= set(union_sites_programme)

    pool: list[str] = []
    if salles_par_site_batiment:
        vus: set[str] = set()
        for site in sorted(sites_pool):
            bucket = salles_par_site_batiment.get(site, {})
            if batiments_module:
                for bat in sorted(batiments_module):
                    for salle in bucket.get(bat, []):
                        if salle not in vus:
                            vus.add(salle)
                            pool.append(salle)
            else:
                for salle in bucket.get("__ALL__", []):
                    if salle not in vus:
                        vus.add(salle)
                        pool.append(salle)
    else:
        pool = sorted(localisations.keys())
        filtered_pool: list[str] = []
        for salle in pool:
            site, batiment, _capacite = localisations.get(salle, ("", "", 0))
            site_ok = (site or "").strip().upper() in sites_pool
            bat_ok = not batiments_module or (batiment or "").strip().upper() in batiments_module
            if site_ok and bat_ok:
                filtered_pool.append(salle)
        pool = filtered_pool

    if nombre > 0:
        pool = pool[:nombre]

    titre_module = ""
    mod = getattr(formation_module, "module", None)
    if mod is not None:
        titre_module = getattr(mod, "titre", "") or ""
    logger.info(
        "planning dispatch pool salles implicites fm_id=%s titre=%r nb=%s sites_pool=%s "
        "batiments_module=%s salle_nombre_limite=%s",
        formation_module.pk,
        titre_module,
        len(pool),
        sorted(sites_pool),
        sorted(batiments_module) if batiments_module else [],
        nombre,
    )
    return pool


def choisir_salle_disponible(
    occupations: OccupationIndex,
    date: datetime.date,
    salles: list[str],
    heure_debut: datetime.time,
    heure_fin: datetime.time,
    effectif: int,
    localisations: LocalisationMap,
    module_id: int,
    max_seances_jour: int,
    module_salle_counts: dict[tuple[datetime.date, int, str], int],
    salle_usage_counts: dict[str, int],
    module_salle_usage_counts: dict[tuple[int, str], int],
    score_weights: tuple[int, int, int],
    salle_ids: Optional[dict[str, int]] = None,
    salle_fixe_module: str = "",
    tolerance_capacite_salle: int = 0,
    periodes_disponibilite_sites: Optional[dict[str, list[tuple[datetime.date, datetime.date]]]] = None,
) -> tuple[str, Optional[int]]:
    """
    Retourne (nom_salle, salle_id) de la meilleure salle disponible selon le scoring.
    Chaîne vide et None si aucune salle disponible.
    """
    fix = (salle_fixe_module or "").strip()
    salles_iter: list[str] = [fix] if fix else salles
    seuil_capacite = max(0, int(effectif or 0) - max(0, int(tolerance_capacite_salle or 0)))
    periodes = periodes_disponibilite_sites or {}
    ids_map = salle_ids or {}

    candidates: list[tuple[tuple[int, int, int, int, str], str]] = []
    nb_rejet_capacite = 0
    for salle in salles_iter:
        cle_salle = salle.strip().upper()
        cle = (date, module_id, cle_salle)
        if module_salle_counts.get(cle, 0) >= max_seances_jour:
            continue
        site_nom = (localisations.get(cle_salle, ("", "", 0)) or ("", "", 0))[0]
        if site_nom and not site_disponible_a_date(site_nom, date, periodes):
            continue
        capacite = int((localisations.get(cle_salle, ("", "", 0)) or ("", "", 0))[2] or 0)
        if capacite > 0 and seuil_capacite > 0 and capacite < seuil_capacite:
            nb_rejet_capacite += 1
            continue
        salle_id = ids_map.get(cle_salle)
        if salle_disponible(
            occupations,
            date,
            salle,
            heure_debut,
            heure_fin,
            salle_id=salle_id,
        ):
            score = score_salle_candidate(
                salle,
                effectif,
                localisations,
                module_id,
                salle_usage_counts,
                module_salle_usage_counts,
                score_weights,
            )
            candidates.append((score, salle))
    if candidates:
        candidates.sort(key=lambda item: item[0])
        chosen = candidates[0][1]
        return chosen, ids_map.get(chosen.strip().upper())

    nb_bloque_quota = sum(
        1 for s in salles_iter if module_salle_counts.get((date, module_id, s.strip().upper()), 0) >= max_seances_jour
    )
    nb_occupees = sum(
        1
        for s in salles_iter
        if module_salle_counts.get((date, module_id, s.strip().upper()), 0) < max_seances_jour
        and not salle_disponible(
            occupations,
            date,
            s,
            heure_debut,
            heure_fin,
            salle_id=ids_map.get(s.strip().upper()),
        )
    )
    logger.debug(
        "choisir_salle_disponible aucune salle date=%s module_id=%s creneau=%s-%s "
        "nb_pool=%s bloque_quota_module_salle_jour=%s occupees_autre=%s rejet_capacite=%s salle_fixe=%r",
        date.isoformat(),
        module_id,
        heure_debut,
        heure_fin,
        len(salles_iter),
        nb_bloque_quota,
        nb_occupees,
        nb_rejet_capacite,
        fix or "",
    )
    return "", None
