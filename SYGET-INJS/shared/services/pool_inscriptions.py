"""Pool d'auditeurs éligibles à une affectation manuelle (formation / source)."""

from __future__ import annotations

import types
from typing import Optional

from apps.auditeurs.models import Auditeur
from apps.formations.models import Inscription
from apps.groupes.services import GroupeService


def ids_auditeurs_formation_source(source_formation_id: int) -> set[int]:
    """Ids des auditeurs inscrits ou membres d'un groupe dans la formation source."""
    par_nom = GroupeService.auditeurs_par_nom_groupe_formation(source_formation_id)
    ids: set[int] = set()
    for aud_ids in par_nom.values():
        ids.update(aud_ids)
    if not ids:
        ids.update(
            Inscription.objects.filter(formation_id=source_formation_id)
            .values_list("auditeur_id", flat=True)
            .distinct()
        )
    return ids


def groupe_source_par_auditeur(source_formation_id: int) -> dict[int, str]:
    """Retourne auditeur_id → nom du groupe dans la formation source."""
    result: dict[int, str] = {}
    for nom, aud_ids in GroupeService.auditeurs_par_nom_groupe_formation(source_formation_id).items():
        for aud_id in aud_ids:
            result[aud_id] = nom
    return result


def pool_inscrits_pour_affectation(
    formation_pk: int,
    source_formation_id: Optional[int],
    auditeurs_deja_en_groupe: set[int],
    exclure_deja_en_groupe: bool = True,
) -> tuple[list, dict[str, set[int]]]:
    """
    Retourne le pool d'auditeurs éligibles et la cartographie nom de groupe source → ids.

    Si ``exclure_deja_en_groupe`` est False, les auditeurs déjà dans un autre groupe
    de la formation restent listés (déplacement possible).
    """
    auditeurs_par_nom_source: dict[str, set[int]] = {}
    if source_formation_id and source_formation_id != formation_pk:
        auditeurs_par_nom_source = GroupeService.auditeurs_par_nom_groupe_formation(source_formation_id)
        ids_eligibles = ids_auditeurs_formation_source(source_formation_id)
        if exclure_deja_en_groupe:
            ids_eligibles -= auditeurs_deja_en_groupe
        pool = [
            types.SimpleNamespace(auditeur=aud, auditeur_id=aud.pk)
            for aud in Auditeur.objects.filter(pk__in=ids_eligibles).order_by("nom", "prenom")
        ]
        return pool, auditeurs_par_nom_source

    inscriptions_brutes = (
        Inscription.objects.filter(formation_id=formation_pk)
        .select_related("auditeur")
        .order_by("auditeur__nom", "auditeur__prenom")
    )
    pool: list = []
    auditeurs_vus: set[int] = set()
    for ins in inscriptions_brutes:
        if ins.auditeur_id in auditeurs_vus:
            continue
        if exclure_deja_en_groupe and ins.auditeur_id in auditeurs_deja_en_groupe:
            continue
        auditeurs_vus.add(ins.auditeur_id)
        pool.append(ins)
    return pool, auditeurs_par_nom_source


def filtrer_disponibles_groupe(
    pool: list,
    groupe_nom: str,
    membres_ids: set[int],
    auditeurs_par_nom_source: dict[str, set[int]],
    source_formation_id: Optional[int],
    q: str = "",
    limit: Optional[int] = None,
    filtrer_homologue: bool = True,
) -> tuple[list, int]:
    """Filtre le pool pour un groupe (homologue source, recherche, limite optionnelle)."""
    if filtrer_homologue and source_formation_id and auditeurs_par_nom_source:
        ids_homologues = auditeurs_par_nom_source.get(groupe_nom, set())
        disponibles = [ins for ins in pool if ins.auditeur_id in ids_homologues and ins.auditeur_id not in membres_ids]
    else:
        disponibles = [ins for ins in pool if ins.auditeur_id not in membres_ids]

    if q:
        q_lower = q.lower()
        disponibles = [
            ins
            for ins in disponibles
            if q_lower in (ins.auditeur.nom or "").lower()
            or q_lower in (ins.auditeur.prenom or "").lower()
            or q_lower in (ins.auditeur.matricule or "").lower()
        ]

    total = len(disponibles)
    if limit is not None:
        disponibles = disponibles[:limit]
    return disponibles, total
