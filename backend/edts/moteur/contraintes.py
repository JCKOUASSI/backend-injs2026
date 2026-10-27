"""Lot L8 — Étapes J & K : contraintes fortes (bloquantes) et souples (pénalités).

Deux registres strictement séparés :

* **Contraintes dures C1→C10** — un placement qui les enfreint est *rejeté*.
  Le moteur ne produit jamais une séance invalide.
* **Contraintes souples (étape K)** — elles produisent une *pénalité* que le
  moteur cherche à minimiser. Elles ne bloquent **jamais** un placement
  (interdiction explicite de transformer une préférence en interdiction).

Aucune contrainte n'est inventée : chacune est soit dérivée d'une règle métier
documentée, soit explicitement listée comme « non applicable » si la donnée
socle ne permet pas de l'exprimer. C'est le cas de C9 (périodes de
l'année académique) : le modèle `AnneeAcademique` ne porte pas de découpage
en périodes, donc C9 est vérifiée par les seules bornes de semaines de l'EDT.
"""

from dataclasses import dataclass, field

# ── Identifiants des contraintes ──────────────────────────────────────────────
C1_CONFLIT_ENSEIGNANT = 'C1_CONFLIT_ENSEIGNANT'
C2_CONFLIT_GROUPE = 'C2_CONFLIT_GROUPE'
C3_CONFLIT_SALLE = 'C3_CONFLIT_SALLE'
C4_CAPACITE = 'C4_CAPACITE'
C5_DISPONIBILITE_ENSEIGNANT = 'C5_DISPONIBILITE_ENSEIGNANT'
C6_DISPONIBILITE_SALLE = 'C6_DISPONIBILITE_SALLE'
C7_COMPATIBILITE_SALLE = 'C7_COMPATIBILITE_SALLE'
C8_COHERENCE_PEDAGOGIQUE = 'C8_COHERENCE_PEDAGOGIQUE'
C9_CALENDRIER = 'C9_CALENDRIER'
C10_VOLUME = 'C10_VOLUME'

CONTRAINTES_DURES = (
    C1_CONFLIT_ENSEIGNANT,
    C2_CONFLIT_GROUPE,
    C3_CONFLIT_SALLE,
    C4_CAPACITE,
    C5_DISPONIBILITE_ENSEIGNANT,
    C6_DISPONIBILITE_SALLE,
    C7_COMPATIBILITE_SALLE,
    C8_COHERENCE_PEDAGOGIQUE,
    C9_CALENDRIER,
    C10_VOLUME,
)

# ── Types de salle compatibles par nature de séance (C7) ──────────────────────
#: Salles génériques utilisables pour tout type d'enseignement. Une salle non
#: qualifiée (`SALLE`) reste utilisable partout — on ne peut pas supposer qu'un
#: espace non typé est incompatible, ce serait un rejet injustifié.
SALLES_GENERIQUES = ('SALLE',)
#: Par nature de séance, les types de salle acceptés en plus des génériques.
SALLES_PAR_NATURE = {
    'COURS': ('COURS', 'AMPHI'),
    'TD': ('TD', 'COURS'),
    'TP': ('TP', 'LABORATOIRE', 'INFORMATIQUE'),
    'AUTRE': ('REUNION', 'CONFERENCE', 'COURS'),
}


@dataclass(frozen=True)
class Violation:
    """Contrainte dure enfreinte sur un placement candidat."""

    code_contrainte: str
    message: str
    ressource: str = ''

    def as_dict(self):
        return {
            'contrainte': self.code_contrainte,
            'message': self.message,
            'ressource': self.ressource,
        }

    def __str__(self):
        return f'{self.code_contrainte}: {self.message}'


@dataclass
class Penalite:
    """Contrainte souple non respectée — n'empêche pas le placement."""

    code: str
    message: str
    poids: int = 1

    def as_dict(self):
        return {'code': self.code, 'message': self.message, 'poids': self.poids}

    def __str__(self):
        return f'{self.code} (−{self.poids})'


# ── Compatibilité salle / nature de séance (C7) ──────────────────────────────

def types_salle_compatibles(nature):
    """Types de salle acceptés pour une nature de séance donnée (C7).

    Les salles génériques (``SALLE``) sont toujours acceptées : on ne peut pas
    supposer qu'un espace non typé est incompatible — ce serait un rejet
    injustifié. Une salle typée par ailleurs (ex. ``TP``) est refusée pour un CM.
    """
    return set(SALLES_GENERIQUES) | set(SALLES_PAR_NATURE.get(nature, ()))


def compatible_salle(salle, nature):
    """Vrai si la salle peut accueillir cette nature de séance."""
    if salle is None:
        return False
    return salle.type_lieu in types_salle_compatibles(nature)


def capacite_suffisante(salle, effectif):
    """C4 — ``effectif <= capacité``.

    Une capacité ``None`` signifie « non renseignée » et ne peut pas être
    traitée comme une capacité suffisante : si l'effectif est connu, la
    contrainte est bloquante. ``None`` d'effectif = effectif non contraint
    (groupe sans capacité ou séance sans groupe) : la contrainte n'est pas
    applicable.
    """
    if effectif is None:
        return True
    if salle is None or salle.capacite is None:
        return False
    return effectif <= salle.capacite


# ── Disponibilités horaires (C5 / C6) ─────────────────────────────────────────

def _chevauche(debut_a, fin_a, debut_b, fin_b):
    return debut_a < fin_b and debut_b < fin_a


def _periode_indisponible(enseignant_id, salle_id, annee_id, jour, heure_debut, heure_fin):
    """Contrôle fin : une indisponibilité couvre-t-elle *effectivement* la plage ?

    Le filtrage SQL s'arrête au jour (index ``(enseignant, annee, statut)``) ;
    le recouvrement horaire est évalué en Python, comme le fait déjà
    ``edts.services.horaires_en_chevauchement`` — portable SQLite/PostgreSQL.
    """
    from edts.models import DisponibiliteHoraire

    qs = DisponibiliteHoraire.objects.filter(
        annee_academique_id=annee_id, statut='INDISPONIBLE', jour=jour,
    )
    if enseignant_id:
        qs = qs.filter(enseignant_id=enseignant_id)
    elif salle_id:
        qs = qs.filter(salle_id=salle_id)
    else:
        return False
    return any(
        _chevauche(heure_debut, heure_fin, d.heure_debut, d.heure_fin)
        for d in qs
    )


def indisponible_enseignant(enseignant_id, annee_id, jour, heure_debut, heure_fin):
    """C5 — l'enseignant est-il déclaré indisponible sur ce créneau ?"""
    if not enseignant_id:
        return False
    return _periode_indisponible(
        enseignant_id, None, annee_id, jour, heure_debut, heure_fin,
    )


def indisponible_salle(salle_id, annee_id, jour, heure_debut, heure_fin):
    """C6 — la salle est-elle déclarée indisponible sur ce créneau ?"""
    if not salle_id:
        return False
    return _periode_indisponible(
        None, salle_id, annee_id, jour, heure_debut, heure_fin,
    )



# ── Conflits sur ressource partagée (C1 / C2 / C3) ───────────────────────────

def conflit_ressource(occupations, *, enseignant_id=None, groupe_id=None, salle_id=None,
                      jour=None, heure_debut=None, heure_fin=None, exclure=None):
    """Renvoie la liste des occupations déjà placées en conflit.

    ``occupations`` est l'état courant du solveur : une liste d'objets
    ``Placement`` (ou de dicts à clés ``enseignant_id``/``groupe_id``/
    ``salle_id``/``jour``/``heure_debut``/``heure_fin``). La vérification est
    purement fonctionnelle — aucun accès base, donc testable sans fixture.
    """
    conflits = []
    for place in occupations:
        if exclure is not None and _identifiant(place) == exclure:
            continue
        if _valeur(place, 'jour') != jour:
            continue
        if not _chevauche(heure_debut, heure_fin,
                          _valeur(place, 'heure_debut'),
                          _valeur(place, 'heure_fin')):
            continue
        if enseignant_id and _valeur(place, 'enseignant_id') == enseignant_id:
            conflits.append((C1_CONFLIT_ENSEIGNANT, 'Enseignant déjà occupé sur ce créneau.'))
        if groupe_id and _valeur(place, 'groupe_id') == groupe_id:
            conflits.append((C2_CONFLIT_GROUPE, 'Groupe déjà occupé sur ce créneau.'))
        if salle_id and _valeur(place, 'salle_id') == salle_id:
            conflits.append((C3_CONFLIT_SALLE, 'Salle déjà occupée sur ce créneau.'))
    return conflits


def _valeur(place, cle):
    return place[cle] if isinstance(place, dict) else getattr(place, cle, None)


def _identifiant(place):
    return place.get('id') if isinstance(place, dict) else getattr(place, 'id', None)


# ── Heuristique de difficulté (étape 20) ─────────────────────────────────────

def difficulte(besoin, nb_groupes=1):
    """Score de difficulté — plus il est élevé, plus la séance est traitée tôt.

    L'ordre de résolution demandé est (étape 20) :

    1. salles spécialisées        → un TP sans salle compatible est difficile ;
    2. enseignants peu disponibles → peu d'options de placement ;
    3. groupes contraints         → un groupe = pas de repli possible ;
    4. séances multi-groupes      → partagées par plusieurs groupes ;
    5. séances ordinaires         → score de base.

    Le score est **déterministe** : aucune valeur aléatoire, afin que deux
    exécutions sur les mêmes données produisent le même EDT.
    """
    score = 0
    if besoin.nature == 'TP':
        # Salle spécialisée : le plus contraignant.
        score += 100
    if besoin.groupe_id is None:
        # Pas de groupe : plusieurs cours peuvent cohabiter, donc plus facile.
        score -= 20
    if besoin.effectif:
        # Effectif connu = contrainte de capacité à vérifier.
        score += 20
    if besoin.enseignant_id is None:
        # Sans enseignant, le moteur ne peut pas garantir C1/C5.
        score += 30
    score += besoin.nb_seances * 2
    score += (100 - min(besoin.credits, 100)) // 10
    return max(score, 0)


def trier_par_difficulte(besoins):
    """Trie les besoins du plus contraint au plus simple (ordre déterministe).

    ``TeachingNeed`` est **immuable** (``frozen=True``) : la difficulté est donc
    portée par le champ ``difficulte``, renseigné à la construction du besoin.
    Ce tri ne fait que l'ordonner — il ne modifie rien.

    Le tri est stable sur l'identifiant d'affectation pédagogique : deux
    besoins de même difficulté restent dans un ordre stable d'une exécution à
    l'autre, ce qui rend le moteur reproductible (exigence §20).
    """
    return sorted(
        besoins,
        key=lambda b: (-b.difficulte, b.affectation_pedagogique_id),
    )

def preference_enseignant(enseignant_id, annee_id, jour, heure_debut, heure_fin):
    """Vrai si l'enseignant a exprimé une *préférence* sur ce créneau (étape K).

    Préférence = contrainte SOUPLE : elle produit une pénalité, jamais un rejet.
    """
    from edts.models import DisponibiliteHoraire

    if not enseignant_id or not annee_id:
        return False
    return any(
        _chevauche(heure_debut, heure_fin, d.heure_debut, d.heure_fin)
        for d in DisponibiliteHoraire.objects.filter(
            annee_academique_id=annee_id, enseignant_id=enseignant_id,
            statut='PREFERENCE', jour=jour,
        )
    )
