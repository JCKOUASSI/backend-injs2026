"""Tests unitaires AuditeurService."""

import pytest

from apps.auditeurs.repositories import AuditeurRepository
from apps.auditeurs.services import AuditeurService


@pytest.mark.django_db
def test_creer_deduit_categorie_depuis_grade():
    svc = AuditeurService(AuditeurRepository())
    aud = svc.creer(nom="TEST", prenom="Cat", grade="A3")
    assert aud.categorie == "A"
    assert aud.grade == "A3"


@pytest.mark.django_db
def test_modifier_conserve_categorie_explicite(auditeur):
    svc = AuditeurService(AuditeurRepository())
    updated = svc.modifier(
        pk=auditeur.pk,
        nom=auditeur.nom,
        prenom=auditeur.prenom,
        categorie="B",
        grade="B2",
    )
    assert updated.categorie == "B"
    assert updated.grade == "B2"
