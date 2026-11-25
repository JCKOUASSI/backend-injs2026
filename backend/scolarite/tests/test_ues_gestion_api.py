"""Tests de la gestion des UE/ECUE d'une maquette : export, modèle, import.

L'import est borné à la maquette ciblée : aucun fichier ne peut créer une
maquette ni toucher une autre maquette. L'aperçu n'écrit rien, l'application
est transactionnelle, et une maquette verrouillée est refusée avant lecture.
"""

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from authentication.models import User
from formations.models import RefFormation
from scolarite.models import ECUE, UE, AnneeAcademique, Maquette, Niveau, Semestre


def make_user(username, role):
    return User.objects.create_user(username=username, password='pass', role=role)


class BaseUes(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.secretariat = make_user('secretariat-ues', 'SECRETARIAT')
        cls.auditeur = make_user('auditeur-ues', 'AUDITEUR')

        cls.annee = AnneeAcademique.objects.create(
            libelle='2026-2027', date_debut='2026-10-01', date_fin='2027-07-31', courante=True,
        )
        cls.formation = RefFormation.objects.create(intitule='LICENCE STAPS')
        cls.niveau = Niveau.objects.create(code='L1', libelle='Licence 1', ordre=1)
        cls.s1 = Semestre.objects.create(niveau=cls.niveau, numero=1, libelle='S1')
        cls.s2 = Semestre.objects.create(niveau=cls.niveau, numero=2, libelle='S2')

        cls.maquette = Maquette.objects.create(
            annee_academique=cls.annee, ref_formation=cls.formation, niveau=cls.niveau,
            version=1, libelle='STAPS L1 2026',
        )
        cls.ue = UE.objects.create(
            maquette=cls.maquette, semestre=cls.s1, code='UE11',
            intitule='Sciences du mouvement', credits=6,
        )
        cls.ecue = ECUE.objects.create(
            ue=cls.ue, code='ECUE111', intitule='Anatomie', credits=3,
            volume_cm=20, volume_td=5, coefficient=2,
        )
        cls.ue_piegee = UE.objects.create(
            maquette=cls.maquette, semestre=cls.s2, code='UE21',
            intitule='=1+1', credits=4,
        )
        cls.maquette_active = Maquette.objects.create(
            annee_academique=cls.annee, ref_formation=cls.formation, niveau=cls.niveau,
            version=2, libelle='STAPS L1 2026 active', statut=Maquette.Statut.ACTIVE,
        )

    def setUp(self):
        self.client = APIClient()

    def connecter(self, user=None):
        self.client.force_authenticate(user or self.secretariat)

    @classmethod
    def _csv(cls, lignes, entete='SEMESTRE;UE_CODE;UE_INTITULE;UE_CREDITS;UE_CARACTERE;'
                                   'ECUE_CODE;ECUE_INTITULE;ECUE_CREDITS;COEFFICIENT;CM;TD;TP'):
        contenu = '\r\n'.join([entete, *lignes]) + '\r\n'
        return SimpleUploadedFile(
            'ue-ecue.csv', contenu.encode('utf-8-sig'), content_type='text/csv',
        )


class ExportUesTests(BaseUes):
    def test_export_quatre_formats(self):
        self.connecter()
        for fmt in ('csv', 'xlsx', 'docx', 'pdf'):
            with self.subTest(fmt=fmt):
                reponse = self.client.get(
                    f'/api/scolarite/maquettes/{self.maquette.pk}/ues/exporter/{fmt}/',
                )
                self.assertEqual(reponse.status_code, status.HTTP_200_OK)
                self.assertIn('attachment;', reponse['Content-Disposition'])
                self.assertGreater(len(reponse.content), 100)

    def test_export_csv_une_ligne_par_ecue_et_ue_seule(self):
        self.connecter()
        texte = self.client.get(
            f'/api/scolarite/maquettes/{self.maquette.pk}/ues/exporter/csv/',
        ).content.decode('utf-8-sig')
        lignes = texte.splitlines()
        self.assertEqual(
            lignes[0],
            'SEMESTRE;UE_CODE;UE_INTITULE;UE_CREDITS;UE_CARACTERE;UE_STATUT;ECUE_CODE;'
            'ECUE_INTITULE;ECUE_CREDITS;COEFFICIENT;HEURES_CM;HEURES_TD;HEURES_TP;'
            'HEURES_TOTAL;ECUE_STATUT',
        )
        self.assertTrue(any('UE11' in ligne and 'ECUE111' in ligne for ligne in lignes))
        # UE sans ECUE : ligne conservée, colonnes ECUE vides.
        self.assertTrue(any(ligne.startswith('S2;UE21;') for ligne in lignes))
        # Neutralisation de la formule.
        self.assertIn("'=1+1", texte)

    def test_export_selection_par_ids(self):
        self.connecter()
        texte = self.client.get(
            f'/api/scolarite/maquettes/{self.maquette.pk}/ues/exporter/csv/?ids={self.ue.pk}',
        ).content.decode('utf-8-sig')
        self.assertIn('UE11', texte)
        self.assertNotIn('UE21', texte)

    def test_export_valide_maquette_et_identifiants(self):
        self.connecter()
        self.assertEqual(
            self.client.get('/api/scolarite/maquettes/99999/ues/exporter/csv/').status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(
            self.client.get(
                f'/api/scolarite/maquettes/{self.maquette.pk}/ues/exporter/csv/?ids=99999',
            ).status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(
            self.client.get(
                f'/api/scolarite/maquettes/{self.maquette.pk}/ues/exporter/csv/?ids=x',
            ).status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            self.client.get(
                f'/api/scolarite/maquettes/{self.maquette.pk}/ues/exporter/xls/',
            ).status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_export_interdit_aux_profils_non_scolarite(self):
        self.connecter(self.auditeur)
        self.assertEqual(
            self.client.get(
                f'/api/scolarite/maquettes/{self.maquette.pk}/ues/exporter/csv/',
            ).status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_modele_ue_ecue(self):
        self.connecter()
        csv_reponse = self.client.get(
            f'/api/scolarite/maquettes/{self.maquette.pk}/ues/importer/modele/csv/',
        )
        self.assertEqual(csv_reponse.status_code, status.HTTP_200_OK)
        self.assertIn('UE_CODE', csv_reponse.content.decode('utf-8-sig').splitlines()[0])
        xlsx = self.client.get(
            f'/api/scolarite/maquettes/{self.maquette.pk}/ues/importer/modele/xlsx/',
        )
        self.assertEqual(xlsx.status_code, status.HTTP_200_OK)
        self.assertTrue(xlsx.content.startswith(b'PK'))


class ImportUesTests(BaseUes):
    def test_apercu_n_ecrit_rien(self):
        self.connecter()
        avant = (UE.objects.count(), ECUE.objects.count())
        reponse = self.client.post(
            f'/api/scolarite/maquettes/{self.maquette.pk}/ues/importer/',
            {'fichier': self._csv([
                'S1;UE-IMP;Psychologie;6;OBLIGATOIRE;EC-IMP;Psychologie du sport;6;1;20;10;0',
            ]), 'mode': 'apercu'},
            format='multipart',
        )
        self.assertEqual(reponse.status_code, status.HTTP_200_OK)
        self.assertTrue(reponse.data['importable'])
        self.assertEqual(reponse.data['resume']['ues_creees'], 1)
        self.assertEqual((UE.objects.count(), ECUE.objects.count()), avant)

    def test_import_groupe_les_ecue_sous_une_ue(self):
        self.connecter()
        reponse = self.client.post(
            f'/api/scolarite/maquettes/{self.maquette.pk}/ues/importer/',
            {'fichier': self._csv([
                'S2;UE-IMP;Psychologie;6;OBLIGATOIRE;EC-1;Psychologie sociale;3;1;20;10;0',
                'S2;UE-IMP;Psychologie;6;OBLIGATOIRE;EC-2;Psychologie cognitive;3;2;20;5;0',
            ]), 'mode': 'importer'},
            format='multipart',
        )
        self.assertEqual(reponse.status_code, status.HTTP_200_OK)
        self.assertEqual(reponse.data['resume']['ues_creees'], 1)
        self.assertEqual(reponse.data['resume']['ecues_creees'], 2)
        ue = UE.objects.get(maquette=self.maquette, code='UE-IMP')
        self.assertEqual(ue.semestre, self.s2)
        self.assertEqual(ue.ecues.count(), 2)

    def test_import_met_a_jour_ue_et_ecue_existantes(self):
        self.connecter()
        reponse = self.client.post(
            f'/api/scolarite/maquettes/{self.maquette.pk}/ues/importer/',
            {'fichier': self._csv([
                'S1;UE11;Sciences du mouvement rénovées;8;OBLIGATOIRE;ECUE111;Anatomie;4;2;25;5;0',
            ]), 'mode': 'importer'},
            format='multipart',
        )
        self.assertEqual(reponse.status_code, status.HTTP_200_OK)
        self.assertEqual(reponse.data['resume']['ues_mises_a_jour'], 1)
        self.assertEqual(reponse.data['resume']['ecues_mises_a_jour'], 1)
        self.ue.refresh_from_db()
        self.ecue.refresh_from_db()
        self.assertEqual(self.ue.intitule, 'Sciences du mouvement rénovées')
        self.assertEqual(self.ue.credits, 8)
        self.assertEqual(self.ecue.credits, 4)
        self.assertEqual(self.ecue.volume_cm, 25)
        self.assertEqual(UE.objects.filter(code='UE11').count(), 1)

    def test_import_refuse_en_bloc_une_ligne_invalide(self):
        self.connecter()
        avant = UE.objects.count()
        reponse = self.client.post(
            f'/api/scolarite/maquettes/{self.maquette.pk}/ues/importer/',
            {'fichier': self._csv([
                'S1;UE-OK;Valide;6;OBLIGATOIRE;EC-OK;ECUE valide;6;1;10;5;0',
                'S1;UE-KO;Invalide;abc;OBLIGATOIRE;EC-KO;ECUE invalide;6;1;10;5;0',
            ]), 'mode': 'importer'},
            format='multipart',
        )
        self.assertEqual(reponse.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(reponse.data['importable'])
        self.assertEqual(UE.objects.count(), avant)

    def test_import_exige_le_semestre_pour_une_nouvelle_ue(self):
        self.connecter()
        reponse = self.client.post(
            f'/api/scolarite/maquettes/{self.maquette.pk}/ues/importer/',
            {'fichier': self._csv([
                ';UE-SANS-SEM;Sans semestre;6;OBLIGATOIRE;EC-SEM;ECUE;6;1;10;0;0',
            ]), 'mode': 'apercu'},
            format='multipart',
        )
        self.assertEqual(reponse.status_code, status.HTTP_200_OK)
        self.assertFalse(reponse.data['importable'])
        self.assertTrue(any('SEMESTRE' in erreur['message'] for erreur in reponse.data['erreurs']))

    def test_import_refuse_une_maquette_verrouillee(self):
        self.connecter()
        reponse = self.client.post(
            f'/api/scolarite/maquettes/{self.maquette_active.pk}/ues/importer/',
            {'fichier': self._csv(['S1;UE-X;Test;6;OBLIGATOIRE;;;',]), 'mode': 'apercu'},
            format='multipart',
        )
        self.assertEqual(reponse.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('modifiables', reponse.data['error'])
        self.assertFalse(UE.objects.filter(maquette=self.maquette_active).exists())

    def test_import_sans_fichier(self):
        self.connecter()
        reponse = self.client.post(
            f'/api/scolarite/maquettes/{self.maquette.pk}/ues/importer/',
            {'mode': 'apercu'}, format='multipart',
        )
        self.assertEqual(reponse.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('fichier', reponse.data['error'])

    def test_import_valide_l_extension(self):
        self.connecter()
        fichier = SimpleUploadedFile('ue-ecue.txt', b'UE_CODE;UE_INTITULE', content_type='text/plain')
        reponse = self.client.post(
            f'/api/scolarite/maquettes/{self.maquette.pk}/ues/importer/',
            {'fichier': fichier, 'mode': 'apercu'}, format='multipart',
        )
        self.assertEqual(reponse.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Format', reponse.data['error'])
