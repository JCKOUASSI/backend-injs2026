"""Tests notifications workflow rapports."""
from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase

from statistiques.models import NotificationRapport, Rapport
from statistiques.rapport_notifications import notifier_rapport_workflow

User = get_user_model()


class RapportWorkflowNotificationTests(TestCase):
    def setUp(self):
        self.direction = User.objects.create_user(
            username='dir1', password='x', role=User.Role.DIRECTION,
        )
        self.admin = User.objects.create_user(
            username='admin1', password='x', role=User.Role.ADMIN,
        )
        self.secretariat = User.objects.create_user(
            username='sec1', password='x', role=User.Role.SECRETARIAT,
        )
        today = date.today()
        self.rapport = Rapport.objects.create(
            titre='Rapport test',
            type=Rapport.Type.MENSUEL,
            periode_debut=today.replace(day=1),
            periode_fin=today,
            generateur=self.secretariat,
            statut=Rapport.Statut.BROUILLON,
        )

    def test_soumettre_notifie_direction(self):
        notifier_rapport_workflow(self.rapport, 'soumettre', self.secretariat)
        destinaires = set(
            NotificationRapport.objects.values_list('destinataire_id', flat=True)
        )
        self.assertIn(self.direction.id, destinaires)
        self.assertIn(self.admin.id, destinaires)
        self.assertNotIn(self.secretariat.id, destinaires)

    def test_rejeter_notifie_generateur(self):
        notifier_rapport_workflow(self.rapport, 'rejeter', self.direction, commentaire='Incomplet')
        self.assertEqual(NotificationRapport.objects.count(), 1)
        notif = NotificationRapport.objects.get()
        self.assertEqual(notif.destinataire, self.secretariat)
        self.assertEqual(notif.evenement, NotificationRapport.Evenement.REJETE)
        self.assertIn('Incomplet', notif.message)
