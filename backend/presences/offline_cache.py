"""Helpers de cache pour l'endpoint offline-data.

Ce module est volontairement isolé pour éviter les imports circulaires entre
``formations`` et ``presences`` lors de l'invalidation du cache.
"""
from django.core.cache import cache
from django.conf import settings


OFFLINE_DATA_CACHE_TIMEOUT = int(
    getattr(settings, 'OFFLINE_DATA_CACHE_TIMEOUT_SECONDS', 3600)
)  # 1 heure par défaut (données quasi-statiques)
OFFLINE_DATA_LOCK_TIMEOUT = 30  # secondes max pour regénérer le payload


def offline_data_cache_key(token):
    """Clé de cache Redis pour les données hors-ligne d'un token QR."""
    return f"offline_data:{str(token).strip().lower()}"


def offline_data_lock_key(token):
    """Clé de verrou anti-stampede pour la regénération du payload."""
    return f"offline_data_lock:{str(token).strip().lower()}"


def invalidate_offline_data_cache(token):
    """Invalide le cache offline-data pour un token QR donné."""
    cache.delete(offline_data_cache_key(token))
