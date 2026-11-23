"""Tests LOT 3 — API d'organisation administrative.

Couvre le garde drapeau + capacité, le CRUD directions/départements/services
(création, doublon, modification, activation/désactivation, filtres), les
rattachements compte ↔ département/service (ajout, retrait, erreurs) et la
lecture des permissions effectives d'un compte (rôles actifs). Les gestes
mutants sont vérifiés comme journalisés (``ORGANISATION_MODIFIEE``).
"""
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from administrations.models import Departement, Direction
from habilitations.models import (
    AttributionRole,
    CompteUtilisateur,
    JournalHabilitation,
    Personne,
    RoleMetier,
)
from parametres.flags import invalidate_flags_cache
from parametres.models import Parametre
from ressources_humaines.models import Service

User = get_user_model()

FLAG_CLE = 'flag.curp_ui_admin'


def _admin_user(username='admin3'):
    return User.objects.create_user(
        username=username, password='Mot#2026x', role='ADMIN', is_staff=True,
    )


def _creer_compte(username='agent3', role_legacy='SECRETARIAT'):
    user = User.objects.create_user(
        username=username, password='Mot#2026x', role=role_legacy,
    )
    personne = Personne.objects.create(nom=username.title(), prenoms='Test')
    return CompteUtilisateur.objects.create(
        user=user, personne=personne, motif_statut='Création test LOT 3.',
    )


class OrganisationApiTests(APITestCase):
    def setUp(self):
        from habilitations.referentiel.chargement import charger_referentiel
        charger_referentiel()
        _admin_user()
        self.admin = User.objects.get(username='admin3')
        self.agent = User.objects.create_user(
            username='agent3x', password='Mot#2026x', role='SECRETARIAT',
        )
        self.compte = _creer_compte()

    def _drapeau(self, actif=True):
        Parametre.objects.update_or_create(
            cle=FLAG_CLE,
            defaults={
                'libelle': 'Console CURP', 'categorie': 'flags',
                'type': 'bool', 'valeur': 'true' if actif else 'false',
                'valeur_defaut': 'false', 'actif': True,
            },
        )
        invalidate_flags_cache()

    def _auth(self, user=None):
        self.client.force_authenticate(user or self.admin)

    def _journal_orga(self):
        return JournalHabilitation.objects.filter(
            type_evenement='ORGANISATION_MODIFIEE'
        )

    def tearDown(self):
        # Le cache de flags est partagé par le processus (LocMem) et n'est
        # pas remis à zéro par le rollback de la transaction : on le purge
        # pour ne pas polluer les tests suivants (contrat de capacités).
        from django.core.cache import cache
        cache.clear()
        super().tearDown()

    # ── Garde ─────────────────────────────────────────────────────────
    def test_01_drapeau_ferme_toutes_les_routessont_403(self):
        self._drapeau(False)
        self._auth()
        for url in (
            '/api/habilitations/organisation/directions/',
            '/api/habilitations/organisation/departements/',
            '/api/habilitations/organisation/services/',
            f'/api/habilitations/comptes/{self.compte.id}/effective-permissions/',
        ):
            with self.subTest(url=url):
                reponse = self.client.get(url)
                self.assertEqual(reponse.status_code, 403)

    def test_02_drapeau_ouvert_mais_non_admin_403(self):
        self._drapeau(True)
        self._auth(self.agent)
        reponse = self.client.get('/api/habilitations/organisation/directions/')
        self.assertEqual(reponse.status_code, 403)

    # ── Directions ────────────────────────────────────────────────────
    def test_03_creation_direction_liste_et_journal(self):
        self._drapeau(True)
        self._auth()
        avant = self._journal_orga().count()
        reponse = self.client.post(
            '/api/habilitations/organisation/directions/',
            {'code': 'DG', 'libelle': 'Direction Générale', 'ordre': 1},
            format='json',
        )
        self.assertEqual(reponse.status_code, 201)
        self.assertEqual(reponse.json()['code'], 'DG')
        self.assertTrue(Direction.objects.filter(code='DG').exists())

        reponse = self.client.get('/api/habilitations/organisation/directions/')
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(len(reponse.json()['results']), 1)

        entrees = self._journal_orga()
        self.assertEqual(entrees.count(), avant + 1)
        derniere = entrees.order_by('-numero').first()
        self.assertIn('Direction Générale', derniere.motif)

    def test_04_direction_doublon_et_champs_manquants_rejetes(self):
        self._drapeau(True)
        self._auth()
        Direction.objects.create(code='DG', libelle='Direction Générale')
        reponse = self.client.post(
            '/api/habilitations/organisation/directions/',
            {'code': 'DG', 'libelle': 'Doublon'}, format='json',
        )
        self.assertEqual(reponse.status_code, 400)
        self.assertIn('existe déjà', reponse.json()['detail'])

        reponse = self.client.post(
            '/api/habilitations/organisation/directions/',
            {'libelle': 'Sans code'}, format='json',
        )
        self.assertEqual(reponse.status_code, 400)

    def test_05_modifier_direction_activer_desactiver(self):
        self._drapeau(True)
        self._auth()
        direction = Direction.objects.create(code='SG', libelle='Secrétariat Général')
        reponse = self.client.patch(
            f'/api/habilitations/organisation/directions/{direction.id}/',
            {'actif': False, 'description': 'Direction autonome.'},
            format='json',
        )
        self.assertEqual(reponse.status_code, 200)
        self.assertFalse(reponse.json()['actif'])
        direction.refresh_from_db()
        self.assertFalse(direction.actif)
        self.assertEqual(direction.description, 'Direction autonome.')
        self.assertEqual(self._journal_orga().count(), 1)

        reponse = self.client.patch(
            f'/api/habilitations/organisation/directions/{direction.id}/',
            {}, format='json',
        )
        self.assertEqual(reponse.status_code, 400)

        reponse = self.client.get(
            f'/api/habilitations/organisation/directions/99999/'
        )
        self.assertEqual(reponse.status_code, 404)

    # ── Départements ──────────────────────────────────────────────────
    def test_06_departements_crud_filtre_et_direction_inconnue(self):
        self._drapeau(True)
        self._auth()
        direction = Direction.objects.create(code='DG', libelle='Direction Générale')
        autonome = Direction.objects.create(code='AUT', libelle='Autonome')

        reponse = self.client.post(
            '/api/habilitations/organisation/departements/',
            {'code': 'DAF', 'libelle': 'Affaires Financières', 'direction': direction.id},
            format='json',
        )
        self.assertEqual(reponse.status_code, 201)
        self.assertEqual(reponse.json()['direction_id'], direction.id)

        reponse = self.client.post(
            '/api/habilitations/organisation/departements/',
            {'code': 'DSC', 'libelle': 'Sciences', 'direction': 99999},
            format='json',
        )
        self.assertEqual(reponse.status_code, 400)

        # Rattachement à l'autre direction via PATCH, puis filtre.
        departement = Departement.objects.get(code='DAF')
        reponse = self.client.patch(
            f'/api/habilitations/organisation/departements/{departement.id}/',
            {'direction': autonome.id}, format='json',
        )
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.json()['direction_id'], autonome.id)

        reponse = self.client.get(
            '/api/habilitations/organisation/departements/?direction='
            f'{direction.id}'
        )
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.json()['results'], [])
        reponse = self.client.get(
            '/api/habilitations/organisation/departements/?direction='
            f'{autonome.id}'
        )
        self.assertEqual(len(reponse.json()['results']), 1)

    # ── Services ──────────────────────────────────────────────────────
    def test_07_services_crud_filtre_et_doublon(self):
        self._drapeau(True)
        self._auth()
        departement = Departement.objects.create(code='DAF', libelle='Affaires')
        reponse = self.client.post(
            '/api/habilitations/organisation/services/',
            {'nom': 'Comptabilité', 'departement': departement.id},
            format='json',
        )
        self.assertEqual(reponse.status_code, 201)
        self.assertEqual(reponse.json()['departement_id'], departement.id)

        reponse = self.client.post(
            '/api/habilitations/organisation/services/',
            {'nom': 'Comptabilité'}, format='json',
        )
        self.assertEqual(reponse.status_code, 400)
        self.assertIn('existe déjà', reponse.json()['detail'])

        reponse = self.client.get(
            f'/api/habilitations/organisation/services/?departement={departement.id}'
        )
        self.assertEqual(len(reponse.json()['results']), 1)
        reponse = self.client.get(
            '/api/habilitations/organisation/services/?departement=99999'
        )
        self.assertEqual(reponse.json()['results'], [])

        # Détacher du département via PATCH.
        service_ = Service.objects.get(nom='Comptabilité')
        reponse = self.client.patch(
            f'/api/habilitations/organisation/services/{service_.id}/',
            {'departement': None}, format='json',
        )
        self.assertEqual(reponse.status_code, 200)
        self.assertIsNone(reponse.json()['departement_id'])

    # ── Rattachements comptes ─────────────────────────────────────────
    def test_08_rattachement_departement_ajout_retrait_erreurs(self):
        self._drapeau(True)
        self._auth()
        departement = Departement.objects.create(code='DAF', libelle='Affaires')

        reponse = self.client.post(
            f'/api/habilitations/organisation/departements/{departement.id}/comptes/',
            {'compte_id': self.compte.id}, format='json',
        )
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(
            [c['id'] for c in reponse.json()['comptes']], [self.compte.id]
        )
        self.assertIn(departement, self.compte.departements.all())

        reponse = self.client.get(
            f'/api/habilitations/organisation/departements/{departement.id}/'
        )
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(len(reponse.json()['comptes']), 1)

        reponse = self.client.delete(
            f'/api/habilitations/organisation/departements/{departement.id}/comptes/',
            {'compte_id': self.compte.id}, format='json',
        )
        self.assertEqual(reponse.status_code, 200)
        self.assertNotIn(departement, self.compte.departements.all())

        reponse = self.client.post(
            f'/api/habilitations/organisation/departements/{departement.id}/comptes/',
            {'compte_id': 99999}, format='json',
        )
        self.assertEqual(reponse.status_code, 404)
        reponse = self.client.post(
            '/api/habilitations/organisation/departements/99999/comptes/',
            {'compte_id': self.compte.id}, format='json',
        )
        self.assertEqual(reponse.status_code, 404)

    def test_09_rattachement_service_ajout_retrait(self):
        self._drapeau(True)
        self._auth()
        service_ = Service.objects.create(nom='Scolarité')

        reponse = self.client.post(
            f'/api/habilitations/organisation/services/{service_.id}/comptes/',
            {'compte_id': self.compte.id}, format='json',
        )
        self.assertEqual(reponse.status_code, 200)
        self.assertIn(service_, self.compte.services.all())

        reponse = self.client.delete(
            f'/api/habilitations/organisation/services/{service_.id}/comptes/',
            {'compte_id': self.compte.id}, format='json',
        )
        self.assertEqual(reponse.status_code, 200)
        self.assertNotIn(service_, self.compte.services.all())

    # ── Permissions effectives ────────────────────────────────────────
    def test_10_permissions_effectives_sans_role(self):
        self._drapeau(True)
        self._auth()
        reponse = self.client.get(
            f'/api/habilitations/comptes/{self.compte.id}/effective-permissions/'
        )
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.json()['count'], 0)
        self.assertEqual(reponse.json()['codes'], [])

        reponse = self.client.get(
            '/api/habilitations/comptes/99999/effective-permissions/'
        )
        self.assertEqual(reponse.status_code, 404)

    def test_11_permissions_effectives_avec_role_actif(self):
        from habilitations.services import comptes_admin
        self._drapeau(True)
        self._auth()
        role = RoleMetier.objects.get(code='AGENT_INSCRIPTIONS')
        AttributionRole.objects.create(
            compte=self.compte, role=role, niveau_effectif='N2',
            statut=AttributionRole.Statut.ACTIVE, motif='Test LOT 3.',
        )
        reponse = self.client.get(
            f'/api/habilitations/comptes/{self.compte.id}/effective-permissions/'
        )
        self.assertEqual(reponse.status_code, 200)
        codes = reponse.json()['codes']
        expected = comptes_admin.permissions_des_roles([role])
        self.assertGreater(len(expected), 0)
        self.assertEqual(set(codes), expected)
        self.assertEqual(reponse.json()['count'], len(codes))
        # Triée et sans doublon.
        self.assertEqual(codes, sorted(set(codes)))

    # ── Journalisation globale ────────────────────────────────────────
    def test_12_chaque_geste_mutant_est_journalise(self):
        self._drapeau(True)
        self._auth()
        self.assertEqual(self._journal_orga().count(), 0)
        self.client.post(
            '/api/habilitations/organisation/directions/',
            {'code': 'DG', 'libelle': 'Direction Générale'}, format='json',
        )
        direction = Direction.objects.get(code='DG')
        self.client.patch(
            f'/api/habilitations/organisation/directions/{direction.id}/',
            {'actif': False}, format='json',
        )
        departement = Departement.objects.create(code='D', libelle='Département test')
        self.client.post(
            f'/api/habilitations/organisation/departements/{departement.id}/comptes/',
            {'compte_id': self.compte.id}, format='json',
        )
        entrees = self._journal_orga().order_by('numero')
        self.assertEqual(entrees.count(), 3)
        for entree in entrees:
            self.assertIsNotNone(entree.acteur_id)
            self.assertNotEqual(entree.object_id, '')
