"""Garde-fous de la démonstration complète (aucune donnée réelle altérée)."""
from datetime import date
from io import StringIO

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from scolarite.models import AnneeAcademique


class SeedPlateformeDemoTests(TestCase):
    def setUp(self):
        self.base = str(settings.DATABASES['default']['NAME'])
        self.annee = AnneeAcademique.objects.create(
            libelle='2026-2027', date_debut=date(2026, 1, 1),
            date_fin=date(2027, 11, 30), courante=True,
        )

    def test_verification_est_sans_ecriture(self):
        sortie = StringIO()
        call_command('seed_plateforme_demo', base=self.base, stdout=sortie)
        self.assertIn('Aucune écriture', sortie.getvalue())
        self.assertIn('etudiants_fictifs: 0', sortie.getvalue())
        self.annee.refresh_from_db()
        self.assertEqual(self.annee.date_debut, date(2026, 1, 1))

    def test_refuse_mauvaise_base_et_confirmation_absente(self):
        with self.assertRaisesMessage(CommandError, 'Base refusée'):
            call_command('seed_plateforme_demo', base='autre-base', appliquer=True)
        with self.assertRaisesMessage(CommandError, 'Sauvegarde vérifiée requise'):
            call_command('seed_plateforme_demo', base=self.base, appliquer=True)

    def test_refuse_effectif_impair(self):
        with self.assertRaisesMessage(CommandError, '--effectif doit être pair'):
            call_command('seed_plateforme_demo', base=self.base, effectif=5001)
