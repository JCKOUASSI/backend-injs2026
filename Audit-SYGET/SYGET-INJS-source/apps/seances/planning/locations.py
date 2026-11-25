"""Chargement et résolution des localisations (sites, bâtiments, salles)."""

from __future__ import annotations

import datetime
import logging
from typing import Optional

logger = logging.getLogger("apps.seances")

LocalisationMap = dict[str, tuple[str, str, int]]
SalleIdsByName = dict[str, int]


def split_noms(valeur: str) -> list[str]:
    """Découpe une chaîne CSV de noms en liste propre."""
    if not valeur:
        return []
    return [p.strip() for p in valeur.split(",") if p.strip()]


def split_noms_salles_uniques(valeur: str) -> list[str]:
    """Découpe une liste CSV de salles en éliminant les doublons (ordre conservé)."""
    vus: set[str] = set()
    out: list[str] = []
    for part in split_noms(valeur):
        cle = part.upper()
        if cle not in vus:
            vus.add(cle)
            out.append(part)
    return out


def charger_localisations_salles() -> tuple[LocalisationMap, SalleIdsByName]:
    """
    Construit un index salle (UPPER) -> (site, bâtiment, capacité) et salle (UPPER) -> pk.
    """
    from apps.parametrage.models import Salle

    mapping: LocalisationMap = {}
    salle_ids: SalleIdsByName = {}
    for salle in Salle.objects.select_related("batiment__site").filter(actif=True):
        nom = salle.nom.strip().upper()
        bat = salle.batiment.nom if salle.batiment_id else ""
        site = salle.batiment.site.nom if salle.batiment_id and salle.batiment.site_id else ""
        mapping[nom] = (site, bat, salle.capacite_max)
        salle_ids[nom] = salle.pk
    return mapping, salle_ids


def salle_id_pour_nom(salle_nom: str, salle_ids: SalleIdsByName) -> Optional[int]:
    """Retourne l'id référentiel de la salle si connue."""
    if not salle_nom or not salle_nom.strip():
        return None
    return salle_ids.get(salle_nom.strip().upper())


def site_pour_salle(salle_nom: str, mapping: LocalisationMap, fallback_sites: list[str]) -> str:
    """Retourne le site cohérent avec la salle, sinon fallback."""
    val = mapping.get(salle_nom.strip().upper())
    if val and val[0]:
        return val[0]
    return fallback_sites[0] if fallback_sites else ""


def batiment_pour_salle(salle_nom: str, mapping: LocalisationMap, fallback_batiments: list[str]) -> str:
    """Retourne le bâtiment cohérent avec la salle, sinon fallback."""
    val = mapping.get(salle_nom.strip().upper())
    if val and val[1]:
        return val[1]
    return fallback_batiments[0] if fallback_batiments else ""


def indexer_salles_par_site_batiment(
    localisations: LocalisationMap,
) -> dict[str, dict[str, list[str]]]:
    """Indexe les salles actives par site et bâtiment pour éviter un scan complet par module."""
    out: dict[str, dict[str, list[str]]] = {}
    for salle, (site, batiment, _capacite) in localisations.items():
        site_u = (site or "").strip().upper()
        if not site_u:
            continue
        bat_u = (batiment or "").strip().upper()
        site_bucket = out.setdefault(site_u, {"__ALL__": []})
        site_bucket["__ALL__"].append(salle)
        if bat_u:
            site_bucket.setdefault(bat_u, []).append(salle)
    for site_bucket in out.values():
        for key, salles in site_bucket.items():
            site_bucket[key] = sorted(salles)
    return out


def charger_periodes_disponibilite_sites() -> dict[str, list[tuple[datetime.date, datetime.date]]]:
    """Index site (UPPER) -> liste de plages [date_debut, date_fin] de disponibilité."""
    from apps.parametrage.models import PeriodeDisponibiliteSite

    out: dict[str, list[tuple[datetime.date, datetime.date]]] = {}
    for periode in PeriodeDisponibiliteSite.objects.select_related("site").order_by("site__nom", "date_debut"):
        site_key = periode.site.nom.strip().upper()
        out.setdefault(site_key, []).append((periode.date_debut, periode.date_fin))
    return out


def site_disponible_a_date(
    site_nom: str,
    date: datetime.date,
    periodes_par_site: dict[str, list[tuple[datetime.date, datetime.date]]],
) -> bool:
    """
    Retourne True si le site peut accueillir des séances à la date donnée.
    Sans période configurée pour ce site, il est considéré toujours disponible.
    """
    site_key = (site_nom or "").strip().upper()
    if not site_key:
        return True
    periodes = periodes_par_site.get(site_key)
    if not periodes:
        return True
    return any(debut <= date <= fin for debut, fin in periodes)
