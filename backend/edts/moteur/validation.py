"""Lot L8 — Étapes P & Q : validation d'un emploi du temps (``validate_schedule``).

Contrôle **a posteriori** d'un plan (généré ou modifié manuellement). Il ne
corrige rien : il qualifie. Un EDT n'est publiable que si ce validateur ne
remonte aucune violation bloquante (étape S : validation humaine obligatoire).

Vérifications (contraintes fortes) :
    conflits enseignant / groupe / salle = 0
    séances hors calendrier = 0
    salles incompatibles = 0
    salles insuffisantes = 0
    indisponibilités enseignant / salle = 0
    volume non couvert = 0

Deux notions distinctes, à ne jamais confondre :

* **violation** — contrainte dure enfreinte ; bloque la publication ;
* **warning**   — situation à connaître (capacité non renseignée, preference
  non respectée) ; n'empêche pas la publication.

Une capacité de salle ``NULL`` n'est **pas** traitée comme un rejet : elle
produit un warning, parce qu'inventer une limite serait plus grave que de
signaler une donnée manquante.
"""

from dataclasses import dataclass, field

from edts.moteur import contraintes as C

BLOQUANT = 'BLOQUANT'
AVERTISSEMENT = 'AVERTISSEMENT'
OK = 'OK'

#: Statuts d'EDT : la publication n'est ouverte qu'à partir de ces états.
STATUTS_PUBLIABLES = ('VALIDE',)


@dataclass
class RapportValidation:
    """Verdict de validation, toujours structuré (étape P)."""

    valide: bool
    violations: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    couverture: dict = field(default_factory=dict)
    statut: str = OK

    def as_dict(self):
        return {
            'valide': self.valide,
            'statut': self.statut,
            'violations': [v.as_dict() for v in self.violations],
            'warnings': self.warnings,
            'couverture': self.couverture,
        }


# ── Vérifications par contrainte ──────────────────────────────────────────────

def verifier_conflits(placements, violations, warnings):
    """C1 / C2 / C3 — aucun chevauchement sur ressource partagée."""
    from collections import defaultdict

    par_creneau = defaultdict(list)
    for place in placements:
        par_creneau[(place.jour, place.semaine_debut)].append(place)

    for (jour, semaine), groupe_places in sorted(
        par_creneau.items(), key=lambda kv: (kv[0][0], kv[0][1]),
    ):
        for i in range(len(groupe_places)):
            for j in range(i + 1, len(groupe_places)):
                a, b = groupe_places[i], groupe_places[j]
                if not C._chevauche(a.heure_debut, a.heure_fin,
                                     b.heure_debut, b.heure_fin):
                    continue
                if a.enseignant_id and a.enseignant_id == b.enseignant_id:
                    violations.append(C.Violation(
                        C.C1_CONFLIT_ENSEIGNANT,
                        f'Enseignant {a.enseignant_id} occupé deux fois le {jour} '
                        f'(semaine {semaine}).',
                    ))
                if a.groupe_id and a.groupe_id == b.groupe_id:
                    violations.append(C.Violation(
                        C.C2_CONFLIT_GROUPE,
                        f'Groupe {a.groupe_id} occupé deux fois le {jour} '
                        f'(semaine {semaine}).',
                    ))
                if a.salle_id and a.salle_id == b.salle_id:
                    violations.append(C.Violation(
                        C.C3_CONFLIT_SALLE,
                        f'Salle {a.salle_id} occupée deux fois le {jour} '
                        f'(semaine {semaine}).',
                    ))
    return violations


def verifier_salles(placements, violations, warnings):
    """C4 (capacité) / C6 (indisponibilité) / C7 (compatibilité)."""
    for place in placements:
        salle = place.salle
        if salle is None:
            warnings.append(
                f'{place.besoin.intitule} : séance sans salle, le contrôle de '
                'capacité et de compatibilité ne peut pas être appliqué.'
            )
            continue
        if not C.compatible_salle(salle, place.besoin.nature):
            violations.append(C.Violation(
                C.C7_COMPATIBILITE_SALLE,
                f'Salle {salle.nom} ({salle.type_lieu}) incompatible avec un '
                f'{place.besoin.type_enseignement}.',
                ressource=salle.nom,
            ))
        if not C.capacite_suffisante(salle, place.besoin.effectif):
            violations.append(C.Violation(
                C.C4_CAPACITE,
                f'Salle {salle.nom} : capacité {salle.capacite} < effectif '
                f'{place.besoin.effectif}.',
                ressource=salle.nom,
            ))
        elif salle.capacite is None:
            warnings.append(
                f'Salle {salle.nom} : capacité non renseignée, contrainte C4 non '
                'vérifiable.'
            )
        if C.indisponible_salle(
            salle.pk, place.besoin.annee_academique_id, place.jour,
            place.heure_debut, place.heure_fin,
        ):
            violations.append(C.Violation(
                C.C6_DISPONIBILITE_SALLE,
                f'Salle {salle.nom} déclarée indisponible le {place.jour}.',
                ressource=salle.nom,
            ))
    return violations


def verifier_enseignants(placements, violations, warnings):
    """C5 (indisponibilité) et cohérence de l'affectation (C8)."""
    for place in placements:
        besoin = place.besoin
        if besoin.enseignant_id and C.indisponible_enseignant(
            besoin.enseignant_id, besoin.annee_academique_id, place.jour,
            place.heure_debut, place.heure_fin,
        ):
            violations.append(C.Violation(
                C.C5_DISPONIBILITE_ENSEIGNANT,
                f'Enseignant {besoin.enseignant_id} indisponible le {place.jour} '
                f'{place.heure_debut:%H:%M}–{place.heure_fin:%H:%M}.',
            ))
        elif not besoin.enseignant_id:
            warnings.append(
                f'{besoin.intitule} : aucun enseignant, les conflits C1/C5 ne sont '
                'pas garantis.'
            )
        # C8 — cohérence pédagogique : la séance garde sa clé d'affectation.
        if not besoin.affectation_pedagogique_id:
            violations.append(C.Violation(
                C.C8_COHERENCE_PEDAGOGIQUE,
                f'{besoin.intitule} : séance sans affectation pédagogique (C8).',
            ))
    return violations


def _couverture(placements, non_places=()):
    """Étape Q — volume attendu / planifié / taux de couverture."""
    def volume(plans):
        return sum(p.besoin.nb_seances * p.besoin.duree_seance_heures
                   for p in plans)

    def seances(plans):
        return sum(p.besoin.nb_seances for p in plans)

    attendu_h = round(volume(list(placements) + list(non_places)), 2)
    planifie_h = round(volume(placements), 2)
    attendu_s = seances(list(placements) + list(non_places))
    planifie_s = seances(placements)
    return {
        'heures_attendues': attendu_h,
        'heures_planifiees': planifie_h,
        'heures_non_couvertes': round(attendu_h - planifie_h, 2),
        'seances_attendues': attendu_s,
        'seances_planifiees': planifie_s,
        'taux_couverture': round(100 * planifie_h / attendu_h, 2) if attendu_h else 0.0,
    }


def validate_schedule(placements, non_places=()):
    """Valide un plan d'EDT (étape P) — ne modifie rien, ne lève jamais.

    Le plan peut provenir de ``generate_schedule`` **ou** d'une modification
    manuelle : dans les deux cas, la même validation s'applique (étape T).
    """
    violations, warnings = [], []
    verifier_conflits(placements, violations, warnings)
    verifier_salles(placements, violations, warnings)
    verifier_enseignants(placements, violations, warnings)

    couverture = _couverture(placements, non_places)
    if couverture['heures_non_couvertes'] > 0:
        violations.append(C.Violation(
            C.C10_VOLUME,
            f'Volume non couvert : {couverture["heures_non_couvertes"]} h '
            f'sur {couverture["heures_attendues"]} h attendues.',
        ))

    return RapportValidation(
        valide=not violations,
        violations=violations,
        warnings=warnings,
        couverture=couverture,
        statut=OK if not violations else BLOQUANT,
    )


def _couverture_seances(affectations, besoins_attendus=None):
    """Couverture d'un EDT persisté, exprimée en nombre de séances placées."""
    placees = len(affectations)
    attendues = len(besoins_attendus) if besoins_attendus is not None else placees
    return {
        'seances_attendues': attendues,
        'seances_planifiees': placees,
        'seances_non_placees': max(attendues - placees, 0),
        'taux_couverture': round(100 * placees / attendues, 2) if attendues else 0.0,
    }


class _SeancePersistee:
    """Vue séance d'une ``AffectationCreneau`` pour les contrôles C1/C2/C3.

    Un conflit se juge sur une ressource et une période : la séance persistée
    porte déjà son groupe, sa salle et — via sa clé d'affectation
    pédagogique (L1) — son enseignant. Aucune ressource n'est inventée.
    """

    __slots__ = ('pk', 'jour', 'heure_debut', 'heure_fin', 'semaine_debut',
                 'enseignant_id', 'groupe_id', 'salle_id')

    def __init__(self, affectation):
        creneau = affectation.creneau_template
        pedagogique = affectation.affectation_pedagogique
        self.pk = affectation.pk
        self.jour = creneau.jour
        self.heure_debut = creneau.heure_debut
        self.heure_fin = creneau.heure_fin
        self.semaine_debut = affectation.semaine_debut
        self.enseignant_id = pedagogique.enseignant_id if pedagogique else None
        self.groupe_id = affectation.groupe_id
        self.salle_id = affectation.salle_id


def placements_seances(affectations):
    """Vues séance exploitables par ``verifier_conflits`` (C1/C2/C3).

    La validation d'un EDT **existant** ne peut pas être plus permissive que
    celle d'un plan fraîchement généré : les mêmes règles de chevauchement
    s'appliquent aux séances persistées.
    """
    return [_SeancePersistee(a) for a in affectations if a.creneau_template_id]


def valider_emploi_du_temps(emploi_du_temps, besoins_attendus=None):
    """Valide un EDT **persisté** (AffectationCreneau) — étape T.

    Les conflits enseignant / groupe / salle (C1/C2/C3) sont vérifiés avec
    **les mêmes règles** que ``validate_schedule`` : un EDT existant n'est pas
    jugé plus permissivement qu'un plan fraîchement généré.

    Les besoins attendus sont fournis par l'appelant (typiquement
    ``calculate_teaching_needs``) : le validateur ne les recalcule pas, pour
    qu'un plan puisse être audité contre un périmètre donné.
    """
    from edts.models import AffectationCreneau

    affectations = list(
        AffectationCreneau.objects
        .filter(emploi_du_temps=emploi_du_temps, actif=True)
        .select_related('creneau_template', 'salle', 'affectation_pedagogique')
    )
    violations, warnings = [], []
    # C1/C2/C3 — chevauchements entre séances persistées : exactement les
    # mêmes règles que `validate_schedule` (aucune seconde logique).
    verifier_conflits(placements_seances(affectations), violations, warnings)
    for affectation in affectations:
        ct = affectation.creneau_template
        salle = affectation.salle
        if affectation.semaine_fin < affectation.semaine_debut:
            violations.append(C.Violation(
                C.C9_CALENDRIER,
                f'Séance #{affectation.pk} : semaines incohérentes.',
            ))
        if not affectation.affectation_pedagogique_id:
            # C8 : une séance publiée doit garder son contexte pédagogique.
            warnings.append(
                f'Séance #{affectation.pk} sans affectation pédagogique : elle ne '
                'sera pas rattachée à un cours (C8).'
            )
        if salle is not None and ct is not None and C.indisponible_salle(
            salle.pk, emploi_du_temps.annee_academique_id, ct.jour,
            ct.heure_debut, ct.heure_fin,
        ):
            violations.append(C.Violation(
                C.C6_DISPONIBILITE_SALLE,
                f'Séance #{affectation.pk} : salle {salle.nom} indisponible.',
            ))
    return RapportValidation(
        valide=not violations,
        violations=violations,
        warnings=warnings,
        couverture=_couverture_seances(affectations, besoins_attendus),
        statut=OK if not violations else BLOQUANT,
    )
