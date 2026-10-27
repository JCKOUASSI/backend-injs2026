"""
Vues de prévisualisation locale (sandbox / démo).

Quand PREVIEW_SPA=1, Django sert directement le build de production du
frontend React (../frontend/dist) :
  - les fichiers existants (/assets/index-*.js, /assets/index-*.css,
    /logo.png, /favicon.ico, /vite.svg…) sont servis tels quels ;
  - tout autre chemin non géré par l'API/ l'admin renvoie index.html
    (routage côté client React / React Router) : c'est le « SPA fallback ».

Ainsi l'application, l'API et l'admin partagent UNE seule origine : plus de
proxy Node, de cookies cross-site, de CORS/CSRF ou de WebSocket à gérer.
En production cette vue n'est pas branchée (cf. config/urls.py).
"""
from pathlib import Path

from django.conf import settings
from django.http import HttpResponse
from django.views.static import serve


def _index_html():
    index = Path(settings.FRONTEND_DIST) / 'index.html'
    if not index.exists():
        return HttpResponse(
            "Le build frontend est introuvable.\n"
            "Lancez : cd frontend && npm install && npm run build",
            status=503,
            content_type='text/plain; charset=utf-8',
        )
    response = HttpResponse(index.read_bytes(), content_type='text/html; charset=utf-8')
    # Le HTML ne doit jamais être mis en cache (renouvellement des hash d'assets).
    response['Cache-Control'] = 'no-store, must-revalidate'
    return response


def spa(request, path=''):
    dist_root = Path(settings.FRONTEND_DIST).resolve()
    if path:
        candidate = (dist_root / path).resolve()
        # Protection anti-traversée de répertoire.
        try:
            candidate.relative_to(dist_root)
        except ValueError:
            return _index_html()
        if candidate.is_file():
            # Fichier statique du build (JS/CSS/images…), cache long sûr
            # (les noms sont hashés).
            response = serve(request, path, document_root=str(dist_root), show_indexes=False)
            if path.startswith('assets/'):
                response['Cache-Control'] = 'public, max-age=31536000, immutable'
            return response
    # Route côté client (/, /login, /formations…) -> index.html
    return _index_html()
