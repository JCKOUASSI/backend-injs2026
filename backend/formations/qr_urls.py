"""
Routes publiques liées aux QR codes de formations.

Ce fichier est monté sur formations/ dans config/urls.py pour que les URLs
de génération d'images QR fonctionnent sans le préfixe api/.
Seules les deux routes nécessaires sont exposées ici — les autres endpoints
de l'API formations restent exclusivement sous api/formations/.
"""
from django.urls import path
from . import views

urlpatterns = [
    path('<int:pk>/qr-image/', views.qr_image, name='qr-image-public'),
    path('<int:pk>/sessions/<int:session_pk>/qr-image/', views.session_qr_image, name='session-qr-image-public'),
]
