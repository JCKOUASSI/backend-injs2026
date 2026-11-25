"""
Repositories de l'app groupes.
"""

from typing import Optional

from shared.repositories.base import BaseRepository
from shared.utils.groupes import cle_tri_groupes

from .models import ConfigGroupe, Groupe, JourCours


class GroupeRepository(BaseRepository[Groupe]):
    """Accès données pour Groupe."""

    def get_by_id(self, pk: int) -> Optional[Groupe]:
        """Retourne un Groupe par pk ou None."""
        return (
            Groupe.objects.select_related("formation", "config")
            .prefetch_related("membres__auditeur", "jours_cours")
            .filter(pk=pk)
            .first()
        )

    def save(self, instance: Groupe) -> Groupe:
        """Persiste un Groupe."""
        instance.save()
        return instance

    def delete(self, pk: int) -> None:
        """Supprime un Groupe."""
        Groupe.objects.filter(pk=pk).delete()

    def list_by_formation(self, formation_id: int) -> list[Groupe]:
        """Retourne les groupes d'une formation (tri : 1, 2, 3… puis préfixe grade)."""
        groupes = list(
            Groupe.objects.filter(formation_id=formation_id)
            .select_related("config")
            .prefetch_related("membres__auditeur", "jours_cours")
        )
        groupes.sort(key=lambda g: cle_tri_groupes(g.nom or ""))
        return groupes


class ConfigGroupeRepository(BaseRepository[ConfigGroupe]):
    """Accès données pour ConfigGroupe."""

    def get_by_groupe(self, groupe_id: int) -> Optional[ConfigGroupe]:
        """Retourne la config d'un groupe ou None."""
        return ConfigGroupe.objects.filter(groupe_id=groupe_id).first()

    def get_by_id(self, pk: int) -> Optional[ConfigGroupe]:
        """Retourne une ConfigGroupe par pk ou None."""
        return ConfigGroupe.objects.filter(pk=pk).first()

    def save(self, instance: ConfigGroupe) -> ConfigGroupe:
        """Persiste une ConfigGroupe."""
        instance.save()
        return instance

    def delete(self, pk: int) -> None:
        """Supprime une ConfigGroupe."""
        ConfigGroupe.objects.filter(pk=pk).delete()


class JourCoursRepository(BaseRepository[JourCours]):
    """Accès données pour JourCours."""

    def get_by_id(self, pk: int) -> Optional[JourCours]:
        """Retourne un JourCours par pk ou None."""
        return JourCours.objects.filter(pk=pk).first()

    def save(self, instance: JourCours) -> JourCours:
        """Persiste un JourCours."""
        instance.save()
        return instance

    def delete(self, pk: int) -> None:
        """Supprime un JourCours."""
        JourCours.objects.filter(pk=pk).delete()

    def list_by_groupe(self, groupe_id: int) -> list[JourCours]:
        """Retourne les jours de cours d'un groupe."""
        return list(JourCours.objects.filter(groupe_id=groupe_id).order_by("jour"))

    def remplacer_pour_groupe(self, groupe_id: int, jours: list[int]) -> None:
        """Remplace tous les jours de cours d'un groupe."""
        JourCours.objects.filter(groupe_id=groupe_id).delete()
        JourCours.objects.bulk_create([JourCours(groupe_id=groupe_id, jour=j) for j in jours])
