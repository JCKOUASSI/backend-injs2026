"""
Commande de gestion : auth_db
Crée un superutilisateur de développement si absent.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    """Crée un superutilisateur par défaut pour le développement."""

    help = "Crée un superutilisateur admin/admin si inexistant"

    def handle(self, *args, **options) -> None:
        """Point d'entrée de la commande."""
        User = get_user_model()
        if not User.objects.filter(username="admin").exists():
            User.objects.create_superuser("admin", "admin@example.com", "admin")
            self.stdout.write(self.style.SUCCESS("Superutilisateur 'admin' créé."))
        else:
            self.stdout.write("Superutilisateur 'admin' déjà présent.")
