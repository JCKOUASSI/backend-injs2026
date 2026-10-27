"""Anti-doublon de libellé portable — ADR-006.

La ``UniqueConstraint(Lower('libelle'))`` des référentiels socles repose sur
``LOWER()`` en base : exact sur PostgreSQL (plie accents et casse), mais
limitée à l'ASCII sur SQLite (base du sandbox). La normalisation
d'application ci-dessous — NFKD, suppression des diacritiques, ``casefold``,
trim — fournit une comparaison **identique sur les deux moteurs** ; la
contrainte base est conservée comme garde-fou (défense de profondeur,
règle 11 : ne pas deviner, ne pas supprimer la contrainte).
"""
import unicodedata


def normaliser_libelle(valeur):
    """Forme canonique insensible à la casse, aux accents et aux marges.

    >>> normaliser_libelle('Épreuve écrite')
    'epreuve ecrite'
    """
    if not valeur:
        return ''
    decompose = unicodedata.normalize('NFKD', valeur)
    sans_diacritiques = ''.join(
        c for c in decompose if not unicodedata.combining(c)
    )
    return sans_diacritiques.casefold().strip()


def libelle_en_doublon(modele, libelle, pk_exclu=None):
    """Vrai si une autre ligne du modèle porte la même forme normalisée.

    Comparaison au niveau application (portable) ; les tables de
    référentiels sont petites, le scan Python est négligeable et évite tout
    dépendance au comportement du moteur.
    """
    if not libelle:
        return False
    forme = normaliser_libelle(libelle)
    if not forme:
        return False
    queryset = modele._default_manager.all()
    if pk_exclu is not None:
        queryset = queryset.exclude(pk=pk_exclu)
    for existant in queryset.values_list('libelle', flat=True):
        if normaliser_libelle(existant) == forme:
            return True
    return False
