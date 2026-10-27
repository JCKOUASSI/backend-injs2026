"""Tests lot A — organigramme unifié (Directions / Départements / Services / Secrétariats).

Couvre : arbre hiérarchique, CRUD et droits (lecture authentifiée, écriture DFRC),
unicité des codes, règle « au plus un rattachement » du secrétariat (§15),
désactivation au lieu de suppression, effectifs CURP (§13.8) et journalisation
immuable des gestes (``ORGANISATION_*``).
"""
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from administrations.models import Departement, Direction
from formations.models import RefTypeSecretariat, Secretariat
from habilitations.models import CompteUtilisateur, JournalHabilitation, Personne
from ressources_humaines.models import Service

User = get_user_model()

BASE = '/api/administrations/organigramme'


def _compte(username, role_legacy):
    user = User.objects.create_user(username=username, password='Mot#2026x', role=role_legacy)
    return user


def _avec_compte_curp(username, role_legacy='SECRETARIAT'):
    user = _compte(username, role_legacy)
    personne = Personne.objects.create(nom=username.title(), prenoms='Test')
    return user, CompteUtilisateur.objects.create(
        user=user, personne=personne, motif_statut='Création test organigramme.',
    )


class OrganigrammeArbreTests(APITestCase):
    def setUp(self):
        self.admin = _compte('orga-admin', 'ADMIN')
        self.dir = Direction.objects.create(code='DG', libelle='Direction Générale')
        self.dep = Departement.objects.create(code='DEP-PED', libelle='Département Pédagogie',
                                               direction=self.dir)
        self.svc = Service.objects.create(nom='Service Scolarité', code='SCOL01',
                                          departement=self.dep)
        self.type_s = RefTypeSecretariat.objects.create(libelle='Scolarité')
        self.sec = Secretariat.objects.create(nom='Secrétariat Scolaire', type=self.type_s,
                                               departement=self.dep)
        self.orphan = Departement.objects.create(code='DEP-X', libelle='Département autonome')

    def test_arbre_hiérarchique(self):
        self.client.force_login(self.admin)
        reponse = self.client.get(f'{BASE}/arbre/')
        self.assertEqual(reponse.status_code, 200, reponse.data)
        directions = reponse.data['directions']
        self.assertEqual([d['code'] for d in directions], ['DG'])
        dep_node = directions[0]['departements'][0]
        self.assertEqual(dep_node['code'], 'DEP-PED')
        self.assertEqual([s['nom'] for s in dep_node['services']], ['Service Scolarité'])
        self.assertEqual([s['nom'] for s in dep_node['secretariats']], ['Secrétariat Scolaire'])
        autonomes = reponse.data['non_rattaches']['departements']
        self.assertEqual([d['code'] for d in autonomes], ['DEP-X'])

    def test_arbre_masque_inactifs_sauf_demande(self):
        self.client.force_login(self.admin)
        self.dep.actif = False
        self.dep.save()
        reponse = self.client.get(f'{BASE}/arbre/')
        self.assertEqual(reponse.data['directions'][0]['departements'], [])
        reponse = self.client.get(f'{BASE}/arbre/?inactifs=1')
        codes = [d['code'] for d in reponse.data['directions'][0]['departements']]
        self.assertIn('DEP-PED', codes)

    def test_lecture_exige_authentification(self):
        reponse = self.client.get(f'{BASE}/arbre/')
        self.assertIn(reponse.status_code, (401, 403))


class OrganigrammeDirectionCrudTests(APITestCase):
    def setUp(self):
        self.admin = _compte('orga-admin2', 'ADMIN')
        self.secretaire = _compte('orga-sec', 'SECRETARIAT')

    def test_creation_et_champs_complets(self):
        self.client.force_login(self.admin)
        reponse = self.client.post(f'{BASE}/directions/', {
            'code': 'DAF', 'libelle': 'Direction Administrative et Financière',
            'description': 'Affaires générales', 'ordre': 2,
            'telephone': '+225 27 20 00 00 00', 'email': 'daf@injs.ci',
            'localisation': 'Bâtiment A, 1er étage',
            'responsable_id': self.secretaire.id, 'motif': 'Création initiale.',
        }, format='json')
        self.assertEqual(reponse.status_code, 201, reponse.data)
        donnees = reponse.data
        self.assertEqual(donnees['responsable']['id'], self.secretaire.id)
        self.assertEqual(donnees['localisation'], 'Bâtiment A, 1er étage')
        direction = Direction.objects.get(code='DAF')
        self.assertTrue(JournalHabilitation.objects.filter(
            type_evenement='ORGANISATION_CREEE', content_type__model='direction',
            object_id=str(direction.id)).exists())

    def test_code_doublon_rejete(self):
        Direction.objects.create(code='DAF', libelle='Existe déjà')
        self.client.force_login(self.admin)
        reponse = self.client.post(f'{BASE}/directions/', {'code': 'DAF', 'libelle': 'Autre'},
                                  format='json')
        self.assertEqual(reponse.status_code, 400)

    def test_ecriture_reservee_a_dfrc(self):
        self.client.force_login(self.secretaire)
        reponse = self.client.post(f'{BASE}/directions/', {'code': 'NOU', 'libelle': 'X'},
                                  format='json')
        self.assertEqual(reponse.status_code, 403)
        reponse = self.client.get(f'{BASE}/directions/')
        self.assertEqual(reponse.status_code, 200)

    def test_delete_desactive_sans_detruire(self):
        direction = Direction.objects.create(code='TEMP', libelle='À désactiver')
        self.client.force_login(self.admin)
        reponse = self.client.delete(f'{BASE}/directions/{direction.pk}/',
                                     {'motif': 'Réorganisation.'}, format='json')
        self.assertEqual(reponse.status_code, 204)
        direction.refresh_from_db()
        self.assertFalse(direction.actif)
        self.assertTrue(JournalHabilitation.objects.filter(
            type_evenement='ORGANISATION_DESACTIVEE').exists())

    def test_patch_partiel_valide(self):
        direction = Direction.objects.create(code='EP', libelle='Enseignement Professionnel')
        self.client.force_login(self.admin)
        reponse = self.client.patch(f'{BASE}/directions/{direction.pk}/',
                                    {'libelle': 'Directions des Enseignements', 'email': 'ep@injs.ci'},
                                    format='json')
        self.assertEqual(reponse.status_code, 200, reponse.data)
        direction.refresh_from_db()
        self.assertEqual(direction.libelle, 'Directions des Enseignements')
        self.assertEqual(direction.email, 'ep@injs.ci')
    # --- Modèle 13.4 : unités feuilles typées et imbriquables -------------------

    def test_sous_unite_imbriquee_dans_l_arbre(self):
        self.client.force_login(self.admin)
        direction = self.client.post(f'{BASE}/directions/', {'code': 'DP', 'libelle': 'DP'},
                                     format='json').data
        dep = self.client.post(f'{BASE}/departements/', {
            'code': 'DPE', 'libelle': 'Département examens',
            'direction': direction['id'],
        }, format='json').data
        racine = self.client.post(f'{BASE}/services/', {'nom': 'Service des examens',
                                                         'departement': dep['id']},
                                  format='json').data
        bureau = self.client.post(f'{BASE}/services/', {
            'nom': 'Bureau des délibérations', 'type_unite': 'BUREAU', 'parent': racine['id'],
        }, format='json').data
        detail = self.client.get(f'{BASE}/services/{bureau["id"]}/').data
        self.assertEqual(detail['type_unite'], 'BUREAU')
        self.assertEqual(detail['parent'], racine['id'])
        arbre = self.client.get(f'{BASE}/arbre/').data
        noeud_dep = arbre['directions'][0]['departements'][0]
        # Seule l'unité racine chapeaute le département ; le bureau est greffé
        # sous son service parent.
        self.assertEqual([s['nom'] for s in noeud_dep['services']], ['Service des examens'])
        self.assertEqual(noeud_dep['services'][0]['nb_sous_unites'], 1)
        self.assertEqual(noeud_dep['services'][0]['sous_unites'][0]['nom'],
                         'Bureau des délibérations')

    def test_rattachement_circulaire_refuse(self):
        self.client.force_login(self.admin)
        pere = self.client.post(f'{BASE}/services/', {'nom': 'Service parent'},
                                format='json').data
        fils = self.client.post(f'{BASE}/services/', {'nom': 'Unité enfant', 'parent': pere['id']},
                                format='json').data
        rep = self.client.patch(f'{BASE}/services/{pere["id"]}/', {'parent': fils['id']},
                                format='json')
        self.assertEqual(rep.status_code, 400)
        self.assertIn('circulaire', rep.data['detail'])

    def test_type_inconnu_et_parent_inexistant_refuses(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(f'{BASE}/services/',
                                          {'nom': 'Service bizare', 'type_unite': 'MAGASIN'},
                                          format='json').status_code, 400)
        self.assertEqual(self.client.post(f'{BASE}/services/',
                                          {'nom': 'Service orphelin', 'parent': 999999},
                                          format='json').status_code, 400)


class OrganigrammeSecretariatRattachementTests(APITestCase):
    def setUp(self):
        self.admin = _compte('orga-admin3', 'ADMIN')
        self.dir = Direction.objects.create(code='SG', libelle='Secrétariat Général')
        self.dep = Departement.objects.create(code='D-ADM', libelle='Département Administratif',
                                              direction=self.dir)
        self.user_sec = _compte('compte-sec', 'SECRETARIAT')

    def test_secretariat_rattache_a_departement(self):
        self.client.force_login(self.admin)
        reponse = self.client.post(f'{BASE}/secretariats/', {
            'nom': 'Bureau du courrier', 'departement': self.dep.pk,
        }, format='json')
        self.assertEqual(reponse.status_code, 201, reponse.data)
        secretariat = Secretariat.objects.get(pk=reponse.data['id'])
        self.assertEqual(secretariat.departement_id, self.dep.pk)
        self.assertIsNone(secretariat.direction_id)

    def test_double_rattachement_rejete(self):
        self.client.force_login(self.admin)
        reponse = self.client.post(f'{BASE}/secretariats/', {
            'nom': 'Anormal', 'direction': self.dir.pk, 'departement': self.dep.pk,
        }, format='json')
        self.assertEqual(reponse.status_code, 400)
        self.assertIn('au plus un', reponse.data['detail'])

    def test_changer_de_rattachement_libere_l_autre(self):
        secretariat = Secretariat.objects.create(nom='Permanence', departement=self.dep)
        self.client.force_login(self.admin)
        reponse = self.client.patch(f'{BASE}/secretariats/{secretariat.pk}/',
                                    {'direction': self.dir.pk}, format='json')
        self.assertEqual(reponse.status_code, 200, reponse.data)
        secretariat.refresh_from_db()
        self.assertEqual(secretariat.direction_id, self.dir.pk)
        self.assertIsNone(secretariat.departement_id)

    def test_effectif_secretariat_via_user(self):
        self.user_sec.secretariat_id = Secretariat.objects.create(nom='Vie étudiante').pk
        self.user_sec.save()
        self.client.force_login(self.admin)
        reponse = self.client.get(f'{BASE}/secretariats/')
        node = next(s for s in reponse.data if s['nom'] == 'Vie étudiante')
        self.assertEqual(node['nb_participants'], 0)  # participants legacy, pas comptes

    def test_types_secretariat_listables(self):
        RefTypeSecretariat.objects.create(libelle='Pédagogie')
        self.client.force_login(self.user_sec)
        reponse = self.client.get(f'{BASE}/types-secretariat/')
        self.assertEqual(reponse.status_code, 200)
        self.assertIn('Pédagogie', [t['libelle'] for t in reponse.data])


class OrganigrammeEffectifCompteTests(APITestCase):
    def setUp(self):
        self.admin = _compte('orga-admin4', 'ADMIN')
        self.dir = Direction.objects.create(code='DGF', libelle='DF')
        self.dep = Departement.objects.create(code='D-1', libelle='Département 1',
                                              direction=self.dir)
        self.svc = Service.objects.create(nom='Service 1', departement=self.dep)

    def test_effectifs_calculés_depuis_les_rattachements_curp(self):
        _, compte = _avec_compte_curp('agent-orga')
        compte.departements.add(self.dep)
        compte.services.add(self.svc)
        self.client.force_login(self.admin)
        reponse = self.client.get(f'{BASE}/departements/{self.dep.pk}/')
        self.assertEqual(reponse.data['effectif'], 1)
        reponse = self.client.get(f'{BASE}/services/{self.svc.pk}/')
        self.assertEqual(reponse.data['effectif'], 1)
        reponse = self.client.get(f'{BASE}/directions/{self.dir.pk}/')
        self.assertEqual(reponse.data['effectif'], 1)

    def test_service_creation_avec_champs_structure(self):
        self.client.force_login(self.admin)
        reponse = self.client.post(f'{BASE}/services/', {
            'nom': 'Service Courrier', 'code': 'SVC-COUR', 'departement': self.dep.pk,
            'telephone': '+225 07 00 00 00 00', 'localisation': 'RDC porte 4',
        }, format='json')
        self.assertEqual(reponse.status_code, 201, reponse.data)
        service = Service.objects.get(nom='Service Courrier')
        self.assertEqual(service.code, 'SVC-COUR')
        self.assertEqual(service.localisation, 'RDC porte 4')


class OrganigrammeMigrationCompatTests(APITestCase):
    """Les données préexistantes (sans les nouveaux champs) restent exploitables."""

    def test_anciens_secretariats_sans_rattachement(self):
        admin = _compte('orga-admin5', 'ADMIN')
        Secretariat.objects.create(nom='Ancien secrétariat')
        self.client.force_login(admin)
        reponse = self.client.get(f'{BASE}/secretariats/')
        self.assertEqual(reponse.status_code, 200)
        node = reponse.data[0]
        self.assertIsNone(node['direction'])
        self.assertTrue(node['actif'])
