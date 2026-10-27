"""Permission inter-plateformes pour les endpoints de synchronisation."""
import os
import secrets

from rest_framework.permissions import BasePermission


class IsInterPlatformServiceAccount(BasePermission):
    """Vérifie que la requête porte le header Authorization: Api-Key <INTER_PLATFORM_API_KEY>.

    La clé est lue depuis la variable d'environnement INTER_PLATFORM_API_KEY.
    Si la variable est vide ou absente, l'accès est refusé.
    """

    def has_permission(self, request, view):
        expected = (os.environ.get('INTER_PLATFORM_API_KEY') or '').strip()
        if not expected:
            return False
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        if not auth_header.startswith('Api-Key '):
            return False
        provided = auth_header[len('Api-Key '):]
        return secrets.compare_digest(provided, expected)
