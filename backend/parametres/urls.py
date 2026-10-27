"""
URL routing pour le module Paramètres.

Enregistre le ViewSet via DefaultRouter.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ParametreViewSet

router = DefaultRouter()
router.register(r'', ParametreViewSet, basename='parametre')

urlpatterns = [
    path('', include(router.urls)),
]
