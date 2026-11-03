"""Tests de `completer_referentiel_lmd` (complément LMD issu du PDF de référence).

La chaîne de préparation reproduit l'ordre de production :
init_referentiels_lmd → importer_referentiels_injs → configurer_referentiel_injs.
"""

from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from formations.models import RefFormation
from scolarite.models import ECUE, UE, Maquette, Niveau, Parcours, Semestre


class CompleterReferentielLmdTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('init_referentiels_lmd', '--annee', '2026-2027',
                     '--courante', stdout=StringIO())
        call_command('importer_referentiels_injs', '--sans-lieux', stdout=StringIO())
        call_command('configurer_referentiel_injs', stdout=StringIO())

    def _completer(self, *args):
        return call_command('completer_referentiel_lmd', *args, stdout=StringIO())

    def test_dry_run_necrit_rien(self):
        self._completer('--dry-run')
        self.assertEqual(Niveau.objects.count(), 5)
        self.assertEqual(Semestre.objects.count(), 10)
        self.assertEqual(Parcours.objects.count(), 0)
        self.assertEqual(UE.objects.count(), 323)

    def test_doctorat_niveaux_et_semestres(self):
        self._completer()
        self.assertEqual(Niveau.objects.count(), 8)
        self.assertEqual(Semestre.objects.count(), 16)
        d1 = Niveau.objects.get(code='D1')
        self.assertEqual(d1.cycle, Niveau.Cycle.DOCTORAT)
        self.assertEqual(d1.credits_requis, 60)
        self.assertEqual(
            sorted(d1.semestres.values_list('numero', flat=True)), [11, 12])
        self.assertEqual(
            Semestre.objects.get(numero=16).niveau.code, 'D3')

    def test_cycles_ensep_coquilles_sans_maquette(self):
        self._completer()
        self.assertEqual(RefFormation.objects.count(), 16)
        for code_dossier in ('F05', 'F06', 'F07', 'F08'):
            cycles = RefFormation.objects.filter(filiere_code=code_dossier)
            self.assertEqual(cycles.count(), 2, code_dossier)
            for cycle in cycles:
                self.assertIsNotNone(cycle.filiere)
                self.assertEqual(cycle.maquettes.count(), 0)

    def test_parcours_seize_zones_remplies(self):
        self._completer()
        self.assertEqual(Parcours.objects.count(), 16)
        for parcours in Parcours.objects.select_related('ref_formation',
                                                         'type_formation'):
            self.assertTrue(parcours.code)
            self.assertTrue(parcours.intitule)
            self.assertTrue(parcours.actif)
            self.assertEqual(parcours.code, parcours.ref_formation.filiere.code)
            self.assertEqual(parcours.intitule,
                             parcours.ref_formation.filiere.libelle)
            self.assertEqual(parcours.type_formation.code,
                             parcours.ref_formation.type_diplome)
        # Les 8 spécialisations du PDF (§6), chacune en Licence et Master.
        self.assertEqual(
            set(Parcours.objects.values_list('code', flat=True)),
            {'EM', 'MS', 'ES', 'APA', 'AND', 'LOI', 'ECJP', 'GER'})

    def test_ms_s8_complete_la_maquette_m1(self):
        self._completer()
        self.assertEqual(UE.objects.count(), 331)
        self.assertEqual(ECUE.objects.count(), 407)
        maquette = Maquette.objects.get(
            ref_formation__filiere__code='MS', niveau__code='M1')
        self.assertEqual(maquette.statut, Maquette.Statut.BROUILLON)
        ues_s8 = UE.objects.filter(maquette=maquette, semestre__numero=8)
        self.assertEqual(ues_s8.count(), 8)
        self.assertEqual(sum(u.credits for u in ues_s8), 30)
        self.assertEqual(
            sum(u.credits for u in UE.objects.filter(maquette=maquette)), 60)
        ue01 = UE.objects.get(maquette=maquette, code='MS-S8-UE01')
        self.assertEqual(ue01.intitule, 'Professionnalisation')
        self.assertEqual(ue01.ecues.count(), 1)
        self.assertIn('RÉFÉRENTIEL COMPLET', maquette.commentaire_validation)

    def test_idempotence_et_cohabitation_configurer(self):
        self._completer()
        compteurs = (Niveau.objects.count(), Semestre.objects.count(),
                     Parcours.objects.count(), Maquette.objects.count(),
                     UE.objects.count(), ECUE.objects.count())
        self._completer()
        call_command('configurer_referentiel_injs', stdout=StringIO())
        self.assertEqual(
            (Niveau.objects.count(), Semestre.objects.count(),
             Parcours.objects.count(), Maquette.objects.count(),
             UE.objects.count(), ECUE.objects.count()),
            compteurs)
        # La commande officielle ne doit pas avoir délié ni dupliqué MS-S8.
        self.assertEqual(UE.objects.filter(code__startswith='MS-S8').count(), 8)

    def test_maquettes_restent_sans_parcours(self):
        """configurer_referentiel_injs cherche ses maquettes avec
        parcours__isnull=True : le complément ne doit jamais les lier."""
        self._completer()
        self.assertEqual(
            Maquette.objects.filter(parcours__isnull=False).count(), 0)


class CompleterReferentielLmdPrerequisTests(TestCase):
    def test_sans_annee_courante_erreur_explicite(self):
        with self.assertRaises(CommandError):
            call_command('completer_referentiel_lmd', stdout=StringIO())
