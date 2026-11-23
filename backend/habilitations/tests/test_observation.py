"""U2 — mode observation (R3) et permission DRF ``ExigePermission``.

L'observation ne modifie JAMAIS une réponse. En revanche elle compte les
écarts, et le mode application (jamais activé en U2 ailleurs que dans ces
tests) refuse et trace.
"""
from types import SimpleNamespace

from django.test import TestCase, override_settings
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory, force_authenticate

from habilitations.models import JournalHabilitation
from habilitations.permissions import ExigePermission
from habilitations.services import observation
from habilitations.services.moteur import est_autorise

from .helpers import (
    creer_attribution,
    creer_compte,
    creer_permission,
    creer_role,
    creer_user,
)

PERM = 'rh.agent.modifier'
TOUT_OFF = dict(HABILITATIONS_OBSERVATION=False, HABILITATIONS_APPLICATION=False)
APPLICATION = dict(HABILITATIONS_OBSERVATION=True, HABILITATIONS_APPLICATION=True)


def _fabrique(user, methode='get', donnees=None):
    fabrique = APIRequestFactory()
    if methode == 'get':
        brute = fabrique.get('/api/bidule/')
    else:
        brute = fabrique.post('/api/bidule/', donnees or {}, format='json')
    # Le forçage se lit sur la requête brute lors de la construction du
    # wrapper DRF (ForcedAuthentication).
    force_authenticate(brute, user=user)
    return Request(brute)


class ObservationTests(TestCase):
    def setUp(self):
        observation.remettre_a_zero()

    def tearDown(self):
        observation.remettre_a_zero()

    def _compte_autorise_refuse(self):
        user_bon = creer_user(username='ob-bon', role_existant='ARCHIVE')
        compte_bon = creer_compte(user=user_bon)
        perm = creer_permission(
            code_module='rh', ressource='agent', action='modifier')
        role = creer_role(code='R_OB_BON')
        role.permissions.add(perm)
        creer_attribution(compte_bon, role)
        user_vide = creer_user(username='ob-vide', role_existant='ARCHIVE')
        creer_compte(user=user_vide)  # gouverné mais sans octroi
        return user_bon, user_vide, perm

    def test_off_est_un_noop_total(self):
        decision = est_autorise(creer_user(username='ob-off'), PERM)
        with override_settings(**TOUT_OFF):
            observation.enregistrer_decision(
                decision, decision_legacy=True, username='ob-off')
        etat = observation.etat_observation()
        self.assertEqual(etat['evaluations_total'], 0)
        self.assertIsNone(etat['premiere_observation'])

    def test_compte_non_gouverne_nest_pas_un_ecart(self):
        user = creer_user(username='ob-ng', role_existant='ARCHIVE')
        decision = est_autorise(user, PERM)
        observation.enregistrer_decision(
            decision, decision_legacy=True, username='ob-ng')
        etat = observation.etat_observation()
        self.assertEqual(etat['non_gouvernees'], 1)
        self.assertEqual(etat['ecarts_total'], 0)

    def test_ecart_legacy_autorise_moteur_refuse_compte(self):
        _, user_vide, _ = self._compte_autorise_refuse()
        decision = est_autorise(user_vide, PERM)
        ecart = observation.enregistrer_decision(
            decision, decision_legacy=True, username='ob-vide')
        etat = observation.etat_observation()
        self.assertTrue(ecart)
        self.assertEqual(etat['ecarts_legacy_autorise_moteur_refuse'], 1)
        self.assertEqual(etat['refusees_moteur'], 1)
        self.assertEqual(etat['motifs']['AUCUNE_ATTRIBUTION_PERMETTANTE'], 1)

    def test_ecart_legacy_refuse_moteur_autorise_compte(self):
        user_bon, _, _ = self._compte_autorise_refuse()
        decision = est_autorise(user_bon, PERM)
        ecart = observation.enregistrer_decision(
            decision, decision_legacy=False, username='ob-bon')
        etat = observation.etat_observation()
        self.assertTrue(ecart)
        self.assertEqual(etat['ecarts_legacy_refuse_moteur_autorise'], 1)
        self.assertEqual(etat['autorisees_moteur'], 1)

    def test_pas_d_ecart_quand_les_deux_accordent(self):
        user_bon, _, _ = self._compte_autorise_refuse()
        decision = est_autorise(user_bon, PERM)
        ecart = observation.enregistrer_decision(
            decision, decision_legacy=True, username='ob-bon')
        self.assertFalse(ecart)
        self.assertEqual(observation.etat_observation()['ecarts_total'], 0)

    def test_remise_a_zero_vide_les_compteurs(self):
        user_bon, _, _ = self._compte_autorise_refuse()
        observation.enregistrer_decision(
            est_autorise(user_bon, PERM), decision_legacy=False)
        observation.remettre_a_zero()
        etat = observation.etat_observation()
        self.assertEqual(etat['evaluations_total'], 0)
        self.assertIsNone(etat['premiere_observation'])

    def test_campagne_est_sans_objet_sans_compte_gouverne(self):
        resultat = observation.executer_campagne(permissions=[])
        self.assertEqual(resultat['evaluations'], 0)
        self.assertEqual(resultat['comptes_gouverves'], 0)


class ExigePermissionTests(TestCase):
    def setUp(self):
        observation.remettre_a_zero()
        self.perm = creer_permission(
            code_module='rh', ressource='agent', action='modifier')
        self.role = creer_role(code='R_DRF')
        self.role.permissions.add(self.perm)

    def tearDown(self):
        observation.remettre_a_zero()

    def test_mode_off_est_noop_total_pour_tous(self):
        user = creer_user(username='drf-off', role_existant='ARCHIVE')
        creer_compte(user=user)
        permission = ExigePermission(PERM)
        requete = _fabrique(user)
        with override_settings(**TOUT_OFF):
            self.assertTrue(permission.has_permission(requete, None))
        self.assertEqual(
            observation.etat_observation()['evaluations_total'], 0)

    def test_observation_laisse_passer_un_refus_moteur_pour_tous(self):
        user = creer_user(username='drf-obs', role_existant='ARCHIVE')
        creer_compte(user=user)  # sans octroi : le moteur refuse
        permission = ExigePermission(PERM)
        requete = _fabrique(user)
        # Réglages par défaut = OBSERVATION.
        self.assertTrue(permission.has_permission(requete, None))
        self.assertEqual(
            observation.etat_observation()['refusees_moteur'], 1)

    def test_observation_compte_non_gouverne_laisse_passer_pour_tous(self):
        user = creer_user(username='drf-ng', role_existant='SECRETARIAT')
        permission = ExigePermission(PERM)
        requete = _fabrique(user)
        self.assertTrue(permission.has_permission(requete, None))

    def test_application_refuse_pour_secretariat_sans_octroi(self):
        user = creer_user(username='drf-app', role_existant='SECRETARIAT')
        creer_compte(user=user)
        permission = ExigePermission(PERM)
        requete = _fabrique(user)
        vue = SimpleNamespace()
        with override_settings(**APPLICATION):
            reponse = permission.has_permission(requete, vue)
        self.assertFalse(reponse)
        self.assertIn('Accès refusé', permission.message)
        self.assertIn('AUCUNE_ATTRIBUTION_PERMETTANTE', permission.message)
        # Le refus est tracé au journal append-only.
        self.assertTrue(
            JournalHabilitation.objects.filter(
                type_evenement=JournalHabilitation.TypeEvenement.ACCES_REFUSE
            ).exists()
        )

    def test_application_autorise_pour_titulaire(self):
        user = creer_user(username='drf-ok', role_existant='ARCHIVE')
        compte = creer_compte(user=user)
        creer_attribution(compte, self.role)
        permission = ExigePermission(PERM)
        requete = _fabrique(user)
        with override_settings(**APPLICATION):
            self.assertTrue(permission.has_permission(requete, None))

    def test_factory_pour_fournit_une_clause_instantiable(self):
        fabrique = ExigePermission.pour(PERM)
        instance = fabrique()
        self.assertEqual(instance.code_permission, PERM)
