"""Routes du noyau transverse (P01-01), montées sous ``/api/core/``."""
from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .api import EvenementAuditViewSet

routeur = SimpleRouter()
routeur.register(r'audit', EvenementAuditViewSet, basename='core-audit')

urlpatterns = [
    path('', include(routeur.urls)),
]
