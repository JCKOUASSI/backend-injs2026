"""
API v1 — routes centralisées (monorepo injs-app-ref).
Délègue aux sous-modules existants dans ce projet.
Seules les apps installées sont référencées ici.
"""
from django.urls import path, include

urlpatterns = [
    path('core/', include('core.urls')),
    path('auth/', include('authentication.urls')),
    path('formations/', include('formations.urls')),
    path('presences/', include('presences.urls')),
    # Namespace distinct de /api/dashboard/ (alias historique dans urls.py).
    path('dashboard/', include('dashboard.api_urls', namespace='dashboard_api_v1')),
    path('exports/', include('exports.urls')),
    path('statistiques/', include('statistiques.urls')),
    path('evaluations/', include('suiviEvaluation.urls')),
    path('parametres/', include('parametres.urls')),
    path('referentiels/', include('referentiels.urls')),
]