"""
Classes d'authentification JWT.

`FlexibleJWTAuthentication` étend la JWTAuthentication de SimpleJWT pour des
environnements de prévisualisation où la passerelle/le navigateur peuvent ne
pas transmettre certains en-têtes ou cookies dans une iframe cross-site :

1. en-tête standard ``Authorization: Bearer <token>`` (normal) ;
2. en-tête de secours ``X-JWT-Access: <token>`` (certaines passerelles d'aperçu
   suppriment l'en-tête ``Authorization`` ; les en-têtes personnalisés passent) ;
3. jeton d'accès en paramètre de requête ``?access_token=`` en dernier recours
   (utile pour les téléchargements de fichiers via des URL directes).

En production, seul le chemin n°1 est utilisé : les autres restent présents
mais ne sont jamais alimentés par le frontend de production.
"""
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken


FALLBACK_HEADER = 'X-JWT-Access'
QUERY_PARAM = 'access_token'


class FlexibleJWTAuthentication(JWTAuthentication):
    def get_header(self, request):
        # 1) En-tête standard Authorization: Bearer ...
        header = super().get_header(request)
        if header:
            return header
        # 2) En-tête de secours
        fallback = request.headers.get(FALLBACK_HEADER)
        if fallback:
            # get_raw_token attend un en-tête de la forme "Bearer <token>" ;
            # on reconstruit ce découpage.
            return ('Bearer ' + fallback).encode()
        return None

    def authenticate(self, request):
        # 3) Dernier recours : jeton en paramètre d'URL (exports/lecteurs médias)
        token = request.GET.get(QUERY_PARAM)
        if token:
            try:
                validated = self.get_validated_token(token)
                user = self.get_user(validated)
                return user, validated
            except InvalidToken:
                return None
        return super().authenticate(request)


class FlexibleJWTScheme(OpenApiAuthenticationExtension):
    """Extension OpenAPI décrivant FlexibleJWTAuthentication.

    Sans elle, drf-spectacular ne sait pas documenter
    l'authentificateur (avertissement W001 répété sur chaque vue) et
    l'ignore. Le schéma déclaré reflète le mécanisme principal réel :
    jeton JWT transmis en « Authorization: Bearer <token> » (les voies
    de secours X-JWT-Access et ?access_token= sont des mécanismes
    d'aperçu, documentés dans le docstring du module).
    """

    target_class = 'authentication.auth_classes.FlexibleJWTAuthentication'
    name = 'BearerAuth'
    match_subclasses = True
    priority = 1

    def get_security_definition(self, auto_schema):
        return {
            'type': 'http',
            'scheme': 'bearer',
            'bearerFormat': 'JWT',
            'description': (
                'Jeton JWT SimpleJWT transmis via '
                '« Authorization: Bearer <token> ».'
            ),
        }
