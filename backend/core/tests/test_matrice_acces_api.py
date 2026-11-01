"""Matrice d'accès : une permission *déclarée* est-elle réellement *appliquée* ?

Origine du test — un défaut réel a été trouvé sur les finances étudiantes : les
permissions étaient écrites, documentées, mais aucune vue ne les portait. Un
compte étudiant (`AUDITEUR`) lisait donc l'intégralité des paiements de
l'établissement par appel direct de l'API, alors que l'interface lui masquait le
module. Le même défaut peut réapparaître à chaque nouvelle vue : ce test le
détecte automatiquement, sur les endpoints sensibles, pour **les 12 rôles**.

Principe : pour chaque couple (endpoint, permission), on demande à la classe de
permission elle-même ce qu'elle attend pour un rôle donné — c'est l'intention
déclarée — puis on compare avec ce que l'API répond réellement — c'est le
câblage. Un écart dans les deux sens est un défaut :

* intention « refusé » + API qui répond autre chose que 403 → permission non
  branchée (fuite de données) ;
* intention « autorisé » + API qui répond 403 → régression d'accès (fonction
  légitime bloquée).

Le test ne fixe aucune règle métier nouvelle : il ne fait que vérifier que les
règles existantes sont bien en vigueur.
"""
from django.test import TestCase
from rest_framework.test import APIClient, APIRequestFactory

from authentication.models import User
from authentication.permissions import (
    IsDFRCOrEncadrant,
    IsSecretariatOrDFRC,
    IsUserMutationAllowed,
)
from authentication.role_groups import SECRETARIAT_ROLES
from finances_etudiantes.permissions import (
    IsFinancesReadOnly,
    IsGestionFinanciere,
    IsValidationFinanciere,
)
from formations.models import Secretariat
from scolarite.api_views import IsDFRC
from statistiques.access import user_has_stats_access

#: Codes qui, pour un rôle *autorisé*, signifient « la permission a laissé
#: passer » : le refus éventuel vient alors de la logique métier (objet absent,
#: transition invalide…), pas des droits.
CODES_APRES_PERMISSION = {200, 201, 204, 400, 404, 405, 409, 422}

CAS = [
    # (méthode, chemin, fabrique de permission, libellé)
    ('get', '/api/finances-etudiantes/paiements/', IsFinancesReadOnly,
     'lecture des paiements'),
    ('get', '/api/finances-etudiantes/echeanciers/', IsFinancesReadOnly,
     'lecture des échéanciers'),
    ('get', '/api/finances-etudiantes/quittances/', IsFinancesReadOnly,
     'lecture des quittances'),
    ('post', '/api/finances-etudiantes/echeanciers/1/facture/', IsGestionFinanciere,
     'génération de facture'),
    ('post', '/api/finances-etudiantes/paiements/1/confirmer/', IsValidationFinanciere,
     'confirmation de paiement'),
    ('post', '/api/finances-etudiantes/rapprochements/creer/', IsValidationFinanciere,
     'rapprochement comptable'),
    ('get', '/api/audit-logs/', IsDFRCOrEncadrant, "journal d'audit"),
    ('get', '/api/auth/users/', IsSecretariatOrDFRC, 'liste des utilisateurs'),
    ('post', '/api/auth/users/', IsUserMutationAllowed, 'création d’utilisateur'),
    ('post', '/api/scolarite/maquettes/1/activer/', IsDFRC, 'activation de maquette'),
]


class MatriceAccesTests(TestCase):
    """Un rôle hors matrice ne doit jamais obtenir autre chose qu'un 403."""

    @classmethod
    def setUpTestData(cls):
        # Un compte de secrétariat est, par conception, rattaché à un
        # secrétariat : sans ce rattachement, le périmètre des statistiques est
        # légitimement refusé (403 « Aucun secrétariat rattaché »).
        cls.secretariat = Secretariat.objects.create(numero='SEC-MAT', nom='Secrétariat test')
        cls.users = {}
        for index, role in enumerate(User.Role.values):
            user = User.objects.create_user(
                username=f'matrice_{index}',
                password='motdepasse',
                role=role,
            )
            if role in SECRETARIAT_ROLES:
                user.secretariat = cls.secretariat
                user.save(update_fields=['secretariat'])
            cls.users[role] = user

    def setUp(self):
        self.client = APIClient()
        # Une vue autorisée peut légitimement lever sur un objet inexistant
        # (aucune fixture métier ici) : on veut alors constater le code HTTP,
        # pas une exception de test.
        self.client.raise_request_exception = False
        self.factory = APIRequestFactory()

    def _intention(self, permission, user, chemin, methode='get'):
        """Ce que la permission déclare pour ce rôle (source de vérité).

        La méthode HTTP compte : plusieurs permissions sont en lecture seule
        pour certains rôles (consultation autorisée, écriture refusée), donc
        interroger la classe en GET pour un endpoint POST donnerait une
        intention fausse.
        """
        request = self.factory.generic(methode.upper(), chemin)
        request.user = user
        if permission is None:  # garde applicatif, non DRF
            return user_has_stats_access(user)
        return bool(permission().has_permission(request, None))

    def test_permissions_declarees_sont_appliquees(self):
        ecarts = []
        for methode, chemin, permission, libelle in CAS:
            for role, user in self.users.items():
                self.client.force_authenticate(user)
                attendu = self._intention(permission, user, chemin, methode)
                reponse = getattr(self.client, methode)(chemin)
                code = reponse.status_code
                if attendu and code not in CODES_APRES_PERMISSION:
                    ecarts.append(
                        f'{libelle} [{methode.upper()} {chemin}] : rôle {role} '
                        f'autorisé par la permission mais API → {code}'
                    )
                elif not attendu and code != 403:
                    ecarts.append(
                        f'{libelle} [{methode.upper()} {chemin}] : rôle {role} '
                        f'refusé par la permission mais API → {code} (fuite ?)'
                    )
        self.assertEqual(ecarts, [], '\n'.join([''] + ecarts))

    def test_statistiques_reservees_aux_roles_habilités(self):
        """Le garde applicatif des statistiques doit rester branché."""
        for role, user in self.users.items():
            self.client.force_authenticate(user)
            code = self.client.get('/api/statistiques/').status_code
            if user_has_stats_access(user):
                self.assertNotEqual(code, 403, f'rôle {role} : accès refusé à tort')
            else:
                self.assertEqual(code, 403, f'rôle {role} : statistiques accessibles')

    def test_endpoints_sensibles_refusent_les_comptes_mobile(self):
        """Un étudiant/formateur n'a aucun accès aux données financières."""
        for role in (User.Role.AUDITEUR, User.Role.FORMATEUR):
            self.client.force_authenticate(self.users[role])
            for chemin in (
                '/api/finances-etudiantes/paiements/',
                '/api/finances-etudiantes/echeanciers/',
                '/api/finances-etudiantes/quittances/',
                '/api/finances-etudiantes/remboursements/',
            ):
                self.assertEqual(
                    self.client.get(chemin).status_code, 403,
                    f'{role} peut lire {chemin}',
                )
