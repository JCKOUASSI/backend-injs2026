"""Détection des conflits visibles dans un planning de groupe."""

from __future__ import annotations

import datetime
from collections import Counter
from dataclasses import dataclass

from apps.formations.models import FormationModule
from apps.formations.rythme import rythme_mensuel_effectif_pour_module
from apps.groupes.models import Groupe
from apps.parametrage.models import JourFerie, get_parametres_pour_formation
from apps.seances.models import Seance
from apps.seances.planning import locations as planning_locations


@dataclass
class ConflitPlanning:
    """Représente une anomalie détectée sur une séance."""

    seance_id: int
    type: str
    message: str


def seance_dans_plages(groupe: Groupe, seance) -> bool:
    """Vérifie si une séance est entièrement incluse dans une plage horaire active."""
    config = getattr(groupe, "config", None)
    if not config:
        return False
    dans_matin = (
        config.matin_actif
        and seance.heure_debut >= config.matin_heure_debut
        and seance.heure_fin <= config.matin_heure_fin
    )
    dans_soir = (
        config.soir_actif
        and seance.heure_debut >= config.soir_heure_debut
        and seance.heure_fin <= config.soir_heure_fin
    )
    return dans_matin or dans_soir


def date_autorisee_par_rythme_mensuel(jour: datetime.date, rythme_mensuel: str) -> bool:
    """Contrainte mensuelle de formation (1/2/3 premières semaines ou tout le mois)."""
    rythme = (rythme_mensuel or "").strip()
    if rythme not in {"1", "2", "3"}:
        return True
    semaine_du_mois = ((jour.day - 1) // 7) + 1
    return semaine_du_mois <= int(rythme)


def detecter_conflits_planning(groupe: Groupe, seances: list) -> list[ConflitPlanning]:
    """Détecte les conflits visibles dans le planning du groupe."""
    conflits: list[ConflitPlanning] = []
    params = get_parametres_pour_formation(groupe.formation_id)
    max_seances_jour = params.max_seances_par_jour_defaut or 2
    tolerance_capacite = max(0, int(getattr(params, "tolerance_capacite_salle", 0) or 0))
    effectif = int(groupe.nb_auditeurs or 0)
    seuil_capacite = max(0, effectif - tolerance_capacite)
    jours_feries = set(JourFerie.objects.filter(actif=True).values_list("date", flat=True))
    localisations, _ = planning_locations.charger_localisations_salles()
    periodes_sites = planning_locations.charger_periodes_disponibilite_sites()
    formation = groupe.formation
    formation_modules_par_module_id = {
        fm.module_id: fm
        for fm in FormationModule.objects.filter(formation_id=formation.pk).select_related("periode", "formation")
    }

    modules_par_date: dict[datetime.date, set[int]] = {}
    for s in seances:
        modules_par_date.setdefault(s.date, set()).add(s.module_id)
    dates_multi_modules = {d for d, mids in modules_par_date.items() if len(mids) > 1}

    counts = Counter(
        (
            s.date,
            s.module_id,
            (s.salle_nom or "").strip().upper(),
        )
        for s in seances
    )
    buckets_satures = sorted(k for k, n in counts.items() if n > max_seances_jour)
    seance_ref_par_bucket = {}
    for s in seances:
        key = (s.date, s.module_id, (s.salle_nom or "").strip().upper())
        seance_ref_par_bucket.setdefault(key, s)

    for date_saturee, module_id, salle_norm in buckets_satures:
        seance_ref = seance_ref_par_bucket.get((date_saturee, module_id, salle_norm))
        module_titre = seance_ref.module.titre if seance_ref and getattr(seance_ref, "module", None) else "Module"
        salle_libelle = salle_norm or "SALLE NON RENSEIGNEE"
        conflits.append(
            ConflitPlanning(
                seance_id=seance_ref.pk if seance_ref and seance_ref.pk else 0,
                type="MAX_SEANCES_JOUR",
                message=(
                    f"Trop de séances le {date_saturee:%d/%m/%Y} pour le module '{module_titre}' "
                    f"en salle '{salle_libelle}' ({counts[(date_saturee, module_id, salle_norm)]} > {max_seances_jour})."
                ),
            )
        )

    counts_formateurs = Counter(
        (s.date, (s.formateur_nom or "").strip().upper()) for s in seances if (s.formateur_nom or "").strip()
    )
    buckets_formateurs = sorted(k for k, n in counts_formateurs.items() if n > max_seances_jour)
    seance_ref_par_formateur = {}
    for s in seances:
        key = (s.date, (s.formateur_nom or "").strip().upper())
        if key[1]:
            seance_ref_par_formateur.setdefault(key, s)

    for date_saturee, formateur_norm in buckets_formateurs:
        seance_ref = seance_ref_par_formateur.get((date_saturee, formateur_norm))
        conflits.append(
            ConflitPlanning(
                seance_id=seance_ref.pk if seance_ref and seance_ref.pk else 0,
                type="MAX_SEANCES_FORMATEUR_JOUR",
                message=(
                    f"Trop de séances le {date_saturee:%d/%m/%Y} pour le formateur '{formateur_norm}' "
                    f"({counts_formateurs[(date_saturee, formateur_norm)]} > {max_seances_jour})."
                ),
            )
        )

    for seance in seances:
        if seance.date in jours_feries:
            conflits.append(
                ConflitPlanning(
                    seance_id=seance.pk,
                    type="JOUR_FERIE",
                    message=f"Séance planifiée un jour férié ({seance.date:%d/%m/%Y}).",
                )
            )

        if not seance_dans_plages(groupe, seance):
            conflits.append(
                ConflitPlanning(
                    seance_id=seance.pk,
                    type="HORS_PLAGE",
                    message="Séance hors des plages horaires autorisées pour ce groupe.",
                )
            )

        if seance.date in dates_multi_modules:
            module_titre = seance.module.titre if getattr(seance, "module", None) else "Module"
            conflits.append(
                ConflitPlanning(
                    seance_id=seance.pk,
                    type="MODULE_PAR_JOUR",
                    message=(
                        f"Plusieurs modules le {seance.date:%d/%m/%Y} pour ce groupe "
                        f"(règle : un seul module par jour) — séance « {module_titre} »."
                    ),
                )
            )

        fm = formation_modules_par_module_id.get(seance.module_id)
        rythme_mensuel = (
            rythme_mensuel_effectif_pour_module(groupe, fm)
            if fm
            else (
                (getattr(groupe, "rythme_mensuel", "") or "").strip()
                or (getattr(formation, "rythme_mensuel", "") or "").strip()
            )
        )
        if not date_autorisee_par_rythme_mensuel(seance.date, rythme_mensuel):
            conflits.append(
                ConflitPlanning(
                    seance_id=seance.pk,
                    type="RYTHME_MENSUEL",
                    message=(
                        f"Séance le {seance.date:%d/%m/%Y} hors de la cadence mensuelle autorisée "
                        f"({rythme_mensuel or 'tout le mois'})."
                    ),
                )
            )

        salle_nom = (seance.salle_nom or "").strip().upper()
        if salle_nom and seuil_capacite > 0:
            capacite = int((localisations.get(salle_nom, ("", "", 0)) or ("", "", 0))[2] or 0)
            if capacite > 0 and capacite < seuil_capacite:
                conflits.append(
                    ConflitPlanning(
                        seance_id=seance.pk,
                        type="CAPACITE_SALLE",
                        message=(
                            f"Capacité insuffisante en salle « {seance.salle_nom} » "
                            f"({capacite} places pour {effectif} auditeur(s), tolérance {tolerance_capacite})."
                        ),
                    )
                )

        site_nom = (seance.site_nom or "").strip()
        if not site_nom and salle_nom:
            site_nom = (localisations.get(salle_nom, ("", "", 0)) or ("", "", 0))[0]
        if site_nom and not planning_locations.site_disponible_a_date(site_nom, seance.date, periodes_sites):
            conflits.append(
                ConflitPlanning(
                    seance_id=seance.pk,
                    type="SITE_INDISPONIBLE",
                    message=(
                        f"Le site « {site_nom} » n'est pas disponible le {seance.date:%d/%m/%Y} "
                        f"(hors période de disponibilité paramétrée)."
                    ),
                )
            )

        if salle_nom:
            overlaps = Seance.objects.exclude(groupe_id=groupe.pk).filter(
                date=seance.date,
                salle_nom__iexact=seance.salle_nom,
                heure_debut__lt=seance.heure_fin,
                heure_fin__gt=seance.heure_debut,
            )
            if overlaps.exists():
                conflits.append(
                    ConflitPlanning(
                        seance_id=seance.pk,
                        type="SALLE_OCCUPEE",
                        message="La salle est déjà occupée par un autre groupe sur ce créneau.",
                    )
                )

    uniques: dict[tuple[int, str, str], ConflitPlanning] = {}
    for conflit in conflits:
        uniques[(conflit.seance_id, conflit.type, conflit.message)] = conflit
    return list(uniques.values())
