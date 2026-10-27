"""Cache API formations (stats, referentiels) + invalidation referentiels."""
import hashlib

from django.core.cache import cache

REFERENTIELS_CACHE_VERSION_KEY = 'referentiels_api_cache_version'


def request_cache_key(prefix, request, extra=()):
    """Clé de cache stable par utilisateur + query string."""
    user = request.user
    qp = '&'.join(
        f'{k}={request.query_params.get(k, "")}'
        for k in sorted(request.query_params.keys())
    )
    parts = (
        prefix,
        str(getattr(user, 'pk', 'anon')),
        getattr(user, 'role', ''),
        str(getattr(user, 'secretariat_id', '') or ''),
        *[str(x) for x in extra],
        qp,
    )
    return hashlib.md5('|'.join(parts).encode()).hexdigest()


def get_cached_response(key):
    return cache.get(key)


def set_cached_response(key, data, timeout):
    cache.set(key, data, timeout)


def referentiels_cache_version():
    return cache.get(REFERENTIELS_CACHE_VERSION_KEY) or 0


def bump_referentiels_cache_version():
    current = cache.get(REFERENTIELS_CACHE_VERSION_KEY) or 0
    cache.set(REFERENTIELS_CACHE_VERSION_KEY, current + 1, timeout=None)


def invalidate_referentiels_cache():
    bump_referentiels_cache_version()
