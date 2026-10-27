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
