"""
Repositories de l'app seances.
"""

from typing import Optional

from shared.repositories.base import BaseRepository

from .models import Seance


class SeanceRepository(BaseRepository[Seance]):
    """Accès données pour Seance."""

    def get_by_id(self, pk: int) -> Optional[Seance]:
        """Retourne une Seance par pk ou None."""
        return Seance.objects.filter(pk=pk).first()

    def save(self, instance: Seance) -> Seance:
        """Persiste une Seance."""
        instance.save()
        return instance

    def delete(self, pk: int) -> None:
        """Supprime une Seance."""
        Seance.objects.filter(pk=pk).delete()

    def list_by_groupe(self, groupe_id: int) -> list[Seance]:
        """Retourne les séances d'un groupe triées par date."""
        return list(
            Seance.objects.filter(groupe_id=groupe_id)
            .select_related("module", "groupe__formation")
            .order_by("date", "heure_debut", "heure_fin", "pk")
        )

    def list_by_formation(self, formation_id: int) -> list[Seance]:
        """Retourne les séances de tous les groupes d'une formation."""
        return list(
            Seance.objects.filter(groupe__formation_id=formation_id)
            .select_related("module", "groupe__formation")
            .order_by("groupe__nom", "date", "heure_debut", "heure_fin", "pk")
        )

    def supprimer_pour_groupe(self, groupe_id: int) -> None:
        """Supprime toutes les séances d'un groupe."""
        Seance.objects.filter(groupe_id=groupe_id).delete()

    def bulk_create(self, seances: list[Seance]) -> list[Seance]:
        """Crée plusieurs séances en une requête."""
        return Seance.objects.bulk_create(seances)
