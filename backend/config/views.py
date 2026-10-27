import os

from django.http import HttpResponse, JsonResponse


def _frontend_url(request):
    """URL du frontend canonique (port 3000, figé pour le projet).

    Priorité : variable ``FRONTEND_URL`` si elle est posée (production /
    Docker). Sinon on dérive l'hôte de la requête (ou de l'en-tête
    ``X-Forwarded-Host`` posé par le proxy d'aperçu) en remplaçant le port de
    l'API (8000) par celui du front (3000) — sans aucun identifiant codé en dur.
    """
    explicite = os.environ.get('FRONTEND_URL')
    if explicite:
        return explicite.rstrip('/')
    proto = 'https' if request.is_secure() else 'http'
    host = request.headers.get('X-Forwarded-Host') or request.get_host()
    if host.startswith('8000-'):
        host = f'3000-{host[len("8000-"):]}'
    elif ':' in host:
        host = f'{host.split(":", 1)[0]}:3000'
    return f'{proto}://{host}'


def _api_links(request):
    base = request.build_absolute_uri('/').rstrip('/')
    frontend = _frontend_url(request)
    return {
        'application': 'INJS LMD API',
        'organisation': 'INJS — Institut National de la Jeunesse et des Sports',
        'version': '1.0',
        'links': {
            'frontend': frontend,
            'documentation': f'{base}/api/docs/',
            'schema': f'{base}/api/schema/',
            'admin': f'{base}/admin/',
            'dashboard': f'{base}/dashboard/',
            'auth': {
                'login': f'{base}/api/auth/login/',
                'me': f'{base}/api/auth/me/',
                'token_refresh': f'{base}/api/auth/token/refresh/',
            },
            'formations': f'{base}/api/formations/',
            'scolarite': f'{base}/api/scolarite/',
            'admissions': f'{base}/api/admissions/',
            'presences': f'{base}/api/scan/',
            'exports': f'{base}/api/exports/',
        },
    }


def api_root(request):
    """Page d'accueil de l'API (JSON ou HTML selon Accept)."""
    payload = _api_links(request)
    accept = request.headers.get('Accept', '')
    wants_html = (
        'text/html' in accept
        and 'application/json' not in accept.split(',')[0].strip()
    ) or request.GET.get('format') == 'html'

    if not wants_html:
        return JsonResponse(payload)

    links = payload['links']
    auth = links['auth']
    rows = [
        ('Application web (React)', links['frontend']),
        ('Documentation API (Swagger)', links['documentation']),
        ('Schéma OpenAPI', links['schema']),
        ('Administration Django', links['admin']),
        ('Dashboard Direction', links['dashboard']),
        ('Connexion API', auth['login']),
        ('Formations', links['formations']),
        ('Badgeage (scan QR)', links['presences']),
        ('Exports PDF / Excel', links['exports']),
    ]
    list_items = '\n'.join(
        f'        <li><a href="{url}">{label}</a></li>' for label, url in rows
    )
    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{payload['application']}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; max-width: 42rem; margin: 2rem auto; padding: 0 1rem; color: #1a1a1a; }}
    h1 {{ font-size: 1.5rem; margin-bottom: 0.25rem; }}
    p.sub {{ color: #555; margin-top: 0; }}
    ul {{ line-height: 1.8; padding-left: 1.25rem; }}
    a {{ color: #0b5cab; }}
    footer {{ margin-top: 2rem; font-size: 0.875rem; color: #666; }}
    code {{ background: #f4f4f4; padding: 0.1em 0.35em; border-radius: 3px; }}
  </style>
</head>
<body>
  <h1>{payload['application']}</h1>
  <p class="sub">{payload['organisation']}</p>
  <p>API REST — utilisez les liens ci-dessous ou l’application web pour vous connecter.</p>
  <ul>
{list_items}
  </ul>
  <footer>
    Réponse JSON : <code>{request.build_absolute_uri()}?format=json</code>
  </footer>
</body>
</html>"""
    return HttpResponse(html)
