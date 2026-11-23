"""Canevas horaire officiel de l'INJS — source de vérité unique.

Le référentiel (feuille Excel « 13. Emploi du temps (modèle) ») décrit une
grille de **6 jours × 4 plages de 2 h = 24 créneaux**. Ce module la déclare une
seule fois, pour que trois usages cessent de la réécrire chacun à leur façon :

* la **vérification** du canevas réellement en base (`verifier_canevas`) ;
* le **rapport** de conformité rendu à l'utilisateur ;
* les **tests**, qui peuvent affirmer « 24 créneaux » sans les compter à la main.

Pourquoi c'est nécessaire. La base de démonstration contenait 14 créneaux aux
plages hétérogènes (08:00–12:00, 14:00–17:00, 18:00–20:00…), dont certains se
**chevauchent** sur un même jour. Un chevauchement n'est pas un détail
cosmétique : deux créneaux qui se recouvrent rendent les contrôles de conflit
(C1 enseignant, C2 groupe, C3 salle) indécidables sur l'intervalle commun — le
moteur peut placer deux séances « compatibles » qui, en réalité, se déroulent en
même temps. Mieux vaut le dire que le laisser passer.

Aucune de ces valeurs n'est inventée : elles viennent du canevas officiel déjà
consigné dans `Conception-GET-INJS.txt` (§ (d) du plan de conformité).
"""

from datetime import time

#: Jours ouvrés du canevas officiel (lundi → samedi).
JOURS_OFFICIELS = ('LUNDI', 'MARDI', 'MERCREDI', 'JEUDI', 'VENDREDI', 'SAMEDI')

#: Plages horaires officielles, chacune de 2 h.
PLAGES_OFFICIELLES = (
    (time(7, 30), time(9, 30)),
    (time(9, 45), time(11, 45)),
    (time(13, 30), time(15, 30)),
    (time(15, 45), time(17, 45)),
)

#: Source documentaire de la grille (traçabilité du référentiel).
SOURCE = 'Canevas officiel INJS — feuille « 13. Emploi du temps (modèle) »'


def grille_officielle():
    """Les 24 créneaux officiels, dans l'ordre jours puis plages."""
    return [
        (jour, debut, fin)
        for jour in JOURS_OFFICIELS
        for debut, fin in PLAGES_OFFICIELLES
    ]


def nombre_officiel():
    return len(JOURS_OFFICIELS) * len(PLAGES_OFFICIELLES)


def interruptions():
    """Intervalles entre deux plages consécutives du canevas officiel.

    Rendues en ``(début, fin, minutes)``. C'est ce qui permet de trancher la
    question de la pause déjeuner sans l'inventer : dans la grille officielle,
    le seul intervalle long est 11:45–13:30 (1 h 45), les autres valant 15 min
    (récréation / changement de salle). La pause institutionnelle se DÉDUIT
    donc du référentiel.
    """
    resultat = []
    for (_, fin_precedente), (debut, _fin) in zip(PLAGES_OFFICIELLES,
                                                  PLAGES_OFFICIELLES[1:]):
        resultat.append((fin_precedente, debut,
                         _minutes(debut) - _minutes(fin_precedente)))
    return resultat


def pause_deduite():
    """Pause institutionnelle déductible du canevas : le plus long intervalle.

    Renvoie ``(début, fin)`` ou ``None`` si la grille n'a qu'un seul intervalle
    comparable. Le seuil retenu est celui de la tolérance par défaut des
    contraintes souples (15 min) : en deçà, une coupure n'est pas une pause.
    """
    intervalles = interruptions()
    if not intervalles:
        return None
    debut, fin, minutes = max(intervalles, key=lambda item: item[2])
    if minutes <= 15:
        return None
    return (debut, fin)


def _minutes(heure):
    return heure.hour * 60 + heure.minute


def _cle(jour, debut, fin):
    return (jour, _minutes(debut), _minutes(fin))


def _texte(jour, debut, fin):
    return f'{jour} {debut:%H:%M}–{fin:%H:%M}'


def chevauchements(creneaux):
    """Paires de créneaux qui se recouvrent sur un même jour.

    ``creneaux`` est une séquence de triplets ``(jour, début, fin)``. Deux
    créneaux qui se chevauchent empêchent de garantir C1/C2/C3 sur l'intervalle
    commun : le signaler vaut mieux que produire un planning douteux.
    """
    par_jour = {}
    for jour, debut, fin in creneaux:
        par_jour.setdefault(jour, []).append((_minutes(debut), _minutes(fin), debut, fin))

    paires = []
    for jour, plages in par_jour.items():
        plages.sort()
        for i, (debut_a, fin_a, _da, _fa) in enumerate(plages):
            for debut_b, fin_b, db, fb in plages[i + 1:]:
                # Trié par début : si le suivant commence avant la fin du
                # précédent, il y a recouvrement (fin exclue : deux créneaux
                # jointifs 08:00–10:00 et 10:00–12:00 ne se chevauchent pas).
                if debut_b < fin_a:
                    paires.append((_texte(jour, time(debut_a // 60, debut_a % 60),
                                          time(fin_a // 60, fin_a % 60)),
                                   _texte(jour, db, fb)))
                else:
                    break
    return paires


def comparer_canevas(creneaux):
    """Compare des créneaux réels à la grille officielle.

    :param creneaux: séquence de triplets ``(jour, début, fin)``.
    :returns: dict avec ``conforme`` (bool), ``attendus``, ``presents``,
        ``manquants``, ``non_prevus``, ``chevauchements``, ``source``.
    """
    attendus = {_cle(*c) for c in grille_officielle()}
    presents = {_cle(*c) for c in creneaux}

    manquants = sorted(attendus - presents)
    non_prevus = sorted(presents - attendus)

    def _formater(cle):
        jour, debut, fin = cle
        return _texte(jour, time(debut // 60, debut % 60), time(fin // 60, fin % 60))

    return {
        'conforme': not manquants and not non_prevus,
        'source': SOURCE,
        'attendus': len(attendus),
        'presents': len(presents),
        'manquants': [_formater(c) for c in manquants],
        'non_prevus': [_formater(c) for c in non_prevus],
        'chevauchements': chevauchements(creneaux),
    }
