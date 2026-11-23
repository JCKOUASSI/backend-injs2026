"""Gestion harmonisée des erreurs DRF (socle L0/L7 — risque R5/R6).

Contrainte de compatibilité : le frontend React (services/api.js) et l'app
mobile Flutter (api_client.dart) consomment le format d'erreur DRF standard
({'detail': …} ou {champ: [erreurs]}). Ce handler **préserve intégralement
le payload** et ajoute uniquement un code machine lisible dans l'en-tête
HTTP `X-Error-Code`, exploitable par les clients sans risque de cassure.
"""
from rest_framework.views import exception_handler as drf_exception_handler


def unified_exception_handler(exc, context):
    """Enrichit la réponse DRF d'un en-tête X-Error-Code sans toucher au payload."""
    response = drf_exception_handler(exc, context)
    if response is None:
        return None  # exception non gérée par DRF → Django 500 standard

    code = getattr(exc, 'default_code', None) or 'error'
    if isinstance(response.data, dict):
        # Certains endpoints métier fournissent déjà un code explicite
        # (ex. {'code': 'DEVICE_LOCKED', 'detail': …} sur /api/auth/login/).
        explicit = response.data.get('code')
        if isinstance(explicit, str) and explicit:
            code = explicit

    response['X-Error-Code'] = str(code).upper()
    return response
