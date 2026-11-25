from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from django.shortcuts import redirect

from config.views import HomeView
from config.api_views import FormationSeancesAPIView, FormationsListAPIView, OpenAPISchemaView, SeanceDetailAPIView

handler404 = "config.views.custom_404"


def root_redirect(request):
    """Redirige vers l'accueil si connecté, sinon vers la connexion."""
    if request.user.is_authenticated:
        return redirect("home")
    return redirect("login")


urlpatterns = [
    path("", root_redirect, name="root"),
    path("accueil/", HomeView.as_view(), name="home"),
    path("admin/", admin.site.urls),
    path("login/", auth_views.LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("parametrage/", include("apps.parametrage.urls")),
    path("referentiels/", include("apps.referentiels.urls")),
    path("formations/", include("apps.formations.urls")),
    path("auditeurs/", include("apps.auditeurs.urls")),
    path("groupes/", include("apps.groupes.urls")),
    path("seances/", include("apps.seances.urls")),
    path("simulation/", include("apps.simulation.urls")),
    path("api/formations/", FormationsListAPIView.as_view(), name="api_formations_list"),
    path(
        "api/formations/<int:pk>/seances/",
        FormationSeancesAPIView.as_view(),
        name="api_formation_seances",
    ),
    path("api/seances/<int:pk>/", SeanceDetailAPIView.as_view(), name="api_seance_detail"),
    path("api/openapi.yaml", OpenAPISchemaView.as_view(), name="api_openapi_schema"),
]
