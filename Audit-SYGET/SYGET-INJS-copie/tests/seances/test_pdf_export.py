"""
Tests de l'export PDF de synthèse du planning (groupe + formation).

On valide :
- Que le service produit un fichier PDF non vide (signature ``%PDF``).
- Que la vue HTTP par groupe renvoie bien un attachment PDF avec le nom du groupe.
- Que la vue HTTP par formation regroupe tous les groupes en un seul fichier.
- Que le journal d'audit enregistre l'export en mode ``EXPORT`` / scope adéquat.
"""

import datetime

import pytest
from django.test import Client
from django.urls import reverse

from apps.auditeurs.models import Auditeur
from apps.formations.models import FormationModule
from apps.groupes.models import Groupe, GroupeAuditeur
from apps.referentiels.models import Module
from apps.seances.models import PlanningAuditLog, Seance
from apps.seances.pdf_export import ExportPlanningPDFService


@pytest.fixture
def logged_client(db):
    """Client Django authentifié superuser (raccourci d'accès aux vues protégées)."""
    from django.contrib.auth.models import User

    User.objects.create_superuser("pdfuser", "pdf@example.com", "testpass123")
    client = Client()
    client.login(username="pdfuser", password="testpass123")
    return client


@pytest.fixture
def groupe_avec_seances(formation, specialite_generale):
    """Crée un groupe + des séances minimales pour valider le rendu PDF."""
    module = Module.objects.create(titre="Module PDF", specialite=specialite_generale)
    FormationModule.objects.create(
        formation=formation,
        module=module,
        volume_horaire=8,
        date_debut=formation.date_debut,
        date_fin=formation.date_fin,
        site_nom="SITE-A",
        batiment_nom="BAT-A",
        salle_nom="SALLE-A",
    )
    auditeur = Auditeur.objects.create(
        matricule="A4PDF001",
        nom="DUPONT",
        prenom="Jean",
        grade="A4",
    )
    groupe = Groupe.objects.create(formation=formation, nom="A4_GROUPE1", max_auditeurs=25)
    GroupeAuditeur.objects.create(groupe=groupe, auditeur=auditeur)
    Seance.objects.create(
        groupe=groupe,
        module=module,
        date=datetime.date(2025, 1, 6),
        heure_debut=datetime.time(8, 0),
        heure_fin=datetime.time(12, 0),
        duree_minutes=240,
        salle_nom="SALLE-A",
        site_nom="SITE-A",
        batiment_nom="BAT-A",
        formateur_nom="MARTIN",
        formateur_prenom="Paul",
    )
    Seance.objects.create(
        groupe=groupe,
        module=module,
        date=datetime.date(2025, 1, 6),
        heure_debut=datetime.time(13, 0),
        heure_fin=datetime.time(17, 0),
        duree_minutes=240,
        salle_nom="SALLE-A",
        formateur_nom="MARTIN",
        formateur_prenom="Paul",
    )
    return groupe


@pytest.mark.django_db
class TestExportPlanningPDFService:
    """Tests directs du service de génération PDF (sans HTTP)."""

    def test_pdf_par_groupe_genere_un_pdf_valide(self, groupe_avec_seances):
        """Le PDF doit commencer par la signature ``%PDF`` et contenir plusieurs Ko."""
        contenu = ExportPlanningPDFService().exporter_groupe(groupe_avec_seances.pk)
        assert isinstance(contenu, bytes)
        assert contenu.startswith(b"%PDF")
        # Heuristique : un PDF avec un en-tête + un tableau pèse au moins 1 Ko.
        assert len(contenu) > 1500

    def test_pdf_par_groupe_supporte_zero_seance(self, formation):
        """Aucun groupe avec séance : on génère quand même un PDF (message « aucune »)."""
        groupe = Groupe.objects.create(formation=formation, nom="GROUPE VIDE", max_auditeurs=10)
        contenu = ExportPlanningPDFService().exporter_groupe(groupe.pk)
        assert contenu.startswith(b"%PDF")

    def test_pdf_par_groupe_deux_modules(self, formation, specialite_generale, groupe_avec_seances):
        """Deux modules de formation : le PDF est plus volumineux (sections distinctes)."""
        module2 = Module.objects.create(titre="Module PDF 2", specialite=specialite_generale)
        FormationModule.objects.create(
            formation=formation,
            module=module2,
            volume_horaire=4,
            date_debut=formation.date_debut,
            date_fin=formation.date_fin,
        )
        groupe = groupe_avec_seances
        contenu_un_module = ExportPlanningPDFService().exporter_groupe(groupe.pk)
        Seance.objects.create(
            groupe=groupe,
            module=module2,
            date=datetime.date(2025, 1, 7),
            heure_debut=datetime.time(8, 0),
            heure_fin=datetime.time(12, 0),
            duree_minutes=240,
            salle_nom="SALLE-B",
            formateur_nom="DURAND",
            formateur_prenom="Anne",
        )
        contenu_deux_modules = ExportPlanningPDFService().exporter_groupe(groupe.pk)
        assert contenu_deux_modules.startswith(b"%PDF")
        assert len(contenu_deux_modules) > len(contenu_un_module)

    def test_pdf_par_formation_couvre_tous_les_groupes(self, formation, specialite_generale, groupe_avec_seances):
        """Un second groupe vide n'empêche pas la génération multi-groupe."""
        Groupe.objects.create(formation=formation, nom="GROUPE PDF 2", max_auditeurs=10)
        contenu = ExportPlanningPDFService().exporter_formation(formation.pk)
        assert contenu.startswith(b"%PDF")
        # Le rendu doit être plus volumineux que le PDF mono-groupe (deux sections).
        contenu_mono = ExportPlanningPDFService().exporter_groupe(groupe_avec_seances.pk)
        assert len(contenu) > len(contenu_mono)

    def test_pdf_zip_formation_un_fichier_par_groupe(self, formation, groupe_avec_seances):
        """L'archive ZIP contient un PDF nommé par groupe."""
        import zipfile
        from io import BytesIO

        Groupe.objects.create(formation=formation, nom="A4_GROUPE2", max_auditeurs=10)
        contenu = ExportPlanningPDFService().exporter_formation_zip(formation.pk)
        assert contenu[:2] == b"PK"
        with zipfile.ZipFile(BytesIO(contenu)) as archive:
            noms = sorted(archive.namelist())
            assert noms == ["A4_EMP_GROUPE1.pdf", "A4_EMP_GROUPE2.pdf"]
            for nom in noms:
                assert archive.read(nom).startswith(b"%PDF")


@pytest.mark.django_db
class TestSeancePDFExportViews:
    """Tests des vues HTTP exposant le téléchargement PDF."""

    def test_export_pdf_groupe_retourne_pdf_attachment(self, logged_client, groupe_avec_seances):
        """La vue par groupe renvoie un PDF en attachment avec le nom du groupe."""
        url = reverse("seances:export_pdf", kwargs={"groupe_pk": groupe_avec_seances.pk})
        resp = logged_client.get(url)
        assert resp.status_code == 200
        assert resp["Content-Type"] == "application/pdf"
        assert "attachment" in resp["Content-Disposition"].lower()
        assert "A4_EMP_GROUPE1" in resp["Content-Disposition"]
        assert resp.content.startswith(b"%PDF")
        # L'audit doit enregistrer l'export PDF (scope = groupe).
        log = PlanningAuditLog.objects.filter(action=PlanningAuditLog.Action.EXPORT).last()
        assert log is not None
        assert log.details.get("format_export") == "pdf"
        assert log.details.get("scope") == "groupe"
        assert log.groupe_id == groupe_avec_seances.pk

    def test_export_pdf_formation_retourne_pdf_attachment(self, logged_client, formation, groupe_avec_seances):
        """La vue par formation renvoie un PDF unique pour tous les groupes."""
        url = reverse("seances:formation_export_pdf", kwargs={"formation_pk": formation.pk})
        resp = logged_client.get(url)
        assert resp.status_code == 200
        assert resp["Content-Type"] == "application/pdf"
        assert resp.content.startswith(b"%PDF")
        log = PlanningAuditLog.objects.filter(action=PlanningAuditLog.Action.EXPORT).last()
        assert log is not None
        assert log.details.get("format_export") == "pdf"
        assert log.details.get("scope") == "formation"
        assert log.details.get("formation_id") == formation.pk

    def test_export_pdf_zip_formation_retourne_archive(self, logged_client, formation, groupe_avec_seances):
        """La vue ZIP renvoie une archive avec un PDF par groupe."""
        import zipfile
        from io import BytesIO

        url = reverse("seances:formation_export_pdf_zip", kwargs={"formation_pk": formation.pk})
        resp = logged_client.get(url)
        assert resp.status_code == 200
        assert resp["Content-Type"] == "application/zip"
        assert "attachment" in resp["Content-Disposition"].lower()
        assert resp.content[:2] == b"PK"
        with zipfile.ZipFile(BytesIO(resp.content)) as archive:
            assert "A4_EMP_GROUPE1.pdf" in archive.namelist()
        log = PlanningAuditLog.objects.filter(action=PlanningAuditLog.Action.EXPORT).last()
        assert log.details.get("scope") == "formation_zip"
