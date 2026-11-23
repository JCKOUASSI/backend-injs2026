"""Tests de sécurité du lot L4a — migration RBAC INJS-LMD.

    CPFAE_ADMIN       -> INJS_ADMIN
    CHEF_CPFAE_ADMIN  -> CHEF_INJS_ADMIN

Le référentiel comporte toujours **12 rôles** : L4a a *renommé* deux
identifiants historiques issus de Sygepcpfae, sans créer ni supprimer de rôle
métier. Le passage à 14 rôles exigerait un lot distinct avec une définition
métier validée (arbitrage du 26/09/2026).

Ces tests sont volontairement stricts : égalité stricte du référentiel,
interdiction de réintroduire les chaînes CPFAE comme valeurs canoniques,
invariance des permissions et des comptes.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase

from authentication import role_groups as rg
from authentication.role_groups import DUAL_ACCESS_ROLES, ensure_role_groups

User = get_user_model()

ROLES_CANONIQUES_ATTENDUS = {
    'ADMIN', 'DIRECTION', 'CHEF_INJS_ADMIN', 'INJS_ADMIN',
    'CHEF_SECRETARIAT', 'SECRETARIAT', 'FINANCE', 'ARCHIVE', 'ENCADRANT',
    'SUPERVISEUR', 'FORMATEUR', 'AUDITEUR',
}
ROLES_LEGACY_INTERDITS = {'CPFAE_ADMIN', 'CHEF_CPFAE_ADMIN'}


def _empreinte(nom_groupe):
    """Signature stable du contenu d'un groupe (applications + codenames)."""
    groupe = Group.objects.filter(name=nom_groupe).first()
    if groupe is None:
        return frozenset()
    return frozenset(
        groupe.permissions.values_list('content_type__app_label', 'codename')
    )


class MigrationRolesInjsTests(TestCase):

    # -- Test 1 — Référentiel : 12 rôles, égalité stricte -----------------

    def test_1_referentiel_exactement_douze_roles_canoniques(self):
        self.assertEqual(set(User.Role.values), ROLES_CANONIQUES_ATTENDUS)
        self.assertEqual(len(User.Role.values), 12)

    def test_1b_aucun_role_legacy_canonique(self):
        """Les chaînes CPFAE ne doivent plus être des valeurs de `Role`."""
        self.assertEqual(set(User.Role.values) & ROLES_LEGACY_INTERDITS, set())

    def test_1c_hierarchie_alignee_sur_le_referentiel(self):
        self.assertEqual(set(rg.ROLE_HIERARCHY), ROLES_CANONIQUES_ATTENDUS)
        self.assertEqual(len(rg.ROLE_HIERARCHY), len(set(rg.ROLE_HIERARCHY)))

    def test_1d_groupes_django_alignes_sans_legacy(self):
        attendus = {f'ROLE_{r}' for r in User.Role.values}
        self.assertEqual(set(rg.ROLE_GROUP_NAMES.values()), attendus)
        noms = set(rg.ROLE_GROUP_NAMES.values())
        self.assertEqual({n for n in noms if n.endswith('CPFAE_ADMIN')}, set())


    # -- Test 4 — Permissions : invariance des groupes -------------------

    def test_4_politique_definie_pour_les_roles_admin(self):
        for role in (User.Role.INJS_ADMIN, User.Role.CHEF_INJS_ADMIN):
            with self.subTest(role=role):
                self.assertIn(role, rg.ROLE_POLICY)

    def test_4b_ensure_role_groups_idempotent_et_sans_perte(self):
        """Rejouer ensure_role_groups ne doit ni vider ni modifier un groupe."""
        noms = ('ROLE_INJS_ADMIN', 'ROLE_CHEF_INJS_ADMIN')
        ensure_role_groups()
        avant = {nom: _empreinte(nom) for nom in noms}
        ensure_role_groups()
        apres = {nom: _empreinte(nom) for nom in noms}
        self.assertEqual(avant, apres)
        for nom, empreinte in apres.items():
            self.assertTrue(empreinte, f'{nom} ne doit pas être vide')

    def test_4c_les_deux_groupes_admin_ont_le_meme_perimetre(self):
        """Perte comme élévation de privilège sont ici détectées."""
        perimetres = {
            nom: _empreinte(nom) for nom in ('ROLE_INJS_ADMIN', 'ROLE_CHEF_INJS_ADMIN')
        }
        self.assertEqual(perimetres['ROLE_INJS_ADMIN'], perimetres['ROLE_CHEF_INJS_ADMIN'])

    # -- Test 5 — Utilisateurs : conservation des comptes ----------------

    def test_5_comptes_preserves_et_migres(self):
        """Un compte créé avec le rôle canonique est accepté et conservé."""
        compte = User.objects.create_user(
            username='test_injs_admin', password='x', role=User.Role.INJS_ADMIN
        )
        compte.refresh_from_db()
        self.assertEqual(compte.role, User.Role.INJS_ADMIN)
        chef = User.objects.create_user(
            username='test_chef_injs', password='x', role=User.Role.CHEF_INJS_ADMIN
        )
        chef.refresh_from_db()
        self.assertEqual(chef.role, User.Role.CHEF_INJS_ADMIN)

    def test_5b_la_chaine_legacy_n_est_plus_acceptee(self):
        """Lot L4b : la chaîne CPFAE n'est plus ni canonique ni persistable.

        Avant L4b, les `choices` n'étaient qu'un contrôle applicatif : un script
        ou une requête directe pouvait écrire `CPFAE_ADMIN`. La contrainte CHECK
        `auth_user_role_canonique_l4b` ferme désormais cette porte au niveau
        PostgreSQL, y compris en contournant l'ORM (voir
        `test_roles_canoniques_contrainte_db.py`).
        """
        # La chaîne n'est plus une valeur canonique du modèle.
        self.assertNotIn('CPFAE_ADMIN', User.Role.values)
        self.assertNotIn('CHEF_CPFAE_ADMIN', User.Role.values)
        # Aucune donnée legacy n'est effectivement persistée.
        restants = list(
            User.objects.filter(role__in=ROLES_LEGACY_INTERDITS)
            .values_list('username', 'role')
        )
        self.assertEqual(restants, [])


    def test_5c_identite_et_mot_de_passe_intacts(self):
        """La migration ne touche que le champ `role`."""
        compte = User.objects.create_user(
            username='test_integre', password='secret-initial',
            role=User.Role.INJS_ADMIN, first_name='Awa',
        )
        compte.refresh_from_db()
        self.assertEqual(compte.first_name, 'Awa')
        self.assertTrue(compte.check_password('secret-initial'))
        compte.role = User.Role.INJS_ADMIN
        compte.save(update_fields=['role'])
        compte.refresh_from_db()
        self.assertTrue(compte.check_password('secret-initial'))



    # -- Test 7 — Non-régression : pas d'élévation de privilège ----------

    def test_7_roles_administratifs_inchanges(self):
        self.assertIn(User.Role.INJS_ADMIN, DUAL_ACCESS_ROLES)
        self.assertIn(User.Role.CHEF_INJS_ADMIN, DUAL_ACCESS_ROLES)
        # Le trio d'administration reste un trio : rien n'a été ajouté.
        trio = {User.Role.ADMIN, User.Role.INJS_ADMIN, User.Role.CHEF_INJS_ADMIN}
        self.assertEqual(trio & set(rg.ROLE_POLICY), trio)

    def test_7b_auditeur_non_admis_sur_le_web(self):
        self.assertNotIn(User.Role.AUDITEUR, rg.ALLOWED_WEB_ROLES)
        self.assertIn(User.Role.AUDITEUR, rg.MOBILE_ONLY_ROLES)

    def test_7c_partition_web_mobile_inchangee(self):
        """SUPERVISEUR est un rôle web ET mobile : on ne l'exclut pas."""
        self.assertFalse(rg.ALLOWED_WEB_ROLES & rg.MOBILE_ONLY_ROLES)
        self.assertEqual(
            set(rg.ALLOWED_WEB_ROLES) | set(rg.MOBILE_ONLY_ROLES),
            set(User.Role.values),
        )

