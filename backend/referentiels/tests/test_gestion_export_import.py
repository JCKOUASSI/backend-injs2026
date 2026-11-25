"""Tests de la gestion par lot des référentiels : export, modèle, import, retrait.

Couvre les quatre formats, la sélection par identifiants, la protection contre
l'injection de formules, l'import en deux temps (aperçu sans écriture puis
application transactionnelle, résolution des clés étrangères, doublons,
valeurs inconnues) et le retrait logique par lot (archivage ou désactivation),
conforme à la règle « pas de suppression physique » du module.
"""

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from authentication.models import User
from scolarite.models import Niveau, Semestre, TypeFormation

BASE = '/api/referentiels'


def make_user(username, role):
    return User.objects.create_user(username=username, password='pass', role=role)


class BaseReferentiels(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = make_user('admin-ref', 'ADMIN')
        cls.secretariat = make_user('secretariat-ref', 'SECRETARIAT')
        cls.direction = make_user('direction-ref', 'DIRECTION')
        cls.auditeur = make_user('auditeur-ref', 'AUDITEUR')

        cls.type_formation = TypeFormation.objects.create(code='LMD', libelle='Licence-Master-Doctorat')
        cls.l1 = Niveau.objects.create(code='L1', libelle='Licence 1', ordre=1, credits_requis=60)
        cls.l2 = Niveau.objects.create(code='L2', libelle='Licence 2', ordre=2, credits_requis=60)
        cls.s1 = Semestre.objects.create(niveau=cls.l1, numero=1, libelle='Semestre 1')
        cls.s2 = Semestre.objects.create(niveau=cls.l1, numero=2, libelle='Semestre 2')
        # Une valeur piégée pour vérifier la neutralisation à l'export.
        cls.piege = TypeFormation.objects.create(code='X', libelle='=1+1')

    def setUp(self):
        self.client = APIClient()

    def connecter(self, user=None):
        self.client.force_authenticate(user or self.admin)

    @classmethod
    def _csv(cls, entete, lignes, nom='referentiel.csv'):
        contenu = '\r\n'.join([entete, *lignes]) + '\r\n'
        return SimpleUploadedFile(nom, contenu.encode('utf-8-sig'), content_type='text/csv')


class ExportReferentielsTests(BaseReferentiels):
    def test_export_quatre_formats(self):
        self.connecter(self.secretariat)
        attendus = {
            'csv': 'text/csv',
            'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'pdf': 'application/pdf',
        }
        for fmt, content_type in attendus.items():
            with self.subTest(fmt=fmt):
                reponse = self.client.get(f'/api/referentiels/niveaux/exporter/{fmt}/')
                self.assertEqual(reponse.status_code, status.HTTP_200_OK)
                self.assertIn(content_type, reponse['Content-Type'])
                self.assertIn('attachment;', reponse['Content-Disposition'])
                self.assertGreater(len(reponse.content), 100)
                self.assertEqual(reponse['Cache-Control'], 'private, no-store')

    def test_export_csv_contient_les_lignes_et_neutralise_les_formules(self):
        self.connecter(self.secretariat)
        reponse = self.client.get('/api/referentiels/types-formation/exporter/csv/')
        self.assertEqual(reponse.status_code, status.HTTP_200_OK)
        self.assertTrue(reponse.content.startswith(b'\xef\xbb\xbf'))  # BOM UTF-8
        texte = reponse.content.decode('utf-8-sig')
        self.assertIn('CODE;LIBELLE;ACTIF', texte.splitlines()[0])
        self.assertIn("X;'=1+1;OUI", texte)

    def test_export_selection_par_ids(self):
        self.connecter(self.secretariat)
        reponse = self.client.get(
            f'/api/referentiels/niveaux/exporter/csv/?ids={self.l2.pk}',
        )
        texte = reponse.content.decode('utf-8-sig')
        self.assertEqual(len(texte.strip().splitlines()), 2)
        self.assertIn('L2', texte)
        self.assertNotIn('L1', texte)

    def test_export_filtre_actif(self):
        Niveau.objects.create(code='L3', libelle='Licence 3', ordre=3, actif=False)
        self.connecter(self.secretariat)
        texte = self.client.get(
            '/api/referentiels/niveaux/exporter/csv/?actif=false',
        ).content.decode('utf-8-sig')
        self.assertIn('L3', texte)
        self.assertNotIn(';L1;', texte)

    def test_export_refuse_identifiant_inconnu_ou_non_numerique(self):
        self.connecter(self.secretariat)
        inconnu = self.client.get('/api/referentiels/niveaux/exporter/csv/?ids=99999')
        self.assertEqual(inconnu.status_code, status.HTTP_404_NOT_FOUND)
        invalide = self.client.get('/api/referentiels/niveaux/exporter/csv/?ids=abc')
        self.assertEqual(invalide.status_code, status.HTTP_400_BAD_REQUEST)
        inconnue = self.client.get('/api/referentiels/inexistant/exporter/csv/')
        self.assertEqual(inconnue.status_code, status.HTTP_404_NOT_FOUND)
        format_ = self.client.get('/api/referentiels/niveaux/exporter/xml/')
        self.assertEqual(format_.status_code, status.HTTP_400_BAD_REQUEST)

    def test_export_lisible_par_tout_utilisateur_authentifie(self):
        # Règle du module : la consultation (donc l’export) est ouverte à tout
        # authentifié ; seules les écritures exigent un rôle de gestion.
        self.connecter(self.auditeur)
        self.assertEqual(
            self.client.get(f'{BASE}/niveaux/exporter/csv/').status_code,
            status.HTTP_200_OK,
        )
        anonyme = APIClient()
        self.assertIn(
            anonyme.get(f'{BASE}/niveaux/exporter/csv/').status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )

    def test_modele_csv_et_xlsx(self):
        self.connecter(self.secretariat)
        csv_reponse = self.client.get('/api/referentiels/niveaux/importer/modele/csv/')
        self.assertEqual(csv_reponse.status_code, status.HTTP_200_OK)
        entete = csv_reponse.content.decode('utf-8-sig').splitlines()[0]
        self.assertEqual(entete, 'CODE;LIBELLE;CYCLE;ORDRE;CREDITS_REQUIS;ACTIF')
        xlsx = self.client.get('/api/referentiels/niveaux/importer/modele/xlsx/')
        self.assertEqual(xlsx.status_code, status.HTTP_200_OK)
        self.assertTrue(xlsx.content.startswith(b'PK'))
        refuse = self.client.get('/api/referentiels/niveaux/importer/modele/pdf/')
        self.assertEqual(refuse.status_code, status.HTTP_400_BAD_REQUEST)


class ImportReferentielsTests(BaseReferentiels):
    ENTETE = 'CODE;LIBELLE;CYCLE;ORDRE;CREDITS_REQUIS;ACTIF'

    def test_apercu_n_ecrit_rien(self):
        self.connecter()
        fichier = self._csv(self.ENTETE, ['L3;Licence 3;LICENCE;3;60;OUI'])
        avant = Niveau.objects.count()
        reponse = self.client.post(
            '/api/referentiels/niveaux/importer/',
            {'fichier': fichier, 'mode': 'apercu'}, format='multipart',
        )
        self.assertEqual(reponse.status_code, status.HTTP_200_OK)
        self.assertTrue(reponse.data['importable'])
        self.assertEqual(reponse.data['resume']['creations'], 1)
        self.assertEqual(Niveau.objects.count(), avant)

    def test_import_applique_et_resout_les_choix(self):
        self.connecter()
        fichier = self._csv(
            self.ENTETE,
            ['L3;Licence 3;licence;3;60;OUI', 'L4;Licence 4;LICENCE;4;60;NON'],
        )
        reponse = self.client.post(
            '/api/referentiels/niveaux/importer/',
            {'fichier': fichier, 'mode': 'importer'}, format='multipart',
        )
        self.assertEqual(reponse.status_code, status.HTTP_200_OK)
        self.assertEqual(reponse.data['resume']['creations'], 2)
        l3 = Niveau.objects.get(code='L3')
        self.assertEqual(l3.cycle, Niveau.Cycle.LICENCE)
        self.assertEqual(l3.credits_requis, 60)
        self.assertFalse(Niveau.objects.get(code='L4').actif)

    def test_import_met_a_jour_la_ligne_existante(self):
        self.connecter()
        fichier = self._csv(
            self.ENTETE, ['L1;Licence 1 rénovée;LICENCE;1;60;OUI'],
        )
        reponse = self.client.post(
            '/api/referentiels/niveaux/importer/',
            {'fichier': fichier, 'mode': 'importer'}, format='multipart',
        )
        self.assertEqual(reponse.status_code, status.HTTP_200_OK)
        self.assertEqual(reponse.data['resume']['mises_a_jour'], 1)
        self.l1.refresh_from_db()
        self.assertEqual(self.l1.libelle, 'Licence 1 rénovée')
        self.assertEqual(Niveau.objects.filter(code='L1').count(), 1)

    def test_import_semestres_resout_le_niveau_par_code(self):
        self.connecter()
        fichier = self._csv(
            'NIVEAU;NUMERO;LIBELLE;ACTIF',
            ['L2;3;Semestre 3;OUI', 'L1;1;Semestre 1 bis;OUI'],
        )
        reponse = self.client.post(
            '/api/referentiels/semestres/importer/',
            {'fichier': fichier, 'mode': 'importer'}, format='multipart',
        )
        self.assertEqual(reponse.status_code, status.HTTP_200_OK)
        self.assertTrue(Semestre.objects.filter(niveau=self.l2, numero=3).exists())
        self.s1.refresh_from_db()
        self.assertEqual(self.s1.libelle, 'Semestre 1 bis')
        self.assertEqual(reponse.data['resume']['mises_a_jour'], 1)

    def test_import_refuse_en_bloc_une_ligne_invalide(self):
        self.connecter()
        avant = Niveau.objects.count()
        fichier = self._csv(
            self.ENTETE,
            ['L3;Licence 3;LICENCE;3;60;OUI', 'L4;Licence 4;INCONNU;4;60;OUI'],
        )
        reponse = self.client.post(
            '/api/referentiels/niveaux/importer/',
            {'fichier': fichier, 'mode': 'importer'}, format='multipart',
        )
        self.assertEqual(reponse.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(reponse.data['importable'])
        self.assertEqual(reponse.data['resume']['rejets'], 1)
        self.assertEqual(Niveau.objects.count(), avant)
        self.assertIn('error', reponse.data)

    def test_import_signale_les_doublons_du_fichier(self):
        self.connecter()
        fichier = self._csv(
            self.ENTETE,
            ['L5;Licence 5;LICENCE;5;60;OUI', 'L5;Licence 5 bis;LICENCE;5;60;OUI'],
        )
        reponse = self.client.post(
            '/api/referentiels/niveaux/importer/?',
            {'fichier': fichier, 'mode': 'apercu'}, format='multipart',
        )
        self.assertEqual(reponse.status_code, status.HTTP_200_OK)
        self.assertFalse(reponse.data['importable'])
        self.assertTrue(any('doublon' in erreur['message'].lower() for erreur in reponse.data['erreurs']))

    def test_import_rejette_un_fichier_sans_colonne_reconnue(self):
        self.connecter()
        fichier = self._csv('FOO;BAR', ['1;2'])
        reponse = self.client.post(
            '/api/referentiels/niveaux/importer/',
            {'fichier': fichier, 'mode': 'apercu'}, format='multipart',
        )
        self.assertEqual(reponse.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('colonne', reponse.data['error'].lower())

    def test_import_est_reserve_aux_roles_de_gestion(self):
        self.connecter(self.auditeur)
        fichier = self._csv(self.ENTETE, ['L6;Licence 6;LICENCE;6;60;OUI'])
        reponse = self.client.post(
            '/api/referentiels/niveaux/importer/',
            {'fichier': fichier, 'mode': 'importer'}, format='multipart',
        )
        self.assertEqual(reponse.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(Niveau.objects.filter(code='L6').exists())


class RetraitReferentielsTests(BaseReferentiels):
    def test_retrait_logique_desactive_la_valeur(self):
        self.connecter()
        reponse = self.client.post(
            f'{BASE}/niveaux/supprimer/', {'ids': [self.l2.pk]}, format='json',
        )
        self.assertEqual(reponse.status_code, status.HTTP_200_OK)
        self.assertEqual(reponse.data['resume']['supprimees'], 1)
        self.assertEqual(reponse.data['mode'], 'désactivation')
        self.l2.refresh_from_db()
        self.assertFalse(self.l2.actif)
        # Aucune suppression physique : la ligne et ses données restent en base.
        self.assertTrue(Niveau.objects.filter(pk=self.l2.pk).exists())

    def test_retrait_relance_sur_une_valeur_deja_retiree(self):
        self.connecter()
        self.client.post(f'{BASE}/niveaux/supprimer/', {'ids': [self.l2.pk]}, format='json')
        reponse = self.client.post(
            f'{BASE}/niveaux/supprimer/', {'ids': [self.l2.pk]}, format='json',
        )
        self.assertEqual(reponse.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(reponse.data['resume']['bloquees'], 1)
        self.assertIn('déjà désactivée', reponse.data['bloquees'][0]['motif'])

    def test_retrait_partiel_et_valeurs_introuvables(self):
        self.connecter()
        reponse = self.client.post(
            f'{BASE}/niveaux/supprimer/', {'ids': [self.l2.pk, 99999]}, format='json',
        )
        self.assertEqual(reponse.status_code, status.HTTP_200_OK)
        self.assertEqual(reponse.data['resume']['supprimees'], 1)
        self.assertEqual(reponse.data['introuvables'], [99999])

    def test_retrait_valide_les_identifiants(self):
        self.connecter()
        self.assertEqual(
            self.client.post(f'{BASE}/niveaux/supprimer/', {'ids': ['abc']}, format='json').status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            self.client.post(f'{BASE}/niveaux/supprimer/', {'ids': []}, format='json').status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        inconnu = self.client.post(f'{BASE}/niveaux/supprimer/', {'ids': [99999]}, format='json')
        self.assertEqual(inconnu.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(inconnu.data['introuvables'], [99999])

    def test_retrait_reserve_aux_roles_de_gestion(self):
        self.connecter(self.auditeur)
        reponse = self.client.post(
            f'{BASE}/niveaux/supprimer/', {'ids': [self.l2.pk]}, format='json',
        )
        self.assertEqual(reponse.status_code, status.HTTP_403_FORBIDDEN)
        self.l2.refresh_from_db()
        self.assertTrue(self.l2.actif)

    def test_retrait_refuse_sur_un_referentiel_non_editable(self):
        self.connecter()
        reponse = self.client.post(
            f'{BASE}/formations/supprimer/', {'ids': [1]}, format='json',
        )
        self.assertEqual(reponse.status_code, status.HTTP_404_NOT_FOUND)
