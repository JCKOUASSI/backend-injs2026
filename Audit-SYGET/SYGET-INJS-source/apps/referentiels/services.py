"""
Services de l'app referentiels.
Logique métier pour TypeFormation et Module.
"""

from dataclasses import dataclass
from typing import Optional

from django.db import transaction

from .models import Module, Specialite, TypeFormation
from .repositories import ModuleRepository, TypeFormationRepository


@dataclass
class ModuleResult:
    """Résultat d'une opération get_or_create sur Module."""

    module: Module
    created: bool


class TypeFormationService:
    """Logique métier pour la gestion des types de formation."""

    def __init__(self, repo: TypeFormationRepository) -> None:
        self._repo = repo

    def get_all(self) -> list[TypeFormation]:
        """Retourne tous les types de formation."""
        return self._repo.list_all()

    @transaction.atomic
    def creer(self, code: str, libelle: str) -> TypeFormation:
        """
        Crée un type de formation.
        Lève ValueError si le code existe déjà.
        """
        code = code.strip().upper()
        if TypeFormation.objects.filter(code=code).exists():
            raise ValueError(f"Le type de formation '{code}' existe déjà.")
        return self._repo.save(TypeFormation(code=code, libelle=libelle.strip()))

    @transaction.atomic
    def modifier(self, pk: int, code: str, libelle: str) -> TypeFormation:
        """
        Modifie un type de formation existant.
        Lève ValueError si le code est déjà utilisé par un autre enregistrement.
        """
        tf = self._repo.get_by_id(pk)
        if tf is None:
            raise ValueError(f"Type de formation {pk} introuvable.")
        code = code.strip().upper()
        if TypeFormation.objects.filter(code=code).exclude(pk=pk).exists():
            raise ValueError(f"Le code '{code}' est déjà utilisé.")
        tf.code = code
        tf.libelle = libelle.strip()
        return self._repo.save(tf)

    @transaction.atomic
    def supprimer(self, pk: int) -> None:
        """
        Supprime un type de formation.
        Lève ValueError si des formations l'utilisent.
        """
        from apps.formations.models import Formation

        if Formation.objects.filter(type_formation_id=pk).exists():
            raise ValueError("Ce type est utilisé par des formations existantes.")
        self._repo.delete(pk)


class ModuleService:
    """Logique métier pour la gestion des modules."""

    def __init__(self, repo: ModuleRepository) -> None:
        self._repo = repo

    @staticmethod
    def specialite_par_defaut() -> Specialite:
        """Spécialité utilisée si aucune n’est fournie à la création."""
        specialite, _ = Specialite.objects.get_or_create(
            code="GENERAL",
            defaults={"libelle": "Général / non classé"},
        )
        return specialite

    def get_all(self) -> list[Module]:
        """Retourne tous les modules."""
        return self._repo.list_all()

    def get_or_create(self, titre: str, specialite: Optional[Specialite] = None) -> ModuleResult:
        """
        Retourne le module correspondant au titre (insensible à la casse),
        ou le crée s'il n'existe pas (avec la spécialité indiquée ou GENERAL).
        """
        titre = titre.strip()
        existing = Module.objects.filter(titre__iexact=titre).first()
        if existing:
            return ModuleResult(module=existing, created=False)
        spec = specialite or self.specialite_par_defaut()
        module = self._repo.save(Module(titre=titre, specialite=spec))
        return ModuleResult(module=module, created=True)

    @transaction.atomic
    def modifier(self, pk: int, titre: str, actif: bool = True, specialite: Optional[Specialite] = None) -> Module:
        """Modifie un module du référentiel."""
        module = self._repo.get_by_id(pk)
        if module is None:
            raise ValueError(f"Module {pk} introuvable.")
        titre = (titre or "").strip()
        if not titre:
            raise ValueError("Le titre du module est obligatoire.")
        if Module.objects.filter(titre__iexact=titre).exclude(pk=pk).exists():
            raise ValueError(f"Le module '{titre}' existe déjà.")
        module.titre = titre
        module.actif = bool(actif)
        if specialite is not None:
            module.specialite = specialite
        return self._repo.save(module)

    @transaction.atomic
    def supprimer(self, pk: int) -> None:
        """
        Supprime un module du référentiel.
        Lève ValueError si des formations l'utilisent.
        """
        from apps.formations.models import FormationModule

        if FormationModule.objects.filter(module_id=pk).exists():
            raise ValueError("Ce module est utilisé dans des formations existantes.")
        self._repo.delete(pk)
