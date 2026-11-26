"""Tests GroupeService.retirer_auditeur."""

import pytest

from apps.groupes.models import GroupeAuditeur
from apps.groupes.repositories import ConfigGroupeRepository, GroupeRepository, JourCoursRepository
from apps.groupes.services import GroupeService


@pytest.mark.django_db
def test_retirer_auditeur(formation, auditeur, parametres):
    svc = GroupeService(GroupeRepository(), ConfigGroupeRepository(), JourCoursRepository())
    groupe = svc.creer(formation_id=formation.pk, nom="G-RET", max_auditeurs=25)
    svc.ajouter_auditeur(groupe.pk, auditeur.pk)
    svc.retirer_auditeur(groupe.pk, auditeur.pk)
    assert not GroupeAuditeur.objects.filter(groupe=groupe, auditeur=auditeur).exists()


@pytest.mark.django_db
def test_retirer_auditeur_inexistant_leve_erreur(formation, auditeur, parametres):
    svc = GroupeService(GroupeRepository(), ConfigGroupeRepository(), JourCoursRepository())
    groupe = svc.creer(formation_id=formation.pk, nom="G-RET2", max_auditeurs=25)
    with pytest.raises(ValueError, match="n'est pas membre"):
        svc.retirer_auditeur(groupe.pk, auditeur.pk)
