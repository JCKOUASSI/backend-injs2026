from django.conf import settings
from django.contrib import admin
from django.urls import path, include, re_path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from config.admin_site import setup_admin_site
from config.views import api_root
from config.health import health_view
from config.preview import spa
from config.static_views import service_worker, favicon
from formations.api_views import formateur_list_api

setup_admin_site()

# En mode prévisualisation SPA, la racine sert l'application React.
_root_view = spa if getattr(settings, 'PREVIEW_SPA', False) else api_root

urlpatterns = [
    # Racine → application React (PREVIEW_SPA) ou page d'accueil API
    path('', _root_view, name='root'),

    # Healthcheck (supervision / load balancer)
    path('api/health/', health_view, name='api-health'),

    # PWA badge + favicon (évite les 404 dans les logs navigateur)
    path('sw.js', service_worker, name='service-worker'),
    path('favicon.ico', favicon, name='favicon'),

    # Admin
    path('admin/', admin.site.urls),

    # API docs (v1)
    path('api/v1/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/v1/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),

    # API v1 endpoints (monorepo injs-app-ref)
    path('api/v1/', include('config.api_urls_v1')),

    # API v0 (compatibilité) — délégue à api_urls_v1 via préfixe
    # Compatibilité API v0 : plusieurs contrats/tests historiques attendent /api/schema/
    path('api/schema/', SpectacularAPIView.as_view(), name='schema-legacy'),

    path('api/', api_root, name='api-root'),
    path('api/core/', include('core.urls')),
    # CURP U2 — moteur d'habilitation (observation ; routes nouvelles uniquement).
    path('api/habilitations/', include('habilitations.api.urls')),
    path('api/auth/', include('authentication.urls')),
    path('api/formations/', include('formations.urls')),
    path('api/formateurs/list/', formateur_list_api, name='api-formateur-list-alias'),
    path('api/', include('presences.urls')),
    path('api/dashboard/', include('dashboard.api_urls')),
    path('api/exports/', include('exports.urls')),
    path('api/statistiques/', include('statistiques.urls')),
    path('api/evaluations/', include('suiviEvaluation.urls')),
    path('api/scolarite/', include('scolarite.urls')),
    path('api/admissions/', include('admissions.urls')),
    path('api/parametres/', include('parametres.urls')),
    path('api/referentiels/', include('referentiels.urls')),
    path('api/equivalences/', include('equivalences.urls')),
    path('api/juries/', include('jurys.urls')),
    path('api/jurys/', include('jurys.urls')),
    path('api/evaluations-academiques/', include('evaluations.urls')),
    path('api/enseignants/', include('scolarite.charges_urls')),
    path('api/finances-etudiantes/', include('finances_etudiantes.urls')),
    path('api/graduation/', include('graduation.urls')),
    path('api/stages/', include('stages.urls')),
    # Lot L8 — Emploi du temps (GET-INJS). Alias /api/timetable/ exigé par le
    # prompt P11 : mêmes vues, mêmes permissions, deux chemins équivalents.
    path('api/edts/', include('edts.urls')),
    path('api/timetable/', include('edts.urls')),
    # Lot L7 — Administration, RH, Patrimoine
    path('api/administrations/', include('administrations.urls')),
    path('api/rh/', include('ressources_humaines.urls')),
    path('api/patrimoine/', include('patrimoine.urls')),

    # Web dashboard CPFAE
    path('dashboard/', include('dashboard.urls')),

    # QR code images publiques (hors préfixe /api/) — routes minimales uniquement
    path('formations/', include('formations.qr_urls')),
]

# Prévisualisation locale : sert le build React (assets + fallback SPA).
# Placé EN DERNIER pour ne jamais masquer l'API, l'admin ou les médias.
# Le chemin complet (y compris assets/) est passé à la vue, qui sert le
# fichier du build s'il existe, sinon renvoie index.html (routage React).
if getattr(settings, 'PREVIEW_SPA', False):
    urlpatterns += [
        re_path(r'^(?P<path>.*)$', spa, name='preview-spa-fallback'),
    ]
