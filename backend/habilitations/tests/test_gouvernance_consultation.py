"""Tests « gouvernance consultable » — catalogue filtrable, matrice réelle
(permissions/actions par cellule, titulaires), impact utilisateur enrichi
(attribuant). Source de vérité : modèles réels, aucun indicateur inventé.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APITestCase

from habilitations.models import AttributionRole
from habilitations.services import impact as service_impact

from . import helpers as fx
from . import _u5_fixtures as fxu5

User = get_user_model()
FLAG_CLE = 'flag.curp_ui_admin'


class PermissionsFiltresTests(APITestCase):
    def setUp(self):
        self.user = fx.creer_user('perm-filtres')
        # Module « sonde » volontairement hors référentiel : les compteurs
        # restent déterministes malgré la migration de données du catalogue.
        self.perm_consulter = fx.creer_permission(
            'gouvernance', 'sonde', 'consulter',
        )
        self.perm_modifier = fx.creer_permission(
            'gouvernance', 'sonde', 'modifier', criticite='CRITIQUE',
        )
        self.perm_scolarite = fx.creer_permission(
            'scolarite', 'annee', 'consulter',
        )
        self.role = fx.creer_role('ROLE_FILTRE', 'Rôle filtre')
        self.role.permissions.add(self.perm_consulter, self.perm_scolarite)

    def tearDown(self):
        from django.core.cache import cache
        cache.clear()
        super().tearDown()

    def test_filtrage_par_module_et_action(self):
        self.client.force_authenticate(self.user)
        par_module = self.client.get(
            '/api/habilitations/permissions/?module=scolarite',
        ).json()
        self.assertEqual(
            {p['module'] for p in par_module['results']}, {'scolarite'},
        )
        par_action = self.client.get(
            '/api/habilitations/permissions/?action=modifier',
        ).json()
        self.assertEqual(
            {p['action'] for p in par_action['results']}, {'modifier'},
        )

    def test_recherche_et_criticite(self):
        self.client.force_authenticate(self.user)
        recherche = self.client.get(
            '/api/habilitations/permissions/?q=gouvernance.sonde',
        ).json()
        self.assertEqual(recherche['count'], 2)
        critiques = self.client.get(
            '/api/habilitations/permissions/?module=gouvernance'
            '&criticite=CRITIQUE',
        ).json()
        self.assertEqual(critiques['count'], 1)
        self.assertEqual(critiques['results'][0]['action'], 'modifier')

    def test_total_roles_refleche_les_octrois_reels(self):
        self.client.force_authenticate(self.user)
        octroyee = self.client.get(
            '/api/habilitations/permissions/?q=gouvernance.sonde.consulter',
        ).json()
        self.assertEqual(octroyee['results'][0]['total_roles'], 1)
        # La permission modifier n'est octroyée par aucun rôle.
        aucune = self.client.get(
            '/api/habilitations/permissions/?q=gouvernance.sonde.modifier',
        ).json()
        self.assertEqual(aucune['results'][0]['total_roles'], 0)


class MatriceEnrichieTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin-matrice', password='Mot#2026x', role='ADMIN',
        )
        fxu5.positionner_flag(FLAG_CLE, True)
        self.perm_a = fx.creer_permission('scolarite', 'annee', 'consulter')
        self.perm_b = fx.creer_permission('scolarite', 'note', 'consulter')
        self.role = fx.creer_role('ROLE_MATRICE', 'Rôle matrice')
        self.role.permissions.add(self.perm_a, self.perm_b)
        self.compte = fx.creer_compte()
        fx.creer_attribution(self.compte, self.role)

    def tearDown(self):
        from django.core.cache import cache
        cache.clear()
        super().tearDown()

    def test_matrice_actions_reelles_et_titulaires(self):
        self.client.force_authenticate(self.admin)
        reponse = self.client.get('/api/habilitations/matrice/')
        self.assertEqual(reponse.status_code, 200)
        ligne = next(
            l for l in reponse.json()['lignes']
            if l['code'] == 'ROLE_MATRICE'
        )
        self.assertEqual(ligne['permissions_count'], 2)
        self.assertEqual(
            sorted(ligne['actions_par_module']['scolarite']),
            ['consulter'],
        )
        self.assertEqual(ligne['comptes_titulaires'], 1)


class ImpactAttribuantTests(TestCase):
    def test_arbre_role_porte_l_attribuant(self):
        attribuant = fx.creer_user('chef-attribuant')
        role = fx.creer_role('ROLE_ATTRUANT', 'Rôle attribué')
        role.permissions.add(fx.creer_permission('scol', 'annee', 'consulter'))
        user = fx.creer_user('hab-cible')
        compte = fx.creer_compte(user=user)
        fx.creer_attribution(compte, role, attribue_par=attribuant)

        donnees = service_impact.impact_utilisateur(user.pk)
        branche = next(
            r for r in donnees['arbre']['roles'] if r['code'] == 'ROLE_ATTRUANT'
        )
        self.assertEqual(branche['attribue_par'], 'chef-attribuant')
        self.assertEqual(branche['niveau_effectif'], role.niveau_defaut)
