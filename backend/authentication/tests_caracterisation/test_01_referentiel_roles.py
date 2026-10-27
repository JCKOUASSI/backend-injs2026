"""U0-CURP — caractérisation du RÉFÉRENTIEL de rôles (état figé au 2026-09-13).

Source de vérité : ``authentication/models.py`` (``User.Role`` et les
permissions métier) et ``authentication/role_groups.py`` (ensembles,
hiérarchie, ``ROLE_POLICY``, noms de groupes).

Toute évolution du référentiel doit passer par U3 (référentiel 35 rôles) :
ces tests décrivent les 12 rôles EXISTANTS et doivent rester verts jusqu'à ce
qu'une unité dédiée modifie explicitement le référentiel.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase

from authentication import role_groups as rg
from authentication.role_groups import (
    ROLE_GROUP_NAMES,
    ROLE_HIERARCHY,
    ROLE_POLICY,
    ensure_role_groups,
)

User = get_user_model()

# L'identité exacte des 12 rôles actuels, figée pour U0.
ROLES_ATTENDUS = frozenset({
    'ADMIN', 'DIRECTION', 'CHEF_INJS_ADMIN', 'INJS_ADMIN',
    'CHEF_SECRETARIAT', 'SECRETARIAT', 'FINANCE', 'ARCHIVE', 'ENCADRANT',
    'SUPERVISEUR', 'FORMATEUR', 'AUDITEUR',
})

# Les 10 permissions métier personnalisées du modèle User.
PERMISSIONS_CUSTOM_ATTENDUES = frozenset({
    'access_web', 'operational_web', 'mutate_users', 'global_scope',
    'list_participants', 'finance_module', 'manage_questionnaires',
    'manage_notes', 'validate_decisions', 'consult_evaluation',
})


class ReferentielRolesTests(TestCase):
    def test_douze_roles_exactement(self):
        self.assertEqual(frozenset(User.Role.values), ROLES_ATTENDUS)
        self.assertEqual(len(User.Role.values), 12)

    def test_hierarchie_contient_exactement_les_douze_roles(self):
        self.assertEqual(frozenset(ROLE_HIERARCHY), ROLES_ATTENDUS)
        # Pas de doublon dans la hiérarchie (ordre strict).
        self.assertEqual(len(ROLE_HIERARCHY), len(set(ROLE_HIERARCHY)))

    def test_admin_est_le_role_le_plus_eleve(self):
        self.assertEqual(ROLE_HIERARCHY[0], 'ADMIN')

    def test_partition_web_mobile_sans_chevauchement(self):
        attendus_web = ROLES_ATTENDUS - {'FORMATEUR', 'AUDITEUR'}
        self.assertEqual(frozenset(rg.ALLOWED_WEB_ROLES), attendus_web)
        self.assertEqual(frozenset(rg.MOBILE_ONLY_ROLES), {'FORMATEUR', 'AUDITEUR'})
        self.assertFalse(rg.ALLOWED_WEB_ROLES & rg.MOBILE_ONLY_ROLES)

    def test_roles_mobile_only_exacts(self):
        self.assertEqual(frozenset(rg.MOBILE_ONLY_ROLES),
                         frozenset({User.Role.FORMATEUR, User.Role.AUDITEUR}))

    def test_trio_admin_roles_a_double_acces(self):
        self.assertEqual(
            frozenset(rg.DUAL_ACCESS_ROLES),
            {'ADMIN', 'CHEF_INJS_ADMIN', 'INJS_ADMIN'},
        )

    def test_roles_a_acces_global_exacts(self):
        self.assertEqual(
            frozenset(rg.GLOBAL_ACCESS_ROLES),
            {'ADMIN', 'CHEF_INJS_ADMIN', 'INJS_ADMIN', 'DIRECTION', 'ARCHIVE'},
        )

    def test_roles_secretariat_exacts(self):
        self.assertEqual(
            frozenset(rg.SECRETARIAT_ROLES),
            {'CHEF_SECRETARIAT', 'SECRETARIAT'},
        )

    def test_roles_module_finance_exacts(self):
        self.assertEqual(
            frozenset(rg.FINANCE_MODULE_ROLES),
            {'FINANCE', 'DIRECTION', 'ARCHIVE'},
        )

    def test_roles_pouvant_muter_un_compte(self):
        self.assertEqual(
            frozenset(rg.USER_MUTATION_ROLES),
            {'ADMIN', 'CHEF_INJS_ADMIN', 'INJS_ADMIN',
             'CHEF_SECRETARIAT', 'SECRETARIAT'},
        )

    def test_role_policy_couvre_exactement_les_douze_roles(self):
        self.assertEqual(frozenset(ROLE_POLICY.keys()), ROLES_ATTENDUS)

    def test_chaque_role_a_un_nom_de_groupe_ro(self):
        self.assertEqual(frozenset(ROLE_GROUP_NAMES.keys()), ROLES_ATTENDUS)
        for nom in ROLE_GROUP_NAMES.values():
            self.assertTrue(nom.startswith('ROLE_'))

    def test_dix_permissions_metier_declarees_sur_le_modele_user(self):
        declarees = {codename for codename, _lib in User._meta.permissions}
        self.assertEqual(declarees, PERMISSIONS_CUSTOM_ATTENDUES)

    def test_permissions_custom_referencees_existent_dans_ro_policy(self):
        # Aucune permission métier référencée dans ROLE_POLICY ne doit être
        # fictive : toutes se résolvent en une Permission Django après
        # migration (vérifié via le ContentType du modèle User).
        for role, politique in ROLE_POLICY.items():
            for cle in politique.get('custom', ()):
                cle_complete = rg.CUSTOM_PERMISSIONS[cle]
                _app, codename = cle_complete.split('.', 1)
                self.assertTrue(
                    Permission.objects.filter(
                        content_type__app_label='authentication',
                        codename=codename,
                    ).exists(),
                    f"permission {cle_complete} introuvable pour le rôle {role}",
                )

    def test_combinaisons_multi_role_autorisees_sont_une_liste_figee(self):
        # État U0 : 5 combinaisons ouvertes (secrétariat + encadrement,
        # encadrement + supervision). À faire évoluer explicitement en U3.
        self.assertEqual(len(rg.ALLOWED_MULTI_ROLE_COMBINATIONS), 5)
        combinaisons = {
            tuple(sorted(combo)) for combo in rg.ALLOWED_MULTI_ROLE_COMBINATIONS
        }
        self.assertEqual(combinaisons, {
            ('CHEF_SECRETARIAT', 'ENCADRANT'),
            ('ENCADRANT', 'SECRETARIAT'),
            ('CHEF_SECRETARIAT', 'SUPERVISEUR'),
            ('SECRETARIAT', 'SUPERVISEUR'),
            ('ENCADRANT', 'SUPERVISEUR'),
        })


class EnsureRoleGroupsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Les signaux post_migrate créent déjà les groupes en base de test ;
        # on force la réconciliation pour garantir l'état caractérisé.
        ensure_role_groups()

    def test_ensure_role_groups_cree_exactement_douze_groupes_ro(self):
        noms = set(Group.objects.filter(name__startswith='ROLE_')
                   .values_list('name', flat=True))
        self.assertEqual(noms, set(ROLE_GROUP_NAMES.values()))
        self.assertEqual(len(noms), 12)

    def test_ensure_role_groups_est_idempotent(self):
        avant = {
            g.name: set(g.permissions.values_list('codename', flat=True))
            for g in Group.objects.filter(name__startswith='ROLE_')
        }
        ensure_role_groups()
        apres = {
            g.name: set(g.permissions.values_list('codename', flat=True))
            for g in Group.objects.filter(name__startswith='ROLE_')
        }
        self.assertEqual(avant, apres)
