"""Attribut ``Partitioned`` (CHIPS) sur les cookies de session et CSRF.

Django 5.1 ne connaît pas ``SESSION_COOKIE_PARTITIONED`` (introduit en 5.2).
Or l'aperçu intégré est une iframe tierce : les navigateurs qui appliquent
« Bloquer les cookies tiers » rejettent un cookie non partitionné, ce qui
aboutit au classique « CSRF cookie not set » puis à un 403 sur /admin/.

Ce middleware ajoute donc ``; Partitioned`` aux en-têtes ``Set-Cookie`` des
cookies concernés, sans toucher au reste de la chaîne.

Activation : uniquement via ``arena.settings_sandbox`` (profil d'aperçu).
"""
from http.cookies import Morsel

# Noms des cookies à partitionner : les noms dédiés du profil d'aperçu, plus
# les noms hérités (un vieux cookie du navigateur reste partitionné lui aussi).
COOKIE_NAMES = (
    'injs_sessionid',
    'injs_csrftoken',
    'sessionid',
    'csrftoken',
)

# ``http.cookies.Morsel`` sérialise uniquement les attributs connus : on
# déclare ``partitioned`` une seule fois, à l'import du module.
#   - ``_reserved`` fournit le libellé de l'attribut ;
#   - ``_flags`` en fait un attribut sans valeur (``Partitioned`` et non
#     ``Partitioned=True``).
Morsel._reserved.setdefault('partitioned', 'Partitioned')
Morsel._flags.add('partitioned')


class PartitionedCookieMiddleware:
    """Pose ``Partitioned`` sur les cookies de session/CSRF de la réponse."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        self._partitionner(response)
        return response

    @staticmethod
    def _partitionner(response):
        cookies = getattr(response, 'cookies', None)
        if not cookies:
            return
        for nom in COOKIE_NAMES:
            morsel = cookies.get(nom)
            if morsel is None or morsel.get('partitioned'):
                continue
            # Partitioned n'est valide qu'avec SameSite=None et Secure : on ne
            # l'ajoute pas à un cookie qui n'en remplirait pas les conditions,
            # car le navigateur le rejetterait silencieusement.
            if str(morsel.get('samesite', '')).lower() != 'none':
                continue
            if not morsel.get('secure'):
                continue
            morsel['partitioned'] = True
