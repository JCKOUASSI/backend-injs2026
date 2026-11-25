"""Import auditeurs depuis Excel : en-têtes SYGEP / français."""

from io import BytesIO

import pandas as pd
import pytest

from apps.auditeurs.repositories import AuditeurRepository
from apps.auditeurs.services import AuditeurService
from apps.formations.models import FormationModule, Inscription


@pytest.fixture
def formation_avec_module(db, formation, module_referentiel):
    """Formation avec un module (grade cible vide = tous les grades)."""
    FormationModule.objects.create(
        formation=formation,
        module=module_referentiel,
        volume_horaire=10,
        grade_cible="",
        date_debut=formation.date_debut,
        date_fin=formation.date_fin,
    )
    return formation


@pytest.mark.django_db
def test_import_en_tetes_sygep_nom_prenom_inscription(formation_avec_module):
    df = pd.DataFrame(
        {
            "N° INSCRIPTION": ["IMP001"],
            "NOM": ["DUPONT"],
            "PRÉNOM(S)": ["Jean"],
            "GENRE": ["M"],
        }
    )
    buf = BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")
    buf.seek(0)

    service = AuditeurService(AuditeurRepository())
    report = service.importer_depuis_excel(buf, formation_id=formation_avec_module.pk)

    assert report.nb_crees == 1
    assert report.nb_inscriptions == 1
    assert not report.erreurs

    assert (
        Inscription.objects.filter(
            formation_id=formation_avec_module.pk,
            auditeur__matricule="IMP001",
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_import_premiere_ligne_titre_puis_entetes(formation_avec_module):
    """Ligne 1 = texte libre, ligne 2 = en-têtes, puis données (pandas header=1)."""
    df = pd.DataFrame(
        [
            ["Export auditeurs", "", "", ""],
            ["N° INSCRIPTION", "NOM", "PRÉNOM(S)", "GENRE"],
            ["IMP002", "MARTIN", "Paul", "M"],
        ]
    )
    buf = BytesIO()
    df.to_excel(buf, index=False, header=False, engine="openpyxl")
    buf.seek(0)

    service = AuditeurService(AuditeurRepository())
    report = service.importer_depuis_excel(buf, formation_id=formation_avec_module.pk)

    assert report.nb_crees == 1
    assert report.nb_inscriptions == 1
    from apps.auditeurs.models import Auditeur

    assert Auditeur.objects.filter(matricule="IMP002").exists()


@pytest.mark.django_db
def test_import_deduit_categorie_depuis_grade(formation_avec_module):
    """Sans colonne catégorie, la lettre est déduite du grade (A3 → A)."""
    from apps.auditeurs.models import Auditeur

    df = pd.DataFrame(
        {
            "N° INSCRIPTION": ["IMP003"],
            "NOM": ["KONE"],
            "PRÉNOM(S)": ["Awa"],
            "GRADE": ["A3"],
        }
    )
    buf = BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")
    buf.seek(0)

    service = AuditeurService(AuditeurRepository())
    report = service.importer_depuis_excel(buf, formation_id=formation_avec_module.pk)

    assert report.nb_crees == 1
    aud = Auditeur.objects.get(matricule="IMP003")
    assert aud.grade == "A3"
    assert aud.categorie == "A"
