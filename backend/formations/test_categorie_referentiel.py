"""Tests — résolution des catégories vers RefCategorie."""
from django.core.management import call_command
from django.test import TestCase

from formations.categorie_referentiel import (
    categories_from_raw_values,
    normalize_categorie_raw,
    q_participant_categorie_ref,
    reset_ref_categorie_index,
    resolve_categorie_participant,
    resolve_categorie_ref,
)
from formations.models import Formation, Module, ModuleParticipant, Participant, RefCategorie


class CategorieReferentielTest(TestCase):
    def setUp(self):
        reset_ref_categorie_index()
        RefCategorie.objects.create(libelle='A', actif=True)
        RefCategorie.objects.create(libelle='B', actif=True)
        reset_ref_categorie_index()

    def tearDown(self):
        reset_ref_categorie_index()

    def test_normalize_variantes_collees(self):
        self.assertEqual(normalize_categorie_raw('FABA'), 'FAB A')
        self.assertEqual(normalize_categorie_raw('fab a'), 'FAB A')

    def test_normalize_preserve_codes_injs(self):
        for code in ('SFC', 'SST', 'SFO', 'SAC', 'SSC', 'SEN'):
            self.assertEqual(normalize_categorie_raw(code), code)

    def test_resolve_lettre_et_famille(self):
        self.assertEqual(resolve_categorie_ref('A'), 'A')
        self.assertEqual(resolve_categorie_ref('FAB A'), 'A')
        self.assertEqual(resolve_categorie_ref('FABA'), 'A')
        self.assertIsNone(resolve_categorie_ref('FAB Z'))

    def test_categories_from_raw_values_dedup(self):
        cats = categories_from_raw_values(['FAB A', 'A', 'FABA', 'B'])
        self.assertEqual(cats, ['A', 'B'])

    def test_q_participant_categorie_ref_matche_variantes(self):
        formation = Formation.objects.create(formation='Test cat')
        module = Module.objects.create(formation=formation, intitule='M1', grade='A4')
        participant = Participant.objects.create(
            matricule='FNCE001',
            nom='Dupont',
            prenom='Jean',
            categorie='FAB A',
        )
        ModuleParticipant.objects.create(module=module, participant=participant)

        mp_qs = ModuleParticipant.objects.filter(q_participant_categorie_ref('A'))
        self.assertEqual(mp_qs.count(), 1)

    def test_categories_for_scope_map_ref(self):
        from statistiques.effectifs import categories_for_scope

        formation = Formation.objects.create(formation='Test scope')
        module = Module.objects.create(formation=formation, intitule='M1', grade='A4')
        participant = Participant.objects.create(
            matricule='FNCE002',
            nom='Martin',
            prenom='Paul',
            categorie='FAB A',
        )
        ModuleParticipant.objects.create(module=module, participant=participant)

        self.assertEqual(categories_for_scope(formation_id=formation.id), ['A'])


class BackfillCategorieRefCommandTest(TestCase):
    def setUp(self):
        reset_ref_categorie_index()
        RefCategorie.objects.create(libelle='A', actif=True)
        RefCategorie.objects.create(libelle='B', actif=True)
        reset_ref_categorie_index()

    def tearDown(self):
        reset_ref_categorie_index()

    def test_backfill_normalise_fab_a(self):
        participant = Participant.objects.create(
            matricule='FNCE100',
            nom='Test',
            prenom='User',
            categorie='FAB A',
        )
        call_command('backfill_categorie_ref')
        participant.refresh_from_db()
        self.assertEqual(participant.categorie, 'A')

    def test_backfill_dry_run_ne_change_pas(self):
        participant = Participant.objects.create(
            matricule='FNCE101',
            nom='Test',
            prenom='Dry',
            categorie='FAB B',
        )
        call_command('backfill_categorie_ref', dry_run=True)
        participant.refresh_from_db()
        self.assertEqual(participant.categorie, 'FAB B')

    def test_resolve_categorie_participant_depuis_grade(self):
        self.assertEqual(resolve_categorie_participant('', grade='A4'), 'A')
