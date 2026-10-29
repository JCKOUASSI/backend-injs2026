"""Redirection de la racine vers l'admin Django — **profil d'aperçu uniquement**.

Constat : `https://<port>-<sandbox>.e2b.app/` (port 8000) renvoie le JSON de la
racine d'API. Un utilisateur qui ouvre l'aperçu de l'API — ou qui clique sur le
bouton « administration » alors que les fenêtres surgissantes sont bloquées dans
l'iframe — tombe sur un bloc JSON et en conclut que « l'admin ne fonctionne
pas ». Le tableau de bord existait pourtant, à `/admin/`.

Ce middleware redirige **les navigations de navigateur** (en-tête
`Accept: text/html`) vers `/admin/`. Les clients d'API, les tests et les sondes
de supervision n'envoient pas cet en-tête : ils continuent de recevoir le JSON
inchangé. Le module n'est branché que par `arena.settings_sandbox`, jamais par la
configuration de production.
"""

from django.http import HttpResponseRedirect


class AdminRedirectApercuMiddleware:
    """`GET /` d'un navigateur → `/admin/` (aperçu seulement)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            request.method == 'GET'
            and request.path == '/'
            and 'text/html' in request.headers.get('Accept', '')
        ):
            return HttpResponseRedirect('/admin/')
        return self.get_response(request)
