"""
Middleware de développement UNIQUEMENT actif quand DEBUG=True.

But : permettre à l'admin Django et aux pages servies par le backend d'être
affichés dans l'iframe d'aperçu de la plateforme (hôte *.e2b.app), ce que
X-Frame-Options: DENY (défaut Django) interdit sinon.

En production (DEBUG=False) ce middleware n'est pas branché : la sécurité
X-Frame-Options par défaut reste pleinement appliquée.
"""
import os


class DevPreviewFrameMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        # On retire le X-Frame-Options posé par Django et on autorise
        # l'intégration via CSP frame-ancestors (large en démo locale).
        response.headers.pop('X-Frame-Options', None)
        response.headers.pop('Content-Security-Policy', None)
        extra = os.environ.get('DEV_FRAME_ANCESTORS', '*')
        response.headers['Content-Security-Policy'] = f"frame-ancestors {extra}"
        return response
