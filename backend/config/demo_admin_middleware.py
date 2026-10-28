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

DÉCONNEXION (correctif du 2026-10-28) :
la reconnexion automatique annulait la déconnexion — la session était bien
détruite, mais la requête suivante sur /admin/ reconnectait aussitôt le
superutilisateur : le bouton semblait inopérant. Une déconnexion explicite
suspend donc la reconnexion automatique, et ce, de deux façons :
  * un drapeau de PROCESSUS, qui fonctionne même quand les cookies sont
    bloqués (cas d'usage même de ce middleware) ;
  * un marqueur de session, propre à chaque navigateur, quand les cookies
    fonctionnent.
La suspension est levée par une connexion explicite (POST du formulaire).
"""

import logging
import os

from django.contrib.auth import get_user_model

log = logging.getLogger('demo_admin')


class DemoAdminAutoLoginMiddleware:
    #: Clé de session mémorisant une déconnexion explicite (par navigateur).
    CLE_DECONNEXION = '_demo_autologin_suspendu'

    #: Drapeau de processus : survit à l'absence de cookies, contrairement au
    #: marqueur de session. Commun à tous les visiteurs, ce qui est acceptable
    #: pour un serveur de démonstration mono-utilisateur.
    _suspendu = False

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if self._enabled(request):
            chemin = request.path.rstrip('/')
            if chemin.endswith('/logout'):
                # Déconnexion demandée : on refuse de reconnecter ensuite.
                DemoAdminAutoLoginMiddleware._suspendu = True
                session = getattr(request, 'session', None)
                if session is not None:
                    session[self.CLE_DECONNEXION] = True
            elif chemin.endswith('/login') and request.method == 'POST':
                # Connexion explicite réussie : la démo peut reprendre la main.
                if getattr(request, 'user', None) and request.user.is_authenticated:
                    DemoAdminAutoLoginMiddleware._suspendu = False
                    session = getattr(request, 'session', None)
                    if session is not None:
                        session.pop(self.CLE_DECONNEXION, None)
        return response

    def _enabled(self, request):
        from django.conf import settings
        return (
            getattr(settings, 'DEBUG', False)
            and os.environ.get('DEMO_ADMIN_AUTOLOGIN', '').lower() in ('1', 'true', 'yes')
            and request.path.startswith('/admin/')
        )

    def _est_suspendu(self, request):
        if DemoAdminAutoLoginMiddleware._suspendu:
            return True
        session = getattr(request, 'session', None)
        return bool(session is not None and session.get(self.CLE_DECONNEXION))

    def process_view(self, request, view_func, view_args, view_kwargs):
        if not self._enabled(request):
            return None

        chemin = request.path.rstrip('/')

        # Une déconnexion ne doit jamais être suivie d'une reconnexion.
        if chemin.endswith('/logout'):
            return None

        if self._est_suspendu(request):
            if chemin.endswith('/login'):
                # Toujours autoriser la saisie manuelle des identifiants :
                # sans le dispenser du contrôle CSRF par cookie, la connexion
                # serait impossible dans une iframe où les cookies sont bloqués.
                request.csrf_processing_done = True
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
