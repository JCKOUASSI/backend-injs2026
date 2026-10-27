"""C2 — Empreinte canonique et déterministe d'un calcul (contrat B.1 §10).

Objectif : deux exécutions identiques du MÊME calcul doivent produire la
MÊME empreinte, quel que soit l'ordre d'itération des objets lus en base.

Règles de canonicalisation (contrat, pas choix d'implémentation) :
    * clés triées ;
    * ``Decimal`` sérialisé en chaîne (jamais en flottant : ``0.1 + 0.2``) ;
    * ensembles et tuples rendus en listes, dans un ordre imposé par
      l'appelant (les composants sont ordonnés par le moteur) ;
    * dates/heures en ISO 8601 ;
    * séparateurs compacts et accents préservés.

Rien ici ne décrit une règle académique : c'est de la traçabilité pure.
"""
import datetime
import decimal
import hashlib
import json


def normaliser(valeur):
    """Convertit une valeur Python en forme JSON canonique."""
    if isinstance(valeur, decimal.Decimal):
        return format(valeur, 'f')
    if isinstance(valeur, (datetime.datetime, datetime.date, datetime.time)):
        return valeur.isoformat()
    if isinstance(valeur, dict):
        return {str(cle): normaliser(valeur[cle]) for cle in sorted(valeur, key=str)}
    if isinstance(valeur, (list, tuple)):
        return [normaliser(item) for item in valeur]
    if isinstance(valeur, set):
        # Un ensemble n'a pas d'ordre : le tri garantit le déterminisme.
        return sorted(normaliser(item) for item in valeur)
    if isinstance(valeur, (bool, int, str)) or valeur is None:
        return valeur
    if isinstance(valeur, float):
        # Un flottant entre dans l'empreinte : on l'ancre sur sa
        # représentation textuelle pour éviter les écarts de plateforme.
        return repr(valeur)
    return str(valeur)


def json_canonique(charge):
    """JSON canonique (trié, compact, UTF-8) de la charge utile."""
    return json.dumps(
        normaliser(charge), sort_keys=True, ensure_ascii=False,
        separators=(',', ':'),
    )


def sha256_texte(texte):
    """SHA-256 hexadécimal d'un texte UTF-8."""
    return hashlib.sha256(texte.encode('utf-8')).hexdigest()


def empreinte(charge):
    """Empreinte SHA-256 de la charge utile, forme canonique."""
    return sha256_texte(json_canonique(charge))