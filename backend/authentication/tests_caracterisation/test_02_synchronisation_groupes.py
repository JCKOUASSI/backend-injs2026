"""U0-CURP — caractérisation de la SYNCHRONISATION compte ↔ groupe Django.

Mécanisme existant (``authentication/apps.py``) :
* à chaque ``User.save()``, ``sync_user_role_group`` ajoute le groupe
  ``ROLE_<rôle>`` correspondant au champ ``User.role`` ;
* ``sync_user_staff_status`` active ``is_staff`` uniquement pour les rôles
  du trio administrateur (``DUAL_ACCESS_ROLES``) ;
* la modification des groupes via l'admin Django resynchronise
  réciproquement ``User.role`` (``sync_role_from_group``).

Ces tests figent ce mécanisme ; U1 introduira le profil d'habilitation
OneToOne sans changer ces synchronisations.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import IntegrityError, connection, transaction
from django.test import TestCase

from authentication.role_groups import (
    DUAL_ACCESS_ROLES,
    ROLE_GROUP_NAMES,
    ROLE_HIERARCHY,
    ensure_role_groups,
    get_user_role,
    get_user_roles,
)

User = get_user_model()

MOT_DE_PASSE = 'Caract#2026x'


class SynchronisationGroupeParRoleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_role_groups()

    def _creer(self, role):
        return User.objects.create_user(
            username=f'car-sync-{role.lower()}',
            password=MOT_DE_PASSE,
            role=role,
        )


# Une méthode de test par rôle : un échec signale EXACTEMENT quel rôle a
# perdu sa synchronisation de groupe.
def _test_groupe_synchronise(role):
    def test(self):
        utilisateur = self._creer(role)
        groupes_ro = list(
            utilisateur.groups.filter(name__startswith='ROLE_')
            .values_list('name', flat=True)
        )
        self.assertEqual(groupes_ro, [ROLE_GROUP_NAMES[role]])
        self.assertEqual(get_user_roles(utilisateur), frozenset({role}))
        self.assertEqual(get_user_role(utilisateur), role)
    test.__doc__ = f"Un compte {role} porte exactement le groupe {ROLE_GROUP_NAMES[role]}."
    return test


for _role in User.Role.values:
    setattr(
        SynchronisationGroupeParRoleTests,
        f'test_compte_{_role.lower()}_porte_le_groupe_attendu',
        _test_groupe_synchronise(_role),
    )


class SynchronisationStaffTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_role_groups()

    def test_trio_admin_recupere_is_staff(self):
        for role in DUAL_ACCESS_ROLES:
            with self.subTest(role=role):
                utilisateur = User.objects.create_user(
                    username=f'car-staff-{role.lower()}',
                    password=MOT_DE_PASSE,
                    role=role,
                )
                self.assertTrue(
                    utilisateur.is_staff,
                    f"{role} devrait avoir is_staff=True (accès admin Django)",
                )

    def test_role_non_admin_n_a_pas_is_staff(self):
        for role in User.Role.values:
            if role in DUAL_ACCESS_ROLES:
                continue
            with self.subTest(role=role):
                utilisateur = User.objects.create_user(
                    username=f'car-nostaff-{role.lower()}',
                    password=MOT_DE_PASSE,
                    role=role,
                )
                self.assertFalse(
                    utilisateur.is_staff,
                    f"{role} ne devrait PAS avoir is_staff",
                )

    def test_superutilisateur_conserve_is_staff_quelle_que_soit_la_sync(self):
        admin = User.objects.create_superuser(
            username='car-root', password=MOT_DE_PASSE, role=User.Role.ADMIN,
        )
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)


class ChangementDeRoleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_role_groups()

    def test_changement_de_role_par_save_ajoute_sans_retirer_l_ancien_groupe(self):
        # COMPORTEMENT ACTUEL CARACTÉRISÉ (à instruire en U1/U2) : un simple
        # ``user.role = X ; user.save()`` AJOUTE le groupe cible mais NE
        # RETIRE PAS l'ancien groupe. Le rôle principal dérivé reste donc le
        # plus élevé des deux (SECRETARIAT > FINANCE dans la hiérarchie). La
        # bascule propre passe par les serializers de comptes ou l'admin.
        utilisateur = User.objects.create_user(
            username='car-mutation', password=MOT_DE_PASSE, role='SECRETARIAT',
        )
        utilisateur.role = 'FINANCE'
        utilisateur.save()
        self.assertTrue(
            utilisateur.groups.filter(name=ROLE_GROUP_NAMES['FINANCE']).exists()
        )
        self.assertTrue(
            utilisateur.groups.filter(name=ROLE_GROUP_NAMES['SECRETARIAT']).exists()
        )
        self.assertEqual(get_user_roles(utilisateur), frozenset({'SECRETARIAT', 'FINANCE'}))
        self.assertEqual(get_user_role(utilisateur), 'SECRETARIAT')

    def test_role_derive_du_groupe_le_plus_haut_dans_la_hierarchie(self):
        # Si un utilisateur porte plusieurs groupes ROLE_* (migration
        # progressive multi-rôle), le rôle principal est le plus élevé.
        utilisateur = User.objects.create_user(
            username='car-multi', password=MOT_DE_PASSE, role='SECRETARIAT',
        )
        utilisateur.groups.add(Group.objects.get(name=ROLE_GROUP_NAMES['ENCADRANT']))
        roles = get_user_roles(utilisateur)
        self.assertEqual(roles, frozenset({'SECRETARIAT', 'ENCADRANT'}))
        self.assertEqual(get_user_role(utilisateur), 'SECRETARIAT')
        self.assertLess(
            ROLE_HIERARCHY.index('SECRETARIAT'),
            ROLE_HIERARCHY.index('ENCADRANT'),
        )

    def test_ajout_d_un_groupe_ro_via_admin_resynchronise_le_champ_role(self):
        utilisateur = User.objects.create_user(
            username='car-admin-sync', password=MOT_DE_PASSE, role='AUDITEUR',
        )
        utilisateur.groups.clear()
        utilisateur.groups.add(Group.objects.get(name=ROLE_GROUP_NAMES['FINANCE']))
        utilisateur.refresh_from_db()
        self.assertEqual(utilisateur.role, 'FINANCE')

    def test_compte_sans_groupe_conserve_son_role_rbac_canonique(self):
        """Lot L4b — `User.role` porte TOUJOURS un rôle RBAC canonique.

        Avant L4b, un compte pouvait être « désarmé » en vidant le champ `role` :
        cet état n'est plus représentable (contrainte `auth_user_role_canonique_l4b`).
        Sans groupe `ROLE_*`, `get_user_roles()` retombe donc toujours sur le
        champ `role`, qui reste renseigné.
        """
        utilisateur = User.objects.create_user(
            username='car-sans-role', password=MOT_DE_PASSE, role='AUDITEUR',
        )
        utilisateur.groups.clear()
        # Le compte est créé avec un rôle canonique : il ne peut pas s'en priver.
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                with connection.cursor() as curseur:
                    curseur.execute(
                        "UPDATE authentication_user SET role = '' WHERE id = %s",
                        [utilisateur.id],
                    )
        # Après refus de l'écriture, l'état est intact.
        utilisateur.refresh_from_db()
        self.assertEqual(utilisateur.role, 'AUDITEUR')
        self.assertEqual(get_user_roles(utilisateur), frozenset({'AUDITEUR'}))
        self.assertEqual(get_user_role(utilisateur), 'AUDITEUR')

    def test_role_vide_refuse_par_la_contrainte_de_base(self):
        """Lot L4b — la chaîne vide n'est pas un rôle RBAC."""
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                with connection.cursor() as curseur:
                    curseur.execute(
                        'INSERT INTO authentication_user '
                        '(password, is_superuser, username, first_name, last_name, '
                        ' email, is_staff, is_active, date_joined, role, telephone, '
                        ' organisation, grade, must_change_password) '
                        # Colonnes boolean : TRUE/FALSE et non 0/1, sinon
                        # PostgreSQL refuse (DatatypeMismatch) et l'erreur SQL
                        # non picklable fait tomber le worker en --parallel.
                        "VALUES ('x', FALSE, 'car-role-vide', '', '', '', "
                        "FALSE, TRUE, CURRENT_TIMESTAMP, '', '', '', '', FALSE)"
                    )
        self.assertFalse(User.objects.filter(username='car-role-vide').exists())
