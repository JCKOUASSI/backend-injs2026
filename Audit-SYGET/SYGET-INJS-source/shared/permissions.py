"""
Mixins d'autorisation partagés entre les apps.

Toutes les vues métier doivent hériter de `RoleProtectedMixin` (ou d'un de ses
descendants) afin de combiner contrôle de session et contrôle de permissions.
Le superutilisateur Django dispose nativement de toutes les permissions.
"""

from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib.auth.views import redirect_to_login


class RoleProtectedMixin(LoginRequiredMixin, PermissionRequiredMixin):
    """Login obligatoire + 403 si permission(s) manquante(s).

    Comportement :
    - utilisateur anonyme  -> redirection vers la page de login (302).
    - utilisateur connecté sans permission -> 403.

    Les vues filles doivent définir `permission_required` (chaîne ou tuple)
    selon la convention Django (`app_label.codename`).
    """

    raise_exception = True

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return redirect_to_login(
                self.request.get_full_path(),
                self.get_login_url(),
                self.get_redirect_field_name(),
            )
        return super().handle_no_permission()
