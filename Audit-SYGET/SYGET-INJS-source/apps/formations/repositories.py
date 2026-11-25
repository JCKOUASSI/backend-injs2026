"""
Repositories de l'app formations.
"""

from typing import Optional

from shared.repositories.base import BaseRepository

from .models import Formateur, Formation, FormationModule, Inscription


class FormationRepository(BaseRepository[Formation]):
    """Accès données pour Formation."""

    def get_by_id(self, pk: int) -> Optional[Formation]:
        """Retourne une Formation par pk ou None."""
        return (
            Formation.objects.select_related("type_formation")
            .prefetch_related("periodes", "modules__module", "modules__periode", "groupes")
            .filter(pk=pk)
            .first()
        )

    def save(self, instance: Formation) -> Formation:
        """Persiste une Formation."""
        instance.save()
        return instance

    def delete(self, pk: int) -> None:
        """
        Supprime une Formation.

        Les modules sont supprimés avant la formation : ``FormationModule.periode``
        est en PROTECT et empêcherait sinon la suppression des périodes en cascade.
        """
        FormationModule.objects.filter(formation_id=pk).delete()
        Formation.objects.filter(pk=pk).delete()

    def list_all(self) -> list[Formation]:
        """Retourne toutes les formations triées."""
        return list(
            Formation.objects.select_related("type_formation", "responsable")
            .prefetch_related("inscriptions", "groupes")
            .order_by("-date_debut", "intitule")
        )

    def list_for_user(self, user) -> list[Formation]:
        """Retourne les formations visibles par l'utilisateur."""
        from shared.formations_scope import queryset_formations

        return list(
            queryset_formations(user).prefetch_related("inscriptions", "groupes").order_by("-date_debut", "intitule")
        )

    def get_for_user(self, user, pk: int) -> Optional[Formation]:
        """Retourne une formation accessible par l'utilisateur ou None."""
        from shared.formations_scope import queryset_formations

        return queryset_formations(user).prefetch_related("modules__module", "groupes").filter(pk=pk).first()

    def list_by_type(self, type_formation_id: int) -> list[Formation]:
        """Retourne les formations d'un type donné."""
        return list(
            Formation.objects.filter(type_formation_id=type_formation_id)
            .select_related("type_formation")
            .order_by("-date_debut")
        )


class FormationModuleRepository(BaseRepository[FormationModule]):
    """Accès données pour FormationModule."""

    def get_by_id(self, pk: int) -> Optional[FormationModule]:
        """Retourne un FormationModule par pk ou None."""
        return FormationModule.objects.filter(pk=pk).first()

    def save(self, instance: FormationModule) -> FormationModule:
        """Persiste un FormationModule."""
        instance.save()
        return instance

    def delete(self, pk: int) -> None:
        """Supprime un FormationModule."""
        FormationModule.objects.filter(pk=pk).delete()

    def list_by_formation(self, formation_id: int) -> list[FormationModule]:
        """Retourne les modules d'une formation."""
        return list(
            FormationModule.objects.filter(formation_id=formation_id).select_related("module").order_by("module__titre")
        )


class InscriptionRepository(BaseRepository[Inscription]):
    """Accès données pour Inscription."""

    def get_by_id(self, pk: int) -> Optional[Inscription]:
        """Retourne une Inscription par pk ou None."""
        return Inscription.objects.filter(pk=pk).first()

    def save(self, instance: Inscription) -> Inscription:
        """Persiste une Inscription."""
        instance.save()
        return instance

    def delete(self, pk: int) -> None:
        """Supprime une Inscription."""
        Inscription.objects.filter(pk=pk).delete()

    def list_by_formation(self, formation_id: int) -> list[Inscription]:
        """Retourne les inscriptions aux modules d'une formation."""
        return list(
            Inscription.objects.filter(formation_id=formation_id)
            .select_related("auditeur", "formation_module__module")
            .order_by("auditeur__nom", "auditeur__prenom")
        )

    def compter_par_formation(self, formation_id: int) -> int:
        """Retourne le nombre d'auditeurs distincts inscrits à une formation."""
        return Inscription.objects.filter(formation_id=formation_id).values("auditeur_id").distinct().count()


class FormateurRepository(BaseRepository[Formateur]):
    """Accès données pour le référentiel Formateur."""

    def save(self, instance: Formateur) -> Formateur:
        instance.save()
        return instance

    def bulk_create(self, formateurs: list[Formateur]) -> list[Formateur]:
        return Formateur.objects.bulk_create(formateurs, ignore_conflicts=True)
