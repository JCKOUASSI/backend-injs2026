"""Feature flags P00-08 — interrupteurs de fonctionnalités livrés DÉSACTIVÉS.

Les flags sont stockés comme des ``Parametre`` ordinaires (clé préfixée
``flag.``), ce qui donne gratuitement :

* le catalogue en base (interdiction de stocker un flag en dur dans le code
  sans entrée correspondante) ;
* l'historique immuable via ``ParametreHistorique`` ;
* l'administration par l'API Paramètres existante.

Deux formes de valeur sont supportées :

* ``Parametre.type = 'bool'`` : interrupteur global (« true »/« false ») ;
* ``Parametre.type = 'text'`` dont la valeur est un tableau JSON de rôles :
  le flag n'est activé que pour les utilisateurs dont l'un des rôles est
  listé (``[]`` = désactivé pour tout le monde).

Sécurité / kill switch :

* un flag **inconnu, inactif ou absent est toujours considéré ÉTEINT** ;
* il n'y a **pas de passe-droit superuser** : un flag éteint reste éteint
  pour tout le monde, y compris les administrateurs (c'est tout l'intérêt
  d'un bouton d'arrêt d'urgence d'une minute).

Le cache (LocMem en sandbox, Redis en production via les réglages Django)
stocke le dictionnaire des flags ; il est invalidé automatiquement par les
signaux ``parametres.signals`` à chaque écriture/suppression.
"""

import json

from django.core.cache import cache
from rest_framework.permissions import BasePermission

from authentication.role_groups import get_user_roles

from .models import Parametre

#: Préfixe obligatoire des clés de feature flags.
FLAG_PREFIX = 'flag.'

#: Clé de cache (le suffixe permet d'invalider en bloc lors d'une évolution).
FLAGS_CACHE_KEY = 'parametres:flags:v1'

#: Durée de mise en cache de secours (s) ; l'invalidation est normale.
FLAGS_CACHE_TIMEOUT = 300


def invalidate_flags_cache(**kwargs):
    """Invalide le cache des flags (appelé par les signaux Parametre)."""
    cache.delete(FLAGS_CACHE_KEY)


def _load_flags():
    """Retourne ``{cle: Parametre}`` des flags actifs, via le cache."""
    flags = cache.get(FLAGS_CACHE_KEY)
    if flags is None:
        flags = {
            p.cle: p
            for p in Parametre.objects.filter(
                cle__startswith=FLAG_PREFIX, actif=True
            )
        }
        cache.set(FLAGS_CACHE_KEY, flags, FLAGS_CACHE_TIMEOUT)
    return flags


def _roles_list(parametre):
    """Liste de rôles si la valeur est un tableau JSON, sinon ``None``."""
    try:
        data = json.loads(parametre.valeur or '[]')
    except (TypeError, ValueError, AttributeError):
        return None
    if isinstance(data, list) and all(isinstance(role, str) for role in data):
        return data
    return None


def is_enabled(flag, user=None):
    """
    Indique si un feature flag est activé.

    :param flag: clé technique (``flag.xxx``)
    :param user: utilisateur courant (obligatoire pour les flags par rôles)
    :returns: ``False`` si le flag est inconnu, inactif ou éteint
    """
    if not flag:
        return False
    parametre = _load_flags().get(flag)
    if parametre is None:
        return False

    roles = _roles_list(parametre)
    if roles is not None:
        if user is None or not getattr(user, 'is_authenticated', False):
            return False
        return bool(get_user_roles(user) & set(roles))

    return parametre.get_valeur_typed() is True


def flags_for_user(user):
    """
    Carte ``{cle: bool}`` de TOUS les flags actifs évalués pour ``user``.

    Seules les valeurs booléennes sont exposées (jamais la liste interne des
    rôles) : c'est la réponse servie à ``GET /api/parametres/flags/``.
    """
    return {cle: is_enabled(cle, user) for cle in _load_flags()}


def require_flag(flag):
    """
    Permission DRF factory : exige un feature flag activé pour l'utilisateur.

    Usage::

        @permission_classes([IsAuthenticated, require_flag('flag.lot02_...')])
    """

    class FeatureFlagPermission(BasePermission):
        message = 'Cette fonctionnalité est désactivée.'

        def has_permission(self, request, view):
            return is_enabled(flag, request.user)

    # Nom explicite dans les traces / logs DRF.
    FeatureFlagPermission.__name__ = f'RequireFlag_{flag.replace(".", "_")}'
    return FeatureFlagPermission
