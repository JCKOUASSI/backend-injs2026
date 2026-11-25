"""
Repositories de l'app parametrage.
Isolation de l'accès ORM pour Grade, Vague et ParametreGeneral.
"""

from typing import Optional

from shared.repositories.base import BaseRepository

from .models import Grade, ParametreFormation, ParametreGeneral, Vague


class GradeRepository(BaseRepository[Grade]):
    """Accès données pour Grade."""

    def get_by_id(self, pk: int) -> Optional[Grade]:
        """Retourne un Grade par pk ou None."""
        return Grade.objects.filter(pk=pk).first()

    def save(self, instance: Grade) -> Grade:
        """Persiste un Grade."""
        instance.save()
        return instance

    def delete(self, pk: int) -> None:
        """Supprime un Grade."""
        Grade.objects.filter(pk=pk).delete()

    def list_actifs(self):
        """Retourne les grades actifs triés."""
        return Grade.objects.filter(actif=True).order_by("ordre", "libelle")

    def list_all(self):
        """Retourne tous les grades triés."""
        return Grade.objects.all().order_by("ordre", "libelle")

    def bulk_update_ordre(self, grades: list[Grade]) -> None:
        """Met à jour l'ordre de plusieurs grades en une requête."""
        Grade.objects.bulk_update(grades, ["ordre"])


class VagueRepository(BaseRepository[Vague]):
    """Accès données pour Vague."""

    def get_by_id(self, pk: int) -> Optional[Vague]:
        """Retourne une Vague par pk ou None."""
        return Vague.objects.filter(pk=pk).first()

    def save(self, instance: Vague) -> Vague:
        """Persiste une Vague."""
        instance.save()
        return instance

    def delete(self, pk: int) -> None:
        """Supprime une Vague."""
        Vague.objects.filter(pk=pk).delete()

    def list_actifs(self):
        """Retourne les vagues actives triées."""
        return Vague.objects.filter(actif=True).order_by("libelle")

    def list_all(self):
        """Retourne toutes les vagues triées."""
        return Vague.objects.all().order_by("libelle")


class ParametreFormationRepository:
    """Accès données pour ParametreFormation (un enregistrement par formation)."""

    def get_for_formation(self, formation_id: int) -> ParametreFormation:
        """Retourne les paramètres de la formation, créés depuis le modèle global si besoin."""
        return ParametreFormation.get_for_formation(formation_id)

    def save(self, instance: ParametreFormation) -> ParametreFormation:
        """Persiste les paramètres d'une formation."""
        instance.save()
        return instance


class ParametreGeneralRepository:
    """Accès données pour ParametreGeneral (singleton)."""

    def get(self) -> ParametreGeneral:
        """Retourne l'instance singleton des paramètres généraux."""
        return ParametreGeneral.get()

    def save(self, instance: ParametreGeneral) -> ParametreGeneral:
        """Persiste les paramètres généraux."""
        instance.save()
        return instance
