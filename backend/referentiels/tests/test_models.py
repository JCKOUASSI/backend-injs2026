"""Tests des règles du socle référentiel (1 à 7 — prompt n°4)."""
from django.db import IntegrityError, transaction
from django.test import TestCase

from authentication.models import User
from referentiels.models import RefTypeFrais, RefTypeEvaluation, ReferentielJournal
from scolarite.models import AnneeAcademique


class RefSocleRuleTests(TestCase):
    """Les règles du socle sont testées sur un modèle concret (RefTypeFrais)."""

    def test_regle1_code_unique(self):
        RefTypeFrais.objects.create(code='INSCRIPTION', libelle='Frais d’inscription')
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                RefTypeFrais.objects.create(code='INSCRIPTION', libelle='Doublon code')

    def test_regle4_anti_doublon_libelle_casse_insensible(self):
        RefTypeEvaluation.objects.create(code='EXAMEN', libelle='Examen final')
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                RefTypeEvaluation.objects.create(code='EXAMEN2', libelle='examen FINAL')

    def test_regle2_pas_de_suppression_physique_archivage(self):
        ref = RefTypeFrais.objects.create(code='SCOLARITE', libelle='Frais de scolarité')
        ref.archiver()
        self.assertTrue(ref.archive)
        self.assertFalse(ref.actif)
        self.assertIsNotNone(ref.date_desactivation)
        # L'objet existe toujours (soft delete) — pas de suppression physique.
        self.assertTrue(RefTypeFrais.objects.filter(pk=ref.pk).exists())

    def test_regle3_dates_activation_desactivation(self):
        ref = RefTypeEvaluation.objects.create(code='CC', libelle='Contrôle continu')
        self.assertIsNone(ref.date_desactivation)
        ref.desactiver()
        self.assertFalse(ref.actif)
        self.assertIsNotNone(ref.date_desactivation)
        ref.activer()
        self.assertTrue(ref.actif)
        self.assertIsNotNone(ref.date_activation)
        self.assertIsNone(ref.date_desactivation)

    def test_regle5_usables_exclut_archive_et_inactif(self):
        ok = RefTypeFrais.objects.create(code='EXAMEN_F', libelle='Frais d’examen')
        inactif = RefTypeFrais.objects.create(code='LABO', libelle='Frais de laboratoire', actif=False)
        archive = RefTypeFrais.objects.create(code='LEGACY', libelle='Ancien frais')
        archive.archiver()
        codes = set(RefTypeFrais.usables().values_list('code', flat=True))
        self.assertIn('EXAMEN_F', codes)
        self.assertNotIn('LABO', codes)
        self.assertNotIn('LEGACY', codes)

    def test_regle6_journalisation(self):
        admin = User.objects.create_user(username='ref_admin', password='x', role='ADMIN')
        ref = RefTypeEvaluation.objects.create(code='ORAL', libelle='Oral')
        ref.journaliser(ReferentielJournal.Action.CREATION, admin)
        ref.archiver(admin, motif='N obsolète')
        actions = list(
            ReferentielJournal.objects.filter(
                object_id=ref.pk,
                content_type__model='reftypeevaluation',
            ).values_list('action', flat=True)
        )
        self.assertIn('CREATION', actions)
        self.assertIn('ARCHIVAGE', actions)

    def test_regle7_annee_academique_facultative(self):
        annee = AnneeAcademique.objects.create(
            libelle='2026-2027', date_debut='2026-10-01', date_fin='2027-07-31', courante=True,
        )
        ref = RefTypeFrais.objects.create(
            code='PONCTUEL', libelle='Frais ponctuel', annee_academique=annee,
        )
        self.assertEqual(ref.annee_academique, annee)
        # Et sans rattachement (le champ reste nullable)
        ref2 = RefTypeFrais.objects.create(code='PERMANENT', libelle='Frais permanent')
        self.assertIsNone(ref2.annee_academique)
