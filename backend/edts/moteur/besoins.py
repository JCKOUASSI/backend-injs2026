"""Lot L8 — Étape E : calcul des besoins horaires (``calculate_teaching_needs``).

Produit les **séances planifiables** à partir de la chaîne LMD réelle :

    AffectationPedagogique (VALIDEE|PLANIFIEE)
        → ECUE / UE (intitulé, ECTS, volumes CM/TD/TP)
        → volume_horaire + type_enseignement
        → groupe (effectif)
        → nb_séances = volume / durée du créneau réel

Traçabilité : chaque besoin conserve l'identifiant de son affectation
pédagogique (``affectation_pedagogique_id``). C'est cette FK — et non un
appariement heuristique ``groupe + cycle + nom enseignant`` — qui est
propagée jusqu'à la séance EDT (étape F / §59).

**Aucun découpage n'est imposé.** La durée de séance provient du canevas réel
(``CreneauTemplate.duree_prevue_minutes``) ; en son absence le calcul est
refusé avec un motif explicite, jamais « 2 h » par défaut (étape E).

Périmètre INJS : seules les formations qualifiées ``perimetre = INJS`` sont
retenues (service ``formations.referentiel_injs_l6``). Aucun cycle legacy
n'est traité comme une formation INJS-LMD.
"""

from dataclasses import dataclass, field, replace

from django.db.models import Q

# ── Motifs de blocage (explicites, jamais de repli) ────────────────────────────
MOTIF_AFFECTATIONS_VIDES = 'AFFECTATIONS_PEDAGOGIQUES_VIDES'
MOTIF_HORS_PERIMETRE_INJS = 'HORS_PERIMETRE_INJS'
MOTIF_CANEVAS_VIDE = 'CANEVAS_HORAIRE_VIDE'
MOTIF_VOLUME_INCONNU = 'VOLUME_HORAIRE_INCONNU'

#: Statuts d'affectation pédagogique éligibles à la planification.
STATUTS_PLANIFIABLES = ('VALIDEE', 'PLANIFIEE')

#: Mapping type d'enseignement → nature de séance. Le mapping CM/TD/TP est
#: documenté par le modèle (`AffectationPedagogique.TypeEnseignement`) ; la
#: correspondance salle est traitée par `contraintypes.compatible`.
NATURE_PAR_TYPE = {
    'CM': 'COURS',
    'TD': 'TD',
    'TP': 'TP',
    'STAGE': 'AUTRE',
    'AUTRE': 'AUTRE',
}


@dataclass(frozen=True)
class TeachingNeed:
    """Séance planifiable, entièrement traçable vers sa source pédagogique.

    Immuable : un besoin est un fait. Toute correction métier passe par une
    nouvelle affectation pédagogique, jamais par l'édition d'un besoin.
    """

    affectation_pedagogique_id: int
    annee_academique_id: int
    ref_formation_id: int
    parcours_id: int | None
    niveau_id: int
    semestre_id: int | None
    groupe_id: int | None
    ue_id: int | None
    ecue_id: int | None
    enseignant_id: int | None
    type_enseignement: str
    nature: str
    intitule: str
    volume_horaire: float
    credits: int
    effectif: int | None
    duree_seance_heures: float
    nb_seances: int
    #: Heuristique de difficulté (étape 20) : plus c'est élevé, plus la
    #: séance est traitée tôt. Calculée par `contraintes.difficulte`.
    difficulte: int = 0

    def __str__(self):
        return (f'{self.type_enseignement} {self.intitule} '
                f'[groupe {self.groupe_id}] {self.volume_horaire} h '
                f'→ {self.nb_seances} séance(s)')


@dataclass
class BesoinsResult:
    """Résultat du calcul — jamais une exception, toujours un état exploitable.

    Le front GET-INJS affiche ``motif_echec`` tel quel : un blocage est
    toujours accompagné de sa cause et d'une action recommandée (§54).
    """

    besoins: list = field(default_factory=list)
    motif_echec: str | None = None
    detail: dict = field(default_factory=dict)

    @property
    def vide(self):
        return not self.besoins

    @property
    def total_heures_attendues(self):
        return round(sum(b.volume_horaire for b in self.besoins), 2)

    @property
    def total_seances_attendues(self):
        return sum(b.nb_seances for b in self.besoins)

    @property
    def total_seances(self):
        return self.total_seances_attendues

    def as_dict(self):
        return {
            'nb_besoins': len(self.besoins),
            'total_heures_attendues': self.total_heures_attendues,
            'total_seances_attendues': self.total_seances_attendues,
            'motif_echec': self.motif_echec,
            'detail': self.detail,
        }


# ── Canevas horaire ───────────────────────────────────────────────────────────

def duree_canevas_heures():
    """Durée horaire des créneaux réels, en heures.

    Le canevas est la donnée qui autorise le découpage. S'il est vide, on ne
    suppose **aucune** durée : l'appelant reçoit ``None`` et doit refuser la
    génération avec ``CANEVAS_HORAIRE_VIDE`` (arbitrage du commanditaire :
    aucun horaire fictif, aucun repli « 2 h »).
    """
    from edts.models import CreneauTemplate

    durees = list(
        CreneauTemplate.objects
        .exclude(duree_prevue_minutes=None)
        .values_list('duree_prevue_minutes', flat=True)
    )
    if not durees:
        return None
    return round(sum(durees) / len(durees) / 60, 2)


def canevas_horaire_riche():
    """Vrai s'il existe au moins un créneau type utilisable (sans exception)."""
    from edts.models import CreneauTemplate

    return CreneauTemplate.objects.exists()


# ── Filtrage des affectations pédagogiques ────────────────────────────────────

def affectations_planifiables(
    *,
    annee_academique_id=None,
    ref_formation_id=None,
    parcours_id=None,
    niveau_id=None,
    semestre_id=None,
    groupe_ids=None,
    perimetre_injs_seulement=True,
):
    """Queryset des affectations éligibles, relations réelles uniquement (étape B).

    Le périmètre INJS est appliqué par la qualification ``perimetre`` de la
    RefFormation (service L6). Un cycle legacy (CPFAE, Sygepcpfae, plans de
    professorat) est donc **exclu de la planification**, sans être supprimé.
    """
    from formations.referentiel_injs_l6 import formations_injs
    from scolarite.models import AffectationPedagogique

    qs = AffectationPedagogique.objects.filter(
        statut__in=STATUTS_PLANIFIABLES,
    ).select_related(
        'annee_academique', 'ref_formation', 'parcours', 'niveau', 'semestre',
        'ue', 'ecue', 'groupe', 'enseignant',
    )
    if perimetre_injs_seulement:
        qs = qs.filter(ref_formation__in=formations_injs())
    if annee_academique_id is not None:
        qs = qs.filter(annee_academique_id=annee_academique_id)
    if ref_formation_id is not None:
        qs = qs.filter(ref_formation_id=ref_formation_id)
    if parcours_id is not None:
        qs = qs.filter(parcours_id=parcours_id)
    if niveau_id is not None:
        qs = qs.filter(niveau_id=niveau_id)
    if semestre_id is not None:
        qs = qs.filter(semestre_id=semestre_id)
    if groupe_ids:
        qs = qs.filter(groupe_id__in=list(groupe_ids))
    return qs.order_by('pk')


def _effectif(groupe):
    """Effectif du groupe : capacité maximale déclarée.

    Le module ne dénombre pas les inscriptions — un effectif pédagogique réel
    n'est pas disponible ici, et l'inventer fausserait la contrainte C4. La
    valeur ``None`` signifie « non contraint » : le moteur n'inventera alors
    aucune capacité de salle.
    """
    return groupe.capacite_max if groupe and groupe.capacite_max else None


def _construire_besoin(affectation, duree_heures):
    """Construit un ``TeachingNeed`` ou ``None`` si le besoin n'est pas planifiable."""
    volume = float(affectation.volume_horaire or 0)
    if volume <= 0:
        return None
    if not affectation.semestre_id:
        # Sans semestre, la séance n'est pas rattachable à une période
        # autorisée (contrainte forte C9) : le besoin est écarté.
        return None
    nb_seances = max(1, round(volume / duree_heures))
    intitule = (
        affectation.ecue.intitule if affectation.ecue_id
        else affectation.ue.intitule if affectation.ue_id
        else 'Enseignement'
    )
    besoin = TeachingNeed(
        affectation_pedagogique_id=affectation.pk,
        annee_academique_id=affectation.annee_academique_id,
        ref_formation_id=affectation.ref_formation_id,
        parcours_id=affectation.parcours_id,
        niveau_id=affectation.niveau_id,
        semestre_id=affectation.semestre_id,
        groupe_id=affectation.groupe_id,
        ue_id=affectation.ue_id,
        ecue_id=affectation.ecue_id,
        enseignant_id=affectation.enseignant_id,
        type_enseignement=affectation.type_enseignement,
        nature=NATURE_PAR_TYPE.get(affectation.type_enseignement, 'AUTRE'),
        intitule=intitule,
        volume_horaire=volume,
        credits=affectation.ecue.credits if affectation.ecue_id else 0,
        effectif=_effectif(affectation.groupe),
        duree_seance_heures=duree_heures,
        nb_seances=nb_seances,
    )
    # Le besoin est immuable (frozen=True) : la difficulté, qui dépend d'un
    # contexte plus large que le besoin lui-même, est injectée par `replace`.
    from edts.moteur.contraintes import difficulte

    return replace(besoin, difficulte=difficulte(besoin))


def _motif_hors_perimetre():
    """Vrai s'il existe des affectations planifiables hors périmètre INJS."""
    from formations.referentiel_injs_l6 import formations_injs
    from scolarite.models import AffectationPedagogique

    return AffectationPedagogique.objects.filter(
        statut__in=STATUTS_PLANIFIABLES,
    ).exclude(ref_formation__in=formations_injs()).exists()


def calculate_teaching_needs(
    *,
    annee_academique_id=None,
    ref_formation_id=None,
    parcours_id=None,
    niveau_id=None,
    semestre_id=None,
    groupe_ids=None,
    duree_seance_heures=None,
    perimetre_injs_seulement=True,
):
    """Calcule les besoins horaires planifiables (étape E).

    Ordre des vérifications — chaque cause est distinguée pour que GET-INJS
    puisse nommer le blocage (§6 de l'arbitrage, §54) :

    1. ``AFFECTATIONS_PEDAGOGIQUES_VIDES`` — aucune entrée pédagogique ;
    2. ``HORS_PERIMETRE_INJS``            — des entrées existent mais aucune
       n'est rattachée à une formation INJS validée ;
    3. ``CANEVAS_HORAIRE_VIDE``           — entrées OK, mais aucun créneau
       réel ne permet de découper les volumes ;
    4. ``VOLUME_HORAIRE_INCONNU``         — entrées OK mais aucun volume
       exploitable (0 h ou absence de semestre).

    La durée de séance est prioritairement fournie par l'appelant ; à défaut
    elle est déduite du canevas réel. **Jamais 2 h par défaut.**
    """
    affectations = list(affectations_planifiables(
        annee_academique_id=annee_academique_id,
        ref_formation_id=ref_formation_id,
        parcours_id=parcours_id,
        niveau_id=niveau_id,
        semestre_id=semestre_id,
        groupe_ids=groupe_ids,
        perimetre_injs_seulement=perimetre_injs_seulement,
    ))

    if not affectations:
        if perimetre_injs_seulement and _motif_hors_perimetre():
            return BesoinsResult(
                motif_echec=MOTIF_HORS_PERIMETRE_INJS,
                detail={
                    'explication': (
                        'Des affectations pédagogiques existent, mais aucune ne porte '
                        'une formation INJS validée (périmètre L6). Les cycles legacy '
                        'CPFAE/Sygepcpfae ne sont pas des formations INJS.'
                    ),
                    'action_recommandee': (
                        'Vérifier le périmètre INJS des formations rattachées, ou '
                        'sélectionner une année/formation INJS précise.'
                    ),
                },
            )
        return BesoinsResult(
            motif_echec=MOTIF_AFFECTATIONS_VIDES,
            detail={
                'explication': (
                    'Aucune affectation pédagogique validée ou planifiée pour ce '
                    'périmètre. Rien à placer : ce n’est pas un échec de génération.'
                ),
                'action_recommandee': (
                    'Créer et valider des affectations pédagogiques (Maquette → UE → '
                    'ECUE → Affectation pédagogique) avant de générer un EDT.'
                ),
            },
        )

    if duree_seance_heures is None:
        duree_seance_heures = duree_canevas_heures()
    if not duree_seance_heures or duree_seance_heures <= 0:
        return BesoinsResult(
            motif_echec=MOTIF_CANEVAS_VIDE,
            detail={
                'explication': (
                    f'{len(affectations)} affectation(s) pédagogique(s) existent, mais '
                    'aucun créneau type n’est défini : impossible de découper les '
                    'volumes horaires sans inventer une durée de séance.'
                ),
                'nb_affectations': len(affectations),
                'action_recommandee': (
                    'Définir le canevas horaire officiel de l’INJS (jours et plages '
                    'horaires) avant toute génération.'
                ),
            },
        )

    besoins = []
    sans_volume = 0
    for affectation in affectations:
        besoin = _construire_besoin(affectation, duree_seance_heures)
        if besoin is None:
            sans_volume += 1
            continue
        besoins.append(besoin)

    if not besoins:
        return BesoinsResult(
            motif_echec=MOTIF_VOLUME_INCONNU,
            detail={
                'explication': (
                    f'{len(affectations)} affectation(s) existent mais aucun volume '
                    'horaire exploitable (volume nul ou semestre non renseigné).'
                ),
                'nb_affectations_sans_volume': sans_volume,
                'action_recommandee': (
                    'Renseigner volume_horaire et semestre sur les affectations '
                    'pédagogiques concernées.'
                ),
            },
        )

    from edts.moteur.contraintes import trier_par_difficulte

    return BesoinsResult(
        besoins=trier_par_difficulte(besoins),
        detail={
            'nb_affectations_examinees': len(affectations),
            'duree_seance_heures': duree_seance_heures,
            'source_duree': 'canevas',
        },
    )
