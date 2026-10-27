"""
Middleware de DÉMONSTRATION UNIQUEMENT (jamais actif en production).

Contexte : dans l'iframe de prévisualisation, les cookies tiers peuvent être
totalement bloqués (iframe « sandbox » sans allow-same-origin ou politique
navigateur anti-cookies tiers). L'admin Django repose pourtant sur deux cookies
(CSRF + session) : sans eux, la connexion renvoie systématiquement un 403
« La vérification CSRF a échoué » puis renvoie au formulaire.

Quand DEBUG=True ET DEMO_ADMIN_AUTOLOGIN=1 (défaut inactif), ce middleware :
  1. dispense les routes /admin/ de la vérification CSRF par cookie
     (pose de l'attribut interne csrf_processing_done avant CsrfViewMiddleware) ;
  2. authentifie automatiquement le superutilisateur de démonstration sur
     chaque requête /admin/ (aucun cookie de session nécessaire).

DOUBLE GARDE-FOU SÉCURITAIRE :
  - ne fait STRICTEMENT rien si DEBUG n'est pas True ;
  - ne fait rien si la variable d'environnement DEMO_ADMIN_AUTOLOGIN n'est pas
    activée. En production ce fichier est donc totalement inerte.
"""
import logging
import os

from django.contrib.auth import get_user_model

log = logging.getLogger('demo_admin')


class DemoAdminAutoLoginMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def _enabled(self, request):
        from django.conf import settings
        return (
            getattr(settings, 'DEBUG', False)
            and os.environ.get('DEMO_ADMIN_AUTOLOGIN', '').lower() in ('1', 'true', 'yes')
            and request.path.startswith('/admin/')
        )

    def process_view(self, request, view_func, view_args, view_kwargs):
        if not self._enabled(request):
            return None
        # 1) Désactive la vérification CSRF pour cette vue d'admin (pas de cookie).
        request.csrf_processing_done = True
        # 2) Connecte automatiquement le premier superutilisateur (démo).
        if not getattr(request.user, 'is_authenticated', False) or not request.user.is_staff:
            User = get_user_model()
            demo_user = (
                User.objects.filter(is_superuser=True, is_active=True)
                .order_by('pk')
                .first()
            )
            if demo_user is not None:
                request.user = demo_user
        return None
