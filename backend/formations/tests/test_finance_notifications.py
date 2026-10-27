"""Tests notifications workflow finance."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from formations.finance_notifications import (
    notifier_ajustement_propose,
    notifier_ajustement_valide,
)
from formations.models import FinanceAjustement, Formation, Formateur, Module, NotificationFinanceAjustement, SessionModule

User = get_user_model()


class FinanceNotificationTests(TestCase):
    def setUp(self):
        self.direction = User.objects.create_user(
            username='dir1', password='x', role=User.Role.DIRECTION,
        )
        self.finance = User.objects.create_user(
            username='fin1', password='x', role=User.Role.FINANCE,
        )
        formation = Formation.objects.create(formation='Cycle test')
        module = Module.objects.create(formation=formation, intitule='Module A')
        self.session = SessionModule.objects.create(
            module=module, numero=1, intitule='Séance 1',
        )
        self.formateur = Formateur.objects.create(nom='Martin', prenom='Paul', numerobadge='F001')
        self.ajustement = FinanceAjustement.objects.create(
            session=self.session,
            formateur=self.formateur,
            minutes_delta=15,
            motif='Prolongation',
            proposed_by=self.finance,
        )

    def test_propose_notifie_direction(self):
        notifier_ajustement_propose(self.ajustement, self.finance)
        self.assertEqual(NotificationFinanceAjustement.objects.count(), 1)
        notif = NotificationFinanceAjustement.objects.get()
        self.assertEqual(notif.destinataire, self.direction)
        self.assertEqual(notif.evenement, NotificationFinanceAjustement.Evenement.PROPOSE)

    def test_valide_notifie_proposeur(self):
        notifier_ajustement_valide(self.ajustement, self.direction)
        self.assertEqual(NotificationFinanceAjustement.objects.count(), 1)
        notif = NotificationFinanceAjustement.objects.get()
        self.assertEqual(notif.destinataire, self.finance)
