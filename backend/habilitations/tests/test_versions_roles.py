"""Tests Lot B — versionnement, comparaison et restauration des rôles.

Le service est testé hors des vues HTTP (pur, déterministe) ; l'API est
testée avec la garde CURP réelle (``ExigeDrapeauAdmin``). Aucun chemin du
moteur RBAC n'est modifié : les tests vérifient aussi que l'attribution de
rôles continue de fonctionner après restauration.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APITestCase

from habilitations.models import (
    AttributionRole,
    JournalHabilitation,
    RoleVersion,
)
from habilitations.services import versions_roles as svc

from . import helpers as fx
from . import _u5_fixtures as fxu5

User = get_user_model()
FLAG_CLE = 'flag.curp_ui_admin'


class VersionsRolesServiceTests(TestCase):
    def setUp(self):
        self.perm_consulter = fx.creer_permission(
            'evaluations', 'note', 'consulter',
        )
        self.perm_modifier = fx.creer_permission(
            'evaluations', 'note', 'modifier', criticite='CRITIQUE',
        )
        self.role = fx.creer_role('ROLE_VER', 'Rôle versionné')
        self.role.permissions.add(self.perm_consulter)

    def test_capture_version_numerotee_et_journalisee(self):
        v1 = svc.capturer_version(self.role, motif='Mise sous version.')
        self.assertEqual(v1.numero, 1)
        self.assertEqual(v1.donnees['permissions'], [
            'evaluations.note.consulter',
        ])
        v2 = svc.capturer_version(self.role, motif='Après retouche.')
        self.assertEqual(v2.numero, 2)
        self.assertTrue(
            JournalHabilitation.objects.filter(
                type_evenement=JournalHabilitation.TypeEvenement.ROLE_VERSIONNE,
            ).exists(),
        )

    def test_instantane_couvre_incompatibilites(self):
        autre = fx.creer_role('ROLE_AUTRE', 'Autre rôle')
        self.role.incompatible_avec.add(autre)
        donnees = svc.instantaner_role(self.role)
        self.assertEqual(donnees['incompatible_avec'], ['ROLE_AUTRE'])

    def test_comparer_roles_diff_permissions(self):
        role_b = fx.creer_role('ROLE_VER_B', 'Rôle B')
        role_b.permissions.add(self.perm_consulter, self.perm_modifier)
        resultat = svc.comparer_roles('ROLE_VER', 'ROLE_VER_B')
        self.assertEqual(resultat['role_a']['code'], 'ROLE_VER')
        self.assertEqual(resultat['permissions_ajoutees'],
                         ['evaluations.note.modifier'])
        self.assertEqual(resultat['permissions_retirees'], [])
        champs = {c['champ'] for c in resultat['champs']}
        self.assertIn('libelle', champs)

    def test_restaurer_version_reapplique_champs_et_permissions(self):
        svc.capturer_version(self.role, motif='État initial.')
        # Modification « hors console » (admin Django) après la capture.
        self.role.libelle = 'Rôle renommé'
        self.role.sensible = True
        self.role.save()
        self.role.permissions.add(self.perm_modifier)

        version = svc.restaurer_version(
            self.role, 1, motif="Retour à l'état initial validé.",
        )
        self.role.refresh_from_db()
        self.assertEqual(self.role.libelle, 'Rôle versionné')
        self.assertFalse(self.role.sensible)
        self.assertEqual(
            set(self.role.permissions.values_list('code', flat=True)),
            {'evaluations.note.consulter'},
        )
        # v1 (initiale) + v2 (avant restauration) + v3 (état restauré).
        self.assertEqual(version.numero, 3)
        self.assertEqual(
            RoleVersion.objects.filter(role=self.role).count(), 3,
        )
        self.assertEqual(
            RoleVersion.objects.get(role=self.role, numero=2).source,
            RoleVersion.Source.AVANT_RESTAURATION,
        )
        self.assertTrue(
            JournalHabilitation.objects.filter(
                type_evenement=JournalHabilitation.TypeEvenement.ROLE_RESTAURE,
            ).exists(),
        )

    def test_restauration_n_altere_pas_le_code_ni_le_moteur(self):
        svc.capturer_version(self.role, motif='Initial.')
        self.role.libelle = 'Renommé'
        self.role.save()
        svc.restaurer_version(self.role, 1, motif='Retour.')
        self.role.refresh_from_db()
        self.assertEqual(self.role.code, 'ROLE_VER')
        # Le moteur RBAC continue d'évaluer les attributions du rôle.
        compte = fx.creer_compte()
        attribution = fx.creer_attribution(compte, self.role)
        self.assertEqual(attribution.statut, AttributionRole.Statut.ACTIVE)

    def test_comparer_versions_renvoie_le_diff(self):
        svc.capturer_version(self.role, motif='Initiale.')
        self.role.libelle = 'Rôle renommé'
        self.role.save()
        self.role.permissions.add(self.perm_modifier)
        svc.capturer_version(self.role, motif='Après retouche.')
        resultat = svc.comparer_versions(self.role, 1, 2)
        self.assertEqual(resultat['de']['numero'], 1)
        self.assertEqual(resultat['vers']['numero'], 2)
        self.assertEqual(resultat['permissions_ajoutees'],
                         ['evaluations.note.modifier'])

    def test_restauration_version_inconnue_echoue(self):
        with self.assertRaises(RoleVersion.DoesNotExist):
            svc.restaurer_version(self.role, 99, motif='Absurde.')

    def test_roles_inconnus_non_comparables(self):
        self.assertIsNone(svc.comparer_roles('ROLE_VER', 'N_IMPORTE'))


class VersionsRolesApiTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin-versions', password='Mot#2026x', role='ADMIN',
        )
        self.simple = User.objects.create_user(
            username='simple-versions', password='Mot#2026x',
            role='SECRETARIAT',
        )
        fxu5.positionner_flag(FLAG_CLE, True)
        self.role = fx.creer_role('ROLE_API_VER', 'Rôle API versions')
        self.perm = fx.creer_permission('scol', 'inscription', 'consulter')
        self.role.permissions.add(self.perm)

    def tearDown(self):
        from django.core.cache import cache
        cache.clear()
        super().tearDown()

    def test_garde_401_et_403(self):
        self.assertEqual(
            self.client.get(
                '/api/habilitations/roles/ROLE_API_VER/versions/',
            ).status_code,
            401,
        )
        self.client.force_authenticate(self.simple)
        self.assertEqual(
            self.client.get(
                '/api/habilitations/roles/ROLE_API_VER/versions/',
            ).status_code,
            403,
        )

    def test_role_inconnu_404(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(
            self.client.get(
                '/api/habilitations/roles/N_IMPORTE/versions/',
            ).status_code,
            404,
        )

    def test_capture_sans_motif_400_puis_avec_motif_201(self):
        self.client.force_authenticate(self.admin)
        vide = self.client.post(
            '/api/habilitations/roles/ROLE_API_VER/versions/', {},
            format='json',
        )
        self.assertEqual(vide.status_code, 400)
        ok = self.client.post(
            '/api/habilitations/roles/ROLE_API_VER/versions/',
            {'motif': 'Mise sous version initiale.'},
            format='json',
        )
        self.assertEqual(ok.status_code, 201)
        self.assertEqual(ok.json()['numero'], 1)

    def test_comparaison_de_deux_roles(self):
        fx.creer_role('ROLE_API_VER_B', 'Rôle B')
        self.client.force_authenticate(self.admin)
        reponse = self.client.get(
            '/api/habilitations/roles/ROLE_API_VER/comparer/'
            '?avec=ROLE_API_VER_B',
        )
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.json()['role_b']['code'], 'ROLE_API_VER_B')

    def test_comparaison_de_deux_versions(self):
        self.client.force_authenticate(self.admin)
        svc.capturer_version(self.role, motif='Initiale.')
        self.role.libelle = 'Rôle renommé'
        self.role.save()
        svc.capturer_version(self.role, motif='Après retouche.')
        reponse = self.client.get(
            '/api/habilitations/roles/ROLE_API_VER/comparer/?de=1&vers=2',
        )
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(
            reponse.json()['champs'][0]['apres'], 'Rôle renommé',
        )

    def test_restauration_via_api_avec_motif_obligatoire(self):
        self.client.force_authenticate(self.admin)
        svc.capturer_version(self.role, motif='Initiale.')
        self.role.libelle = 'Rôle renommé'
        self.role.save()
        sans_motif = self.client.post(
            '/api/habilitations/roles/ROLE_API_VER/versions/1/restaurer/',
            {}, format='json',
        )
        self.assertEqual(sans_motif.status_code, 400)
        ok = self.client.post(
            '/api/habilitations/roles/ROLE_API_VER/versions/1/restaurer/',
            {'motif': 'Décision de gouvernance.'}, format='json',
        )
        self.assertEqual(ok.status_code, 200)
        self.role.refresh_from_db()
        self.assertEqual(self.role.libelle, 'Rôle API versions')

    def test_comparaison_sans_parametres_400(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(
            self.client.get(
                '/api/habilitations/roles/ROLE_API_VER/comparer/',
            ).status_code,
            400,
        )
