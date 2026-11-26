"""Allocation et disponibilité des formateurs pour la génération de planning."""

from __future__ import annotations

import datetime
import logging
from typing import Optional

from django.db.models import Q

from apps.seances.models import Seance

logger = logging.getLogger("apps.seances")

FormateurDict = dict[str, str]

FormateurOccupationIndex = dict[tuple[datetime.date, str], int]


def formateur_pk_from_dict(formateur: FormateurDict) -> Optional[int]:
    """Retourne l'id référentiel si présent dans le dict de planning."""
    raw = (formateur.get("formateur_id") or "").strip()
    if raw.isdigit():
        return int(raw)
    return None


def _seance_a_formateur_referentiel_id() -> bool:
    return hasattr(Seance, "formateur_referentiel_id")


def formateur_occupation_keys(
    date: datetime.date,
    formateur: FormateurDict,
) -> list[tuple[datetime.date, str]]:
    """Clés d'occupation : id référentiel (#pk) et clé texte stable si renseignées."""
    keys: list[tuple[datetime.date, str]] = []
    fid = (formateur.get("formateur_id") or "").strip()
    if fid:
        key_id = (date, f"#{fid}")
        keys.append(key_id)
    text = formateur_key(formateur)
    if text and not text.endswith("NOM:|PRENOM:"):
        key_text = (date, text)
        if key_text not in keys:
            keys.append(key_text)
    return keys


def formateur_key(formateur: FormateurDict) -> str:
    """Construit une clé stable d'identification d'un formateur."""
    nom = (formateur.get("nom") or "").strip().upper()
    prenom = (formateur.get("prenom") or "").strip().upper()
    if nom:
        return f"NOM:{nom}|PRENOM:{prenom}"
    numero = (formateur.get("numero") or "").strip().upper()
    email = (formateur.get("email") or "").strip().upper()
    if numero:
        return f"NUM:{numero}"
    if email:
        return f"MAIL:{email}"
    return f"NOM:{nom}|PRENOM:{prenom}"


def formateur_from_seance(seance: Seance) -> FormateurDict:
    """Retourne les détails formateur depuis une séance."""
    return {
        "nom": (seance.formateur_nom or "").strip(),
        "prenom": (seance.formateur_prenom or "").strip(),
        "numero": (seance.formateur_numero or "").strip(),
        "email": (seance.formateur_email or "").strip(),
        "telephone": (seance.formateur_telephone or "").strip(),
        "organisation": (seance.formateur_organisation or "").strip(),
    }


def formateur_disponible(
    occupations: FormateurOccupationIndex,
    date: datetime.date,
    formateur: FormateurDict,
    max_seances_jour: int,
) -> bool:
    """Retourne True si le formateur n'a pas atteint le max de séances sur la date."""
    keys = formateur_occupation_keys(date, formateur)
    if not keys:
        return True
    for key in keys:
        if occupations.get(key, 0) >= max_seances_jour:
            return False
    return True


def reserver_formateur(
    occupations: FormateurOccupationIndex,
    date: datetime.date,
    formateur: FormateurDict,
) -> None:
    """Incrémente le compteur de séances du formateur sur la date (toutes clés applicables)."""
    for key in formateur_occupation_keys(date, formateur):
        occupations[key] = occupations.get(key, 0) + 1


def dict_formateur_depuis_instance(formateur) -> FormateurDict:
    """Détails planning ; ``formateur_id`` sert à dédoublonner (non persisté sur Seance)."""
    return {
        "nom": (formateur.nom or "").strip(),
        "prenom": (formateur.prenom or "").strip(),
        "numero": (formateur.numero or "").strip(),
        "email": (formateur.email or "").strip(),
        "telephone": (formateur.telephone or "").strip(),
        "organisation": (formateur.organisation or "").strip(),
        "formateur_id": str(formateur.pk),
    }


def dict_formateur_vide() -> FormateurDict:
    return {
        "nom": "",
        "prenom": "",
        "numero": "",
        "email": "",
        "telephone": "",
        "organisation": "",
    }


def formateur_dict_est_renseigne(f: FormateurDict) -> bool:
    """True si le dict décrit un formateur assignable (identité minimale renseignée)."""
    return bool((f.get("nom") or "").strip() or (f.get("numero") or "").strip() or (f.get("email") or "").strip())


def build_formateurs_pool(groupe) -> dict[int, FormateurDict]:
    """
    Pool des affectations groupe/module (une entrée par module).
    Une incohérence M2M formateur/module est journalisée ; le planning décide de l'ordre
    de préférence dans ``choisir_formateur_disponible``.
    Format : {module_id: details_formateur}.
    """
    from apps.formations.models import AffectationFormateurGroupe

    pool: dict[int, FormateurDict] = {}
    affectations = (
        AffectationFormateurGroupe.objects.filter(groupe_id=groupe.pk)
        .select_related("module", "module__specialite", "formateur")
        .prefetch_related("formateur__specialites")
        .order_by("module__titre", "-id")
    )
    for item in affectations:
        if item.module_id in pool:
            continue
        formateur = item.formateur
        sid_set = item.module.ids_specialites_pour_matching_formateurs()
        if not formateur.specialites.filter(pk__in=sid_set).exists():
            logger.warning(
                "POOL_FORMATEUR_SPECIALITE_MISMATCH groupe_id=%s module_id=%s formateur_id=%s "
                "specialites_module_ids=%s — affectation conservée pour le planning",
                groupe.pk,
                item.module_id,
                formateur.pk,
                tuple(sorted(sid_set)),
            )
        pool[item.module_id] = dict_formateur_depuis_instance(formateur)
    return pool


def _incrementer_occupation_formateur(
    occupations: FormateurOccupationIndex,
    date: datetime.date,
    cle: str,
) -> None:
    key = (date, cle)
    occupations[key] = occupations.get(key, 0) + 1


def charger_occupations_formateurs_existantes(groupe_id: int) -> FormateurOccupationIndex:
    """Construit l'index du nombre de séances déjà assignées par formateur et par date."""
    occupations: FormateurOccupationIndex = {}
    if _seance_a_formateur_referentiel_id():
        qs = Seance.objects.exclude(groupe_id=groupe_id).filter(
            Q(formateur_nom__gt="") | Q(formateur_referentiel_id__isnull=False)
        )
    else:
        qs = Seance.objects.exclude(groupe_id=groupe_id).exclude(formateur_nom="")

    for s in qs:
        ref_id = getattr(s, "formateur_referentiel_id", None)
        if ref_id:
            _incrementer_occupation_formateur(occupations, s.date, f"#{ref_id}")
        details = formateur_from_seance(s)
        text_key = formateur_key(details)
        if text_key and not text_key.endswith("NOM:|PRENOM:"):
            _incrementer_occupation_formateur(occupations, s.date, text_key)
    return occupations


def charger_formateurs_par_module_date_salle_formation(
    formation_id: int, groupe_id: int
) -> dict[tuple[datetime.date, int], dict[str, str]]:
    """
    Index (date, module_id) -> {salle_norm: clé formateur} pour les séances des **autres**
    groupes de la même formation.

    Règle métier : même module et même jour, **groupes différents en parallèle** occupent des
    **salles différentes** ; chaque salle doit alors avoir un **formateur différent** (clé
    stable : nom+prénom, ou n°, ou e-mail). La détection repose sur la salle (une séance =
    une salle renseignée).
    """
    out: dict[tuple[datetime.date, int], dict[str, str]] = {}
    qs = (
        Seance.objects.filter(groupe__formation_id=formation_id)
        .exclude(groupe_id=groupe_id)
        .exclude(salle_nom="")
        .only(
            "date",
            "module_id",
            "salle_nom",
            "formateur_nom",
            "formateur_prenom",
            "formateur_numero",
            "formateur_email",
            "formateur_telephone",
            "formateur_organisation",
        )
    )
    for s in qs:
        fk = formateur_key(formateur_from_seance(s))
        if not fk or fk.endswith("NOM:|PRENOM:"):
            continue
        sn = s.salle_nom.strip().upper()
        out.setdefault((s.date, s.module_id), {})[sn] = fk
    return out


def enregistrer_formateur_meme_module_autre_salle(
    mapping: dict[tuple[datetime.date, int], dict[str, str]],
    date_val: datetime.date,
    module_id: int,
    salle_nom: str,
    formateur: FormateurDict,
) -> None:
    fk = formateur_key(formateur)
    if not fk or fk.endswith("NOM:|PRENOM:"):
        return
    sn = (salle_nom or "").strip().upper()
    if not sn:
        return
    mapping.setdefault((date_val, module_id), {})[sn] = fk


def choisir_formateur_disponible(
    occupations_formateurs: FormateurOccupationIndex,
    affectations_formateur: dict[int, FormateurDict],
    module_id: int,
    module_specialite_id: Optional[int],
    date: datetime.date,
    max_seances_jour: int,
    fallback: FormateurDict,
    *,
    specialite_ids: Optional[frozenset[int]] = None,
    salle_nom: str = "",
    occ_formateur_par_salle_meme_module: Optional[dict[tuple[datetime.date, int], dict[str, str]]] = None,
    formateurs_par_specialites_cache: Optional[dict[tuple[int, ...], list[FormateurDict]]] = None,
) -> FormateurDict:
    """
    Choisit un formateur pour le créneau.

    Module sans spécialité référentielle : affectation puis fallback texte du FormationModule.

    Module avec spécialité : si une **affectation groupe/module** existe (identifiant formateur
    renseigné), **seul** ce formateur est candidat (aucun autre du référentiel, pas de texte
    ``FormationModule``). Sinon les formateurs du référentiel dont la M2M couvre l'une des
    spécialités alignées sur le module (spécialité du module et/ou code ou libellé égal au
    titre du module, insensible à la casse), puis les textes ``formateur_*`` du
    ``FormationModule`` en dernier recours.

    Si ``occ_formateur_par_salle_meme_module`` et ``salle_nom`` sont fournis : un même
    formateur (clé stable) ne peut pas enseigner le même module le même jour dans une **autre**
    salle où un autre groupe de la formation a déjà ce module (en pratique : groupes
    différents => salles différentes => formateurs différents).

    Si aucun formateur n'est assignable (liste vide, quota/jour, affectation ou texte FM
    indisponible), retourne un dict formateur vide : le dispatch place la séance sans formateur.
    """

    def _eligible_salle_meme_module(c: FormateurDict) -> bool:
        if not occ_formateur_par_salle_meme_module or not (salle_nom or "").strip():
            return True
        fk = formateur_key(c)
        if not fk or fk.endswith("NOM:|PRENOM:"):
            return True
        s_norm = salle_nom.strip().upper()
        for autre_salle, autre_fk in occ_formateur_par_salle_meme_module.get((date, module_id), {}).items():
            if autre_salle == s_norm:
                continue
            if autre_fk and autre_fk == fk:
                return False
        return True

    def _premier_libre(candidats: list[FormateurDict]) -> Optional[FormateurDict]:
        for c in candidats:
            if formateur_disponible(occupations_formateurs, date, c, max_seances_jour):
                if _eligible_salle_meme_module(c):
                    return c
        return None

    if not module_specialite_id:
        candidat = affectations_formateur.get(module_id)
        if candidat:
            if formateur_disponible(occupations_formateurs, date, candidat, max_seances_jour):
                if _eligible_salle_meme_module(candidat):
                    return candidat
            logger.debug(
                "_choisir_formateur_disponible affectation groupe indisponible date=%s module_id=%s",
                date.isoformat(),
                module_id,
            )
            return dict_formateur_vide()

        if (fallback.get("nom") or "").strip():
            if formateur_disponible(occupations_formateurs, date, fallback, max_seances_jour):
                if _eligible_salle_meme_module(fallback):
                    return fallback
            logger.debug(
                "_choisir_formateur_disponible fallback FM texte indisponible date=%s module_id=%s",
                date.isoformat(),
                module_id,
            )
            return dict_formateur_vide()
        return dict_formateur_vide()

    from apps.formations.models import Formateur

    spec_ids = (
        specialite_ids
        if specialite_ids is not None
        else (frozenset({module_specialite_id}) if module_specialite_id else frozenset())
    )

    ordre: list[FormateurDict] = []
    pool_c = affectations_formateur.get(module_id)
    pool_pid = (pool_c or {}).get("formateur_id")
    affectation_exclusive = bool(pool_c and (pool_pid or "").strip())

    if affectation_exclusive:
        ordre.append(pool_c)
    else:
        spec_key = tuple(sorted(spec_ids))
        candidats_cache = None
        if formateurs_par_specialites_cache is not None:
            candidats_cache = formateurs_par_specialites_cache.get(spec_key)
        if candidats_cache is None:
            candidats_cache = []
            if spec_ids:
                for f in (
                    Formateur.objects.filter(specialites__id__in=spec_ids).distinct().order_by("nom", "prenom", "pk")
                ):
                    candidats_cache.append(dict_formateur_depuis_instance(f))
            if formateurs_par_specialites_cache is not None:
                formateurs_par_specialites_cache[spec_key] = candidats_cache
        ordre.extend(candidats_cache)

        if formateur_dict_est_renseigne(fallback):
            ordre.append(
                {
                    "nom": (fallback.get("nom") or "").strip(),
                    "prenom": (fallback.get("prenom") or "").strip(),
                    "numero": (fallback.get("numero") or "").strip(),
                    "email": (fallback.get("email") or "").strip(),
                    "telephone": (fallback.get("telephone") or "").strip(),
                    "organisation": (fallback.get("organisation") or "").strip(),
                    "formateur_id": "",
                }
            )

    result = _premier_libre(ordre)
    if result is not None:
        return result
    if len(ordre) == 0:
        logger.info(
            "_choisir_formateur_disponible aucun candidat pour la spécialité du module "
            "(affectation absente ou sans spécialité, et aucun formateur référentiel) "
            "date=%s module_id=%s specialite_ids=%s ; planning sans formateur sur ce créneau",
            date.isoformat(),
            module_id,
            tuple(sorted(spec_ids)),
        )
    else:
        logger.info(
            "_choisir_formateur_disponible aucun formateur libre (quota max séances/jour ou "
            "créneaux déjà pris) date=%s module_id=%s specialite_ids=%s nb_candidats=%s ; "
            "planning sans formateur sur ce créneau",
            date.isoformat(),
            module_id,
            tuple(sorted(spec_ids)),
            len(ordre),
        )
    return dict_formateur_vide()
