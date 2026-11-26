"""
Repositories de l'app referentiels.
Isolation de l'accès ORM pour TypeFormation et Module.
"""

from typing import Optional

from shared.repositories.base import BaseRepository

from .models import Module, TypeFormation


class TypeFormationRepository(BaseRepository[TypeFormation]):
    """Accès données pour TypeFormation."""

    def get_by_id(self, pk: int) -> Optional[TypeFormation]:
        """Retourne un TypeFormation par pk ou None."""
        return TypeFormation.objects.filter(pk=pk).first()

    def get_by_code(self, code: str) -> Optional[TypeFormation]:
        """Retourne un TypeFormation par code ou None."""
        return TypeFormation.objects.filter(code=code).first()

    def save(self, instance: TypeFormation) -> TypeFormation:
        """Persiste un TypeFormation."""
        instance.save()
        return instance

    def delete(self, pk: int) -> None:
        """Supprime un TypeFormation."""
        TypeFormation.objects.filter(pk=pk).delete()

    def list_all(self) -> list[TypeFormation]:
        """Retourne tous les types de formation triés par code."""
        return list(TypeFormation.objects.all().order_by("code"))


class ModuleRepository(BaseRepository[Module]):
    """Accès données pour Module."""

    def get_by_id(self, pk: int) -> Optional[Module]:
        """Retourne un Module par pk ou None."""
        return Module.objects.filter(pk=pk).first()

    def save(self, instance: Module) -> Module:
        """Persiste un Module."""
        instance.save()
        return instance

    def delete(self, pk: int) -> None:
        """Supprime un Module."""
        Module.objects.filter(pk=pk).delete()

    def list_all(self) -> list[Module]:
        """Retourne tous les modules triés par titre."""
        return list(Module.objects.all().order_by("titre"))

    def list_actifs(self) -> list[Module]:
        """Retourne tous les modules actifs triés par titre."""
        return list(Module.objects.filter(actif=True).order_by("titre"))

    def list_all_with_associations(self):
        """
        Retourne tous les modules avec leurs associations de type prefetchées.
        Utilisé par la page paramétrage pour afficher les volumes horaires par type.
        """
        return Module.objects.prefetch_related("type_associations__type_formation").all().order_by("titre")
