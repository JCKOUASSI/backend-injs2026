"""
Tests du service de gestion des groupes.
"""

import pytest

from apps.groupes.repositories import ConfigGroupeRepository, GroupeRepository, JourCoursRepository
from apps.groupes.services import GroupeService


@pytest.mark.django_db
class TestGroupeService:
    """Vérifie les règles métier de gestion des groupes."""

    def _service(self):
        return GroupeService(
            repo=GroupeRepository(),
            config_repo=ConfigGroupeRepository(),
            jours_repo=JourCoursRepository(),
        )

    def test_creer_groupe(self, formation, parametres):
        """Un groupe est créé et sa configuration initialisée."""
        groupe = self._service().creer(
            formation_id=formation.pk,
            nom="Groupe A",
            max_auditeurs=20,
        )
        assert groupe.pk is not None
        assert groupe.nom == "Groupe A"
        assert groupe.max_auditeurs == 20
        assert hasattr(groupe, "config")

    def test_nom_duplique_leve_erreur(self, formation, parametres):
        """Deux groupes portant le même nom dans la même formation levent ValueError."""
        svc = self._service()
        svc.creer(formation_id=formation.pk, nom="Groupe B")
        with pytest.raises(ValueError, match="existe déjà"):
            svc.creer(formation_id=formation.pk, nom="Groupe B")

    def test_ajouter_auditeur(self, formation, auditeur, parametres):
        """Un auditeur peut être ajouté à un groupe."""
        groupe = self._service().creer(formation_id=formation.pk, nom="Groupe C")
        ga = self._service().ajouter_auditeur(groupe.pk, auditeur.pk)
        assert ga.pk is not None
        assert ga.auditeur == auditeur

    def test_double_ajout_auditeur_leve_erreur(self, formation, auditeur, parametres):
        """Ajouter le même auditeur deux fois lève ValueError."""
        svc = self._service()
        groupe = svc.creer(formation_id=formation.pk, nom="Groupe D")
        svc.ajouter_auditeur(groupe.pk, auditeur.pk)
        with pytest.raises(ValueError, match="déjà dans ce groupe"):
            svc.ajouter_auditeur(groupe.pk, auditeur.pk)

    def test_capacite_max_leve_erreur(self, formation, auditeur, auditeur2, parametres):
        """Ajouter un auditeur à un groupe plein lève ValueError."""
        svc = self._service()
        groupe = svc.creer(formation_id=formation.pk, nom="Groupe E", max_auditeurs=1)
        svc.ajouter_auditeur(groupe.pk, auditeur.pk)
        with pytest.raises(ValueError, match="capacité maximale"):
            svc.ajouter_auditeur(groupe.pk, auditeur2.pk)

    def test_nb_auditeurs_propriete(self, formation, auditeur, auditeur2, parametres):
        """La propriété nb_auditeurs reflète les membres réels."""
        svc = self._service()
        groupe = svc.creer(formation_id=formation.pk, nom="Groupe F")
        assert groupe.nb_auditeurs == 0
        svc.ajouter_auditeur(groupe.pk, auditeur.pk)
        svc.ajouter_auditeur(groupe.pk, auditeur2.pk)
        groupe.refresh_from_db()
        assert groupe.nb_auditeurs == 2
