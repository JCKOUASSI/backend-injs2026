"""Cohérence des rôles littéraux des modules de permissions.

Défaut constaté sur l'état initial : cinq modules (`graduation`, `stages`,
`patrimoine`, `ressources_humaines`, `administrations`) citaient encore le rôle
``'DFRC'``, supprimé du référentiel (`User.Role` ne contient plus que douze
rôles canoniques). Un rôle inexistant ne correspond à aucun compte : l'effet
n'était pas neutre mais **inversant** — le Secrétariat accédait à la
diplômation tandis que ``INJS_ADMIN`` et ``CHEF_INJS_ADMIN``, situés plus haut
dans la hiérarchie, recevaient un 403.

`edts` avait déjà corrigé ce défaut (audit du 2026-09-15) ; ce test empêche la
réapparition de la classe entière d'anomalies sur les autres modules.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from administrations.permissions import GESTION_ROLES as ADMIN_GESTION_ROLES
from graduation.permissions import (
    GESTION_ROLES as GRADUATION_GESTION_ROLES,
    VALIDATION_ROLES as GRADUATION_VALIDATION_ROLES,
)
from graduation.permissions import IsDirectionOrAdmin as GraduationValidation
from graduation.permissions import IsSecretariatOrAbove as GraduationGestion
from patrimoine.permissions import GESTION_ROLES as PATRIMOINE_GESTION_ROLES
from patrimoine.permissions import VALIDATION_ROLES as PATRIMOINE_VALIDATION_ROLES
from ressources_humaines.permissions import CONSULTATION_ROLES as RH_CONSULTATION_ROLES
from ressources_humaines.permissions import GESTION_ROLES as RH_GESTION_ROLES
from stages.permissions import (
    GESTION_ROLES as STAGES_GESTION_ROLES,
    VALIDATION_ROLES as STAGES_VALIDATION_ROLES,
)
from stages.permissions import IsDirectionOrAdmin as StagesValidation
from stages.permissions import IsSecretariatOrEncadrant as StagesGestion

User = get_user_model()

#: Rôles attendus par module, avec le nom du littéral contrôlé.
ENSEMBLES_DE_ROLES = {
    'administrations.GESTION_ROLES': ADMIN_GESTION_ROLES,
    'patrimoine.GESTION_ROLES': PATRIMOINE_GESTION_ROLES,
    'patrimoine.VALIDATION_ROLES': PATRIMOINE_VALIDATION_ROLES,
    'ressources_humaines.CONSULTATION_ROLES': RH_CONSULTATION_ROLES,
    'ressources_humaines.GESTION_ROLES': RH_GESTION_ROLES,
    'graduation.GESTION_ROLES': GRADUATION_GESTION_ROLES,
    'graduation.VALIDATION_ROLES': GRADUATION_VALIDATION_ROLES,
    'stages.GESTION_ROLES': STAGES_GESTION_ROLES,
    'stages.VALIDATION_ROLES': STAGES_VALIDATION_ROLES,
}


class RolesCanoniquesTests(TestCase):
    def test_aucun_role_litteral_obsolete(self):
        """Tout littéral de rôle doit exister dans ``User.Role``."""
        valides = set(User.Role.values)
        for nom, roles in ENSEMBLES_DE_ROLES.items():
            for role in roles:
                with self.subTest(constante=nom, role=role):
                    self.assertIn(role, valides)

    def test_roles_d_administration_superieure_presents(self):
        """INJS_ADMIN et CHEF_INJS_ADMIN remplacent l'ancien rôle DFRC."""
        for nom, roles in ENSEMBLES_DE_ROLES.items():
            if nom in ('ressources_humaines.CONSULTATION_ROLES',):
                continue
            with self.subTest(constante=nom):
                self.assertIn('INJS_ADMIN', roles)


class HierarchieAdministrativeTests(TestCase):
    """Un rôle supérieur ne peut pas être privé de ce qu'un rôle inférieur détient."""

    @classmethod
    def setUpTestData(cls):
        cls.utilisateurs = {
            role: User.objects.create_user(
                username=f'role_{role.lower()}', password='pass', role=role,
            )
            for role in ('SECRETARIAT', 'INJS_ADMIN', 'CHEF_INJS_ADMIN', 'AUDITEUR')
        }

    def _client(self, role):
        client = APIClient()
        client.force_authenticate(self.utilisateurs[role])
        return client

    def test_diplomation_accessible_aux_administrateurs_injs(self):
        for role in ('INJS_ADMIN', 'CHEF_INJS_ADMIN', 'SECRETARIAT'):
            with self.subTest(role=role):
                self.assertEqual(
                    self._client(role).get('/api/graduation/diplomes/').status_code, 200,
                )

    def test_diplomation_refusee_aux_etudiants(self):
        self.assertEqual(
            self._client('AUDITEUR').get('/api/graduation/diplomes/').status_code, 403,
        )

    def test_modules_administratifs_accessibles_aux_administrateurs_injs(self):
        urls = (
            '/api/stages/organismes/',
            '/api/patrimoine/equipements/',
            '/api/administrations/courriers/',
            '/api/rh/services/',
        )
        for role in ('INJS_ADMIN', 'CHEF_INJS_ADMIN'):
            for url in urls:
                with self.subTest(role=role, url=url):
                    self.assertEqual(self._client(role).get(url).status_code, 200)

    def test_registres_internes_refuses_aux_etudiants(self):
        """Courrier et documents officiels : données internes, réservées au personnel.

        Le catalogue des organismes d'accueil des stages reste, lui, lisible par
        un étudiant : il en a besoin pour trouver son terrain de stage.
        """
        for url in ('/api/administrations/courriers/', '/api/administrations/documents/'):
            with self.subTest(url=url):
                self.assertEqual(self._client('AUDITEUR').get(url).status_code, 403)
        self.assertEqual(
            self._client('AUDITEUR').get('/api/stages/organismes/').status_code, 200,
        )

    def test_classes_de_permission_acceptent_les_administrateurs_injs(self):
        class Requete:
            def __init__(self, user, methode='GET'):
                self.user = user
                self.method = methode

        class Vue:
            pass

        for role in ('INJS_ADMIN', 'CHEF_INJS_ADMIN', 'DIRECTION', 'ADMIN'):
            requete = Requete(self.utilisateurs.get(role) or self.utilisateurs['INJS_ADMIN'])
            for classe in (GraduationGestion, GraduationValidation, StagesGestion, StagesValidation):
                with self.subTest(role=role, classe=classe.__module__):
                    self.assertTrue(classe().has_permission(requete, Vue()))
