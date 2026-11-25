"""
Détection des chevauchements de salle entre formations distinctes.

Une "collision" est un couple de séances :
 - sur la même date,
 - dans la même salle (site/bâtiment/salle, comparaison insensible à la casse),
 - appartenant à deux formations différentes,
 - dont les créneaux horaires se chevauchent strictement.

Un "partage de salle le même jour" est plus permissif : même critère sans
imposer le chevauchement horaire (utile pour repérer les jours sensibles à
surveiller même si les créneaux sont disjoints).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date as date_cls, time
from typing import Iterable, Optional

from .models import Seance


def _norm(value: Optional[str]) -> str:
    return (value or "").strip().lower()


def _intervals_overlap(a_start: time, a_end: time, b_start: time, b_end: time) -> bool:
    """Vrai si [a_start, a_end[ et [b_start, b_end[ se chevauchent strictement."""
    return a_start < b_end and b_start < a_end


@dataclass
class SeanceLite:
    """Vue allégée d'une séance pour l'affichage des conflits."""

    seance_id: int
    formation_id: int
    formation_intitule: str
    formation_vague: str
    groupe_id: int
    groupe_nom: str
    module_titre: str
    site_nom: str
    batiment_nom: str
    salle_nom: str
    heure_debut: time
    heure_fin: time

    @classmethod
    def from_seance(cls, seance: Seance) -> "SeanceLite":
        formation = seance.groupe.formation
        return cls(
            seance_id=seance.pk,
            formation_id=formation.pk,
            formation_intitule=formation.intitule,
            formation_vague=formation.vague or "",
            groupe_id=seance.groupe_id,
            groupe_nom=seance.groupe.nom,
            module_titre=seance.module.titre if seance.module else "",
            site_nom=seance.site_nom or "",
            batiment_nom=seance.batiment_nom or "",
            salle_nom=seance.salle_nom or "",
            heure_debut=seance.heure_debut,
            heure_fin=seance.heure_fin,
        )


@dataclass
class CollisionSalle:
    """Conflit horaire avéré entre deux formations dans une même salle."""

    date: date_cls
    site_nom: str
    batiment_nom: str
    salle_nom: str
    seance_a: SeanceLite
    seance_b: SeanceLite

    @property
    def salle_libelle(self) -> str:
        parts = [p for p in [self.site_nom, self.batiment_nom, self.salle_nom] if p]
        return " / ".join(parts) or "—"


@dataclass
class PartageSalleJour:
    """Même salle, même jour, formations différentes — sans collision horaire."""

    date: date_cls
    site_nom: str
    batiment_nom: str
    salle_nom: str
    seance_a: SeanceLite
    seance_b: SeanceLite

    @property
    def salle_libelle(self) -> str:
        parts = [p for p in [self.site_nom, self.batiment_nom, self.salle_nom] if p]
        return " / ".join(parts) or "—"


@dataclass
class FormationResume:
    """Synthèse d'occupation par formation."""

    formation_id: int
    intitule: str
    vague: str
    nb_seances: int = 0
    nb_jours: int = 0
    date_premier_jour: Optional[date_cls] = None
    date_dernier_jour: Optional[date_cls] = None
    salles: set[tuple[str, str, str]] = field(default_factory=set)


@dataclass
class ChevauchementsReport:
    """Rapport complet pour l'IHM."""

    formations: list[FormationResume]
    salles_partagees: list[tuple[str, str, str]]
    jours_communs: list[date_cls]
    partages_jour: list[PartageSalleJour]
    collisions: list[CollisionSalle]

    @property
    def nb_formations(self) -> int:
        return len(self.formations)

    @property
    def nb_collisions(self) -> int:
        return len(self.collisions)

    @property
    def nb_partages_jour(self) -> int:
        return len(self.partages_jour)

    @property
    def nb_salles_partagees(self) -> int:
        return len(self.salles_partagees)


def _collect_seances(formation_ids: Optional[Iterable[int]] = None) -> list[Seance]:
    """Charge les séances avec les jointures utiles pour l'affichage."""
    qs = Seance.objects.select_related("groupe__formation", "module").all().order_by("date", "heure_debut")
    if formation_ids:
        qs = qs.filter(groupe__formation_id__in=list(formation_ids))
    return list(qs)


def detecter_chevauchements(
    formation_ids: Optional[Iterable[int]] = None,
) -> ChevauchementsReport:
    """
    Analyse les séances et retourne le rapport de chevauchements de salles
    inter-formations.

    Si `formation_ids` est fourni, l'analyse se restreint à cet ensemble.
    Sinon, on regarde toutes les formations existantes.
    """
    seances = _collect_seances(formation_ids)

    resumes: dict[int, FormationResume] = {}
    by_room_day: dict[tuple, list[Seance]] = defaultdict(list)
    days_per_formation: dict[int, set[date_cls]] = defaultdict(set)

    for s in seances:
        formation = s.groupe.formation
        resume = resumes.setdefault(
            formation.pk,
            FormationResume(
                formation_id=formation.pk,
                intitule=formation.intitule,
                vague=formation.vague or "",
            ),
        )
        resume.nb_seances += 1
        room_key = (_norm(s.site_nom), _norm(s.batiment_nom), _norm(s.salle_nom))
        if any(room_key):
            resume.salles.add(room_key)
        if resume.date_premier_jour is None or s.date < resume.date_premier_jour:
            resume.date_premier_jour = s.date
        if resume.date_dernier_jour is None or s.date > resume.date_dernier_jour:
            resume.date_dernier_jour = s.date
        days_per_formation[formation.pk].add(s.date)

        if not any(room_key):
            continue
        by_room_day[(s.date, room_key)].append(s)

    for resume in resumes.values():
        resume.nb_jours = len(days_per_formation.get(resume.formation_id, set()))

    collisions: list[CollisionSalle] = []
    partages_jour: list[PartageSalleJour] = []

    for (jour, room_key), seances_du_lot in by_room_day.items():
        if len(seances_du_lot) < 2:
            continue
        for i in range(len(seances_du_lot)):
            for j in range(i + 1, len(seances_du_lot)):
                sa, sb = seances_du_lot[i], seances_du_lot[j]
                fa = sa.groupe.formation_id
                fb = sb.groupe.formation_id
                if fa == fb:
                    continue
                lite_a = SeanceLite.from_seance(sa)
                lite_b = SeanceLite.from_seance(sb)
                site_lbl = sa.site_nom or sb.site_nom
                bat_lbl = sa.batiment_nom or sb.batiment_nom
                salle_lbl = sa.salle_nom or sb.salle_nom
                if _intervals_overlap(sa.heure_debut, sa.heure_fin, sb.heure_debut, sb.heure_fin):
                    collisions.append(
                        CollisionSalle(
                            date=jour,
                            site_nom=site_lbl,
                            batiment_nom=bat_lbl,
                            salle_nom=salle_lbl,
                            seance_a=lite_a,
                            seance_b=lite_b,
                        )
                    )
                else:
                    partages_jour.append(
                        PartageSalleJour(
                            date=jour,
                            site_nom=site_lbl,
                            batiment_nom=bat_lbl,
                            salle_nom=salle_lbl,
                            seance_a=lite_a,
                            seance_b=lite_b,
                        )
                    )

    formations_resume = sorted(
        resumes.values(),
        key=lambda r: (r.date_premier_jour or date_cls.max, r.intitule),
    )

    # Jours en intersection entre au moins 2 formations.
    all_days_sets = list(days_per_formation.values())
    jours_communs: set[date_cls] = set()
    if len(all_days_sets) >= 2:
        for i in range(len(all_days_sets)):
            for j in range(i + 1, len(all_days_sets)):
                jours_communs.update(all_days_sets[i] & all_days_sets[j])

    # Salles utilisées par au moins 2 formations sur l'ensemble de la période.
    salles_par_formation: dict[int, set[tuple]] = {r.formation_id: set(r.salles) for r in formations_resume}
    salle_use_count: Counter = Counter()
    for salles in salles_par_formation.values():
        for k in salles:
            salle_use_count[k] += 1
    salles_partagees = sorted(k for k, n in salle_use_count.items() if n >= 2)

    collisions.sort(key=lambda c: (c.date, c.salle_nom, c.seance_a.heure_debut))
    partages_jour.sort(key=lambda p: (p.date, p.salle_nom))

    return ChevauchementsReport(
        formations=list(formations_resume),
        salles_partagees=salles_partagees,
        jours_communs=sorted(jours_communs),
        partages_jour=partages_jour,
        collisions=collisions,
    )
