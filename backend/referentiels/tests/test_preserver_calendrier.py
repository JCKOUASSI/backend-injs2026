"""L'import documentaire ne doit pas imposer son calendrier à la production."""
from datetime import date
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from referentiels.models import RefModePaiement
from scolarite.models import AnneeAcademique


class PreserverCalendrierTests(TestCase):
    def test_ne_touche_pas_aux_dates_statuts_ou_annees_planifiees(self):
        AnneeAcademique.objects.create(
            libelle='2026-2027', date_debut=date(2026, 1, 1),
            date_fin=date(2027, 11, 30), courante=True, actif=True,
            description='Calendrier arrêté localement',
        )
        sortie = StringIO()
        for _ in range(2):
            call_command('importer_referentiels_injs', '--sans-cycles',
                         '--preserver-calendrier', stdout=sortie)
        self.assertEqual(AnneeAcademique.objects.count(), 1)
        annee = AnneeAcademique.objects.get()
        self.assertEqual(annee.date_debut, date(2026, 1, 1))
        self.assertEqual(annee.date_fin, date(2027, 11, 30))
        self.assertTrue(annee.courante)
        self.assertFalse(annee.cloturee)
        self.assertEqual(annee.description, 'Calendrier arrêté localement')
        self.assertEqual(RefModePaiement.objects.count(), 14)
        self.assertIn('préservées', sortie.getvalue())

    def test_simulation_ne_change_rien_non_plus(self):
        call_command('importer_referentiels_injs', '--sans-cycles',
                     '--preserver-calendrier', '--dry-run', stdout=StringIO())
        self.assertEqual(AnneeAcademique.objects.count(), 0)
        self.assertEqual(RefModePaiement.objects.count(), 0)
