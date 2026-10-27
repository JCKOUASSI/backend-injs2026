"""U2 — commande ``observations_habilitations`` (synthèse, campagne, reset)."""
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from habilitations.models import CompteUtilisateur
from habilitations.services import observation

from .helpers import (
    creer_compte,
    creer_permission,
    creer_user,
)


class CommandeObservationsTests(TestCase):
    def setUp(self):
        observation.remettre_a_zero()

    def tearDown(self):
        observation.remettre_a_zero()

    def test_synthese_sort_0_sans_donnee(self):
        sortie = StringIO()
        call_command('observations_habilitations', stdout=sortie)
        self.assertIn('Mode du moteur', sortie.getvalue())
        self.assertIn('Écarts constatés : 0', sortie.getvalue())

    def test_remettre_a_zero_vide_les_compteurs(self):
        user = creer_user(username='cmd-ng', role_existant='ARCHIVE')
        creer_compte(user=user)
        from habilitations.services.moteur import est_autorise
        observation.enregistrer_decision(
            est_autorise(user, 'x.y.consulter'), decision_legacy=True)
        self.assertGreaterEqual(
            observation.etat_observation()['evaluations_total'], 1)
        sortie = StringIO()
        call_command('observations_habilitations',
                     '--remettre-a-zero', stdout=sortie)
        self.assertIn('remis à zéro', sortie.getvalue())
        self.assertEqual(
            observation.etat_observation()['evaluations_total'], 0)

    def test_campagne_sans_objet_avant_u3_u8(self):
        # Aucun compte gouverné, référentiel vide : campagne explicitement
        # sans objet, mais jamais en échec.
        sortie = StringIO()
        call_command('observations_habilitations', '--campagne',
                     stdout=sortie)
        texte = sortie.getvalue()
        self.assertIn('campagne sans objet', texte)
        self.assertIn('Comptes gouvernés : 0', texte)

    def test_campagne_releve_un_compte_suspendu(self):
        user = creer_user(username='cmd-susp', role_existant='ARCHIVE')
        creer_compte(
            user=user, statut=CompteUtilisateur.Statut.SUSPENDU)
        permission = creer_permission(
            code_module='cmd', ressource='x', action='consulter')
        resultat = observation.executer_campagne(permissions=[permission])
        self.assertEqual(resultat['comptes_gouverves'], 1)
        self.assertGreaterEqual(resultat['refus_significatifs'], 1)
        self.assertIn('COMPTE_SUSPENDU', resultat['motifs'])
