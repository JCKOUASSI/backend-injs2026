"""Cache des réponses API statistiques (dashboard, secrétariats, bilans)."""
import hashlib
import json

from formations.api_cache import get_cached_response, set_cached_response

STATS_DASHBOARD_CACHE_TTL = 180
STATS_SECRETARIATS_CACHE_TTL = 180
STATS_BILANS_CACHE_TTL = 300


def _scope_parts(user, scope, period):
    meta = period.get('meta') or {}
    module_ids_key = ''
    if scope.module_ids is not None:
        module_ids_key = hashlib.md5(
            ','.join(str(x) for x in sorted(scope.module_ids)).encode()
        ).hexdigest()[:16]
    return [
        str(getattr(user, 'pk', 'anon')),
        getattr(user, 'role', ''),
        str(getattr(user, 'secretariat_id', '') or ''),
        str(scope.formation_id or ''),
        str(scope.secretariat_id or ''),
        module_ids_key,
        str(period.get('date_debut') or ''),
        str(period.get('date_fin') or ''),
        json.dumps(meta, sort_keys=True, default=str),
    ]


def _cache_key(prefix, parts):
    return hashlib.md5('|'.join([prefix, *parts]).encode()).hexdigest()


def stats_dashboard_cache_key(request, sections, scope, period):
    parts = _scope_parts(request.user, scope, period)
    parts.insert(0, ','.join(sorted(sections)))
    return _cache_key('stats_dash', parts)


def stats_secretariats_cache_key(request, scope, period):
    return _cache_key('stats_sec', _scope_parts(request.user, scope, period))


def stats_bilans_cache_key(request, scope, bilans_params):
    user = request.user
    module_ids_key = ''
    if scope.module_ids is not None:
        module_ids_key = hashlib.md5(
            ','.join(str(x) for x in sorted(scope.module_ids)).encode()
        ).hexdigest()[:16]
    parts = [
        str(getattr(user, 'pk', 'anon')),
        getattr(user, 'role', ''),
        str(getattr(user, 'secretariat_id', '') or ''),
        str(scope.formation_id or ''),
        str(scope.secretariat_id or ''),
        module_ids_key,
        json.dumps(bilans_params, sort_keys=True, default=str),
    ]
    return _cache_key('stats_bilans', parts)


def get_stats_dashboard_cached(key):
    return get_cached_response(key)


def set_stats_dashboard_cached(key, payload, timeout=STATS_DASHBOARD_CACHE_TTL):
    set_cached_response(key, payload, timeout)


def get_stats_secretariats_cached(key):
    return get_cached_response(key)


def set_stats_secretariats_cached(key, payload, timeout=STATS_SECRETARIATS_CACHE_TTL):
    set_cached_response(key, payload, timeout)


def get_stats_bilans_cached(key):
    return get_cached_response(key)


def set_stats_bilans_cached(key, payload, timeout=STATS_BILANS_CACHE_TTL):
    set_cached_response(key, payload, timeout)
