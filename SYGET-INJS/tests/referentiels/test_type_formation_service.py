"""
Tests du service de gestion des types de formation.
"""

import pytest

from apps.referentiels.repositories import TypeFormationRepository
from apps.referentiels.services import TypeFormationService


@pytest.mark.django_db
class TestTypeFormationService:
    """Vérifie les règles métier de gestion des types de formation."""

    def _service(self):
        return TypeFormationService(TypeFormationRepository())

    def test_creer_nouveau_type(self):
        """Un nouveau type de formation est correctement créé."""
        tf = self._service().creer(code="CPT", libelle="Formation Comptabilité")
        assert tf.pk is not None
        assert tf.code == "CPT"
        assert tf.libelle == "Formation Comptabilité"

    def test_code_normalise_en_majuscules(self):
        """Le code est automatiquement mis en majuscules."""
        tf = self._service().creer(code="inf", libelle="Informatique")
        assert tf.code == "INF"

    def test_code_duplique_leve_erreur(self):
        """La création avec un code existant lève ValueError."""
        svc = self._service()
        svc.creer(code="DUP", libelle="Dupliqué")
        with pytest.raises(ValueError, match="existe déjà"):
            svc.creer(code="DUP", libelle="Autre")

    def test_modifier_type(self):
        """Un type existant peut être modifié."""
        svc = self._service()
        tf = svc.creer(code="OLD", libelle="Ancien libellé")
        updated = svc.modifier(tf.pk, "NEW", "Nouveau libellé")
        assert updated.code == "NEW"
        assert updated.libelle == "Nouveau libellé"

    def test_modifier_code_existant_autre_type_leve_erreur(self):
        """Modifier vers un code déjà pris par un autre type lève ValueError."""
        svc = self._service()
        svc.creer(code="T1", libelle="Type 1")
        t2 = svc.creer(code="T2", libelle="Type 2")
        with pytest.raises(ValueError, match="déjà utilisé"):
            svc.modifier(t2.pk, "T1", "Collision")

    def test_supprimer_type_non_utilise(self):
        """Un type non utilisé peut être supprimé."""
        svc = self._service()
        tf = svc.creer(code="DEL", libelle="À supprimer")
        svc.supprimer(tf.pk)
        from apps.referentiels.models import TypeFormation

        assert not TypeFormation.objects.filter(pk=tf.pk).exists()

    def test_supprimer_type_utilise_leve_erreur(self, formation, type_formation):
        """Un type lié à une formation ne peut pas être supprimé."""
        with pytest.raises(ValueError, match="utilisé"):
            self._service().supprimer(type_formation.pk)
