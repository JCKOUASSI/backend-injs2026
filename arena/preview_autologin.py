"""Auto-connexion du compte de démonstration dans l'admin embarqué.

La passerelle d'aperçu filtre parfois **tous** les cookies : sans cookie de
session ni de CSRF, l'admin Django renvoie systématiquement 403 « La
vérification CSRF a échoué ». Ce middleware, strictement réservé au profil
d'aperçu (``arena.settings_sandbox``), rend l'admin utilisable :

  1. dispense les routes ``/admin/`` de la vérification CSRF par cookie ;
  2. authentifie le compte de démonstration sur chaque requête ``/admin/``.

Double garde-fou : il ne fait rien si ``DEBUG`` est faux, ni si
``PREVIEW_AUTOLOGIN_ENABLED`` est désactivé. En production, il est inerte et
n'est même pas référencé par ``config.settings``.
"""
import logging

from django.conf import settings
from django.contrib.auth import get_user_model

log = logging.getLogger('arena.preview_autologin')

PREFIXE_ADMIN = '/admin/'


class AutoLoginApercuMiddleware:
    """Rend ``/admin/`` utilisable sans cookie (iframe d'aperçu)."""

    #: Une déconnexion explicite doit rester effective. Sans ce drapeau, la
    #: requête suivante sur /admin/ reconnectait aussitôt le compte de
    #: démonstration : la session était pourtant bien détruite, mais le bouton
    #: « Déconnexion » semblait ne rien faire.
    #: Drapeau de PROCESSUS (et non de session) : dans l'iframe d'aperçu les
    #: cookies peuvent être totalement bloqués, donc un marqueur de session ne
    #: survivrait pas — c'est précisément le cas d'usage de ce middleware.
    _deconnecte = False

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if self._actif(request):
            chemin = request.path.rstrip('/')
            if chemin.endswith('/logout'):
                AutoLoginApercuMiddleware._deconnecte = True
            elif chemin.endswith('/login') and request.method == 'POST':
                if getattr(request, 'user', None) and request.user.is_authenticated:
                    AutoLoginApercuMiddleware._deconnecte = False
        return response

    @staticmethod
    def _actif(request):
        return (
            getattr(settings, 'DEBUG', False)
            and getattr(settings, 'PREVIEW_AUTOLOGIN_ENABLED', False)
            and request.path.startswith(PREFIXE_ADMIN)
        )

    def process_view(self, request, view_func, view_args, view_kwargs):
        if not self._actif(request):
            return None

        chemin = request.path.rstrip('/')

        # Une déconnexion ne doit jamais être suivie d'une reconnexion.
        if chemin.endswith('/logout'):
            return None

        if AutoLoginApercuMiddleware._deconnecte:
            # On ne reconnecte plus, mais on laisse la connexion manuelle
            # possible : sans dispense CSRF, l'iframe sans cookies renverrait 403.
            if chemin.endswith('/login'):
                request.csrf_processing_done = True
            return None

        # 1) Pas de jeton CSRF par cookie : la vue est réputée vérifiée.
        request.csrf_processing_done = True
        # 2) Session de démonstration, sans cookie.
        if not getattr(request.user, 'is_authenticated', False) or not request.user.is_staff:
            username = getattr(settings, 'PREVIEW_AUTOLOGIN_USERNAME', 'admin')
            User = get_user_model()
            utilisateur = User.objects.filter(
                username=username, is_active=True, is_staff=True,
            ).first()
            if utilisateur is None:
                log.warning(
                    "Auto-connexion d'aperçu ignorée : compte %r introuvable "
                    "ou non-staff.", username,
                )
                return None
            request.user = utilisateur
        return None
