"""Tests F8 — couche IMPACT (service, vues d'impact, dashboard).

Nom demandé par le prompt : ``services_impact.py`` ; adapté en
``test_impact_dashboard.py`` car le runner Django ne découvre que les
modules préfixés ``test_``. Aucune règle métier n'est modifiée.

Le service est testé HORS des vues HTTP (déterministe, testable
indépendamment) ; l'API est testée avec la garde CURP réelle
(``ExigeDrapeauAdmin``) : 401 non authentifié, 403 non-administrateur ou
drapeau fermé, 404 objet inconnu, structure JSON stable.
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APITestCase

from habilitations.models import (
    DelegationHabilitation,
    PermissionAttribuee,
)
from habilitations.services import impact as service_impact
from habilitations.services.comptes_admin import permissions_effectives

from . import helpers as fx
from . import _u5_fixtures as fxu5

User = get_user_model()
FLAG_CLE = 'flag.curp_ui_admin'


class ImpactServiceTestsBase:
    """Base commune : petit référentiel dédié (rapide, sans le catalogue complet)."""

    def setUp(self):
        self.perm_note_modifier = fx.creer_permission(
            'evaluations', 'note', 'modifier',
            criticite='CRITIQUE', necessite_motif=True,
        )
        self.perm_note_consulter = fx.creer_permission(
            'evaluations', 'note', 'consulter',
        )
        self.role = fx.creer_role('ROLE_SCOL', 'Scolarité de test')
        self.role.permissions.add(
            self.perm_note_modifier, self.perm_note_consulter
        )
        self.user = fx.creer_user('hab-agent')
        self.compte = fx.creer_compte(user=self.user)
        fx.creer_attribution(self.compte, self.role)


class ImpactPermissionTests(ImpactServiceTestsBase, TestCase):
    def test_impact_permission_complete(self):
        donnees = service_impact.impact_permission('evaluations.note.modifier')
        self.assertEqual(donnees['code'], 'evaluations.note.modifier')
        self.assertEqual(donnees['module'], 'evaluations')
        self.assertEqual(donnees['action'], 'modifier')
        self.assertEqual(donnees['criticite'], 'CRITIQUE')
        self.assertTrue(donnees['sensible'])
        self.assertTrue(donnees['necessite_motif'])
        self.assertEqual(donnees['total_roles'], 1)
        self.assertEqual(donnees['roles'][0]['code'], 'ROLE_SCOL')
        self.assertEqual(donnees['total_comptes_roles'], 1)
        self.assertEqual(donnees['comptes_roles'][0]['username'], 'hab-agent')
        self.assertEqual(donnees['total_comptes'], 1)

    def test_permission_inconnue_renvoie_none(self):
        self.assertIsNone(service_impact.impact_permission('n.importe.quoi'))

    def test_permission_sans_roles(self):
        fx.creer_permission('diplomation', 'diplome', 'valider', criticite='CRITIQUE')
        donnees = service_impact.impact_permission('diplomation.diplome.valider')
        self.assertEqual(donnees['total_roles'], 0)
        self.assertEqual(donnees['total_comptes'], 0)

    def test_octroi_direct_inclus_dans_l_impact(self):
        # Compte SANS rôle : sa dérogation OCTROI est son seul accès.
        user_direct = fx.creer_user('hab-direct')
        compte_direct = fx.creer_compte(user=user_direct)
        fx.creer_derogation(compte_direct, self.perm_note_consulter,
                            statut=PermissionAttribuee.Statut.ACTIVE)
        donnees = service_impact.impact_permission('evaluations.note.consulter')
        self.assertEqual(donnees['total_comptes_derogation'], 1)
        self.assertEqual(donnees['comptes_derogation'][0]['username'],
                         'hab-direct')
        # Le compte titulaire du rôle reste dédupliqué des accès directs.
        self.assertEqual(donnees['total_comptes'], 2)


class ImpactRoleTests(ImpactServiceTestsBase, TestCase):
    def test_impact_role_complete(self):
        donnees = service_impact.impact_role('ROLE_SCOL')
        self.assertEqual(donnees['code'], 'ROLE_SCOL')
        self.assertFalse(donnees['sensible'])
        self.assertEqual(donnees['total_permissions'], 2)
        self.assertEqual(donnees['total_titulaires'], 1)
        self.assertEqual(donnees['titulaires'][0]['username'], 'hab-agent')
        modules = {m['module'] for m in donnees['permissions_par_module']}
        self.assertEqual(modules, {'evaluations'})

    def test_role_inconnu_renvoie_none(self):
        self.assertIsNone(service_impact.impact_role('ROLE_ABSURDE'))

    def test_sensible_est_signale(self):
        role_sensible = fx.creer_role('ROLE_SENS', sensible=True)
        role_sensible.permissions.add(self.perm_note_modifier)
        donnees = service_impact.impact_role('ROLE_SENS')
        self.assertTrue(donnees['sensible'])
        self.assertIn('evaluations.note.modifier', donnees['permissions_sensibles'])


class ImpactModuleTests(ImpactServiceTestsBase, TestCase):
    """Cartographie §28 : MODULE → PERMISSIONS → RÔLES → COMPTES."""

    def test_impact_module_complet(self):
        donnees = service_impact.impact_module('evaluations')
        self.assertEqual(donnees['type'], 'module')
        self.assertEqual(donnees['module'], 'evaluations')
        self.assertEqual(donnees['total_permissions'], 2)
        codes = {p['code'] for p in donnees['permissions']}
        self.assertEqual(
            codes, {'evaluations.note.modifier', 'evaluations.note.consulter'}
        )
        self.assertEqual(donnees['total_roles'], 1)
        self.assertEqual(donnees['roles'][0]['code'], 'ROLE_SCOL')
        self.assertEqual(donnees['roles'][0]['comptes_titulaires'], 1)
        self.assertEqual(donnees['total_comptes'], 1)
        self.assertEqual(donnees['comptes'][0]['username'], 'hab-agent')
        self.assertEqual(donnees['criticite_max'], 'CRITIQUE')

    def test_module_inconnu_renvoie_none(self):
        self.assertIsNone(service_impact.impact_module('module_absurde_xyz'))

    def test_module_catalogue_sans_permissions_cas_vide(self):
        donnees = service_impact.impact_module('administration')
        self.assertEqual(donnees['total_permissions'], 0)
        self.assertEqual(donnees['total_roles'], 0)
        self.assertEqual(donnees['total_comptes'], 0)
        self.assertTrue(donnees['catalogue'])

    def test_module_hors_catalogue_mais_en_base(self):
        fx.creer_permission('module_fictif_xyz', 'dossier', 'consulter')
        donnees = service_impact.impact_module('module_fictif_xyz')
        self.assertIsNotNone(donnees)
        self.assertFalse(donnees['catalogue'])
        self.assertEqual(donnees['total_permissions'], 1)


class ImpactUtilisateurTests(ImpactServiceTestsBase, TestCase):
    def test_impact_utilisateur_complete(self):
        donnees = service_impact.impact_utilisateur(self.user.pk)
        self.assertEqual(donnees['username'], 'hab-agent')
        self.assertEqual(donnees['total_roles'], 1)
        self.assertEqual(donnees['roles'][0]['code'], 'ROLE_SCOL')
        self.assertEqual(donnees['total_effectives'], 2)
        # Cohérence avec la résolution CURP (aucune logique parallèle) :
        self.assertEqual(
            donnees['total_effectives'],
            len(permissions_effectives(self.compte)),
        )
        self.assertEqual(donnees['total_directes'], 0)
        self.assertEqual(donnees['modules_effectifs'][0]['module'], 'evaluations')
        self.assertEqual(donnees['actions_sensibles_effectives'],
                         ['evaluations.note.modifier'])
        # Arbre : rôle → module → permission
        branche = donnees['arbre']['roles'][0]
        self.assertEqual(branche['code'], 'ROLE_SCOL')
        self.assertTrue(any(m['module'] == 'evaluations' for m in branche['modules']))

    def test_octroi_direct_et_retrait_se_distinguent(self):
        perm_ecrire = fx.creer_permission('scolarite', 'dossier', 'creer')
        fx.creer_derogation(self.compte, perm_ecrire,
                            statut=PermissionAttribuee.Statut.ACTIVE)
        fx.creer_derogation(
            self.compte, self.perm_note_consulter,
            sens=PermissionAttribuee.Sens.RETRAIT,
            statut=PermissionAttribuee.Statut.ACTIVE,
        )
        donnees = service_impact.impact_utilisateur(self.user.pk)
        self.assertEqual(donnees['total_directes'], 1)
        self.assertEqual(donnees['octrois_directs'], ['scolarite.dossier.creer'])
        self.assertIn('evaluations.note.consulter', donnees['retraits'])
        # L'effectif CURP est bien déduit : le retrait n'est plus accessible.
        self.assertNotIn('evaluations.note.consulter',
                         permissions_effectives(self.compte))

    def test_delegation_recue_est_signalee(self):
        delegant_user = fx.creer_user('hab-delegant')
        delegant = fx.creer_compte(user=delegant_user)
        delegation = DelegationHabilitation.objects.create(
            delegant=delegant, delegataire=self.compte,
            date_debut=fx.date_il_y_a(1), date_fin=fx.date_dans(5),
            motif='Délégation de test.',
            statut=DelegationHabilitation.Statut.ACTIVE,
        )
        delegation.roles.add(self.role)
        donnees = service_impact.impact_utilisateur(self.user.pk)
        self.assertEqual(donnees['delegations_recues'][0]['delegant']['username'],
                         'hab-delegant')
        self.assertIn('ROLE_SCOL', donnees['delegations_recues'][0]['roles'])

    def test_compte_sans_roles_cas_vide(self):
        user_vide = fx.creer_user('hab-vide')
        fx.creer_compte(user=user_vide)
        donnees = service_impact.impact_utilisateur(user_vide.pk)
        self.assertEqual(donnees['total_roles'], 0)
        self.assertEqual(donnees['total_effectives'], 0)
        self.assertEqual(donnees['arbre']['roles'], [])

    def test_utilisateur_inconnu_renvoie_none(self):
        self.assertIsNone(service_impact.impact_utilisateur(999999))


class ImpactApiTests(APITestCase):
    """Garde CURP réelle + contrats JSON des vues d'impact."""

    @classmethod
    def setUpTestData(cls):
        cls.perm = fx.creer_permission(
            'evaluations', 'note', 'modifier', criticite='CRITIQUE',
        )
        cls.role = fx.creer_role('ROLE_API', 'Rôle API de test')
        cls.role.permissions.add(cls.perm)
        cls.user_cible = fx.creer_user('hab-api-cible')
        cls.compte_cible = fx.creer_compte(user=cls.user_cible)
        fx.creer_attribution(cls.compte_cible, cls.role)

    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin-impact', password='Mot#2026x', role='ADMIN',
        )
        self.simple = User.objects.create_user(
            username='simple-impact', password='Mot#2026x', role='SECRETARIAT',
        )
        fxu5.positionner_flag(FLAG_CLE, True)

    def tearDown(self):
        from django.core.cache import cache
        cache.clear()
        super().tearDown()

    def test_non_authentifie_401(self):
        reponse = self.client.get('/api/habilitations/dashboard/')
        self.assertEqual(reponse.status_code, 401)

    def test_non_administrateur_403(self):
        self.client.force_authenticate(self.simple)
        reponse = self.client.get('/api/habilitations/dashboard/')
        self.assertEqual(reponse.status_code, 403)

    def test_admin_sans_drapeau_403(self):
        fxu5.positionner_flag(FLAG_CLE, False)
        self.client.force_authenticate(self.admin)
        reponse = self.client.get('/api/habilitations/dashboard/')
        self.assertEqual(reponse.status_code, 403)

    def test_impact_permission_200(self):
        self.client.force_authenticate(self.admin)
        reponse = self.client.get(
            '/api/habilitations/impact/permission/evaluations.note.modifier/'
        )
        self.assertEqual(reponse.status_code, 200)
        donnees = reponse.json()
        self.assertEqual(donnees['code'], 'evaluations.note.modifier')
        self.assertEqual(donnees['type'], 'permission')
        self.assertIn('roles', donnees)
        self.assertIn('total_comptes', donnees)

    def test_impact_permission_inconnue_404(self):
        self.client.force_authenticate(self.admin)
        reponse = self.client.get(
            '/api/habilitations/impact/permission/n.importe.quoi/'
        )
        self.assertEqual(reponse.status_code, 404)
        self.assertEqual(reponse.json()['code'], 'PERMISSION_INCONNUE')

    def test_impact_role_200_et_404(self):
        self.client.force_authenticate(self.admin)
        ok = self.client.get('/api/habilitations/impact/role/ROLE_API/')
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.json()['type'], 'role')
        self.assertIn('titulaires', ok.json())
        absent = self.client.get('/api/habilitations/impact/role/ROLE_ABSURDE/')
        self.assertEqual(absent.status_code, 404)
        self.assertEqual(absent.json()['code'], 'ROLE_INCONNU')

    def test_impact_module_200_et_404(self):
        self.client.force_authenticate(self.admin)
        ok = self.client.get('/api/habilitations/impact/module/evaluations/')
        self.assertEqual(ok.status_code, 200)
        donnees = ok.json()
        self.assertEqual(donnees['type'], 'module')
        self.assertEqual(donnees['module'], 'evaluations')
        self.assertIn('permissions', donnees)
        self.assertIn('roles', donnees)
        self.assertIn('total_comptes', donnees)
        absent = self.client.get('/api/habilitations/impact/module/module_absurde_xyz/')
        self.assertEqual(absent.status_code, 404)
        self.assertEqual(absent.json()['code'], 'MODULE_INCONNU')

    def test_impact_module_non_administrateur_403(self):
        self.client.force_authenticate(self.simple)
        reponse = self.client.get('/api/habilitations/impact/module/evaluations/')
        self.assertEqual(reponse.status_code, 403)

    def test_impact_utilisateur_200_et_404(self):
        self.client.force_authenticate(self.admin)
        ok = self.client.get(
            f'/api/habilitations/impact/utilisateur/{self.user_cible.pk}/'
        )
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.json()['username'], 'hab-api-cible')
        self.assertEqual(ok.json()['type'], 'utilisateur')
        self.assertIn('arbre', ok.json())
        absent = self.client.get('/api/habilitations/impact/utilisateur/999999/')
        self.assertEqual(absent.status_code, 404)
        self.assertEqual(absent.json()['code'], 'COMPTE_INCONNU')

    def test_dashboard_200_structure(self):
        self.client.force_authenticate(self.admin)
        reponse = self.client.get('/api/habilitations/dashboard/')
        self.assertEqual(reponse.status_code, 200)
        donnees = reponse.json()
        for cle in ('comptes', 'roles', 'permissions', 'comptes_privileges',
                    'derogations', 'delegations', 'provisionnement',
                    'dernieres_actions'):
            self.assertIn(cle, donnees)
        self.assertEqual(donnees['permissions']['par_module'][0]['module'],
                         'evaluations')
        self.assertGreaterEqual(donnees['comptes']['total'], 1)

    def test_dashboard_lot_a_habilitations_et_alertes(self):
        """Lot A : compteurs d'habilitations + alertes prioritaires."""
        # Attribution échue : encore ACTIVE, date_fin dépassée → alerte revue.
        role_etanche = fx.creer_role('ROLE_ETANCHE', 'Rôle échue de test')
        user_echu = fx.creer_user('hab-echu')
        compte_echu = fx.creer_compte(user=user_echu)
        fx.creer_attribution(
            compte_echu, role_etanche,
            date_fin=timezone.localdate() - timedelta(days=3),
        )

        # Conflit de séparation des tâches : deux rôles incompatibles portés
        # simultanément par le même compte.
        role_a = fx.creer_role('ROLE_SOD_A', 'SoD A')
        role_b = fx.creer_role('ROLE_SOD_B', 'SoD B')
        role_a.incompatible_avec.add(role_b)
        user_sod = fx.creer_user('hab-sod')
        compte_sod = fx.creer_compte(user=user_sod)
        fx.creer_attribution(compte_sod, role_a)
        fx.creer_attribution(compte_sod, role_b)

        self.client.force_authenticate(self.admin)
        donnees = self.client.get('/api/habilitations/dashboard/').json()

        for cle in ('habilitations', 'alertes'):
            self.assertIn(cle, donnees)
        self.assertIn('actives', donnees['habilitations'])
        self.assertIn('expirant_prochainement', donnees['habilitations'])
        self.assertIn('echues', donnees['habilitations'])
        self.assertEqual(donnees['habilitations']['echues'], 1)

        alertes = donnees['alertes']
        self.assertGreaterEqual(alertes['habilitations_echues'], 1)
        self.assertGreaterEqual(
            alertes['conflits_separation_taches']['total'], 1,
        )
        codes_exemple = {
            tuple(exemple['roles'])
            for exemple in alertes['conflits_separation_taches']['exemples']
        }
        self.assertIn(('ROLE_SOD_A', 'ROLE_SOD_B'), codes_exemple)
        # Le seuil d'inactivité dérive de la politique de sécurité réelle.
        self.assertIn('seuil_jours', alertes['comptes_inactifs'])

    def test_dashboard_sans_conflit_alertes_vides(self):
        """Sans attribution incompatible, aucun conflit SoD n'est signalé."""
        self.client.force_authenticate(self.admin)
        donnees = self.client.get('/api/habilitations/dashboard/').json()
        self.assertEqual(
            donnees['alertes']['conflits_separation_taches']['total'], 0,
        )

    def test_acces_transversal_permission_sensible_exposee_nulle_part(self):
        # Un non-administrateur ne doit pas obtenir la moindre donnée
        # d'habilitation, même en devinant l'URL d'un impact.
        self.client.force_authenticate(self.simple)
        for url in (
            '/api/habilitations/impact/permission/evaluations.note.modifier/',
            '/api/habilitations/impact/role/ROLE_API/',
            f'/api/habilitations/impact/utilisateur/{self.user_cible.pk}/',
        ):
            self.assertEqual(self.client.get(url).status_code, 403)
