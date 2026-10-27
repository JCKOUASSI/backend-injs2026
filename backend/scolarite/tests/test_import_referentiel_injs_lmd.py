"""Tests A-4.4 : import controle du referentiel INJS-LMD.

Garanties : idempotence (rejouable sans doublon), aucune UE/ECUE/parcours
inventes, metadonnees NULL preservees (D9, coquilles ES/MS/ENSEP).
"""

from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from formations.models import RefFormation
from scolarite.models import (
    ECUE,
    UE,
    Niveau,
    Parcours,
    RegleValidationLMD,
    Semestre,
)


class ImportReferentielInjsLmdTests(TestCase):
    def _importer(self):
        call_command("init_referentiels_lmd", "--annee", "2026-2027",
                     stdout=StringIO())
        call_command("import_referentiel_injs_lmd", stdout=StringIO())

    def test_idempotent_sans_invention(self):
        self._importer()
        etat1 = (
            RefFormation.objects.count(),
            Niveau.objects.count(),
            Semestre.objects.count(),
            RegleValidationLMD.objects.count(),
        )
        call_command("import_referentiel_injs_lmd", stdout=StringIO())
        etat2 = (
            RefFormation.objects.count(),
            Niveau.objects.count(),
            Semestre.objects.count(),
            RegleValidationLMD.objects.count(),
        )
        self.assertEqual(etat1, etat2)

    def test_structure_lmd_garantie(self):
        self._importer()
        self.assertEqual(
            sorted(Niveau.objects.values_list("code", flat=True)),
            ["L1", "L2", "L3", "M1", "M2"],
        )
        self.assertEqual(
            sorted(Semestre.objects.values_list("numero", flat=True)),
            [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        )
        self.assertFalse(Niveau.objects.filter(code__in=["M3", "M4", "M5"]).exists())

    def test_aucune_invention_pedagogique(self):
        self._importer()
        self.assertEqual(UE.objects.count(), 0)
        self.assertEqual(ECUE.objects.count(), 0)
        self.assertEqual(Parcours.objects.count(), 0)

    def test_dry_run_sans_ecriture(self):
        call_command("init_referentiels_lmd", "--annee", "2026-2027",
                     stdout=StringIO())
        avant = (
            RefFormation.objects.count(),
            Niveau.objects.count(),
            Semestre.objects.count(),
            RegleValidationLMD.objects.count(),
        )
        call_command("import_referentiel_injs_lmd", "--dry-run", stdout=StringIO())
        apres = (
            RefFormation.objects.count(),
            Niveau.objects.count(),
            Semestre.objects.count(),
            RegleValidationLMD.objects.count(),
        )
        self.assertEqual(avant, apres)
