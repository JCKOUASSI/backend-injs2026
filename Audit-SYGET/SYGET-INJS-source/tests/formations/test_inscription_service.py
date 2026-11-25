"""
Tests du service d'inscription des auditeurs aux formations.
"""

import pytest

from apps.formations.models import FormationModule
from apps.formations.repositories import FormationRepository, InscriptionRepository
from apps.formations.services import InscriptionService


@pytest.mark.django_db
class TestInscriptionService:
    """Vérifie les règles métier de gestion des inscriptions."""

    def _service(self):
        return InscriptionService(InscriptionRepository(), FormationRepository())

    def _module_formation(self, formation, module_referentiel):
        return FormationModule.objects.create(
            formation=formation,
            module=module_referentiel,
            volume_horaire=20,
        )

    def test_inscrire_auditeur(self, formation, auditeur, module_referentiel):
        """Un auditeur peut s'inscrire à un module de formation."""
        fm = self._module_formation(formation, module_referentiel)
        inscription = self._service().inscrire(fm.pk, auditeur.pk)
        assert inscription.pk is not None
        assert inscription.formation == formation
        assert inscription.formation_module == fm
        assert inscription.auditeur == auditeur

    def test_double_inscription_meme_module_leve_erreur(self, formation, auditeur, module_referentiel):
        """Une double inscription sur le même module lève ValueError."""
        fm = self._module_formation(formation, module_referentiel)
        svc = self._service()
        svc.inscrire(fm.pk, auditeur.pk)
        with pytest.raises(ValueError, match="déjà inscrit"):
            svc.inscrire(fm.pk, auditeur.pk)

    def test_desinscrire_auditeur(self, formation, auditeur, module_referentiel):
        """Un auditeur peut être désinscrit."""
        fm = self._module_formation(formation, module_referentiel)
        svc = self._service()
        svc.inscrire(fm.pk, auditeur.pk)
        assert formation.inscriptions.count() == 1
        svc.desinscrire(fm.pk, auditeur.pk)
        assert formation.inscriptions.count() == 0

    def test_nb_inscrits_propriete_formation(self, formation, auditeur, auditeur2, module_referentiel):
        """La propriété nb_inscrits compte les auditeurs distincts sur les modules."""
        fm = self._module_formation(formation, module_referentiel)
        svc = self._service()
        assert formation.nb_inscrits == 0
        svc.inscrire(fm.pk, auditeur.pk)
        svc.inscrire(fm.pk, auditeur2.pk)
        formation.refresh_from_db()
        assert formation.nb_inscrits == 2
