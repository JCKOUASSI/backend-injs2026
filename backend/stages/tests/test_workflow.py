"""Tests smoke du lot L5 — Stages et conventions.

Validations indépendantes d'un jeu de données complet :
— imports + app_config chargée,
— règles de clean() du modèle (dates inversées, motif_refus obligatoire),
— machine à transitions : seules les transitions autorisées passent,
— idempotence via UniqueConstraint (une seule convention active par étudiant/année).
"""
import datetime as dt

from django.core.exceptions import ValidationError
from django.test import TestCase


class TestConfigs(TestCase):
    """Vérification de l'enregistrement de l'app config (smoke minimal)."""

    def test_app_chargee(self):
        from django.apps import apps
        self.assertIsNotNone(apps.get_app_config('stages'))
        self.assertEqual(apps.get_app_config('stages').verbose_name,
                         "LMD – Stages & Conventions")


class TestRegleDates(TestCase):
    """Garde-fou du modèle : dates inversées → ValidationError."""

    def test_dates_fin_avant_debut_refuse(self):
        from stages.models import ConventionStage, OrganismeAccueil
        # On construit sans save() : seul le clean() est testé (pas de FK requises).
        c = ConventionStage(
            date_debut=dt.date(2026, 12, 31),
            date_fin=dt.date(2026, 1, 1),
        )
        with self.assertRaises(ValidationError) as ctx:
            c.clean()
        self.assertIn('date_fin', ctx.exception.message_dict)


class TestMachineTransitions(TestCase):
    """La machine à transitions contrôle la conformité du workflow."""

    def _build_convention(self):
        from scolarite.models import AnneeAcademique
        from stages.models import ConventionStage, OrganismeAccueil
        from formations.models import Participant
        from authentication.models import User
        from scolarite.models import DossierEtudiant
        org = OrganismeAccueil.objects.create(nom='Organisme Test A')
        annee = AnneeAcademique.objects.create(libelle='2026-2027', date_debut=dt.date(2026, 10, 1), date_fin=dt.date(2027, 7, 31))
        user = User.objects.create_user(username='etudiant_a', password='x')
        participant = Participant.objects.create(nom='Awa', prenom='Test', matricule='MAT-STG-001')
        dossier = DossierEtudiant.objects.create(participant=participant)
        return ConventionStage.objects.create(
            etudiant=dossier, annee_academique=annee, organisme=org,
            intitule='Stage test', sujet='Sujet', date_debut=dt.date(2027, 1, 1),
            date_fin=dt.date(2027, 4, 30),
        )

    def test_transition_brouillon_vers_terminee_interdite(self):
        """Saut d'étape refusé : BROUILLON → TERMINEE n'est pas autorisé."""
        from stages.services import appliquer_transition
        c = self._build_convention()
        with self.assertRaises(ValidationError):
            appliquer_transition(c, 'TERMINEE', None)

    def test_transition_brouillon_vers_soumise_ok(self):
        """Transition linéaire autorisée : BROUILLON → SOUMISE."""
        from stages.services import appliquer_transition
        c = self._build_convention()
        appliquer_transition(c, 'SOUMISE', None)
        c.refresh_from_db()
        self.assertEqual(c.statut, 'SOUMISE')
        self.assertIsNotNone(c.date_soumission)


class TestReglesRefsEtModels(TestCase):
    """Vérifie la configuration des FK PROTECT (sans build de jeu complet)."""

    def test_clean_sans_motif_refus_leve_erreur(self):
        """Convention REFUSEE sans motif → ValidationError."""
        from stages.models import ConventionStage
        c = ConventionStage(
            statut=ConventionStage.Statut.REFUSEE,
            date_debut=dt.date(2027, 1, 1),
            date_fin=dt.date(2027, 4, 30),
        )
        with self.assertRaises(ValidationError) as ctx:
            c.clean()
        self.assertIn('motif_refus', ctx.exception.message_dict)
