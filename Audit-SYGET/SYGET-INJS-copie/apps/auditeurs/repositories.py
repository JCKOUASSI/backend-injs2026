"""
Repositories de l'app auditeurs.
"""

from typing import Optional

from django.db.models import Q

from shared.repositories.base import BaseRepository

from .models import Auditeur


class AuditeurRepository(BaseRepository[Auditeur]):
    """Accès données pour Auditeur."""

    PAGE_SIZE = 50

    def get_by_id(self, pk: int) -> Optional[Auditeur]:
        """Retourne un Auditeur par pk ou None."""
        return Auditeur.objects.filter(pk=pk).first()

    def get_by_matricule(self, matricule: str) -> Optional[Auditeur]:
        """Retourne un Auditeur par matricule ou None."""
        return Auditeur.objects.filter(matricule=matricule).first()

    def save(self, instance: Auditeur) -> Auditeur:
        """Persiste un Auditeur."""
        instance.save()
        return instance

    def delete(self, pk: int) -> None:
        """Supprime un Auditeur."""
        Auditeur.objects.filter(pk=pk).delete()

    def search_queryset(self, query: str = ""):
        """QuerySet filtré et trié (pagination côté vue)."""
        qs = Auditeur.objects.all().order_by("nom", "prenom")
        q = (query or "").strip()
        if not q:
            return qs
        return qs.filter(
            Q(nom__icontains=q)
            | Q(prenom__icontains=q)
            | Q(matricule__icontains=q)
            | Q(libelle_concours__icontains=q)
            | Q(categorie__icontains=q)
            | Q(grade__icontains=q)
        )

    def list_all(self) -> list[Auditeur]:
        """Retourne tous les auditeurs triés."""
        return list(self.search_queryset())

    def bulk_create(self, auditeurs: list[Auditeur]) -> list[Auditeur]:
        """Crée plusieurs auditeurs en une requête."""
        return Auditeur.objects.bulk_create(auditeurs, ignore_conflicts=True)
