"""Décision unitaire commune aux campagnes et au mode manuel (phase 3).

Le solveur est pur : aucune mutation DB, aucun effet sur Présences QR.
L'écriture expérimentale est séparée et interdite hors années BENCHMARK.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable

from edts.moteur.calendrier_v2 import evaluer_periodes
from edts.moteur.occupation_v2 import IndexOccupation, minute


@dataclass(frozen=True)
class TravailSeance:
    annee_id: int
    groupe_id: int
    ecue_id: int
    type_seance: str
    ordinal: int
    duree_minutes: int
    effectif: int
    formateur_id: int | None = None
    affectation_pedagogique_id: int | None = None
    source_confirmee: bool = False
    source_document: str = ''

    def cle(self) -> str:
        entree = (f'GETINJS-V2|{self.annee_id}|{self.groupe_id}|{self.ecue_id}|'
                  f'{self.type_seance}|{self.ordinal}')
        return hashlib.sha256(entree.encode()).hexdigest()


@dataclass(frozen=True)
class DecisionLigne:
    statut: str
    code: str
    cle: str
    jour: date | None = None
    creneau_id: int | None = None
    salle_id: int | None = None
    debut: int | None = None
    fin: int | None = None
    score_souple: float = 0.0
    alternatives: tuple[tuple[date, int, int], ...] = ()


NATURE = {'CM': 'COURS', 'TD': 'TD', 'TP': 'TP', 'EXAM': 'EVALUATION'}
JOURS = ('LUNDI', 'MARDI', 'MERCREDI', 'JEUDI', 'VENDREDI', 'SAMEDI', 'DIMANCHE')


def dates_annee(annee) -> Iterable[date]:
    jour = annee.date_debut
    while jour <= annee.date_fin:
        yield jour
        jour += timedelta(days=1)


def _indisponible(disponibilites, travail, salle, jour, debut, fin):
    """INDISPONIBLE est dur ; PREFERENCE reste souple (phase 3 minimale)."""
    for dispo in disponibilites:
        if dispo.jour != JOURS[jour.weekday()] or dispo.statut != 'INDISPONIBLE':
            continue
        if not (dispo.enseignant_id == travail.formateur_id and travail.formateur_id or
                dispo.salle_id == salle.pk):
            continue
        if debut < minute(dispo.heure_fin) and minute(dispo.heure_debut) < fin:
            return True
    return False


def choisir_ligne(travail: TravailSeance, *, annee, groupe, revision: int,
                  periodes: Iterable, creneaux: Iterable, salles: Iterable,
                  disponibilites: Iterable = (), index: IndexOccupation,
                  dates: Iterable[date] | None = None, graine: int = 0,
                  suggestions: int = 3, politique: dict | None = None) -> DecisionLigne:
    """Recherche déterministe en flux ; une ligne → un résultat explicite."""
    cle = travail.cle()
    if travail.annee_id != annee.pk or travail.groupe_id != groupe.pk:
        return DecisionLigne('A_REVOIR', 'PERIMETRE_INCOHERENT', cle)
    if not (travail.source_confirmee and travail.source_document.strip()):
        return DecisionLigne('A_REVOIR', 'VOLUME_NON_CONFIRME', cle)
    if travail.type_seance not in NATURE or travail.duree_minutes <= 0 or travail.effectif <= 0:
        return DecisionLigne('A_REVOIR', 'BESOIN_INCOMPLET', cle)
    if not travail.formateur_id:
        return DecisionLigne('A_REVOIR', 'ENSEIGNANT_NON_RESOLU', cle)
    from edts.moteur.contraintes import compatible_salle, capacite_suffisante

    slots = tuple(sorted(creneaux, key=lambda c: (JOURS.index(c.jour), c.heure_debut, c.pk)))
    rooms = tuple(sorted(salles, key=lambda s: s.pk))
    periods = tuple(periodes)
    unavail = tuple(disponibilites)
    if not slots or not rooms:
        return DecisionLigne('ECHEC', 'RESSOURCES_ABSENTES', cle)
    candidats = []
    motifs = set()
    # Un parcours déterministe sur les dates réelles, sans charger les étudiants.
    for jour in dates if dates is not None else dates_annee(annee):
        calendrier = evaluer_periodes(annee, groupe, jour, NATURE[travail.type_seance],
                                      periods, revision_numero=revision)
        if not calendrier.autorise:
            motifs.add(calendrier.code)
            continue
        for slot in slots:
            if slot.jour != JOURS[jour.weekday()]:
                continue
            debut, fin = minute(slot.heure_debut), minute(slot.heure_fin)
            if fin - debut != travail.duree_minutes:
                motifs.add('DUREE_CRENEAU_INCOMPATIBLE')
                continue
            for salle in rooms:
                if not compatible_salle(salle, NATURE[travail.type_seance]):
                    motifs.add('TYPE_SALLE')
                    continue
                if not capacite_suffisante(salle, travail.effectif):
                    motifs.add('CAPACITE_SALLE')
                    continue
                if _indisponible(unavail, travail, salle, jour, debut, fin):
                    motifs.add('INDISPONIBILITE')
                    continue
                if index.conflits(jour, debut, fin, groupe_id=travail.groupe_id,
                                  formateur_id=travail.formateur_id, salle_id=salle.pk):
                    motifs.add('OCCUPATION')
                    continue
                # Politique souple pondérée ; la préférence matinale ne sert
                # qu'à départager les candidats (aucune contrainte dure).
                score = (index.score_souple(jour, travail.groupe_id, debut, fin, politique)
                         + (debut // 60 - 8) ** 2 / 1000)
                tie = hashlib.sha256(f'{graine}|{cle}|{jour}|{slot.pk}|{salle.pk}'.encode()).hexdigest()
                candidats.append((score, tie, jour, slot.pk, salle.pk, debut, fin))
                if len(candidats) >= max(1, suggestions) * 8:
                    break
            if len(candidats) >= max(1, suggestions) * 8:
                break
        if len(candidats) >= max(1, suggestions) * 8:
            break
    if candidats:
        candidats.sort()
        premier = candidats[0]
        alternatives = tuple((c[2], c[3], c[4]) for c in candidats[1:suggestions + 1])
        return DecisionLigne('PLACEE', 'PLACEMENT_POSSIBLE', cle, jour=premier[2],
                             creneau_id=premier[3], salle_id=premier[4],
                             debut=premier[5], fin=premier[6],
                             score_souple=float(premier[0]), alternatives=alternatives)
    if 'CALENDRIER_NON_VALIDE' in motifs or 'AUCUNE_PERIODE_VALIDEE' in motifs or 'CALENDRIER_AMBIGU' in motifs:
        return DecisionLigne('A_REVOIR', 'CALENDRIER_A_REVOIR', cle)
    return DecisionLigne('ECHEC', sorted(motifs)[0] if motifs else 'AUCUN_CRENEAU', cle)
