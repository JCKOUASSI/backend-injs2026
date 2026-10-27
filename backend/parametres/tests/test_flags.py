"""Tests P00-08 — feature flags : helper, cache, permission, endpoint, seed.

Les flags sont livrés DÉSACTIVÉS et n'altèrent aucun comportement métier.
"""

from types import SimpleNamespace

from django.core.cache import cache
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from authentication.models import User
from parametres.flags import (
    FLAGS_CACHE_KEY,
    FLAG_PREFIX,
    flags_for_user,
    invalidate_flags_cache,
    is_enabled,
    require_flag,
)
from importlib import import_module

from parametres.models import Parametre, ParametreHistorique


# Contrat du seed (migration 0004) : un flag par lot + le flag de réserve G2.
SEED_FLAGS = [
    'flag.lot01_socle_referentiels_rbac',
    'flag.lot02_verrous_maquettes_notes',
    'flag.lot03_admissions_chaine_depense',
    'flag.lot04_fiches_360_pedagogie',
    'flag.lot05_charge_enseignants',
    'flag.lot06_edt_campus_patrimoine',
    'flag.lot07_qr_rh_ged',
    'flag.lot08_evaluations_jurys_cloture_comptable',
    'flag.lot09_finances_etudiantes_decisionnel',
    'flag.lot10_organisation_administrative',
    'flag.lot11_notifications_multicanal',
    'flag.lot12_securite_retrait_legacy',
    'flag.g2_niveaux_n4_validation',
]


def make_user(username, role='ADMIN', **kwargs):
    return User.objects.create_user(username=username, password='pass', role=role, **kwargs)


def make_bool_flag(cle, valeur='false', actif=True, lecturable=None):
    return Parametre.objects.create(
        cle=cle,
        libelle=cle,
        categorie='flags',
        type='bool',
        valeur=valeur,
        valeur_defaut='false',
        modifiable=True,
        modifiable_par_roles='["ADMIN", "CHEF_INJS_ADMIN", "INJS_ADMIN"]',
        lecturable_par_roles=lecturable or '["ADMIN", "CHEF_INJS_ADMIN", "INJS_ADMIN"]',
        actif=actif,
    )


class FeatureFlagsSeedTests(TestCase):
    def test_les_flags_initiaux_sont_seedes_et_tous_eteints(self):
        flags = Parametre.objects.filter(cle__startswith=FLAG_PREFIX)
        cles = list(flags.values_list('cle', flat=True))
        for attendue in SEED_FLAGS:
            self.assertIn(attendue, cles)
        for flag in flags:
            self.assertEqual(flag.type, 'bool')
            self.assertEqual(flag.categorie, 'flags')
            self.assertEqual(flag.valeur, 'false')
            self.assertTrue(flag.actif)
            # Aucun flag seedé n'est activé.
            self.assertFalse(is_enabled(flag.cle))

    def test_la_migration_est_reversible(self):
        migration = import_module('parametres.migrations.0004_feature_flags_seed')
        # La migration reçoit historiquement un registre « apps » ; on lui passe
        # les modèles réels (la transaction du TestCase annulera la suppression).
        fake_apps = SimpleNamespace(get_model=lambda _app, model: Parametre if model == 'Parametre' else None)
        migration.unseed_feature_flags(fake_apps, None)
        self.assertFalse(
            Parametre.objects.filter(cle__in=SEED_FLAGS).exists(),
            'Le reverse de la migration doit supprimer les flags seedés',
        )


class IsEnabledTests(TestCase):
    def setUp(self):
        cache.clear()  # Autorisé en test : isole le cache entre cas de test.

    def tearDown(self):
        cache.clear()

    def test_flag_inconnu_ou_vide_est_eteint(self):
        self.assertFalse(is_enabled('flag.inexistant'))
        self.assertFalse(is_enabled(''))
        self.assertFalse(is_enabled(None))

    def test_flag_booleen_eteint_puis_allume(self):
        flag = make_bool_flag('flag.test_bool')
        admin = make_user('u_bool')
        self.assertFalse(is_enabled('flag.test_bool', admin))
        flag.valeur = 'true'
        flag.save()
        self.assertTrue(is_enabled('flag.test_bool', admin))

    def test_flag_inactif_reste_eteint_meme_valeur_true(self):
        make_bool_flag('flag.test_inactif', valeur='true', actif=False)
        self.assertFalse(is_enabled('flag.test_inactif', make_user('u_inact')))

    def test_le_kill_switch_ne_connait_pas_de_passe_droit_superuser(self):
        # Un administrateur superuser ne force PAS un flag éteint : c'est le
        # gage d'une extinction d'urgence efficace pour tout le monde.
        su = User.objects.create_superuser(username='su_flags', password='x', role='ADMIN')
        make_bool_flag('flag.test_killswitch', valeur='false')
        self.assertFalse(is_enabled('flag.test_killswitch', su))

    def test_flag_par_liste_de_roles(self):
        Parametre.objects.create(
            cle='flag.test_roles', libelle='rôles', categorie='flags', type='text',
            valeur='["SECRETARIAT"]', valeur_defaut='[]',
            modifiable=True,
            modifiable_par_roles='["ADMIN"]',
            lecturable_par_roles='["ADMIN"]', actif=True,
        )
        secretariat = make_user('u_sec', role='SECRETARIAT')
        admin = make_user('u_adm', role='ADMIN')
        self.assertTrue(is_enabled('flag.test_roles', secretariat))
        self.assertFalse(is_enabled('flag.test_roles', admin))
        # Sans utilisateur, une liste de rôles ne peut pas être évaluée → éteint.
        self.assertFalse(is_enabled('flag.test_roles'))

    def test_liste_de_roles_vide_eteint_pour_tous(self):
        Parametre.objects.create(
            cle='flag.test_roles_vide', libelle='rôles vides', categorie='flags', type='text',
            valeur='[]', valeur_defaut='[]', modifiable=True,
            modifiable_par_roles='["ADMIN"]', lecturable_par_roles='["ADMIN"]', actif=True,
        )
        self.assertFalse(is_enabled('flag.test_roles_vide', make_user('u_vide', role='SECRETARIAT')))

    def test_invalidation_immediate_du_cache_apres_ecriture(self):
        flag = make_bool_flag('flag.test_cache')
        # Premier appel : peuple le cache.
        self.assertFalse(is_enabled('flag.test_cache'))
        self.assertIn('flag.test_cache', cache.get(FLAGS_CACHE_KEY))
        # Bascule passant par une écriture ORM réelle (signal post_save) :
        # aucun cache.clear() ici, l'effet doit être immédiat.
        flag.valeur = 'true'
        flag.save()
        self.assertTrue(is_enabled('flag.test_cache'))

    def test_invalidation_apres_suppression(self):
        flag = make_bool_flag('flag.test_delete')
        self.assertFalse(is_enabled('flag.test_delete'))
        flag.delete()
        self.assertFalse(is_enabled('flag.test_delete', make_user('u_del')))


class RequireFlagPermissionTests(TestCase):
    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_permission_refuse_quand_eteint_puis_accepte_quand_allume(self):
        make_bool_flag('flag.test_perm')
        admin = make_user('u_perm')
        request = SimpleNamespace(user=admin)
        permission = require_flag('flag.test_perm')()
        self.assertFalse(permission.has_permission(request, None))
        flag = Parametre.objects.get(cle='flag.test_perm')
        flag.valeur = 'true'
        flag.save()
        self.assertTrue(permission.has_permission(request, None))

    def test_permission_sur_flag_inconnu_refuse(self):
        request = SimpleNamespace(user=make_user('u_inconnu'))
        self.assertFalse(require_flag('flag.jaimais')().has_permission(request, None))


class FeatureFlagsEndpointTests(TestCase):
    URL = '/api/parametres/flags/'

    def setUp(self):
        cache.clear()
        self.client = APIClient()

    def tearDown(self):
        cache.clear()

    def test_anonyme_refuse(self):
        res = self.client.get(self.URL)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_carte_booleenne_pour_un_utilisateur_authentifie(self):
        make_bool_flag('flag.test_api_off')
        make_bool_flag('flag.test_api_on', valeur='true')
        admin = make_user('u_api')
        self.client.force_authenticate(admin)
        res = self.client.get(self.URL)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        flags = res.data['flags']
        self.assertIsInstance(flags, dict)
        self.assertFalse(flags['flag.test_api_off'])
        self.assertTrue(flags['flag.test_api_on'])
        # La réponse ne contient QUE des booléens (jamais la liste des rôles).
        for valeur in flags.values():
            self.assertIsInstance(valeur, bool)

    def test_flag_par_roles_non_fuite_dans_la_reponse(self):
        Parametre.objects.create(
            cle='flag.test_api_roles', libelle='rôles', categorie='flags', type='text',
            valeur='["SECRETARIAT"]', valeur_defaut='[]', modifiable=True,
            modifiable_par_roles='["ADMIN"]', lecturable_par_roles='["ADMIN"]', actif=True,
        )
        sec = make_user('u_sec_api', role='SECRETARIAT')
        self.client.force_authenticate(sec)
        res = self.client.get(self.URL)
        self.assertEqual(res.data['flags']['flag.test_api_roles'], True)
        # La valeur brute liste n'est jamais exposée.
        self.assertNotIn('SECRETARIAT', str(res.data))

    def test_effet_immediate_apres_patch_admin_avec_historique(self):
        flag = make_bool_flag('flag.test_patch')
        admin = make_user('u_patch_admin')
        self.client.force_authenticate(admin)

        res = self.client.patch(
            f'/api/parametres/{flag.pk}/',
            {'valeur': 'true', 'motif_modification': 'activation de démo P00-08'},
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.content)

        # 1) Effet immédiat sur l'endpoint d'évaluation…
        res_flags = self.client.get(self.URL)
        self.assertTrue(res_flags.data['flags']['flag.test_patch'])
        # …et sur le helper.
        self.assertTrue(is_enabled('flag.test_patch', admin))
        # 2) Le changement est historisé (piste d'audit existante).
        hist = ParametreHistorique.objects.filter(parametre=flag)
        self.assertEqual(hist.count(), 1)
        self.assertEqual(hist.first().ancienne_valeur, 'false')
        self.assertEqual(hist.first().nouvelle_valeur, 'true')
        self.assertIn('P00-08', hist.first().motif_modification)

    def test_secretariat_ne_peut_patcher_ni_voir_le_catalogue(self):
        flag = make_bool_flag(
            'flag.test_admin_only',
            lecturable='["ADMIN", "CHEF_INJS_ADMIN", "INJS_ADMIN"]',
        )
        sec = make_user('u_patch_sec', role='SECRETARIAT')
        self.client.force_authenticate(sec)
        # Le catalogue (ViewSet paramètres) est filtré par droits de lecture.
        res_liste = self.client.get('/api/parametres/?categorie=flags')
        self.assertEqual(res_liste.status_code, status.HTTP_200_OK)
        cles = [row['cle'] for row in res_liste.data]
        self.assertNotIn('flag.test_admin_only', cles)
        # Le PATCH est refusé.
        res_patch = self.client.patch(f'/api/parametres/{flag.pk}/', {'valeur': 'true'}, format='json')
        self.assertEqual(res_patch.status_code, status.HTTP_403_FORBIDDEN)
        # Mais la carte évaluée reste servie (toutes les valeurs à False).
        res_flags = self.client.get(self.URL)
        self.assertFalse(res_flags.data['flags']['flag.test_admin_only'])


class FlagsForUserContractTests(TestCase):
    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_flags_for_user_couvre_tous_les_flags_seedes(self):
        admin = make_user('u_couverture')
        carte = flags_for_user(admin)
        for cle in SEED_FLAGS:
            self.assertIn(cle, carte)
            self.assertFalse(carte[cle])

    def test_invalidate_flags_cache_vide_le_cache(self):
        make_bool_flag('flag.test_inval')
        self.assertFalse(is_enabled('flag.test_inval'))
        self.assertIsNotNone(cache.get(FLAGS_CACHE_KEY))
        invalidate_flags_cache()
        self.assertIsNone(cache.get(FLAGS_CACHE_KEY))
