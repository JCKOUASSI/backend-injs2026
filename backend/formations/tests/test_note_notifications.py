"""Tests notifications modification de notes."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from formations.models import (
    Formation, Module, Participant, NoteModule, NoteModuleColonne,
    ModuleParticipant, NotificationModificationNote,
)
from formations.note_notifications import note_deja_enregistree, notifier_modification_note

User = get_user_model()


class NoteModificationNotificationTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin1', password='x', role=User.Role.ADMIN,
            first_name='Admin', last_name='Test',
        )
        self.direction = User.objects.create_user(
            username='dir1', password='x', role=User.Role.DIRECTION,
            first_name='Directeur', last_name='Test',
        )
        self.secretariat = User.objects.create_user(
            username='sec1', password='x', role=User.Role.SECRETARIAT,
        )
        self.formation = Formation.objects.create(formation='Formation test')
        self.module = Module.objects.create(formation=self.formation, intitule='Module A')
        self.participant = Participant.objects.create(
            nom='Dupont', prenom='Jean', matricule='M001',
        )
        ModuleParticipant.objects.create(module=self.module, participant=self.participant)
        self.colonne = NoteModuleColonne.objects.create(
            module=self.module, libelle='Contrôle 1', note_max=20,
        )

    def test_premiere_saisie_sans_notification(self):
        notifier_modification_note(
            self.admin, self.participant, self.module, self.colonne, None, 14,
        )
        self.assertEqual(NotificationModificationNote.objects.count(), 0)

    def test_modification_admin_notifie_direction(self):
        NoteModule.objects.create(
            colonne=self.colonne, participant=self.participant, note=Decimal('12'),
        )
        notifier_modification_note(
            self.admin, self.participant, self.module, self.colonne,
            Decimal('12'), Decimal('15'),
        )
        self.assertEqual(NotificationModificationNote.objects.count(), 1)
        notif = NotificationModificationNote.objects.get()
        self.assertEqual(notif.destinataire, self.direction)
        self.assertIn('Admin Test', notif.message)
        self.assertIn('12', notif.message)
        self.assertIn('15', notif.message)

    def test_secretariat_ne_declenche_pas_notification(self):
        NoteModule.objects.create(
            colonne=self.colonne, participant=self.participant, note=Decimal('10'),
        )
        notifier_modification_note(
            self.secretariat, self.participant, self.module, self.colonne,
            Decimal('10'), Decimal('11'),
        )
        self.assertEqual(NotificationModificationNote.objects.count(), 0)

    def test_note_deja_enregistree(self):
        self.assertFalse(note_deja_enregistree(None))
        nm = NoteModule(colonne=self.colonne, participant=self.participant, note=None)
        self.assertFalse(note_deja_enregistree(nm))
        nm.note = Decimal('8')
        self.assertTrue(note_deja_enregistree(nm))
