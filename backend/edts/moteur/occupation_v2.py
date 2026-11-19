"""Index daté en mémoire pour vérifier les conflits de créneaux (phase 2).

Sans accès DB et sans modification des placements : les chemins de mutation
seront raccordés et sérialisés sur VerrouJour dans une phase ultérieure.
"""
from __future__ import annotations

from datetime import date, time
from typing import Iterable


class OccupationHeriteeNonResolue(ValueError):
    """Une plage historique non datée exige un audit avant calcul exact."""


def minute(horaire: time) -> int:
    if horaire.second or horaire.microsecond:
        raise ValueError('Horaire hors précision minute : pas d’arrondi implicite.')
    return horaire.hour * 60 + horaire.minute


class IndexOccupation:
    """Bitsets de 1440 minutes, par (date, ressource, identifiant).

    Intersection et ajout par opérateurs entiers, pour une journée bornée ;
    l'effectif des étudiants n'est jamais chargé dans l'index.
    """

    def __init__(self):
        self._masques: dict[tuple[date, str, int], int] = {}

    @staticmethod
    def _masque(debut: int, fin: int) -> int:
        if not (0 <= debut < fin <= 1440):
            raise ValueError('Créneau invalide [début, fin) en minutes.')
        return ((1 << (fin - debut)) - 1) << debut

    @staticmethod
    def _cles(jour: date, groupe_id: int, formateur_id: int | None,
              salle_id: int | None) -> tuple[tuple[date, str, int], ...]:
        if not isinstance(jour, date) or not groupe_id or groupe_id < 1:
            raise ValueError('Date et identifiant de groupe sont obligatoires.')
        return tuple((jour, type_ressource, identifiant) for type_ressource, identifiant in (
            ('GROUPE', groupe_id), ('FORMATEUR', formateur_id), ('SALLE', salle_id)
        ) if identifiant is not None)

    def conflits(self, jour: date, debut: int, fin: int, *, groupe_id: int,
                 formateur_id: int | None = None, salle_id: int | None = None) -> list[str]:
        masque = self._masque(debut, fin)
        return [ressource for cle in self._cles(jour, groupe_id, formateur_id, salle_id)
                if self._masques.get(cle, 0) & masque
                for ressource in [cle[1]]]

    def ajouter(self, jour: date, debut: int, fin: int, *, groupe_id: int,
                formateur_id: int | None = None, salle_id: int | None = None) -> list[str]:
        """Ajout atomique dans l'index : en cas de conflit aucun bit ne change."""
        masque = self._masque(debut, fin)
        cles = self._cles(jour, groupe_id, formateur_id, salle_id)
        conflits = [cle[1] for cle in cles if self._masques.get(cle, 0) & masque]
        if not conflits:
            for cle in cles:
                self._masques[cle] = self._masques.get(cle, 0) | masque
        return conflits

    @property
    def nombre_ressources_dates(self) -> int:
        return len(self._masques)


def indexer_affectations(affectations: Iterable) -> IndexOccupation:
    """Alimente l'index en flux, refuse toute plage historique non résolue."""
    index = IndexOccupation()
    for aff in affectations:
        if not aff.actif:
            continue
        if aff.date_seance is None:
            raise OccupationHeriteeNonResolue('Placement actif sans date réelle : audit requis.')
        if aff.groupe_id is None or aff.minute_debut is None or aff.minute_fin is None:
            raise OccupationHeriteeNonResolue('Placement daté sans ressource ou plage validée.')
        conflits = index.ajouter(aff.date_seance, aff.minute_debut, aff.minute_fin,
                                  groupe_id=aff.groupe_id, formateur_id=aff.formateur_id,
                                  salle_id=aff.salle_id)
        if conflits:
            raise ValueError('Conflit préexistant dans les séances datées : revue requise.')
    return index
