"""Tests smoke du lot L7 — Administration générale.

Couverture : workflow courrier, versionnement document, transitions réunion
et mission, garde de dates inversées.
"""
import datetime as dt

from django.core.exceptions import ValidationError
from django.test import TestCase

from administrations import services
from administrations.models import Courrier, DocumentOfficiel, Mission, ReunionCommission
from administrations.services import (
    transitionner_courrier, transitionner_document, transitionner_mission,
    transitionner_reunion, valider_document,
)


class TestCourrier(TestCase):
    def test_creation_courrier(self):
        c = Courrier.objects.create(
            sens=Courrier.Sens.ENTRANT, reference='REF-001', objet='Demande de stage',
            expediteur='Entreprise X',
        )
        self.assertEqual(c.statut, Courrier.Statut.RECU)
        self.assertEqual(str(c), 'ENTRANT REF-001 – Demande de stage')

    def test_transition_courrier_valide(self):
        c = Courrier.objects.create(reference='REF-002', objet='Note')
        transitionner_courrier(c, Courrier.Statut.EN_COURS)
        c.refresh_from_db()
        self.assertEqual(c.statut, Courrier.Statut.EN_COURS)

    def test_transition_courrier_invalide(self):
        c = Courrier.objects.create(reference='REF-003', objet='Note')
        with self.assertRaises(ValueError):
            transitionner_courrier(c, Courrier.Statut.ARCHIVE)  # saut interdit


class TestDocument(TestCase):
    def test_creation_document(self):
        d = DocumentOfficiel.objects.create(
            type_document=DocumentOfficiel.Type.NOTE_SERVICE, titre='Note N°1',
        )
        self.assertEqual(d.statut, DocumentOfficiel.Statut.BROUILLON)

    def test_signature_document_apres_validation(self):
        d = DocumentOfficiel.objects.create(titre='Arrêté 2026')
        # Passage en validation puis signature
        transitionner_document(d, DocumentOfficiel.Statut.EN_VALIDATION)
        d.refresh_from_db()
        self.assertEqual(d.statut, DocumentOfficiel.Statut.EN_VALIDATION)
        valider_document(d)
        d.refresh_from_db()
        self.assertEqual(d.statut, DocumentOfficiel.Statut.SIGNE)

    def test_versionnement_document(self):
        d = DocumentOfficiel.objects.create(titre='Charte')
        v1 = services.creer_version_document(d, contenu='v1')
        v2 = services.creer_version_document(d, contenu='v2')
        self.assertEqual(v1.numero_version, 1)
        self.assertEqual(v2.numero_version, 2)
        self.assertEqual(d.versions.count(), 2)


class TestReunion(TestCase):
    def test_transition_reunion(self):
        r = ReunionCommission.objects.create(
            titre='Commission pédagogique', type_reunion='Commission',
            date_reunion=dt.date(2026, 10, 5),
        )
        transitionner_reunion(r, ReunionCommission.Statut.TENUE)
        r.refresh_from_db()
        self.assertEqual(r.statut, ReunionCommission.Statut.TENUE)

    def test_transition_reunion_invalide(self):
        r = ReunionCommission.objects.create(
            titre='Commission', type_reunion='Commission',
            date_reunion=dt.date(2026, 10, 5),
        )
        with self.assertRaises(ValueError):
            transitionner_reunion(r, ReunionCommission.Statut.PV_EMIS)  # saut interdit


class TestMission(TestCase):
    def test_creation_mission_dates_inverses_refuse(self):
        m = Mission(
            objet='Mission Abidjan', lieu='Abidjan',
            date_debut=dt.date(2026, 12, 31), date_fin=dt.date(2026, 1, 1),
        )
        with self.assertRaises(ValidationError):
            m.full_clean()

    def test_transition_mission_sans_motif_refus(self):
        m = Mission.objects.create(
            objet='Mission', lieu='Bouaké',
            date_debut=dt.date(2026, 10, 1), date_fin=dt.date(2026, 10, 3),
        )
        with self.assertRaises(ValueError):
            transitionner_mission(m, Mission.Statut.REFUSEE, motif_refus='')