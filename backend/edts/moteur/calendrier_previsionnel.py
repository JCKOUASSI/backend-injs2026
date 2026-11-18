"""Proposition NON officielle des semaines d'une année académique GET-INJS.

Les semaines sont des index de blocs de sept jours depuis ``date_debut`` ;
aucune date de rentrée S1/S2 n'est déduite du seul libellé de l'année.
Ce découpage régulier est destiné aux brouillons explicitement confirmés,
jamais à une publication automatique.
"""

from datetime import timedelta


def proposer(annee):
    if not annee or not annee.date_debut or not annee.date_fin:
        raise ValueError('Dates de l’année académique manquantes.')
    duree = (annee.date_fin - annee.date_debut).days + 1
    nombre = (duree + 6) // 7
    if not 4 <= nombre <= 53:
        raise ValueError('Durée de l’année incompatible avec un calendrier prévisionnel (4–53 semaines).')
    moitie = nombre // 2
    coupure = annee.date_debut + timedelta(weeks=moitie)
    return {
        'source': 'PROVISOIRE_NON_OFFICIEL',
        'date_debut': annee.date_debut.isoformat(),
        'date_fin': annee.date_fin.isoformat(),
        'date_bascule_estimee': coupure.isoformat(),
        'impairs': list(range(1, moitie + 1)),
        'pairs': list(range(moitie + 1, nombre + 1)),
    }
