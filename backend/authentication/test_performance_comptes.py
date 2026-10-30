"""Non-régression performance : la liste des comptes ne doit pas être en N+1.

Constat d'audit : ``GET /api/auth/users/`` exécutait une requête de groupes
**par utilisateur** (21 requêtes pour 20 comptes). Le correctif ajoute
``select_related('secretariat')`` et ``prefetch_related('groups')``.

Le test compare le nombre de requêtes pour 5 comptes puis pour 40 comptes :
il doit être identique. Une régression N+1 le ferait exploser.
"""

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from authentication.models import User
from authentication.role_groups import ROLE_GROUP_NAMES


class ListeComptesSansNPlus1Tests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            username='admin_perf', password='x', role=User.Role.ADMIN,
            is_staff=True, is_superuser=True,
        )
        # Un premier lot de comptes subordonnés visibles par l'administrateur.
        cls._creer_comptes(5, prefixe='lot1')

    @classmethod
    def _creer_comptes(cls, nombre, prefixe):
        groupe = ROLE_GROUP_NAMES[User.Role.SECRETARIAT]
        from django.contrib.auth.models import Group

        grp, _ = Group.objects.get_or_create(name=groupe)
        for i in range(nombre):
            u = User.objects.create_user(
                username=f'{prefixe}_{i}', password='x',
                role=User.Role.SECRETARIAT,
            )
            u.groups.add(grp)

    def _compter_requetes(self):
        client = APIClient()
        client.force_authenticate(user=self.admin)
        with CaptureQueriesContext(connection) as ctx:
            reponse = client.get('/api/auth/users/?page_size=200')
        self.assertEqual(reponse.status_code, 200)
        return len(ctx.captured_queries)

    def test_le_nombre_de_requetes_ne_depend_pas_du_nombre_de_comptes(self):
        requetes_petit_lot = self._compter_requetes()

        self._creer_comptes(35, prefixe='lot2')
        requetes_grand_lot = self._compter_requetes()

        self.assertEqual(
            requetes_petit_lot, requetes_grand_lot,
            f"Régression N+1 : {requetes_petit_lot} requêtes pour 5 comptes, "
            f'{requetes_grand_lot} pour 40.',
        )
