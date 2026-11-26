import pytest

from apps.referentiels.repositories import ModuleRepository
from apps.referentiels.services import ModuleService


@pytest.mark.django_db
class TestModuleService:
    """Tests du service de gestion des modules."""

    def test_get_or_create_nouveau_module(self):
        """Un nouveau module est créé si le titre n'existe pas."""
        service = ModuleService(ModuleRepository())
        result = service.get_or_create("Droit public")
        assert result.created is True
        assert result.module.titre == "Droit public"

    def test_get_or_create_existant(self):
        """Le service retourne le module existant sans doublon."""
        service = ModuleService(ModuleRepository())
        service.get_or_create("Informatique")
        result = service.get_or_create("Informatique")
        assert result.created is False

    def test_get_or_create_insensible_casse(self):
        """La recherche est insensible à la casse."""
        service = ModuleService(ModuleRepository())
        service.get_or_create("Management")
        result = service.get_or_create("MANAGEMENT")
        assert result.created is False

    def test_modifier_module(self):
        """Un module existant peut être renommé."""
        service = ModuleService(ModuleRepository())
        created = service.get_or_create("Module Ancien").module
        updated = service.modifier(created.pk, "Module Nouveau")
        assert updated.titre == "Module Nouveau"

    def test_supprimer_module(self):
        """Un module non utilisé peut être supprimé."""
        service = ModuleService(ModuleRepository())
        module = service.get_or_create("Module Temporaire").module
        service.supprimer(module.pk)
