"""
Repository de base générique.
Toutes les repositories concrètes en héritent pour bénéficier du typage générique.
"""

from __future__ import annotations

from typing import Generic, Optional, TypeVar

T = TypeVar("T")


class BaseRepository(Generic[T]):
    """
    Classe de base pour tous les repositories.
    Définit le contrat minimal : get_by_id, save, delete.
    Les sous-classes spécialisées ajoutent les méthodes propres à leur domaine.
    """

    def get_by_id(self, pk: int) -> Optional[T]:
        """Retourne l'instance par clé primaire ou None."""
        raise NotImplementedError

    def save(self, instance: T) -> T:
        """Persiste l'instance et la retourne."""
        raise NotImplementedError

    def delete(self, pk: int) -> None:
        """Supprime l'instance identifiée par pk."""
        raise NotImplementedError
