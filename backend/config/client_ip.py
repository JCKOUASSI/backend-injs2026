"""Extraction de l'IP client derrière reverse proxy (Nginx Proxy Manager, etc.)."""


def get_client_ip(request) -> str:
    """
    Récupère la vraie IP du client derrière le(s) proxy(s).

    codeqr-be n'est jamais exposé directement à Internet (port Docker
    non publié, uniquement joignable depuis le réseau interne où tourne
    Nginx Proxy Manager), donc X-Forwarded-For posé par NPM est fiable ici.

    X-Forwarded-For peut contenir "client, proxy1, proxy2" — on prend le
    premier élément (le client d'origine).
    """
    if request is None:
        return ''

    xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if xff:
        ip = xff.split(',')[0].strip()
        if ip:
            return ip
    return (request.META.get('REMOTE_ADDR') or '').strip()
