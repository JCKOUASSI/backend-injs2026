import logging

from rest_framework.throttling import SimpleRateThrottle

logger = logging.getLogger(__name__)


def _client_ip(request) -> str:
    """
    Récupère la vraie IP du client derrière le(s) proxy(s).

    codeqr-be n'est jamais exposé directement à Internet (port Docker
    non publié, uniquement joignable depuis le réseau interne où tourne
    Nginx Proxy Manager), donc X-Forwarded-For posé par NPM est fiable ici.

    X-Forwarded-For peut contenir "client, proxy1, proxy2" — on prend le
    premier élément (le client d'origine).
    """
    xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if xff:
        ip = xff.split(',')[0].strip()
        if ip:
            return ip
    return (request.META.get('REMOTE_ADDR') or '').strip()


class LoginRateThrottle(SimpleRateThrottle):
    """Throttling anti bruteforce sur l'endpoint login.

    Contrairement à un throttling strict, si le backend de cache est
    inaccessible (ex: Redis absent en environnement local), on autorise
    la requête (fail-open) plutôt que de bloquer tous les logins par
    une erreur 500. Le risque d'attaque par force brute est déjà atténué
    par ``connexion_sure.verifier_verrouillage`` (verrouillage de compte),
    qui ne dépend pas du cache.
    """
    scope = 'login'

    def allow_request(self, request, view):
        try:
            allowed = super().allow_request(request, view)
        except Exception:
            # — Fail-open : si le cache est inaccessible (Redis down en dev),
            # — on autorise la requête et on journalise un avertissement.
            # — Le verrouillage de compte (connexion_sure) reste actif.
            logger.warning(
                'login_throttle_cache_error ip=%s error=%s',
                _client_ip(request),
                'cache backend unavailable',
                exc_info=True,
            )
            return True
        if not allowed:
            logger.warning(
                'login_throttled ip=%s',
                _client_ip(request),
            )
        return allowed

    def get_cache_key(self, request, view):
        ip = _client_ip(request)
        if not ip:
            return None
        return f'login:{ip}'


class ScanRateThrottle(SimpleRateThrottle):
    """Throttling anti spam sur les endpoints de scan QR.

    - Compte authentifié (app mobile) : quota par utilisateur (+ appareil si fourni),
      pour éviter qu'une salle entière partage le même plafond derrière un NAT WiFi.
    - Scan public (web) : quota par IP + token QR.
    """
    scope = 'scan'

    def _request_value(self, request, key):
        try:
            val = (request.data or {}).get(key, '')
            if val:
                return str(val).strip()
        except Exception:
            pass
        if hasattr(request, 'POST'):
            val = request.POST.get(key, '')
            if val:
                return str(val).strip()
        return ''

    def _scan_device_id(self, request):
        return self._request_value(request, 'device_id')

    def get_cache_key(self, request, view):
        user = getattr(request, 'user', None)
        if user is not None and getattr(user, 'is_authenticated', False):
            device_id = self._scan_device_id(request)
            device_key = device_id[:64] if device_id else 'no-device'
            return f'scan:user:{user.pk}:{device_key}'
        ip = _client_ip(request)
        if not ip:
            return None
        token = self._request_value(request, 'token_qr')
        if not token:
            query_params = getattr(request, 'query_params', None) or getattr(request, 'GET', None) or {}
            token = query_params.get('token_qr', '') or ''
        token_key = str(token).split('-')[0] if token else 'no-token'
        return f'scan:ip:{ip}:{token_key}'


class OfflineDataRateThrottle(SimpleRateThrottle):
    """Throttling anti polling agressif sur l'endpoint offline-data."""
    scope = 'offline_data'

    def get_cache_key(self, request, view):
        token = (
            (request.query_params or {}).get('token', '')
            or getattr(view, 'kwargs', {}).get('token', '')
            or ''
        )
        token = str(token).strip().lower()
        if not token:
            ip = _client_ip(request)
            return f'offline_data:{ip}:no-token'
        return f'offline_data:{token}'
