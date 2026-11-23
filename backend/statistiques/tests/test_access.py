"""Tests d'étanchéité des données — module Statistiques."""
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from authentication.models import User
from formations.models import Formation, Module, Secretariat
from statistiques.access import resolve_stats_scope, rapport_accessible, user_secretariat_scope_locked
from statistiques.models import ConfigAlerteSeuil, Rapport


def make_user(username, role='INJS_ADMIN', **kwargs):
    return User.objects.create_user(username=username, password='pass', role=role, **kwargs)


class ResolveStatsScopeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sec_a = Secretariat.objects.create(nom='Sec A')
        cls.sec_b = Secretariat.objects.create(nom='Sec B')
        cls.formation = Formation.objects.create(formation='Cycle scope')
        cls.module_a = Module.objects.create(
            formation=cls.formation, intitule='Mod A', secretariat=cls.sec_a,
        )
        cls.module_b = Module.objects.create(
            formation=cls.formation, intitule='Mod B', secretariat=cls.sec_b,
        )

    def test_secretariat_forced_to_own_secretariat(self):
        user = make_user('sec_user', role='SECRETARIAT', secretariat=self.sec_a)
        scope, err = resolve_stats_scope(user, secretariat_id=self.sec_b.id)
        self.assertIsNotNone(err)
        self.assertIn('non autorisé', err.lower())

    def test_secretariat_default_scope(self):
        user = make_user('sec_user2', role='CHEF_SECRETARIAT', secretariat=self.sec_a)
        scope, err = resolve_stats_scope(user)
        self.assertIsNone(err)
        self.assertEqual(scope.secretariat_id, self.sec_a.id)

    def test_user_secretariat_scope_locked(self):
        sec = make_user('sec_lock', role='SECRETARIAT', secretariat=self.sec_a)
        admin = make_user('admin_lock', role='INJS_ADMIN')
        self.assertTrue(user_secretariat_scope_locked(sec))
        self.assertFalse(user_secretariat_scope_locked(admin))

    def test_encadrant_limited_to_supervised_modules(self):
        enc = make_user('enc_user', role='ENCADRANT')
        self.module_a.superviseur = enc
        self.module_a.save(update_fields=['superviseur'])
        scope, err = resolve_stats_scope(enc)
        self.assertIsNone(err)
        self.assertEqual(scope.module_ids, [self.module_a.id])

    def test_encadrant_rejects_foreign_secretariat(self):
        enc = make_user('enc_user2', role='ENCADRANT')
        self.module_a.superviseur = enc
        self.module_a.save(update_fields=['superviseur'])
        _, err = resolve_stats_scope(enc, secretariat_id=self.sec_b.id)
        self.assertIsNotNone(err)

    def test_admin_global_scope(self):
        admin = make_user('admin_stats', role='INJS_ADMIN')
        scope, err = resolve_stats_scope(admin, secretariat_id=self.sec_b.id)
        self.assertIsNone(err)
        self.assertEqual(scope.secretariat_id, self.sec_b.id)
        self.assertIsNone(scope.module_ids)


class StatistiquesAPIAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sec_a = Secretariat.objects.create(nom='Sec API A')
        cls.sec_b = Secretariat.objects.create(nom='Sec API B')
        cls.formation = Formation.objects.create(formation='Cycle API')
        cls.module_a = Module.objects.create(formation=cls.formation, intitule='M A', secretariat=cls.sec_a)
        cls.module_b = Module.objects.create(formation=cls.formation, intitule='M B', secretariat=cls.sec_b)

    def setUp(self):
        self.client = APIClient()

    def test_secretariat_cannot_query_other_secretariat_dashboard(self):
        user = make_user('sec_api', role='SECRETARIAT', secretariat=self.sec_a)
        self.client.force_authenticate(user)
        res = self.client.get(f'/api/statistiques/?secretariat_id={self.sec_b.id}&sections=kpis')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_secretariat_sees_only_own_secretariat_in_list(self):
        user = make_user('sec_api2', role='SECRETARIAT', secretariat=self.sec_a)
        self.client.force_authenticate(user)
        res = self.client.get('/api/statistiques/?sections=secretariats_liste')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data['secretariats_liste']), 1)
        self.assertEqual(res.data['secretariats_liste'][0]['id'], self.sec_a.id)

    def test_secretariats_stats_limited_for_secretariat_role(self):
        user = make_user('sec_api3', role='SECRETARIAT', secretariat=self.sec_a)
        self.client.force_authenticate(user)
        res = self.client.get('/api/statistiques/secretariats/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['total'], 1)
        self.assertEqual(res.data['secretariats'][0]['secretariat_id'], self.sec_a.id)

    def test_secretariat_point_journalier_scoped_to_own_modules(self):
        from formations.models import SessionModule
        from datetime import date

        user = make_user('sec_pj', role='SECRETARIAT', secretariat=self.sec_a)
        self.client.force_authenticate(user)
        jour = date.today()
        SessionModule.objects.create(
            module=self.module_a,
            date_journee=jour,
            numero=1,
            intitule='Séance PJ A',
        )
        SessionModule.objects.create(
            module=self.module_b,
            date_journee=jour,
            numero=1,
            intitule='Séance PJ B',
        )
        res = self.client.get(
            f'/api/statistiques/point-journalier/?annee={jour.year}&mois={jour.month}&tous_tableaux=1',
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        mod_ids = set()
        for tb in res.data.get('tableaux_complets') or res.data.get('tableaux') or []:
            payload = tb.get('tableau', tb)
            for creneau in ('matin', 'soir'):
                bloc = payload.get(creneau) or {}
                for grp in bloc.get('groupes') or []:
                    mod_ids.update(grp.get('module_ids') or [])
        if mod_ids:
            self.assertTrue(mod_ids.issubset({self.module_a.id}))
        res_other = self.client.get(
            f'/api/statistiques/point-journalier/?annee={jour.year}&secretariat_id={self.sec_b.id}',
        )
        self.assertEqual(res_other.status_code, status.HTTP_403_FORBIDDEN)

    def test_secretariat_bilans_scoped_to_own_modules(self):
        from formations.models import SessionModule
        from datetime import date

        user = make_user('sec_bl', role='CHEF_SECRETARIAT', secretariat=self.sec_a)
        self.client.force_authenticate(user)
        jour = date.today()
        SessionModule.objects.create(module=self.module_a, date_journee=jour, numero=1, intitule='Séance BL A')
        SessionModule.objects.create(module=self.module_b, date_journee=jour, numero=1, intitule='Séance BL B')
        res = self.client.get(
            f'/api/statistiques/bilans/?annee={jour.year}&mois={jour.month}&dimension=module',
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        mod_ids = {b['module_id'] for b in res.data.get('bilans', []) if b.get('module_id')}
        if mod_ids:
            self.assertTrue(mod_ids.issubset({self.module_a.id}))
        res_other = self.client.get(
            f'/api/statistiques/bilans/?annee={jour.year}&secretariat_id={self.sec_b.id}&dimension=module',
        )
        self.assertEqual(res_other.status_code, status.HTTP_403_FORBIDDEN)

    def test_encadrant_without_modules_can_open_dashboard(self):
        enc = make_user('enc_empty', role='ENCADRANT')
        self.client.force_authenticate(enc)
        res = self.client.get('/api/statistiques/?sections=kpis')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['kpis']['modules'], 0)

    def test_legacy_dfrc_alias_maps_to_injs_admin(self):
        """L'alias historique DFRC pointe vers le rôle canonique INJS_ADMIN.

        Lot L4b : `User.role` n'accepte plus que les 12 rôles RBAC canoniques,
        donc `DFRC` ne peut plus être écrit en base. C'est désormais
        `statistiques.access.ROLE_ALIASES` — et non le champ lui-même — qui
        assure la compatibilité de lecture. Le test vérifie donc l'alias, et
        non une écriture devenue impossible.
        """
        from statistiques.access import ROLE_ALIASES, _normalize_stats_roles

        self.assertEqual(ROLE_ALIASES['DFRC'], 'INJS_ADMIN')
        self.assertIn('INJS_ADMIN', _normalize_stats_roles({'DFRC'}))

        # Le compte réel porte le rôle canonique : il accède au dashboard.
        user = make_user('dfrc_alias', role='INJS_ADMIN')
        self.client.force_authenticate(user)
        res = self.client.get('/api/statistiques/?sections=kpis')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_put_alertes_seuils_accepts_list_body(self):
        admin = make_user('admin_seuils', role='INJS_ADMIN')
        ConfigAlerteSeuil.objects.create(
            indicateur='taux_presence',
            seuil_avertissement=75,
            seuil_critique=60,
            actif=True,
        )
        self.client.force_authenticate(admin)
        res = self.client.put(
            '/api/statistiques/alertes/seuils/',
            [
                {
                    'indicateur': 'taux_presence',
                    'seuil_avertissement': 80,
                    'seuil_critique': 65,
                    'actif': True,
                },
            ],
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['detail'], 'Seuils mis à jour.')
        seuil = ConfigAlerteSeuil.objects.get(indicateur='taux_presence')
        self.assertEqual(seuil.seuil_avertissement, 80)
        self.assertEqual(seuil.seuil_critique, 65)


class RapportAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sec_a = Secretariat.objects.create(nom='Sec Rap A')
        cls.sec_b = Secretariat.objects.create(nom='Sec Rap B')
        cls.gen = make_user('gen', role='SECRETARIAT', secretariat=cls.sec_a)
        cls.other = make_user('other_sec', role='SECRETARIAT', secretariat=cls.sec_b)
        cls.admin = make_user('admin_rap', role='INJS_ADMIN')
        cls.rapport = Rapport.objects.create(
            titre='Rapport test',
            type=Rapport.Type.MENSUEL,
            periode_debut='2026-01-01',
            periode_fin='2026-01-31',
            secretariat=cls.sec_a,
            generateur=cls.gen,
        )

    def test_rapport_accessible_same_secretariat(self):
        self.assertTrue(rapport_accessible(self.gen, self.rapport))

    def test_rapport_not_accessible_other_secretariat(self):
        self.assertFalse(rapport_accessible(self.other, self.rapport))

    def test_rapport_list_filtered_for_secretariat(self):
        client = APIClient()
        client.force_authenticate(self.other)
        res = client.get('/api/statistiques/rapports/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data, [])
