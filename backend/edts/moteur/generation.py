"""Lot L8 — Étapes L→O : moteur de génération (``generate_schedule``).

Solveur **déterministe et sans dépendance externe** : ni OR-Tools, ni PuLP.
Le choix est assumé (étape 20 : « une solution déterministe et testable est
préférable ») — l'ajout d'une dépendance lourde exigerait une validation
préalable, et aucune n'a été accordée.

Principe : backtracking chronologique, propagation de contraintes et
heuristique de difficulté.

    1. besoins triés du plus contraint au plus simple (``contraintes.difficulte``) ;
    2. pour chaque besoin, candidats = créneaux × salles compatibles ;
    3. un candidat enfreignant une contrainte DURE C1→C10 est éliminé d'emblée ;
    4. les contraintes SOUPLES produisent une pénalité, jamais un rejet ;
    5. le candidat de moindre pénalité est retenu ;
    6. si la suite échoue, on **défait** le placement (retour arrière) et on
       essaie le candidat suivant ;
    7. en cas d'échec global : ``GENERATION_PARTIELLE`` documenté (étape O),
       jamais un EDT incomplet silencieux.

**Aucune publication, aucune écriture base.** Ce service ne renvoie qu'un plan ;
la persistance relève de ``publication.py`` et de la couche API.
"""

from dataclasses import dataclass, field
from datetime import time

from edts.moteur import contraintes as C
from edts.moteur.besoins import (
    MOTIF_CANEVAS_VIDE,
    calculate_teaching_needs,
)

# ── Statuts de génération ─────────────────────────────────────────────────────
GENERATION_OK = 'GENERATION_OK'
GENERATION_PARTIELLE = 'GENERATION_PARTIELLE'
GENERATION_IMPOSSIBLE = 'GENERATION_IMPOSSIBLE'
GENERATION_BUDGET_EXHAUSTED = 'GENERATION_BUDGET_EXHAUSTED'

#: Finalité de la recherche — classification explicite de la fin du moteur
#: (étape P). Elle complète `status` (statut métier observable) sans modifier
#: le contrat public : un consommateur garde l'accès à `status`, `motif_echec`
#: et `metrics`, et dispose désormais d'une information non ambiguë sur le
#: motif de fin de la recherche.
FINALITE_COMPLETE = 'COMPLETE'
FINALITE_PARTIAL = 'PARTIAL'
FINALITE_BUDGET_EXHAUSTED = 'BUDGET_EXHAUSTED'
FINALITE_IMPOSSIBLE = 'IMPOSSIBLE'
FINALITE_ERREUR = 'ERREUR'


#: Garde-fou : nombre maximal de placements explorés. Un budget borné garantit
#: que le moteur termine au lieu de boucler.
BUDGET_PLACEMENTS_DEFAUT = 200_000

#: Motif propre au moteur : besoins et créneaux existent, mais aucune salle ne
#: peut accueillir les séances (contraintes dures C7 / C4).
MOTIF_AUCUNE_SALLE_COMPATIBLE = 'AUCUNE_SALLE_COMPATIBLE'



@dataclass
class Placement:
    """Séance planifiée — l'équivalent d'une ``AffectationCreneau``, non persistée."""

    besoin: object
    creneau: object
    salle: object | None
    semaine_debut: int
    semaine_fin: int
    penalites: list = field(default_factory=list)
    score: int = 0

    @property
    def enseignant_id(self):
        return self.besoin.enseignant_id

    @property
    def groupe_id(self):
        return self.besoin.groupe_id

    @property
    def salle_id(self):
        return self.salle.pk if self.salle is not None else None

    @property
    def jour(self):
        return self.creneau.jour

    @property
    def heure_debut(self):
        return self.creneau.heure_debut

    @property
    def heure_fin(self):
        return self.creneau.heure_fin

    def as_dict(self):
        return {
            'affectation_pedagogique_id': self.besoin.affectation_pedagogique_id,
            'intitule': self.besoin.intitule,
            'type_enseignement': self.besoin.type_enseignement,
            'nature': self.besoin.nature,
            'creneau_template_id': self.creneau.pk,
            'jour': self.creneau.jour,
            'heure_debut': self.creneau.heure_debut.isoformat(timespec='minutes'),
            'heure_fin': self.creneau.heure_fin.isoformat(timespec='minutes'),
            'semaine_debut': self.semaine_debut,
            'semaine_fin': self.semaine_fin,
            'salle_id': self.salle_id,
            'salle_nom': self.salle.nom if self.salle is not None else '',
            'groupe_id': self.besoin.groupe_id,
            'enseignant_id': self.besoin.enseignant_id,
            'penalites': [p.as_dict() for p in self.penalites],
            'score': self.score,
        }


@dataclass
class BesoinNonPlace:
    """Besoin non placé, avec sa cause — traçabilité de l'échec (étape O)."""

    besoin: object
    raison: str
    contraintes_bloquantes: list = field(default_factory=list)
    creneaux_testes: int = 0
    salles_testees: int = 0

    def as_dict(self):
        return {
            'affectation_pedagogique_id': self.besoin.affectation_pedagogique_id,
            'intitule': self.besoin.intitule,
            'type_enseignement': self.besoin.type_enseignement,
            'groupe_id': self.besoin.groupe_id,
            'raison': self.raison,
            'contraintes_bloquantes': [c.as_dict() for c in self.contraintes_bloquantes],
            'creneaux_testes': self.creneaux_testes,
            'salles_testees': self.salles_testees,
        }


@dataclass
class GenerationResult:
    """Résultat structuré de ``generate_schedule`` (étapes L & Q)."""

    status: str
    placements: list = field(default_factory=list)
    non_places: list = field(default_factory=list)
    conflits: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    motif_echec: str | None = None
    detail: dict = field(default_factory=dict)
    #: Classification de la fin de la recherche (étape P). Complément de
    #: `status` : le statut reste identique (contrat public); la finalité
    #: permet de distinguer un échec de recherche normal d'un épuisement
    #: du budget de recherche.
    finalite: str | None = None

    @property
    def succes(self):
        return self.status == GENERATION_OK

    def as_dict(self):
        return {
            'status': self.status,
            'placements': [p.as_dict() for p in self.placements],
            'non_places': [n.as_dict() for n in self.non_places],
            'conflits': self.conflits,
            'warnings': self.warnings,
            'metrics': self.metrics,
            'motif_echec': self.motif_echec,
            'detail': self.detail,
        }


# ── Candidats (étape M) ───────────────────────────────────────────────────────

def _salles_compatibles(besoin, salles):
    """Salles utilisables pour ce besoin (C7 + C4), triées par marge.

    Les salles les plus « justes » passent d'abord : une grande salle reste
    disponible pour un groupe plus grand, ce qui réduit les impasses en fin de
    résolution. Tri déterministe : égalité départagée par ``pk``.
    """
    compatibles = [
        salle for salle in salles
        if C.compatible_salle(salle, besoin.nature)
        and C.capacite_suffisante(salle, besoin.effectif)
    ]
    return sorted(compatibles, key=lambda s: (s.capacite or 10 ** 6, s.pk))


def _penalites(besoin, creneau, salle, annee_id, index=None,
               index_occupations=None, politique_souples=None,
               souples=None):
    """Contraintes SOUPLES (étape K) — jamais bloquantes.

    Deux familles :
      * historiques (préférence enseignant, salle surdimensionnée, contexte
        incomplet) : toujours évaluées ;
      * configurables (trous, séries trop longues, surcharge journalière) :
        évaluées **uniquement** si la politique les active. Par défaut elles
        sont inactives (``contraintes.SOUPLES_DEFAUT``), donc le plan produit
        reste identique à ce qu'il était avant leur introduction.
    """
    penalites = []
    if not C.preference_enseignant(
        besoin.enseignant_id, annee_id, creneau.jour,
        creneau.heure_debut, creneau.heure_fin, index=index,
    ):
        penalites.append(C.Penalite(
            'PREFERENCE_ENSEIGNANT_NON_RESPECTEE',
            'Créneau hors des préférences déclarées de l’enseignant.',
            poids=2,
        ))
    if besoin.effectif and salle is not None and salle.capacite \
            and salle.capacite > besoin.effectif * 2:
        penalites.append(C.Penalite(
            'SALLE_SUR_DIMENSIONNEE',
            'Salle nettement plus grande que l’effectif du groupe.',
            poids=1,
        ))
    if besoin.semestre_id is None:
        penalites.append(C.Penalite(
            'CONTEXTE_PEDAGOGIQUE_INCOMPLET',
            'La séance n’est rattachée à aucun semestre.',
            poids=1,
        ))
    # Contraintes souples configurables — la journée du GROUPE est jugée
    # (c'est la cohorte qui subit les trous et les journées trop longues).
    # Aucun effet si la politique est inactive : c'est le cas par défaut.
    # Contraintes souples : elles ne dépendent QUE du groupe et du créneau,
    # jamais de la salle. `candidats()` les calcule donc une fois par créneau
    # et les passe ici — sinon le même calcul serait refait pour chaque salle
    # éligible (mesuré : +78 % de temps de génération à 3 500 étudiants).
    if souples is None:
        souples = C.penalites_souples(
            index_occupations,
            prefixe='G', ressource=besoin.groupe_id, jour=creneau.jour,
            heure_debut=creneau.heure_debut, heure_fin=creneau.heure_fin,
            politique=politique_souples,
        )
    penalites.extend(souples)
    return penalites


def candidats(besoin, contexte, occupations):
    """Placements valides pour un besoin, du meilleur au moins bon.

    Le contexte porte ``creneaux``, ``salles``, ``annee_id`` et ``semaines`` :
    il est distinct du besoin, qui reste immuable.

    Retourne ``(retenus, ecartees, creneaux_testes, salles_testees)`` où
    ``ecartees`` liste, par créneau, les ``Violation`` expliquant l'élimination.
    """
    creneaux = contexte['creneaux']
    salles = contexte['salles']
    annee_id = contexte['annee_id']
    semaines = contexte['semaines']
    retenus, ecartees = [], []
    creneaux_testes = salles_testes = 0
    index = contexte.get('index_disponibilites')
    index_occupations = contexte.get('index_occupations')
    politique_souples = contexte.get('politique_souples')
    eligibles = _salles_compatibles(besoin, salles)

    for creneau in creneaux:
        creneaux_testes += 1
        base = []
        # C5 — indisponibilité enseignant (dure).
        if C.indisponible_enseignant(
            besoin.enseignant_id, annee_id, creneau.jour,
            creneau.heure_debut, creneau.heure_fin, index=index,
        ):
            base.append(C.Violation(
                C.C5_DISPONIBILITE_ENSEIGNANT,
                f'Enseignant indisponible le {creneau.jour} '
                f'{creneau.heure_debut:%H:%M}–{creneau.heure_fin:%H:%M}.',
                ressource=str(besoin.enseignant_id),
            ))
        if not eligibles:
            base.append(C.Violation(
                C.C7_COMPATIBILITE_SALLE,
                'Aucune salle compatible avec ce type d’enseignement.',
            ))

        # Une seule évaluation des règles souples par créneau (invariant de salle).
        souples_creneau = (
            C.penalites_souples(
                index_occupations,
                prefixe='G', ressource=besoin.groupe_id, jour=creneau.jour,
                heure_debut=creneau.heure_debut, heure_fin=creneau.heure_fin,
                politique=politique_souples,
            )
            if politique_souples and politique_souples.get('actives') else ()
        )
        for salle in eligibles:
            salles_testes += 1
            violations = list(base)
            # C6 — indisponibilité salle.
            if C.indisponible_salle(
                salle.pk, annee_id, creneau.jour,
                creneau.heure_debut, creneau.heure_fin, index=index,
            ):
                violations.append(C.Violation(
                    C.C6_DISPONIBILITE_SALLE,
                    f'Salle indisponible le {creneau.jour}.',
                    ressource=salle.nom,
                ))
            # C1 / C2 / C3 — conflits sur ressource partagée.
            for code, message in C.conflit_ressource(
                occupations,
                enseignant_id=besoin.enseignant_id,
                groupe_id=besoin.groupe_id,
                salle_id=salle.pk,
                jour=creneau.jour,
                heure_debut=creneau.heure_debut,
                heure_fin=creneau.heure_fin,
                index=index_occupations,
            ):
                violations.append(C.Violation(code, message, ressource=salle.nom))
            if violations:
                ecartees.append(violations)
                continue
            penalites = _penalites(
                besoin, creneau, salle, annee_id, index=index,
                index_occupations=index_occupations,
                politique_souples=politique_souples,
                souples=list(souples_creneau),
            )
            retenus.append(Placement(
                besoin=besoin, creneau=creneau, salle=salle,
                semaine_debut=semaines[0], semaine_fin=semaines[-1],
                penalites=penalites, score=sum(p.poids for p in penalites),
            ))
        if not eligibles:
            ecartees.append(base)

    # Tri déterministe : score, puis jour/heure, puis salle.
    retenus.sort(key=lambda p: (p.score, p.creneau.jour, p.creneau.heure_debut,
                                p.salle_id or 0))
    return retenus, ecartees, creneaux_testes, salles_testes


# ── Solveur (étapes N & O) ────────────────────────────────────────────────────

def _backtrack(restes, index, occupations, budget, contexte):
    """Placement récursif avec retour arrière (backtracking chronologique).

    À chaque étape on prend le besoin le plus contraint restant et l'on essaie
    ses candidats par score croissant. Si la suite échoue, on **défait** le
    placement (``occupations.pop()``) et l'on essaie le candidat suivant.

    Le budget borne l'exploration. Le solveur ne lève jamais : il renvoie au
    mieux un plan partiel documenté, au pire ``None`` (échec complet).
    """
    if index >= len(restes):
        return []
    besoin = restes[index]
    retenus, _ecartees, _nc, _ns = candidats(besoin, contexte, occupations)
    for candidat in retenus:
        if budget[0] <= 0:
            return None
        budget[0] -= 1
        occupations.append(candidat)
        index_occupations = contexte.get('index_occupations')
        if index_occupations is not None:
            from edts.moteur import contraintes as C

            C.ajouter_occupation(index_occupations, candidat)
        suite = _backtrack(restes, index + 1, occupations, budget, contexte)
        if suite is not None:
            return [candidat] + suite
        occupations.pop()
        if index_occupations is not None:
            from edts.moteur import contraintes as C

            C.retirer_occupation(index_occupations, candidat)
    return None


def _construire_contexte(creneaux, salles, annee_id, semaines):
    """Contexte de résolution, transmis au solveur.

    Il est **distinct** des besoins : ceux-ci restent immuables. Aucune donnée
    de résolution n'est donc collée sur l'objet métier.
    """
    from edts.moteur import contraintes as C

    return {
        'creneaux': creneaux,
        'salles': salles,
        'annee_id': annee_id,
        'semaines': list(semaines),
        # Une seule requête pour toutes les disponibilités de l'année : le
        # solveur ne fait plus de SQL par candidat.
        'index_disponibilites': C.indexer_disponibilites(annee_id),
    }


def _contraintes_dominantes(ecartees):
    """Contraintes les plus fréquemment bloquantes d'un besoin non placé."""
    from collections import Counter

    compteur = Counter()
    for lot in ecartees:
        for violation in lot:
            compteur[violation.code_contrainte] += 1
    return [C.Violation(code, '', '') for code, _compte in compteur.most_common()]


def _warnings(besoins, salles):
    """Avertissements non bloquants pour l'administrateur (§53)."""
    avertissements = []
    if not salles:
        avertissements.append(
            'Aucune salle active au référentiel : les séances seront sans salle.'
        )
    elif all(s.capacite is None for s in salles):
        avertissements.append(
            'Aucune salle n’a de capacité renseignée : la contrainte C4 ne peut pas '
            'être vérifiée (contrôle non appliqué, aucun rejet arbitraire).'
        )
    sans_enseignant = [b for b in besoins if not b.enseignant_id]
    if sans_enseignant:
        avertissements.append(
            f'{len(sans_enseignant)} besoin(s) sans enseignant : les conflits C1/C5 '
            'ne peuvent pas être garantis pour ces séances.'
        )
    return avertissements


def _construire_resultat(resultat_besoins, besoins, placements, occupations,
                         contexte, budget, budget_liste):
    """Assemble le résultat final : placements, non-placés, métriques (étape Q)."""
    places_ids = {p.besoin.affectation_pedagogique_id for p in placements}
    non_places = []
    for besoin in besoins:
        if besoin.affectation_pedagogique_id in places_ids:
            continue
        _, ecartees, n_creneaux, n_salles = candidats(besoin, contexte, occupations)
        contraintes = _contraintes_dominantes(ecartees)
        dominantes = {c.code_contrainte for c in contraintes}
        raison = (
            'Aucune salle compatible (C7/C4) sur les créneaux autorisés.'
            if contraintes and dominantes <= {C.C7_COMPATIBILITE_SALLE, C.C4_CAPACITE}
            else 'Aucune combinaison créneau/salle ne satisfait les contraintes dures.'
        )
        non_places.append(BesoinNonPlace(
            besoin=besoin, raison=raison, contraintes_bloquantes=contraintes,
            creneaux_testes=n_creneaux, salles_testees=n_salles,
        ))

    attendues = resultat_besoins.total_seances_attendues
    placees = sum(p.besoin.nb_seances for p in placements)
    couverture = round(100 * placees / attendues, 2) if attendues else 0.0
    if not non_places:
        finalite = FINALITE_COMPLETE
    elif not placements:
        finalite = FINALITE_BUDGET_EXHAUSTED if budget_liste[0] <= 0 else FINALITE_IMPOSSIBLE
    elif budget_liste[0] <= 0:
        finalite = FINALITE_BUDGET_EXHAUSTED
    else:
        finalite = FINALITE_PARTIAL
    status = {
        FINALITE_COMPLETE: GENERATION_OK,
        FINALITE_PARTIAL: GENERATION_PARTIELLE,
        FINALITE_BUDGET_EXHAUSTED: GENERATION_PARTIELLE,
        FINALITE_IMPOSSIBLE: GENERATION_IMPOSSIBLE,
    }[finalite]
    return GenerationResult(
        status=status,
        placements=placements,
        non_places=non_places,
        warnings=_warnings(besoins, contexte['salles']),
        metrics={
            'seances_attendues': attendues,
            'seances_placees': placees,
            'seances_non_placees': attendues - placees,
            'heures_attendues': resultat_besoins.total_heures_attendues,
            'heures_placees': round(
                sum(p.besoin.nb_seances * p.besoin.duree_seance_heures
                    for p in placements), 2,
            ),
            'taux_couverture': couverture,
            'score_penalites': sum(p.score for p in placements),
            'creneaux_explores': budget - budget_liste[0],
            'nb_conflits_critiques': 0,
            # Diagnostic explicite de la fin de recherche (étape P).
            'budget_configured': budget,
            'budget_restant': budget_liste[0],
            'nb_placements_effectues': len(placements),
            'finalite': finalite,
            # Contraintes souples : politique effective + bilan du plan.
            # Inactives par défaut → le bilan est vide et rien ne change.
            'contraintes_souples': C.resume_souples(
                placements, contexte.get('politique_souples')),
        },
        motif_echec=None if placements or not non_places else (
            MOTIF_AUCUNE_SALLE_COMPATIBLE if not placements else None
        ),
        detail=resultat_besoins.detail,
        finalite=finalite,
    )


def generate_schedule(
    *,
    annee_academique_id=None,
    ref_formation_id=None,
    parcours_id=None,
    niveau_id=None,
    semestre_id=None,
    groupe_ids=None,
    semaines=None,
    creneaux=None,
    salles=None,
    duree_seance_heures=None,
    budget=BUDGET_PLACEMENTS_DEFAUT,
    perimetre_injs_seulement=True,
    occupations_initiales=None,
    besoins=None,
    contraintes_souples=None,
):
    """Génère un plan d'emploi du temps (étape L) — **sans jamais publier**.

    Retour toujours structuré : ``status``, ``placements``, ``non_places``,
    ``conflits``, ``warnings``, ``metrics``, ``motif_echec``.

    LOT 3 — ``occupations_initiales`` (additif) : état d'occupation déjà
    consommé ailleurs (séances persistées d'autres EDT, placements de runs
    antérieurs d'une même opération coordonnée). Ces entrées sont injectées
    dans ``occupations`` avant le backtracking : elles participent aux
    contrôles C1/C2/C3 comme n'importe quel placement du run, **sans jamais
    être modifiées ni persistées**. ``None`` (défaut) conserve strictement le
    comportement des LOTS 1 et 2 : un run isolé, sans vue externe.
    Les entrées acceptées sont les objets ``Placement`` ou des dicts à clés
    ``enseignant_id`` / ``groupe_id`` / ``salle_id`` / ``jour`` /
    ``heure_debut`` / ``heure_fin`` (format consommé par
    ``contraintes.conflit_ressource``). Le filtrage par semaines (C9) revient
    à l'appelant : ``conflit_ressource`` compare des créneaux hebdomadaires.

    Causes de blocage distinguées (arbitrage du commanditaire, §6) :

    * ``AFFECTATIONS_PEDAGOGIQUES_VIDES`` — aucune entrée pédagogique ;
    * ``HORS_PERIMETRE_INJS``            — entrées hors périmètre INJS-LMD ;
    * ``CANEVAS_HORAIRE_VIDE``           — aucun créneau type réel ;
    * ``C9_CALENDRIER``                 — aucune période autorisée ;
    * ``AUCUNE_SALLE_COMPATIBLE``       — ni salle ne peut accueillir (C7/C4).

    LOT GET-INJS (additif) — ``besoins`` : liste de ``TeachingNeed`` déjà
    calculés. Elle permet de planifier des cohortes **importées**, dont les
    besoins sont dérivés de la maquette (``edts.moteur.besoins_maquette``)
    plutôt que d'``AffectationPedagogique``. ``None`` (défaut) conserve
    strictement le comportement historique : les besoins sont alors recalculés
    depuis les affectations.

    Le service n'écrit rien en base : il renvoie un plan. La persistance est
    l'affaire de ``publication.py`` et de la couche API.
    """
    from edts.models import CreneauTemplate
    from formations.models import RefSalle

    # 1. Besoins — peut déjà refuser avec un motif explicite.
    if besoins is not None:
        from edts.moteur.besoins import BesoinsResult

        resultat_besoins = BesoinsResult(besoins=list(besoins))
    else:
        resultat_besoins = calculate_teaching_needs(
            annee_academique_id=annee_academique_id,
            ref_formation_id=ref_formation_id,
            parcours_id=parcours_id,
            niveau_id=niveau_id,
            semestre_id=semestre_id,
            groupe_ids=groupe_ids,
            duree_seance_heures=duree_seance_heures,
            perimetre_injs_seulement=perimetre_injs_seulement,
        )
    if resultat_besoins.vide:
        return GenerationResult(
            status=GENERATION_IMPOSSIBLE,
            motif_echec=resultat_besoins.motif_echec,
            detail=resultat_besoins.detail,
            finalite=FINALITE_IMPOSSIBLE,
        )

    # 2. Canevas réel — jamais de créneau inventé.
    if creneaux is None:
        creneaux = list(CreneauTemplate.objects.order_by('jour', 'heure_debut'))
    if not creneaux:
        return GenerationResult(
            status=GENERATION_IMPOSSIBLE,
            motif_echec=MOTIF_CANEVAS_VIDE,
            detail={
                'explication': (
                    f'{len(resultat_besoins.besoins)} besoin(s) calculé(s), mais le '
                    'canevas horaire est vide : aucun créneau réel sur lequel placer.'
                ),
                'nb_besoins': len(resultat_besoins.besoins),
                'action_recommandee': (
                    'Définir le canevas horaire officiel (jours + plages) de l’INJS.'
                ),
            },
            finalite=FINALITE_IMPOSSIBLE,
        )

    # 3. Salles du référentiel, actives uniquement.
    if salles is None:
        salles = list(RefSalle.objects.filter(actif=True).order_by('pk'))

    # 4. Périodes autorisées (bornes de semaines de l'EDT).
    if semaines is None:
        semaines = [1]
    if not semaines:
        return GenerationResult(
            status=GENERATION_IMPOSSIBLE,
            motif_echec=C.C9_CALENDRIER,
            detail={
                'explication': 'Aucune période de planification (semaines) autorisée.',
                'action_recommandee': 'Renseigner les bornes de semaines de l’EDT.',
            },
            finalite=FINALITE_IMPOSSIBLE,
        )

    # 5. Résolution. L'état d'occupation initial (LOT 3) précède les placements
    #    de ce run : `_backtrack` n'en retire que ce qu'il ajoute lui-même.
    contexte = _construire_contexte(creneaux, salles, annee_academique_id, semaines)
    # Politique des contraintes souples : défaut (inactives) sauf réglage
    # Django ou paramètre explicite de l'appelant.
    contexte['politique_souples'] = C.politique_souples(contraintes_souples)
    besoins = list(resultat_besoins.besoins)
    occupations = list(occupations_initiales or [])
    # Index incrémental des occupations : le solveur ne parcourt plus toute la
    # liste à chaque candidat (facteur déterminant au-delà de 3 500 étudiants).
    contexte['index_occupations'] = C.indexer_occupations(occupations)
    budget_liste = [budget]
    placements = _backtrack(besoins, 0, occupations, budget_liste, contexte) or []

    return _construire_resultat(
        resultat_besoins, besoins, placements, occupations, contexte,
        budget, budget_liste,
    )
