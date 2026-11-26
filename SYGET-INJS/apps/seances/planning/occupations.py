"""Suivi des occupations salles et modules (créneaux en mémoire et requêtes base)."""

from __future__ import annotations

import datetime
from typing import Optional

from django.db.models import Q

from apps.seances.models import Seance

from .locations import LocalisationMap

OccupationKey = tuple[datetime.date, str]
OccupationIndex = dict[OccupationKey, list[tuple[datetime.time, datetime.time]]]


def occupation_key(
    date: datetime.date,
    salle_nom: str = "",
    *,
    salle_id: Optional[int] = None,
) -> Optional[OccupationKey]:
    """Clé d'occupation : priorité à l'id référentiel, sinon nom normalisé."""
    if salle_id:
        return (date, f"#{salle_id}")
    sn = (salle_nom or "").strip().upper()
    if not sn:
        return None
    return (date, sn)


def occupation_keys_for_seance(
    date: datetime.date,
    salle_nom: str,
    salle_id: Optional[int],
) -> list[OccupationKey]:
    """Retourne toutes les clés à enregistrer pour une séance (id + nom si les deux existent)."""
    keys: list[OccupationKey] = []
    key_id = occupation_key(date, salle_id=salle_id)
    if key_id:
        keys.append(key_id)
    key_name = occupation_key(date, salle_nom=salle_nom)
    if key_name and key_name not in keys:
        keys.append(key_name)
    return keys


def salle_disponible(
    occupations: OccupationIndex,
    date: datetime.date,
    salle_nom: str,
    heure_debut: datetime.time,
    heure_fin: datetime.time,
    *,
    salle_id: Optional[int] = None,
) -> bool:
    """Retourne True si la salle est libre sur le créneau [heure_debut, heure_fin[."""
    if not salle_nom.strip() and not salle_id:
        return True
    keys = occupation_keys_for_seance(date, salle_nom, salle_id)
    for key in keys:
        for debut_existant, fin_existante in occupations.get(key, []):
            if heure_debut < fin_existante and heure_fin > debut_existant:
                return False
    return True


def reserver_creneau(
    occupations: OccupationIndex,
    date: datetime.date,
    salle_nom: str,
    heure_debut: datetime.time,
    heure_fin: datetime.time,
    *,
    salle_id: Optional[int] = None,
) -> None:
    """Ajoute un créneau réservé dans l'index mémoire des occupations."""
    keys = occupation_keys_for_seance(date, salle_nom, salle_id)
    if not keys:
        return
    for key in keys:
        occupations.setdefault(key, []).append((heure_debut, heure_fin))


def charger_occupations_existantes(groupe_id: int) -> OccupationIndex:
    """Construit l'index des créneaux déjà utilisés par salle pour les autres groupes."""
    occupations: OccupationIndex = {}
    qs = (
        Seance.objects.exclude(groupe_id=groupe_id)
        .filter(Q(salle_nom__gt="") | Q(salle_id__isnull=False))
        .only("date", "salle_nom", "salle_id", "heure_debut", "heure_fin")
    )
    for s in qs:
        keys = occupation_keys_for_seance(s.date, s.salle_nom or "", s.salle_id)
        slot = (s.heure_debut, s.heure_fin)
        for key in keys:
            occupations.setdefault(key, []).append(slot)
    return occupations


def charger_occupations_modules_existantes(
    groupe_id: int,
    formation_id: int,
) -> tuple[set[tuple[datetime.date, int, str, str]], set[tuple[datetime.date, int]]]:
    """
    Occupation « même formation, autre groupe » pour le partage des modules.
    """
    quadruples: set[tuple[datetime.date, int, str, str]] = set()
    sans_salle: set[tuple[datetime.date, int]] = set()
    qs = (
        Seance.objects.filter(groupe__formation_id=formation_id)
        .exclude(groupe_id=groupe_id)
        .only("date", "module_id", "site_nom", "salle_nom", "salle_id")
    )
    for s in qs:
        sn = (s.salle_nom or "").strip().upper()
        site = (s.site_nom or "").strip().upper()
        if sn or s.salle_id:
            if not sn and s.salle_id:
                from apps.parametrage.models import Salle

                salle_obj = Salle.objects.filter(pk=s.salle_id).only("nom").first()
                sn = (salle_obj.nom if salle_obj else "").strip().upper()
            if sn:
                quadruples.add((s.date, s.module_id, site, sn))
            else:
                sans_salle.add((s.date, s.module_id))
        else:
            sans_salle.add((s.date, s.module_id))
    return quadruples, sans_salle


def indexer_occupations_modules_triples(
    occ_quadruples: set[tuple[datetime.date, int, str, str]],
) -> dict[tuple[datetime.date, int, str], set[str]]:
    """Index (date, module, site) -> salles déjà prises (autres groupes, même formation)."""
    out: dict[tuple[datetime.date, int, str], set[str]] = {}
    for d, m, site, s in occ_quadruples:
        out.setdefault((d, m, site), set()).add(s)
    return out


def salles_eligibles_hors_occupation_module_intergroupes(
    salles_module: list[str],
    current_date: datetime.date,
    module_id: int,
    occ_par_jour: dict[tuple[datetime.date, int, str], set[str]],
    occ_sans_salle: set[tuple[datetime.date, int]],
    max_salles_simultanees_module: int,
    salle_localisations: LocalisationMap,
) -> list[str]:
    """Salles du pool encore autorisées pour ce module à cette date (autres groupes, même formation)."""
    if (current_date, module_id) in occ_sans_salle:
        return []
    cap = max(1, int(max_salles_simultanees_module or 1))
    eligibles: list[str] = []
    for s in salles_module:
        sn = s.strip().upper()
        site_norm = (salle_localisations.get(sn, ("", "", 0))[0] or "").strip().upper()
        prises = occ_par_jour.get((current_date, module_id, site_norm), set())
        if sn in prises:
            continue
        if len(prises) >= cap:
            continue
        eligibles.append(s)
    return eligibles


def occupation_details_salles(
    salles_module: list[str],
    date_debut: datetime.date,
    date_fin: datetime.date,
    groupe_id: int,
    *,
    masquer_noms_formations: bool = False,
) -> str:
    """
    Résumé des formations occupant les salles du pool sur la période.
    Si ``masquer_noms_formations``, les intitulés sont remplacés par « une autre formation »
    (périmètre gestionnaire ne voyant pas les formations des collègues).
    """
    if not salles_module:
        return ""
    salles_set = {s.strip().upper() for s in salles_module}
    qs = (
        Seance.objects.filter(date__range=(date_debut, date_fin))
        .exclude(groupe_id=groupe_id)
        .select_related("groupe__formation")
        .only("salle_nom", "salle_id", "date", "groupe__formation__intitule")
        .order_by("date")
    )
    occ: dict[str, dict[str, datetime.date]] = {}
    for seance in qs:
        salle_u = (seance.salle_nom or "").strip().upper()
        if not salle_u and seance.salle_id:
            from apps.parametrage.models import Salle

            salle_obj = Salle.objects.filter(pk=seance.salle_id).only("nom").first()
            salle_u = (salle_obj.nom if salle_obj else "").strip().upper()
        if not salle_u or salle_u not in salles_set:
            continue
        if masquer_noms_formations:
            formation_intitule = "une autre formation"
        else:
            formation_intitule = (
                getattr(getattr(seance.groupe, "formation", None), "intitule", None) or "Formation inconnue"
            )
        occ.setdefault(salle_u, {})
        prev = occ[salle_u].get(formation_intitule)
        if prev is None or seance.date > prev:
            occ[salle_u][formation_intitule] = seance.date
    if not occ:
        return ""
    lines = []
    for salle_u in sorted(occ.keys()):
        for formation, derniere_date in sorted(occ[salle_u].items(), key=lambda x: x[1]):
            lines.append(f"salle {salle_u} occupée par « {formation} » jusqu'au {derniere_date:%d/%m/%Y}")
    return "Occupations détectées sur la période : " + " ; ".join(lines) + "."
