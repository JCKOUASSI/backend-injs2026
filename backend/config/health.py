"""Healthcheck applicatif (socle L0/L7).

Endpoint : GET /api/health/
Utilisable par un load balancer, une supervision ou un script de déploiement.
Réponse minimale — aucune information sensible (pas de version, pas de DEBUG).
"""
from django.db import connection
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


class HealthReponseSerializer(serializers.Serializer):
    """Contrat réel de GET /api/health/ (voir health_view)."""

    status = serializers.ChoiceField(choices=['ok', 'degraded'])
    database = serializers.ChoiceField(choices=['ok', 'unavailable'])
    timestamp = serializers.DateTimeField()


@extend_schema(
    responses={200: HealthReponseSerializer, 503: HealthReponseSerializer},
)
@api_view(['GET'])
@permission_classes([AllowAny])
def health_view(request):
    """Vérifie la disponibilité de l'application et de la base de données."""
    db_ok = True
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()
    except Exception:
        db_ok = False

    payload = {
        'status': 'ok' if db_ok else 'degraded',
        'database': 'ok' if db_ok else 'unavailable',
        'timestamp': timezone.now().isoformat(),
    }
    return Response(
        payload,
        status=status.HTTP_200_OK if db_ok else status.HTTP_503_SERVICE_UNAVAILABLE,
    )
