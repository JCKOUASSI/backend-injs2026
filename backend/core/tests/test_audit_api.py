"""Tests d'API du journal d'audit unifié : flag, rôles, filtres, lecture seule."""
from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from authentication.models import User
from core.audit_services import FLAG_LOT1, enregistrer_evenement
from core.models import EvenementAudit
from parametres.flags import FLAGS_CACHE_KEY
from parametres.models import Parametre

URL = '/api/core/audit/'


def _positionner_flag(valeur):
    Parametre.objects.update_or_create(
        cle=FLAG_LOT1,
        defaults=dict(
            libelle=FLAG_LOT1, categorie='flags', type='bool',
            valeur=valeur, valeur_defaut='false', modifiable=True,
            modifiable_par_roles='["ADMIN", "CHEF_INJS_ADMIN", "INJS_ADMIN"]',
            lecturable_par_roles='["ADMIN", "CHEF_INJS_ADMIN", "INJS_ADMIN"]',
            actif=True))
    cache.delete(FLAGS_CACHE_KEY)


def activer_flag_lot1():
    _positionner_flag('true')


def desactiver_flag_lot1():
    _positionner_flag('false')


class AuditCoreAPITests(APITestCase):
    def setUp(self):
        desactiver_flag_lot1()
        cache.clear()

    def tearDown(self):
        desactiver_flag_lot1()
        cache.clear()

    def _user(self, username, role):
        return User.objects.create_user(
            username=username, password='x', role=role)

    def test_anonyme_refuse(self):
        reponse = self.client.get(URL)
        self.assertEqual(reponse.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_role_autorise_mas_flag_off_refuse(self):
        # Le kill switch s'applique aussi aux administrateurs.
        admin = self._user('admin1', User.Role.ADMIN)
        self.client.force_authenticate(admin)
        self.assertEqual(self.client.get(URL).status_code, status.HTTP_403_FORBIDDEN)

    def test_matrice_des_roles_avec_flag_actif(self):
        activer_flag_lot1()
        autorises = (
            User.Role.ADMIN, User.Role.DIRECTION, User.Role.CHEF_INJS_ADMIN,
            User.Role.INJS_ADMIN, User.Role.AUDITEUR, User.Role.ARCHIVE,
        )
        interdits = (
            User.Role.CHEF_SECRETARIAT, User.Role.SECRETARIAT, User.Role.FINANCE,
            User.Role.ENCADRANT, User.Role.SUPERVISEUR, User.Role.FORMATEUR,
        )
        for role in autorises:
            with self.subTest(role=role):
                user = self._user(f'ok_{role}', role)
                self.client.force_authenticate(user)
                self.assertEqual(
                    self.client.get(URL).status_code, status.HTTP_200_OK, role)
        for role in interdits:
            with self.subTest(role=role):
                user = self._user(f'ko_{role}', role)
                self.client.force_authenticate(user)
                self.assertEqual(
                    self.client.get(URL).status_code, status.HTTP_403_FORBIDDEN, role)

    def test_liste_paginee_et_detail_par_code(self):
        activer_flag_lot1()
        admin = self._user('admin2', User.Role.ADMIN)
        self.client.force_authenticate(admin)
        evt = enregistrer_evenement(
            source=EvenementAudit.Source.SCOLARITE, action='JURY_DECISION',
            acteur=admin, objet_libelle='Jury de démo')
        reponse = self.client.get(URL)
        self.assertEqual(reponse.status_code, status.HTTP_200_OK)
        donnees = reponse.json()
        self.assertIn('results', donnees)
        self.assertTrue(any(
            ligne['code'] == evt.code for ligne in donnees['results']))
        detail = self.client.get(URL + f'{evt.code}/')
        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        self.assertEqual(detail.data['code'], evt.code)
        self.assertEqual(detail.data['source'], 'scolarite')

    def test_filtres_de_liste(self):
        activer_flag_lot1()
        admin = self._user('admin3', User.Role.ADMIN)
        autre = self._user('autre', User.Role.DIRECTION)
        self.client.force_authenticate(admin)
        recent = enregistrer_evenement(
            source=EvenementAudit.Source.PRESENCES, action='USER_LOGIN',
            acteur=admin, objet_libelle='Session')
        enregistrer_evenement(
            source=EvenementAudit.Source.SCOLARITE, action='JURY_DECISION',
            acteur=autre, objet_libelle='Jury',
            horodatage=timezone.now() - timedelta(days=10))

        reponse = self.client.get(URL, {'source': 'presences'})
        codes = [l['code'] for l in reponse.json()['results']]
        self.assertEqual(codes, [recent.code])

        reponse = self.client.get(URL, {'action': 'JURY_DECISION'})
        self.assertEqual(len(reponse.json()['results']), 1)

        reponse = self.client.get(URL, {'acteur': admin.pk})
        self.assertEqual(len(reponse.json()['results']), 1)

        reponse = self.client.get(
            URL, {'date_debut': (timezone.localdate() - timedelta(days=1)).isoformat()})
        self.assertEqual(len(reponse.json()['results']), 1)

        reponse = self.client.get(URL, {'objet': 'Jury'})
        self.assertEqual(len(reponse.json()['results']), 1)

    def test_pas_d_ecriture_possible(self):
        activer_flag_lot1()
        admin = self._user('admin4', User.Role.ADMIN)
        self.client.force_authenticate(admin)
        for methode in ('post', 'put', 'patch', 'delete'):
            reponse = getattr(self.client, methode)(URL, {})
            self.assertIn(
                reponse.status_code,
                (status.HTTP_403_FORBIDDEN, status.HTTP_405_METHOD_NOT_ALLOWED),
                methode,
            )

    def test_route_presente_dans_le_schema_openapi(self):
        activer_flag_lot1()
        admin = self._user('admin5', User.Role.ADMIN)
        self.client.force_authenticate(admin)
        schema = self.client.get('/api/schema/')
        self.assertEqual(schema.status_code, status.HTTP_200_OK)
        self.assertIn('/api/core/audit/', schema.content.decode())
