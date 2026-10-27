"""Tests du garde-fou SQL du lot L4b.

`User.Role.choices` n'est qu'un contrôle applicatif : il n'empêche ni un script
SQL, ni un import, ni une requête directe d'écrire une valeur arbitraire dans
`authentication_user.role`. La migration `authentication.0024` ajoute la
contrainte PostgreSQL (ou les triggers SQLite du profil sandbox) qui ferme
cette porte.

Ces tests vérifient le comportement **réel** du SGBD en contournant
l'ORM et les validateurs Django pour ne tester que le garde-fou.
"""

from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction
from django.test import TestCase

User = get_user_model()

ROLES_CANONIQUES_ATTENDUS = (
    'ADMIN', 'DIRECTION', 'CHEF_INJS_ADMIN', 'INJS_ADMIN',
    'CHEF_SECRETARIAT', 'SECRETARIAT', 'FINANCE', 'ARCHIVE', 'ENCADRANT',
    'SUPERVISEUR', 'FORMATEUR', 'AUDITEUR',
)
VALEURS_INTERDITES = (
    'CPFAE_ADMIN',
    'CHEF_CPFAE_ADMIN',
    'UNKNOWN_ROLE',
    'ROLE_CPFAE_ADMIN',
    '',
)


class ContrainteRoleCanoniqueTests(TestCase):
    """Le RBAC INJS-LMD est verrouillé au niveau base."""

    def _ecriture_sql_directe(self, role, username):
        """Écrit un utilisateur via SQL brut, sans passer par l'ORM.

        C'est le seul moyen de démontrer que la contrainte est bien une
        garantie de la base, et non un effet de bord des `choices`.
        """
        with transaction.atomic():
            with connection.cursor() as curseur:
                curseur.execute(
                    'INSERT INTO authentication_user '
                    '(password, is_superuser, username, first_name, last_name, '
                    ' email, is_staff, is_active, date_joined, role, telephone, '
                    ' organisation, grade, must_change_password) '
                    # is_superuser / is_staff / is_active / must_change_password
                    # sont des colonnes boolean : on écrit TRUE/FALSE et non 0/1,
                    # sinon PostgreSQL refuse l'insertion
                    # (DatatypeMismatch: column "is_superuser" is of type boolean
                    #  but expression is of type integer). L'échec SQL non
                    # picklable faisait ensuite tomber tout le worker en
                    # --parallel et polluait la suite de 'connection already
                    # closed'.
                    "VALUES ('x', FALSE, %s, '', '', '', FALSE, TRUE, "
                    'CURRENT_TIMESTAMP, %s, %s, %s, %s, FALSE)',
                    [username, role, '', '', ''],
                )

    # -- Les 12 valeurs canoniques sont acceptées -----------------------

    def test_1_toutes_les_valeurs_canoniques_sont_acceptees(self):
        for index, role in enumerate(ROLES_CANONIQUES_ATTENDUS):
            with self.subTest(role=role):
                self._ecriture_sql_directe(role, f'zz_canon_{index}')
                self.assertTrue(User.objects.filter(username=f'zz_canon_{index}').exists())

    def test_1b_la_liste_canonique_est_bien_ceux_du_modele(self):
        """La migration ne doit pas diverger du modèle."""
        self.assertEqual(tuple(User.Role.values), ROLES_CANONIQUES_ATTENDUS)

    # -- Les valeurs legacy sont refusées --------------------------------

    def test_2_valeurs_legacy_refusees(self):
        for index, role in enumerate(VALEURS_INTERDITES):
            if role == '':
                # La colonne est NOT NULL : une chaîne vide est admise par la
                # contrainte, mais refusée par la contrainte NOT NULL, pas par
                # la contrainte de nomenclature. On ne la teste donc pas ici.
                continue
            with self.subTest(role=role):
                with self.assertRaises(IntegrityError):
                    self._ecriture_sql_directe(role, f'zz_legacy_{index}')

    def test_3_valeur_arbitraire_refusee(self):
        with self.assertRaises(IntegrityError):
            self._ecriture_sql_directe('UNKNOWN_ROLE', 'zz_unknown')

    def test_3b_aucune_ligne_rejetee_n_a_ete_creee(self):
        """Une écriture refusée ne laisse aucune trace en base."""
        with self.assertRaises(IntegrityError):
            self._ecriture_sql_directe('CPFAE_ADMIN', 'zz_trace')
        self.assertFalse(User.objects.filter(username='zz_trace').exists())

    # -- Régression : les comptes existants restent intacts --------------

    def test_4_mise_a_jour_vers_valeur_non_canonique_refusee(self):
        """Le verrou vaut aussi en UPDATE, pas seulement en INSERT."""
        compte = User.objects.create_user(
            username='zz_update', password='x', role=User.Role.INJS_ADMIN,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                with connection.cursor() as curseur:
                    curseur.execute(
                        'UPDATE authentication_user SET role = %s WHERE username = %s',
                        ['CPFAE_ADMIN', 'zz_update'],
                    )
        compte.refresh_from_db()
        self.assertEqual(compte.role, User.Role.INJS_ADMIN)

    def test_4b_mise_a_jour_vers_valeur_canonique_autorisee(self):
        """Le verrou ne bloque pas les écritures légitimes."""
        compte = User.objects.create_user(
            username='zz_ok', password='x', role=User.Role.INJS_ADMIN,
        )
        compte.role = User.Role.CHEF_INJS_ADMIN
        compte.save(update_fields=['role'])
        compte.refresh_from_db()
        self.assertEqual(compte.role, User.Role.CHEF_INJS_ADMIN)

    def test_4c_la_contrainte_est_bien_nommee(self):
        with connection.cursor() as curseur:
            tables = connection.introspection.table_names(curseur)
        self.assertIn('authentication_user', tables)
