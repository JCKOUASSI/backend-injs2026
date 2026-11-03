"""Normalisation des identifiants d'entrée du moteur (groupes, salles, années).

Pourquoi ce module existe. ``groupe_ids`` circule sous trois formes selon
l'appelant : ``10`` (entier), ``'10'`` (chaîne, ce que produit ``str(pk)``) et
``'10,11'`` (chaîne multiple, ce que reçoit l'API depuis l'URL). Écrire
``list(groupe_ids)`` sur une chaîne ne donne pas la liste des identifiants mais
la liste de ses **caractères** : ``list('10') == ['1', '0']``.

Conséquence observée : un groupe dont la clé primaire tient sur un chiffre
fonctionnait par accident (``list('9') == ['9']``), et dès que la séquence
dépassait 9 — ce qui arrive sur une base qui a vécu, ou sur PostgreSQL où la
séquence avance plus vite que sur SQLite — le moteur ne trouvait plus aucune
affectation et répondait ``AFFECTATIONS_PEDAGOGIQUES_VIDES``. Le défaut ne
dépendait donc pas de la base, seulement de la taille de l'identifiant.

La normalisation est faite ici, une seule fois, pour que tous les appelants
partagent la même règle : chaîne simple, chaîne à virgules, entier, liste ou
tuple d'entiers et/ou de chaînes.
"""


def normaliser_ids(valeur):
    """Renvoie une liste d'identifiants, ou ``None`` si aucun filtre n'est demandé.

    >>> normaliser_ids('10')
    ['10']
    >>> normaliser_ids(10)
    [10]
    >>> normaliser_ids('10, 11')
    ['10', '11']
    >>> normaliser_ids([10, '11'])
    [10, '11']
    >>> normaliser_ids('') is None
    True
    """
    if valeur is None:
        return None
    # Une chaîne est UN identifiant ou une liste séparée par des virgules —
    # jamais une suite de caractères.
    if isinstance(valeur, str):
        morceaux = [morceau.strip() for morceau in valeur.split(',')]
        identifiants = [morceau for morceau in morceaux if morceau]
    elif isinstance(valeur, int):
        identifiants = [valeur]
    elif isinstance(valeur, (list, tuple, set, frozenset)):
        identifiants = []
        for element in valeur:
            if element is None:
                continue
            if isinstance(element, str):
                identifiants.extend(
                    morceau.strip() for morceau in element.split(',')
                    if morceau.strip()
                )
            else:
                identifiants.append(element)
    else:
        raise TypeError(
            'Identifiants attendus sous forme d’entier, de chaîne ou de liste '
            f'(reçu : {type(valeur).__name__}).')
    return identifiants or None
