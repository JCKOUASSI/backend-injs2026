"""U2 — tests de l'API REST /api/habilitations/ et de l'extension additive
de /api/auth/capabilities/."""
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from habilitations.models import CompteUtilisateur
from habilitations.services import observation

from .helpers import (
    creer_attribution,
    creer_compte,
    creer_permission,
    creer_role,
    creer_user,
)


class ApiAnonymeTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_mes_acces_exige_une_authentification(self):
        self.assertEqual(
            self.client.get('/api/habilitations/mes-acces/').status_code, 401)

    def test_evaluer_exige_une_authentification(self):
        self.assertEqual(
            self.client.post('/api/habilitations/evaluer/', {}, format='json').status_code,
            401)

    def test_synthese_exige_une_authentification(self):
        self.assertEqual(
            self.client.get('/api/habilitations/observations/synthese/').status_code,
            401)

    def test_roles_exige_une_authentification(self):
        self.assertEqual(
            self.client.get('/api/habilitations/roles/').status_code, 401)


class MesAccesTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_compte_non_gouverne_renvoie_gouverne_faux(self):
        user = creer_user(username='api-ng', role_existant='SECRETARIAT')
        self.client.force_authenticate(user)
        reponse = self.client.get('/api/habilitations/mes-acces/')
        self.assertEqual(reponse.status_code, 200)
        corps = reponse.json()
        self.assertFalse(corps['gouverne'])
        self.assertIn('mode', corps)

    def test_compte_gouverne_renvoie_ses_attributions(self):
        user = creer_user(username='api-g', role_existant='ARCHIVE')
        compte = creer_compte(user=user)
        perm = creer_permission(
            code_module='scol', ressource='jury', action='consulter')
        role = creer_role(code='R_API')
        role.permissions.add(perm)
        creer_attribution(compte, role)
        self.client.force_authenticate(user)
        corps = self.client.get('/api/habilitations/mes-acces/').json()
        self.assertTrue(corps['gouverne'])
        self.assertEqual(corps['compte']['statut'], CompteUtilisateur.Statut.ACTIF)
        self.assertEqual(len(corps['attributions']), 1)
        self.assertEqual(corps['attributions'][0]['role'], 'R_API')
        self.assertTrue(corps['attributions'][0]['active'])


class EvaluerTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = creer_user(username='api-ev', role_existant='ARCHIVE')
        self.compte = creer_compte(user=self.user)
        self.perm = creer_permission(
            code_module='rh', ressource='agent', action='modifier')
        self.role = creer_role(code='R_EV')
        self.role.permissions.add(self.perm)
        self.client.force_authenticate(self.user)

    def test_evaluation_soi_autorisee_pour_titulaire(self):
        creer_attribution(self.compte, self.role)
        reponse = self.client.post(
            '/api/habilitations/evaluer/',
            {'permission': 'rh.agent.modifier'}, format='json')
        self.assertEqual(reponse.status_code, 200)
        corps = reponse.json()
        self.assertTrue(corps['autorise'])
        self.assertTrue(corps['gouverne'])
        self.assertEqual(corps['octrois'][0]['source'], 'ROLE')

    def test_evaluation_soi_refusee_sans_octroi_pour_tous(self):
        reponse = self.client.post(
            '/api/habilitations/evaluer/',
            {'permission': 'rh.agent.modifier'}, format='json')
        corps = reponse.json()
        self.assertFalse(corps['autorise'])
        self.assertIn('AUCUNE_ATTRIBUTION_PERMETTANTE',
                      [m['code'] for m in corps['motifs']])

    def test_evaluation_permission_inconnue(self):
        corps = self.client.post(
            '/api/habilitations/evaluer/',
            {'permission': 'inexistant.rien.fer'}, format='json').json()
        self.assertFalse(corps['autorise'])
        self.assertEqual(corps['motifs'][0]['code'], 'PERMISSION_INCONNUE')

    def test_evaluation_d_autrui_refusee_pour_secretariat(self):
        secretaire = creer_user(username='api-sec', role_existant='SECRETARIAT')
        self.client.force_authenticate(secretaire)
        reponse = self.client.post(
            '/api/habilitations/evaluer/',
            {'permission': 'rh.agent.modifier', 'username': self.user.username},
            format='json')
        self.assertEqual(reponse.status_code, 403)

    def test_evaluation_d_autrui_autorisee_pour_administrateur(self):
        admin = creer_user(username='api-admin', role_existant='ADMIN')
        self.client.force_authenticate(admin)
        reponse = self.client.post(
            '/api/habilitations/evaluer/',
            {'permission': 'rh.agent.modifier', 'username': self.user.username},
            format='json')
        self.assertEqual(reponse.status_code, 200)
        self.assertFalse(reponse.json()['autorise'])

    def test_evaluation_d_autri_inexistant_renvoie_404_pour_administrateur(self):
        admin = creer_user(username='api-admin-404', role_existant='ADMIN')
        self.client.force_authenticate(admin)
        reponse = self.client.post(
            '/api/habilitations/evaluer/',
            {'permission': 'rh.agent.modifier', 'username': 'personne'},
            format='json')
        self.assertEqual(reponse.status_code, 404)

    def test_evaluation_ne_nourrit_pas_les_compteurs_d_observation(self):
        observation.remettre_a_zero()
        self.client.post(
            '/api/habilitations/evaluer/',
            {'permission': 'rh.agent.modifier'}, format='json')
        self.assertEqual(
            observation.etat_observation()['evaluations_total'], 0)


class ObservationsTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        observation.remettre_a_zero()

    def tearDown(self):
        observation.remettre_a_zero()

    def test_synthese_refusee_pour_secretariat(self):
        user = creer_user(username='obs-sec', role_existant='SECRETARIAT')
        self.client.force_authenticate(user)
        self.assertEqual(
            self.client.get('/api/habilitations/observations/synthese/').status_code,
            403)

    def test_synthese_autorisee_pour_administrateur(self):
        admin = creer_user(username='obs-adm', role_existant='ADMIN')
        self.client.force_authenticate(admin)
        reponse = self.client.get('/api/habilitations/observations/synthese/')
        self.assertEqual(reponse.status_code, 200)
        self.assertIn('observations', reponse.json())
        self.assertEqual(reponse.json()['mode'], 'OBSERVATION')

    def test_remise_a_zero_autorisee_pour_administrateur_et_tracee(self):
        from habilitations.models import JournalHabilitation
        admin = creer_user(username='obs-rst', role_existant='ADMIN')
        self.client.force_authenticate(admin)
        avant = JournalHabilitation.objects.count()
        reponse = self.client.post(
            '/api/habilitations/observations/remettre-a-zero/', {}, format='json')
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(
            reponse.json()['observations']['evaluations_total'], 0)
        self.assertGreater(JournalHabilitation.objects.count(), avant)

    def test_remise_a_zero_refusee_pour_secretariat(self):
        user = creer_user(username='obs-rst-sec', role_existant='SECRETARIAT')
        self.client.force_authenticate(user)
        self.assertEqual(
            self.client.post(
                '/api/habilitations/observations/remettre-a-zero/', {},
                format='json').status_code,
            403)


class ReferentielsLectureTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_liste_roles_pour_compte_connecte(self):
        creer_role(code='R_LISTE')
        user = creer_user(username='ref-r', role_existant='ARCHIVE')
        self.client.force_authenticate(user)
        reponse = self.client.get('/api/habilitations/roles/')
        self.assertEqual(reponse.status_code, 200)
        codes = [r['code'] for r in reponse.json()['results']]
        self.assertIn('R_LISTE', codes)

    def test_liste_permissions_pour_compte_connecte(self):
        creer_permission(code_module='lst', ressource='x', action='consulter')
        user = creer_user(username='ref-p', role_existant='ARCHIVE')
        self.client.force_authenticate(user)
        reponse = self.client.get('/api/habilitations/permissions/')
        self.assertEqual(reponse.status_code, 200)
        codes = [r['code'] for r in reponse.json()['results']]
        self.assertIn('lst.x.consulter', codes)


class CapabilitesAdditivesTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_cle_habilitations_pour_compte_non_gouverne(self):
        user = creer_user(username='cap-sec', role_existant='SECRETARIAT')
        self.client.force_authenticate(user)
        corps = self.client.get('/api/auth/capabilities/').json()
        self.assertIn('habilitations', corps)
        self.assertFalse(corps['habilitations']['gouverne'])
        # Ancien contenu strictement intact.
        self.assertEqual(corps['version'], 1)
        self.assertEqual(corps['role'], 'SECRETARIAT')
        self.assertIn('lister', corps['capacites']['participants'])

    def test_ancien_dispositif_intact_pour_finance(self):
        user = creer_user(username='cap-fin', role_existant='FINANCE')
        self.client.force_authenticate(user)
        corps = self.client.get('/api/auth/capabilities/').json()
        self.assertEqual(corps['capacites']['participants'], [])
        self.assertIn('habilitations', corps)

    def test_cle_habilitations_gouverne_pour_compte_profile(self):
        user = creer_user(username='cap-g', role_existant='ARCHIVE')
        creer_compte(user=user)
        self.client.force_authenticate(user)
        corps = self.client.get('/api/auth/capabilities/').json()
        self.assertTrue(corps['habilitations']['gouverne'])
        self.assertEqual(corps['habilitations']['statut'],
                         CompteUtilisateur.Statut.ACTIF)

    @override_settings(HABILITATIONS_OBSERVATION=False,
                       HABILITATIONS_APPLICATION=False)
    def test_cle_indique_le_mode_off_quand_tout_est_eteint(self):
        user = creer_user(username='cap-off', role_existant='ARCHIVE')
        self.client.force_authenticate(user)
        corps = self.client.get('/api/auth/capabilities/').json()
        self.assertEqual(corps['habilitations']['mode'], 'OFF')
