"""Tests de résolution participant par module (chemin chaud scan)."""

from django.contrib.auth import get_user_model
from django.test import TestCase

from formations.models import (
    Formation,
    Module,
    ModuleParticipant,
    Participant,
    RefTypeSecretariat,
    Secretariat,
)
from presences.participant_scope import (
    participant_for_module,
    participant_in_module_by_matricule,
)

User = get_user_model()


class ParticipantScopeLookupTests(TestCase):
    def setUp(self):
        ref_type = RefTypeSecretariat.objects.create(libelle='FAB')
        self.secretariat = Secretariat.objects.create(numero=1, nom='FAB', type=ref_type)
        formation = Formation.objects.create(formation='Test formation')
        self.module = Module.objects.create(formation=formation, intitule='Module A')
        self.participant = Participant.objects.create(
            matricule='OPH-2026-1',
            nom='Kone',
            prenom='Ali',
            secretariat=self.secretariat,
        )
        ModuleParticipant.objects.create(module=self.module, participant=self.participant)

    def test_participant_in_module_by_matricule_iexact(self):
        found = participant_in_module_by_matricule(self.module, 'OPH-2026-1', 'OPH20261')
        self.assertEqual(found.pk, self.participant.pk)

    def test_participant_in_module_by_matricule_compact_fallback(self):
        found = participant_in_module_by_matricule(self.module, '', 'OPH20261')
        self.assertEqual(found.pk, self.participant.pk)

    def test_participant_for_module_links_by_user_id_first(self):
        user = User.objects.create_user(
            username='OPH-2026-1',
            password='pass12345',
            role='AUDITEUR',
            matricule='OPH-2026-1',
        )
        self.participant.refresh_from_db()
        self.assertEqual(self.participant.user_id, user.pk)
        found = participant_for_module(user, self.module)
        self.assertEqual(found.pk, self.participant.pk)

    def test_participant_for_module_matches_matricule_format_differs(self):
        user = User.objects.create_user(
            username='OPH20261',
            password='pass12345',
            role='AUDITEUR',
            matricule='OPH20261',
        )
        found = participant_for_module(user, self.module)
        self.assertEqual(found.pk, self.participant.pk)
