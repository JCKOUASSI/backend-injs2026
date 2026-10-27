"""Tests de validation et synchronisation du matricule auditeur."""

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from formations.models import Participant, Secretariat, RefTypeSecretariat
from formations.participant_matricule import (
    normalize_matricule,
    secretariat_from_matricule_for_actor,
    sync_participant_user_after_matricule_change,
    validate_participant_matricule,
)
from formations.tests.test_core import make_user

User = get_user_model()


class ParticipantMatriculeValidationTests(TestCase):
    def setUp(self):
        self.participant = Participant.objects.create(
            matricule='OLD-001',
            nom='Kouassi',
            prenom='Aya',
        )

    def test_normalize_matricule_strips_spaces(self):
        self.assertEqual(normalize_matricule('  ABC  '), 'ABC')

    def test_rejects_empty_matricule(self):
        with self.assertRaises(ValidationError):
            validate_participant_matricule('   ')

    def test_rejects_duplicate_participant(self):
        Participant.objects.create(matricule='DUP-001', nom='Autre', prenom='Personne')
        with self.assertRaises(ValidationError):
            validate_participant_matricule('dup-001', participant_id=self.participant.pk)

    def test_rejects_existing_user_badge(self):
        User.objects.create_user(
            username='USER-777',
            password='pass12345',
            role=User.Role.AUDITEUR,
            matricule='USER-777',
        )
        with self.assertRaises(ValidationError):
            validate_participant_matricule('user-777', participant_id=self.participant.pk)

    def test_allows_linked_user_matricule(self):
        user = User.objects.create_user(
            username='OLD-001',
            password='pass12345',
            role=User.Role.AUDITEUR,
            matricule='OLD-001',
        )
        self.participant.user = user
        self.participant.save(update_fields=['user'])
        self.assertEqual(
            validate_participant_matricule('OLD-001', participant_id=self.participant.pk, linked_user_id=user.pk),
            'OLD-001',
        )


class ParticipantMatriculeSyncTests(TestCase):
    def setUp(self):
        self.admin = make_user('admin_matricule', role='INJS_ADMIN')
        ref_type = RefTypeSecretariat.objects.create(libelle='FAB')
        self.sec_fab = Secretariat.objects.create(numero=1, nom='FAB', type=ref_type)
        ref_type_fac = RefTypeSecretariat.objects.create(libelle='FAC')
        self.sec_fac = Secretariat.objects.create(numero=2, nom='FAC', type=ref_type_fac)
        # Fiche d'abord : la création du compte AUDITEUR déclenche sync_user_profile_links
        # qui rattache (ou créerait en doublon) un Participant au même matricule.
        self.participant = Participant.objects.create(
            matricule='MAT-SYNC-001',
            nom='Traore',
            prenom='Fatou',
            secretariat=self.sec_fab,
        )
        self.user = User.objects.create_user(
            username='MAT-SYNC-001',
            password='pass12345',
            role=User.Role.AUDITEUR,
            matricule='MAT-SYNC-001',
        )
        self.participant.refresh_from_db()
        self.assertEqual(self.participant.user_id, self.user.id)

    def test_secretariat_reassigned_from_matricule_prefix(self):
        secretariat = secretariat_from_matricule_for_actor('FNCP26-777', self.admin)
        self.assertEqual(secretariat.pk, self.sec_fac.pk)

    def test_sync_updates_linked_user_badge(self):
        self.participant.matricule = 'FNCP26-888'
        self.participant.save(update_fields=['matricule'])
        sync_participant_user_after_matricule_change(self.participant)
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, 'FNCP26-888')
        self.assertEqual(self.user.matricule, 'FNCP26-888')
