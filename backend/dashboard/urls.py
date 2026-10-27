from django.urls import path, re_path
from django.views.generic import RedirectView
from . import views

_frontend = RedirectView.as_view(url='/', permanent=False)

urlpatterns = [
    # Public badge page (conservée)
    path('badge/', views.badge_view, name='web-badge'),
    # Politique de confidentialité — URL à renseigner dans Google Play (permission CAMÉRA, etc.)
    path(
        'legal/confidentialite-qr-badge/',
        views.qr_badge_privacy_view,
        name='qr-badge-privacy',
    ),
    # Support — URL à renseigner dans App Store Connect (Support URL)
    path(
        'legal/support-qr-badge/',
        views.qr_badge_support_view,
        name='qr-badge-support',
    ),

    # Auth (conservées pour compatibilité QR badge)
    path('login/', views.login_view, name='web-login'),
    path('logout/', views.logout_view, name='web-logout'),

    # Toutes les autres pages HTML désactivées → redirection frontend React
    path('', _frontend, name='web-dashboard'),
    re_path(r'^formations/', _frontend, name='web-formations'),
    re_path(r'^participants/', _frontend, name='web-participants'),
    re_path(r'^formateurs/', _frontend, name='web-formateurs'),
    re_path(r'^users/', _frontend, name='web-users'),
    path('import/', _frontend, name='web-import-excel'),
]
