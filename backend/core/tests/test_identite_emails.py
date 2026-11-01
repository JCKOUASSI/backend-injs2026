"""Les e-mails envoyés aux utilisateurs portent l'identité INJS, pas l'ancienne.

Origine — la signature et le bandeau des deux e-mails métier (création de
compte et alerte de présence hors ligne) affichaient encore le sigle **DFRC**,
administration de l'application historique. Les sujets, eux, étaient déjà en
INJS : l'écart ne se voyait donc que dans le corps du message, c'est-à-dire
précisément là où personne ne relit.

Ces tests capturent le message réellement remis à la couche d'envoi Django
(`django.core.mail.outbox`) et inspectent son contenu.
"""
from django.core import mail
from django.test import TestCase, override_settings

from authentication.emails import (
    send_suspect_heartbeat_email,
    send_welcome_email,
)
from authentication.models import User

SIGLES_HISTORIQUES = ('DFRC', 'CPFAE', 'SYGEP')


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class IdentiteDesEmailsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='email_identite', password='motdepasse', role=User.Role.SECRETARIAT,
            first_name='Awa', last_name='Kone', email='awa.kone@injs.example',
        )

    def _messages(self):
        return mail.outbox

    def _verifier_identite(self, *contenus):
        for contenu in contenus:
            texte = str(contenu).upper()
            for sigle in SIGLES_HISTORIQUES:
                self.assertNotIn(
                    sigle, texte,
                    f"le sigle historique {sigle} subsiste dans un e-mail utilisateur",
                )
            self.assertIn('INJS', texte)

    def test_email_de_bienvenue_porte_l_identite_injs(self):
        send_welcome_email(self.user, 'MotDePasse2026!')
        self.assertEqual(len(self._messages()), 1)
        message = self._messages()[0]
        self._verifier_identite(message.subject, message.body, message.alternatives[0][0])

    def test_email_de_bienvenue_mobile_porte_l_identite_injs(self):
        send_welcome_email(self.user, 'MotDePasse2026!', mobile=True)
        self.assertEqual(len(self._messages()), 1)
        message = self._messages()[0]
        self._verifier_identite(message.subject, message.body, message.alternatives[0][0])

    def test_alerte_de_presence_porte_l_identite_injs(self):
        send_suspect_heartbeat_email(
            self.user, 'Awa Kone', 'MAT-001', 'Formation test',
            'Déontologie', 'Séance 1 — matin', 45,
        )
        self.assertEqual(len(self._messages()), 1)
        message = self._messages()[0]
        self._verifier_identite(message.subject, message.body, message.alternatives[0][0])

    def test_email_de_bienvenue_contient_les_identifiants(self):
        """Garde-fou fonctionnel : le message doit rester utilisable."""
        send_welcome_email(self.user, 'MotDePasse2026!')
        corps = self._messages()[0].body
        self.assertIn('email_identite', corps)
        self.assertIn('MotDePasse2026!', corps)
