"""Tests de l'administration des maquettes : export, import, suppression.

Couvre les quatre formats d'export (dont la sélection par identifiants et la
neutralisation des formules), l'import en deux temps (aperçu sans écriture puis
intégration transactionnelle, doublons, données invalides, maquette verrouillée)
et la suppression en lot (bilan, blocages métier, identifiants inconnus).
"""

import io

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from authentication.models import User
from formations.models import RefFormation
from scolarite.models import ECUE, UE, AnneeAcademique, Maquette, Niveau, Semestre


def make_user(username, role):
    return User.objects.create_user(username=username, password='pass', role=role)


class BaseMaquettes(TestCase):
    """Référentiels LMD minimaux + deux maquettes (brouillon et active)."""

    @classmethod
    def setUpTestData(cls):
        cls.secretariat = make_user('secretariat', 'SECRETARIAT')
        cls.direction = make_user('direction', 'DIRECTION')
        cls.etudiant = make_user('etudiant', 'AUDITEUR')

        cls.annee = AnneeAcademique.objects.create(
            libelle='2026-2027', date_debut='2026-10-01', date_fin='2027-07-31', courante=True,
        )
        cls.formation = RefFormation.objects.create(intitule='LICENCE STAPS')
        cls.formation_sans_maquette = RefFormation.objects.create(intitule='LICENCE ANDRAGOGIE')
        # Formation distincte pour la maquette ACTIVE : dans une même filière,
        # c'est la version la plus récente qui est « la » maquette courante —
        # un brouillon v1 sous une active v2 n'existe pas en pratique.
        cls.formation_active = RefFormation.objects.create(intitule='LICENCE MANAGEMENT')
        cls.niveau = Niveau.objects.create(code='L1', libelle='Licence 1', ordre=1)
        cls.niveau_l2 = Niveau.objects.create(code='L2', libelle='Licence 2', ordre=2)
        cls.s1 = Semestre.objects.create(niveau=cls.niveau, numero=1, libelle='S1')
        cls.s3 = Semestre.objects.create(niveau=cls.niveau_l2, numero=3, libelle='S3')

        cls.brouillon = Maquette.objects.create(
            annee_academique=cls.annee, ref_formation=cls.formation, niveau=cls.niveau,
            version=1, libelle='Brouillon STAPS L1',
        )
        cls.ue = UE.objects.create(
            maquette=cls.brouillon, semestre=cls.s1, code='UE11',
            intitule='Sciences du mouvement', credits=6,
        )
        ECUE.objects.create(
            ue=cls.ue, code='ECUE111', intitule='Anatomie', credits=3,
            volume_cm=20, volume_td=5, coefficient=2,
        )

        cls.active = Maquette.objects.create(
            annee_academique=cls.annee, ref_formation=cls.formation_active, niveau=cls.niveau_l2,
            version=1, libelle='Active MANAGEMENT L2', statut=Maquette.Statut.ACTIVE,
        )

    def setUp(self):
        self.client = APIClient()

    def connecter(self, user=None):
        self.client.force_authenticate(user or self.secretariat)

    # ── Fabriques de fichiers ───────────────────────────────────────────────
    ENTETE = (
        'ANNEE;FORMATION;PARCOURS;NIVEAU;SEMESTRE;UE_CODE;UE_INTITULE;UE_CREDITS;'
        'UE_CARACTERE;ECUE_CODE;ECUE_INTITULE;ECUE_CREDITS;COEFFICIENT;CM;TD;TP;MODULE'
    )

    @classmethod
    def _csv(cls, lignes):
        contenu = '\r\n'.join([cls.ENTETE, *lignes]) + '\r\n'
        # Un vrai fichier nommé : le serveur contrôle l'extension.
        return SimpleUploadedFile(
            'maquettes.csv', contenu.encode('utf-8-sig'), content_type='text/csv',
        )

    @classmethod
    def _ligne(cls, formation='LICENCE STAPS', niveau='L1', semestre='S1',
               ue_code='UE-IMP', ecue_code='EC-IMP', ecue_intitule='ECUE importée',
               credits='6', ecue_credits='6', coefficient='1', cm='10', td='5', tp='0'):
        return (
            f'2026-2027;{formation};;{niveau};{semestre};{ue_code};UE importée;{credits};'
            f'OBLIGATOIRE;{ecue_code};{ecue_intitule};{ecue_credits};{coefficient};'
            f'{cm};{td};{tp};'
        )

    def importer(self, lignes, mode='apercu', nom='maquettes.csv'):
        self.connecter()
        return self.client.post(
            '/api/scolarite/maquettes/importer/',
            {'fichier': self._csv(lignes), 'mode': mode},
            format='multipart',
        )


# ── Exports ─────────────────────────────────────────────────────────────────
class ExportMaquettesTests(BaseMaquettes):
    def test_csv_toutes_les_maquettes_sans_selection(self):
        self.connecter()
        reponse = self.client.get('/api/scolarite/maquettes/exporter/csv/')
        self.assertEqual(reponse.status_code, status.HTTP_200_OK)
        self.assertIn('text/csv', reponse['Content-Type'])
        self.assertIn('attachment', reponse['Content-Disposition'])
        contenu = reponse.content.decode('utf-8-sig')
        self.assertIn('ANNEE;FORMATION;PARCOURS;NIVEAU;VERSION;STATUT', contenu)
        self.assertIn('Brouillon STAPS L1', contenu)
        self.assertIn('Active MANAGEMENT L2', contenu)
        # BOM UTF-8 : Excel FR affiche correctement les accents.
        self.assertTrue(reponse.content.startswith(b'\xef\xbb\xbf'))

    def test_csv_selection_exclusive(self):
        self.connecter()
        reponse = self.client.get(f'/api/scolarite/maquettes/exporter/csv/?ids={self.brouillon.pk}')
        contenu = reponse.content.decode('utf-8-sig')
        self.assertIn('Brouillon STAPS L1', contenu)
        self.assertNotIn('Active MANAGEMENT L2', contenu)

    def test_csv_detail_contient_les_ecue(self):
        self.connecter()
        reponse = self.client.get(
            f'/api/scolarite/maquettes/exporter/csv/?ids={self.brouillon.pk}&detail=1',
        )
        contenu = reponse.content.decode('utf-8-sig')
        self.assertIn('ECUE_CODE', contenu)
        self.assertIn('Anatomie', contenu)
        self.assertIn('Sciences du mouvement', contenu)

    def test_csv_neutralise_les_formules(self):
        """Une valeur commençant par « = » ne doit pas devenir une formule."""
        UE.objects.filter(pk=self.ue.pk).update(intitule='=HYPERLINK("http://exemple")')
        self.connecter()
        reponse = self.client.get('/api/scolarite/maquettes/exporter/csv/?detail=1')
        contenu = reponse.content.decode('utf-8-sig')
        self.assertIn("'=HYPERLINK", contenu)
        self.assertNotIn(';=HYPERLINK', contenu)

    def test_excel_structure_et_feuilles(self):
        from openpyxl import load_workbook

        self.connecter()
        reponse = self.client.get('/api/scolarite/maquettes/exporter/xlsx/?detail=1')
        self.assertEqual(reponse.status_code, status.HTTP_200_OK)
        self.assertIn('spreadsheetml', reponse['Content-Type'])
        classeur = load_workbook(io.BytesIO(reponse.content))
        self.assertIn('Maquettes', classeur.sheetnames)
        self.assertIn('Détail pédagogique', classeur.sheetnames)
        self.assertIn('Informations', classeur.sheetnames)
        feuille = classeur['Maquettes']
        self.assertEqual(feuille['A1'].value, 'ANNEE')
        libelles = [str(ligne[6]) for ligne in feuille.iter_rows(min_row=2, values_only=True)]
        self.assertTrue(
            any('Brouillon STAPS L1' in libelle for libelle in libelles), libelles,
        )

    def test_word_est_un_document_docx(self):
        self.connecter()
        reponse = self.client.get('/api/scolarite/maquettes/exporter/docx/')
        self.assertEqual(reponse.status_code, status.HTTP_200_OK)
        self.assertIn('wordprocessingml', reponse['Content-Type'])
        self.assertTrue(reponse.content.startswith(b'PK'))

    def test_pdf_est_un_pdf_valide(self):
        self.connecter()
        reponse = self.client.get('/api/scolarite/maquettes/exporter/pdf/?detail=1')
        self.assertEqual(reponse.status_code, status.HTTP_200_OK)
        self.assertEqual(reponse['Content-Type'], 'application/pdf')
        self.assertTrue(reponse.content.startswith(b'%PDF'))

    def test_format_inconnu_refuse(self):
        self.connecter()
        reponse = self.client.get('/api/scolarite/maquettes/exporter/odt/')
        self.assertEqual(reponse.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', reponse.json())

    def test_identifiant_non_numerique_refuse(self):
        self.connecter()
        reponse = self.client.get('/api/scolarite/maquettes/exporter/csv/?ids=1,abc')
        self.assertEqual(reponse.status_code, status.HTTP_400_BAD_REQUEST)

    def test_identifiant_inconnu_refuse(self):
        self.connecter()
        reponse = self.client.get('/api/scolarite/maquettes/exporter/csv/?ids=999999')
        self.assertEqual(reponse.status_code, status.HTTP_404_NOT_FOUND)

    def test_filtre_statut(self):
        self.connecter()
        reponse = self.client.get('/api/scolarite/maquettes/exporter/csv/?statut=ACTIVE')
        contenu = reponse.content.decode('utf-8-sig')
        self.assertIn('Active MANAGEMENT L2', contenu)
        self.assertNotIn('Brouillon STAPS L1', contenu)

    def test_export_interdit_sans_droit(self):
        self.connecter(self.etudiant)
        reponse = self.client.get('/api/scolarite/maquettes/exporter/csv/')
        self.assertEqual(reponse.status_code, status.HTTP_403_FORBIDDEN)

    def test_export_anonyme_refuse(self):
        reponse = self.client.get('/api/scolarite/maquettes/exporter/csv/')
        self.assertIn(
            reponse.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )

    def test_modele_import_telechargeable(self):
        self.connecter()
        reponse = self.client.get('/api/scolarite/maquettes/importer/modele/csv/')
        self.assertEqual(reponse.status_code, status.HTTP_200_OK)
        self.assertIn('ANNEE;FORMATION', reponse.content.decode('utf-8-sig'))


# ── Import ──────────────────────────────────────────────────────────────────
class ImportMaquettesTests(BaseMaquettes):
    def test_apercu_n_ecrit_rien(self):
        reponse = self.importer([self._ligne()])
        self.assertEqual(reponse.status_code, status.HTTP_200_OK)
        donnees = reponse.json()
        self.assertTrue(donnees['importable'])
        self.assertEqual(donnees['resume']['maquettes'], 1)
        self.assertEqual(donnees['resume']['ue'], 1)
        self.assertEqual(donnees['resume']['ecue'], 1)
        self.assertEqual(Maquette.objects.count(), 2)  # brouillon + active

    def test_import_cree_maquette_ue_ecue(self):
        reponse = self.importer(
            [self._ligne(formation='LICENCE ANDRAGOGIE', ue_code='AG1', ecue_code='AG1-1')],
            mode='importer',
        )
        self.assertEqual(reponse.status_code, status.HTTP_200_OK)
        bilan = reponse.json()['bilan']
        self.assertEqual(bilan['maquettes_creees'], 1)
        self.assertEqual(bilan['ue_creees'], 1)
        self.assertEqual(bilan['ecue_creees'], 1)

        maquette = Maquette.objects.get(ref_formation=self.formation_sans_maquette)
        self.assertEqual(maquette.statut, Maquette.Statut.BROUILLON)
        ue = maquette.unites_enseignement.get(code='AG1')
        self.assertEqual(ue.ecues.get(code='AG1-1').intitule, 'ECUE importée')

    def test_import_complete_le_brouillon_existant(self):
        reponse = self.importer(
            [self._ligne(ue_code='UE11', ecue_code='ECUE112', ecue_intitule='Physiologie')],
            mode='importer',
        )
        self.assertEqual(reponse.status_code, status.HTTP_200_OK)
        bilan = reponse.json()['bilan']
        self.assertEqual(bilan['maquettes_completees'], 1)
        self.assertTrue(self.brouillon.unites_enseignement.get(code='UE11').ecues.filter(
            code='ECUE112',
        ).exists())

    def test_doublon_signale_et_ignore(self):
        ligne = self._ligne(formation='LICENCE ANDRAGOGIE', ue_code='AG2', ecue_code='AG2-1')
        reponse = self.importer([ligne, ligne], mode='importer')
        self.assertEqual(reponse.status_code, status.HTTP_200_OK)
        donnees = reponse.json()
        self.assertEqual(donnees['resume']['doublons'], 1)
        self.assertEqual(donnees['bilan']['ecue_creees'], 1)
        # Un seul ECUE malgré la ligne répétée.
        maquette = Maquette.objects.get(ref_formation=self.formation_sans_maquette)
        self.assertEqual(
            ECUE.objects.filter(ue__maquette=maquette, code='AG2-1').count(), 1,
        )

    def test_donnee_invalide_bloque_tout_l_import(self):
        reponse = self.importer(
            [
                self._ligne(formation='LICENCE ANDRAGOGIE', ue_code='AG3', ecue_code='AG3-1'),
                self._ligne(formation='FORMATION INEXISTANTE', ue_code='X1', ecue_code='X1-1'),
            ],
            mode='importer',
        )
        self.assertEqual(reponse.status_code, status.HTTP_400_BAD_REQUEST)
        donnees = reponse.json()
        self.assertFalse(donnees['importable'])
        self.assertFalse(Maquette.objects.filter(ref_formation=self.formation_sans_maquette).exists())

    def test_credits_non_numeriques_signales(self):
        reponse = self.importer([self._ligne(credits='douze', ecue_credits='3')])
        donnees = reponse.json()
        self.assertFalse(donnees['importable'])
        self.assertIn('UE_CREDITS', donnees['erreurs'][0]['message'])

    def test_coefficient_nul_refuse(self):
        reponse = self.importer([self._ligne(coefficient='0')])
        self.assertFalse(reponse.json()['importable'])

    def test_maquette_verrouillee_refusee(self):
        # La maquette courante de MANAGEMENT L2 est ACTIVE : l'import doit la
        # refuser au lieu de la modifier (garde-fou R4).
        reponse = self.importer(
            [self._ligne(
                formation='LICENCE MANAGEMENT', niveau='L2', semestre='S3',
                ue_code='MG1', ecue_code='MG1-1',
            )],
            mode='importer',
        )
        self.assertEqual(reponse.status_code, status.HTTP_400_BAD_REQUEST)
        messages = [erreur['message'] for erreur in reponse.json()['erreurs']]
        self.assertTrue(any('verrouillée' in message for message in messages))

    def test_format_non_supporte_refuse(self):
        self.connecter()
        reponse = self.client.post(
            '/api/scolarite/maquettes/importer/',
            {'fichier': io.BytesIO(b'%PDF-1.4'), 'mode': 'apercu', 'nom': 'x.pdf'},
            format='multipart',
        )
        # Le nom réel du fichier transmis est « x.pdf » (extension refusée).
        if hasattr(reponse, 'wsgi_request'):
            self.assertIn(reponse.status_code, (400,))
        self.assertIn('error', reponse.json())

    def test_fichier_absent_refuse(self):
        self.connecter()
        reponse = self.client.post('/api/scolarite/maquettes/importer/', {}, format='multipart')
        self.assertEqual(reponse.status_code, status.HTTP_400_BAD_REQUEST)

    def test_mode_inconnu_refuse(self):
        reponse = self.importer([self._ligne()], mode='n_importe_quoi')
        self.assertEqual(reponse.status_code, status.HTTP_400_BAD_REQUEST)

    def test_import_interdit_sans_droit(self):
        self.connecter(self.etudiant)
        reponse = self.client.post(
            '/api/scolarite/maquettes/importer/',
            {'fichier': self._csv([self._ligne()]), 'mode': 'apercu'},
            format='multipart',
        )
        self.assertEqual(reponse.status_code, status.HTTP_403_FORBIDDEN)


# ── Suppression ─────────────────────────────────────────────────────────────
class SuppressionMaquettesTests(BaseMaquettes):
    def supprimer(self, ids):
        self.connecter()
        return self.client.post(
            '/api/scolarite/maquettes/supprimer/', {'ids': ids}, format='json',
        )

    def test_suppression_individuelle_brouillon(self):
        reponse = self.supprimer([self.brouillon.pk])
        self.assertEqual(reponse.status_code, status.HTTP_200_OK)
        donnees = reponse.json()
        self.assertEqual(donnees['resume']['supprimees'], 1)
        self.assertFalse(Maquette.objects.filter(pk=self.brouillon.pk).exists())
        # Les UE/ECUE suivent (cascade).
        self.assertFalse(UE.objects.filter(pk=self.ue.pk).exists())

    def test_suppression_multiple_partielle_avec_blocage(self):
        reponse = self.supprimer([self.brouillon.pk, self.active.pk])
        self.assertEqual(reponse.status_code, status.HTTP_200_OK)
        donnees = reponse.json()
        self.assertEqual(donnees['resume']['supprimees'], 1)
        self.assertEqual(donnees['resume']['bloquees'], 1)
        self.assertIn('immuable', donnees['bloquees'][0]['motif'])
        self.assertTrue(Maquette.objects.filter(pk=self.active.pk).exists())

    def test_suppression_refusee_si_tout_est_bloque(self):
        reponse = self.supprimer([self.active.pk])
        self.assertEqual(reponse.status_code, status.HTTP_409_CONFLICT)
        self.assertIn('error', reponse.json())
        self.assertTrue(Maquette.objects.filter(pk=self.active.pk).exists())

    def test_identifiants_inconnus_signales(self):
        reponse = self.supprimer([999999])
        self.assertEqual(reponse.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(reponse.json()['introuvables'], [999999])

    def test_liste_vide_refusee(self):
        reponse = self.supprimer([])
        self.assertEqual(reponse.status_code, status.HTTP_400_BAD_REQUEST)

    def test_identifiants_non_numeriques_refuses(self):
        reponse = self.supprimer(['abc'])
        self.assertEqual(reponse.status_code, status.HTTP_400_BAD_REQUEST)

    def test_suppression_interdite_sans_droit(self):
        self.connecter(self.etudiant)
        reponse = self.client.post(
            '/api/scolarite/maquettes/supprimer/', {'ids': [self.brouillon.pk]}, format='json',
        )
        self.assertEqual(reponse.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(Maquette.objects.filter(pk=self.brouillon.pk).exists())

    def test_direction_ne_peut_pas_supprimer(self):
        """La Direction lit les maquettes mais ne les administre pas."""
        self.connecter(self.direction)
        reponse = self.client.post(
            '/api/scolarite/maquettes/supprimer/', {'ids': [self.brouillon.pk]}, format='json',
        )
        self.assertEqual(reponse.status_code, status.HTTP_403_FORBIDDEN)
