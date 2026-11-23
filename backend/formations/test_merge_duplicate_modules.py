from datetime import date

from django.test import TestCase
from django.utils import timezone

from formations.models import Formation, Module, ModuleParticipant, Participant, SessionModule
from formations.module_merge import find_duplicate_module_groups, merge_module_into, pick_keeper_module


class MergeDuplicateModulesTest(TestCase):
    def setUp(self):
        self.formation = Formation.objects.create(formation='FAB test')
        self.participant = Participant.objects.create(
            matricule='M900', nom='Test', prenom='User',
        )

    def test_pick_keeper_prefers_active_module(self):
        active = Module.objects.create(
            formation=self.formation, intitule='Comptabilité A',
            grade='B1', groupe='GROUPE 1', vague='VAGUE 1', statut='EN_COURS',
        )
        empty = Module.objects.create(
            formation=self.formation, intitule='Comptabilité B',
            grade='B1', groupe='GROUPE 1', vague='VAGUE 1', statut='PLANIFIEE',
        )
        SessionModule.objects.create(
            module=active,
            date_journee=date.today(),
            numero=1,
            demarree_le=timezone.now(),
        )
        keeper = pick_keeper_module([active, empty])
        self.assertEqual(keeper.pk, active.pk)

    def test_merge_moves_sessions_and_deletes_source(self):
        keeper = Module.objects.create(
            formation=self.formation, intitule='Gestion A',
            grade='C1', groupe='GROUPE 2', vague='VAGUE 1', statut='EN_COURS',
        )
        source = Module.objects.create(
            formation=self.formation, intitule='Gestion B',
            grade='C1', groupe='GROUPE 2', vague='VAGUE 1', statut='PLANIFIEE',
        )
        started = SessionModule.objects.create(
            module=source,
            date_journee=date.today(),
            numero=1,
            demarree_le=timezone.now(),
        )
        ModuleParticipant.objects.create(module=source, participant=self.participant)

        merge_module_into(keeper, source)

        self.assertFalse(Module.objects.filter(pk=source.pk).exists())
        started.refresh_from_db()
        self.assertEqual(started.module_id, keeper.pk)
        self.assertEqual(keeper.module_participants.count(), 1)
        self.assertEqual(keeper.statut, 'EN_COURS')

    def test_find_duplicate_groups_empty_when_unique(self):
        Module.objects.create(
            formation=self.formation, intitule='Unique',
            grade='A1', groupe='G1', vague='V1',
        )
        self.assertEqual(find_duplicate_module_groups(), [])
