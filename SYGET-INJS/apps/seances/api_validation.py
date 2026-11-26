"""Validation métier pour les mises à jour API de séances."""

from __future__ import annotations

from apps.parametrage.models import JourFerie, get_parametres_pour_formation
from apps.seances.models import Seance
from apps.seances.planning import locations as planning_locations

PATCH_ALLOWED_FIELDS = frozenset(
    {
        "date",
        "heure_debut",
        "heure_fin",
        "site_nom",
        "batiment_nom",
        "salle_nom",
        "formateur_nom",
        "formateur_prenom",
        "formateur_numero",
        "formateur_email",
    }
)


def valider_patch_seance(seance: Seance, data: dict) -> list[str]:
    """
    Retourne la liste des erreurs métier après application virtuelle des champs fournis.
    ``data`` contient uniquement les champs autorisés déjà parsés (date/time objects ou str).
    """
    errors: list[str] = []
    changed = set(data.keys())

    date = data.get("date", seance.date)
    heure_debut = data.get("heure_debut", seance.heure_debut)
    heure_fin = data.get("heure_fin", seance.heure_fin)
    site_nom = data.get("site_nom", seance.site_nom or "")
    salle_nom = data.get("salle_nom", seance.salle_nom or "")

    if heure_fin <= heure_debut:
        errors.append("heure_fin doit être postérieure à heure_debut.")

    if "date" in changed and JourFerie.objects.filter(actif=True, date=date).exists():
        errors.append(f"La date {date:%d/%m/%Y} est un jour férié.")

    localisations, _salle_ids = planning_locations.charger_localisations_salles()
    cle_salle = (salle_nom or "").strip().upper()
    if "salle_nom" in changed and cle_salle:
        loc = localisations.get(cle_salle)
        if loc is None:
            errors.append(f"Salle « {salle_nom} » inconnue du référentiel paramétrage.")
        else:
            _site_resolu, _batiment_resolu, capacite = loc
            params = get_parametres_pour_formation(seance.groupe.formation_id)
            tolerance = max(0, int(getattr(params, "tolerance_capacite_salle", 0) or 0))
            effectif = int(seance.groupe.nb_auditeurs or 0)
            seuil = max(0, effectif - tolerance)
            if capacite > 0 and seuil > 0 and capacite < seuil:
                errors.append(
                    f"Capacité insuffisante en salle « {salle_nom} » "
                    f"({capacite} places pour {effectif} auditeur(s))."
                )

    site_effectif = (site_nom or "").strip()
    if not site_effectif and cle_salle:
        site_effectif = (localisations.get(cle_salle, ("", "", 0)) or ("", "", 0))[0]
    if site_effectif and ("date" in changed or "site_nom" in changed or "salle_nom" in changed):
        periodes = planning_locations.charger_periodes_disponibilite_sites()
        if not planning_locations.site_disponible_a_date(site_effectif, date, periodes):
            errors.append(f"Le site « {site_effectif} » n'est pas disponible le {date:%d/%m/%Y}.")

    if (salle_nom or "").strip() and changed & {"date", "heure_debut", "heure_fin", "salle_nom"}:
        overlaps = (
            Seance.objects.exclude(pk=seance.pk)
            .filter(
                date=date,
                salle_nom__iexact=(salle_nom or "").strip(),
                heure_debut__lt=heure_fin,
                heure_fin__gt=heure_debut,
            )
            .exclude(salle_nom="")
        )
        if overlaps.exists():
            errors.append("La salle est déjà occupée par une autre séance sur ce créneau.")

    return errors
