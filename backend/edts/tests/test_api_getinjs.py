"""GET-INJS — tests des routes ajoutées (import des inscrits, génération annuelle).

Chemins testés :

* ``POST /api/edts/lmd/import/inscrits/analyser/`` — analyse sans écriture ;
* ``POST /api/edts/lmd/import/inscrits/``          — import réel, idempotent ;
* ``GET  /api/edts/lmd/import/inscrits/synthese/`` — effectifs réels ;
* ``POST /api/edts/lmd/generate-annee/``           — génération des EDT ;
* ``GET  /api/edts/lmd/conception/``               — téléchargement du document.

Les gardes (RBAC) sont celles du module : lecture pour la synthèse et la
conception, planification pour l'import et la génération.
"""

import io
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from edts.models import CreneauTemplate, EmploiDuTemps, InscriptionImportee
from edts.tests.test_lot2_moteur import FabriqueLMD
from scolarite.models import Maquette

ENTETE = 'matricule;nom;prenoms;formation;niveau;semestre;groupe;vague\n'


def _utilisateur(nom, role):
    from django.contrib.auth import get_user_model

    U = get_user_model()
    user = U.objects.create_user(username=nom, password='x')
    user.role = role
    user.save()
    return user


class BaseApiTest(TestCase):
    def setUp(self):
        self.f = FabriqueLMD(self).creer_base(perimetre='INJS', filiere='F01')
        self.formation = self.f.cycle
        self.annee = self.f.annee
        self.f.creer_creneaux(jours=('LUNDI', 'MARDI'), heures=((8, 10), (10, 12)))
        self.f.creer_salle(nom='Salle A', capacite=60)
        maquette, ue, ecue = self.f.creer_maquette()
        ecue.volume_cm = 4
        ecue.save()
        maquette.statut = Maquette.Statut.ACTIVE
        maquette.save()

        self.admin = _utilisateur('admin-get', 'ADMIN')
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def fichier(self, lignes, nom='inscrits.csv'):
        contenu = (ENTETE + '\n'.join(lignes) + '\n').encode('utf-8')
        return SimpleUploadedFile(nom, contenu, content_type='text/csv')

    def lignes(self, nombre=10, groupe='L1-G1'):
        return [
            f'INJS-{i:03d};Nom{i};Prenom;{self.formation.intitule};L1;S1;{groupe};V1'
            for i in range(nombre)
        ]


class ImportApiTests(BaseApiTest):
    def test_analyse_sans_ecriture(self):
        reponse = self.client.post(
            '/api/edts/lmd/import/inscrits/analyser/',
            {'annee_academique_id': self.annee.pk, 'fichier': self.fichier(self.lignes(5))},
            format='multipart',
        )
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.data['lignes_valides'], 5)
        self.assertFalse(reponse.data['applique'])
        self.assertEqual(InscriptionImportee.objects.count(), 0)

    def test_import_reel(self):
        reponse = self.client.post(
            '/api/edts/lmd/import/inscrits/',
            {'annee_academique_id': self.annee.pk, 'fichier': self.fichier(self.lignes(5))},
            format='multipart',
        )
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.data['creees'], 5)
        self.assertTrue(reponse.data['applique'])
        self.assertEqual(InscriptionImportee.objects.count(), 5)

    def test_import_idempotent(self):
        donnees = {'annee_academique_id': self.annee.pk, 'fichier': self.fichier(self.lignes(3))}
        self.client.post('/api/edts/lmd/import/inscrits/', donnees, format='multipart')
        donnees['fichier'] = self.fichier(self.lignes(3))
        reponse = self.client.post('/api/edts/lmd/import/inscrits/', donnees, format='multipart')
        self.assertEqual(reponse.data['creees'], 0)
        self.assertEqual(reponse.data['mises_a_jour'], 3)
        self.assertEqual(InscriptionImportee.objects.count(), 3)

    def test_fichier_absent(self):
        reponse = self.client.post(
            '/api/edts/lmd/import/inscrits/',
            {'annee_academique_id': self.annee.pk},
            format='multipart',
        )
        self.assertEqual(reponse.status_code, 400)
        self.assertEqual(reponse.data['motif_echec'], 'FICHIER_REQUIS')

    def test_annee_requise(self):
        reponse = self.client.post(
            '/api/edts/lmd/import/inscrits/',
            {'fichier': self.fichier(self.lignes(1))},
            format='multipart',
        )
        self.assertEqual(reponse.status_code, 400)
        self.assertEqual(reponse.data['motif_echec'], 'ANNEE_ACADEMIQUE_REQUISE')

    def test_annee_introuvable(self):
        reponse = self.client.post(
            '/api/edts/lmd/import/inscrits/',
            {'annee_academique_id': 999999, 'fichier': self.fichier(self.lignes(1))},
            format='multipart',
        )
        self.assertEqual(reponse.status_code, 404)

    def test_fichier_sans_ligne_exploitable(self):
        reponse = self.client.post(
            '/api/edts/lmd/import/inscrits/',
            {'annee_academique_id': self.annee.pk,
             'fichier': self.fichier([';Sans;Matricule;X;L1;S1;G;V'])},
            format='multipart',
        )
        self.assertEqual(reponse.status_code, 422)
        self.assertEqual(reponse.data['lignes_valides'], 0)
        self.assertEqual(InscriptionImportee.objects.count(), 0)

    def test_synthese(self):
        self.client.post(
            '/api/edts/lmd/import/inscrits/',
            {'annee_academique_id': self.annee.pk, 'fichier': self.fichier(self.lignes(7))},
            format='multipart',
        )
        reponse = self.client.get(
            '/api/edts/lmd/import/inscrits/synthese/',
            {'annee': self.annee.pk},
        )
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.data['effectif_total'], 7)
        self.assertEqual(reponse.data['cohortes'][0]['groupe'], 'L1-G1')

    def test_synthese_refusee_sans_authentification(self):
        """La lecture reste réservée aux comptes authentifiés."""
        self.client.force_authenticate(user=None)
        reponse = self.client.get(
            '/api/edts/lmd/import/inscrits/synthese/', {'annee': self.annee.pk},
        )
        self.assertIn(reponse.status_code, (401, 403))

    def test_import_refuse_a_un_role_sans_droit_de_planification(self):
        """L'écriture (import) exige la capacité de planification EDT."""
        self.client.force_authenticate(user=_utilisateur('lecteur', 'AUDITEUR'))
        reponse = self.client.post(
            '/api/edts/lmd/import/inscrits/',
            {'annee_academique_id': self.annee.pk, 'fichier': self.fichier(self.lignes(1))},
            format='multipart',
        )
        self.assertIn(reponse.status_code, (401, 403))
        self.assertEqual(InscriptionImportee.objects.count(), 0)


class GenerationAnneeApiTests(BaseApiTest):
    def test_generation_annee(self):
        self.client.post(
            '/api/edts/lmd/import/inscrits/',
            {'annee_academique_id': self.annee.pk, 'fichier': self.fichier(self.lignes(12))},
            format='multipart',
        )
        reponse = self.client.post(
            '/api/edts/lmd/generate-annee/',
            {'annee_academique_id': self.annee.pk, 'semaines': [1]},
            format='json',
        )
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.data['totaux']['nb_groupes'], 1)
        self.assertEqual(reponse.data['totaux']['etudiants_couverts'], 12)
        self.assertGreater(reponse.data['totaux']['seances_placees'], 0)
        self.assertFalse(reponse.data['persistence_demandee'])

    def test_generation_persistee_cree_des_brouillons(self):
        self.client.post(
            '/api/edts/lmd/import/inscrits/',
            {'annee_academique_id': self.annee.pk, 'fichier': self.fichier(self.lignes(12))},
            format='multipart',
        )
        reponse = self.client.post(
            '/api/edts/lmd/generate-annee/',
            {'annee_academique_id': self.annee.pk, 'semaines': [1], 'persister': True},
            format='json',
        )
        self.assertEqual(reponse.status_code, 201)
        self.assertTrue(reponse.data['persistence_demandee'])
        self.assertEqual(EmploiDuTemps.objects.count(), 1)
        self.assertEqual(EmploiDuTemps.objects.first().statut, 'BROUILLON')

    def test_annee_sans_groupe_renvoie_409(self):
        CreneauTemplate.objects.all().delete()
        reponse = self.client.post(
            '/api/edts/lmd/generate-annee/',
            {'annee_academique_id': self.annee.pk, 'semaines': [1]},
            format='json',
        )
        self.assertEqual(reponse.status_code, 409)
        self.assertEqual(reponse.data['motif_echec'], 'AUCUN_GROUPE_INJS')

    def test_annee_impossible_explique_le_motif_global(self):
        """Un 409 doit dire pourquoi : groupes présents mais aucun besoin."""
        from scolarite.models import ECUE, Groupe, UE

        ECUE.objects.all().delete()
        UE.objects.all().delete()
        Maquette.objects.all().delete()
        Groupe.objects.create(
            annee_academique=self.annee, ref_formation=self.formation,
            niveau=self.f.niveau, nom='L1-ORPHELIN',
        )
        reponse = self.client.post(
            '/api/edts/lmd/generate-annee/',
            {'annee_academique_id': self.annee.pk, 'semaines': [1]},
            format='json',
        )
        self.assertEqual(reponse.status_code, 409)
        self.assertEqual(reponse.data['status_global'], 'IMPOSSIBLE')
        self.assertEqual(reponse.data['motif_echec'], 'AUCUN_BESOIN_PLANIFIABLE')
        self.assertTrue(reponse.data['detail']['explication'])
        self.assertTrue(reponse.data['detail']['action_recommandee'])


# Le manifeste WhiteNoise n'existe pas en base de test : même contournement que
# core/tests/test_admin_complet.py pour rendre l'admin réellement consultable.
STORAGE_DE_TEST = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}


@override_settings(STORAGES=STORAGE_DE_TEST)
class AdminInscriptionImporteeTests(BaseApiTest):
    """L'admin doit rendre les inscrits importés consultables, sans réécriture.

    Une inscription importée est la trace d'un fichier : la modifier romprait
    l'idempotence (année + matricule) et fausserait l'effectif réel.
    """

    def _superuser(self):
        from django.contrib.auth import get_user_model

        U = get_user_model()
        user = U.objects.create_superuser(
            username='root-get', email='root@example.org', password='x',
        )
        return user

    def test_inscription_importee_est_enregistree_dans_l_admin(self):
        from django.contrib import admin

        self.assertIn(InscriptionImportee, admin.site._registry)
        modele_admin = admin.site._registry[InscriptionImportee]
        self.assertFalse(modele_admin.has_add_permission(None))
        self.assertFalse(modele_admin.has_change_permission(None))

    def test_liste_admin_accessible_et_ajout_interdit(self):
        self.client.post(
            '/api/edts/lmd/import/inscrits/',
            {'annee_academique_id': self.annee.pk, 'fichier': self.fichier(self.lignes(3))},
            format='multipart',
        )
        self.assertEqual(InscriptionImportee.objects.count(), 3)

        navigateur = APIClient(SERVER_NAME='localhost')
        navigateur.force_login(self._superuser())
        liste = navigateur.get('/admin/edts/inscriptionimportee/')
        self.assertEqual(liste.status_code, 200)
        self.assertContains(liste, 'INJS-000')

        ajout = navigateur.get('/admin/edts/inscriptionimportee/add/')
        self.assertEqual(ajout.status_code, 403)


class ConceptionApiTests(BaseApiTest):
    def test_telechargement_du_document(self):
        chemin = Path(__file__).resolve().parents[3] / 'docs' / 'getinjs' / 'Conception-GET-INJS.txt'
        self.assertTrue(chemin.is_file(), 'le document de conception doit exister')

        reponse = self.client.get('/api/edts/lmd/conception/')
        self.assertEqual(reponse.status_code, 200)
        self.assertIn('attachment', reponse['Content-Disposition'])
        self.assertIn('Conception-GET-INJS.txt', reponse['Content-Disposition'])
        contenu = b''.join(reponse.streaming_content).decode('utf-8')
        self.assertIn('GET-INJS', contenu)
