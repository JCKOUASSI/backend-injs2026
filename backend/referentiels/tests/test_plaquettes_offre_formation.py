"""Plaquettes « Offre de formation » du tableau de bord : gérées comme les autres.

Exigence : « Formations (cycles) », « Modules officiels » et « Volumes horaires
(modélisation) » doivent être gérables exactement comme « Filières » — créer,
visualiser, modifier, supprimer, archiver, exporter (Word/Excel/CSV/PDF) et
importer (Excel/CSV).

Ces trois référentiels étaient déclarés en lecture seule et servis par des
routes dédiées non éditables. Ils passent désormais par le socle générique du
registre ; ce module verrouille ce contrat.
"""

from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from formations.models import RefFormation
from referentiels.models import RefModuleOfficiel, RefVolumeHoraireFormation
from referentiels.registre import REGISTRE

SLUGS = ('formations', 'modules-officiels', 'volumes-modules')
FORMATS_EXPORT = ('xlsx', 'docx', 'csv', 'pdf')


def _utilisateur(nom):
    """Utilisateur habilité à administrer les référentiels."""
    from authentication.models import User

    return User.objects.create_user(
        username=nom, password='pass1234', role='ADMIN',
    )


class PlaquettesEditablesTests(TestCase):
    """Le registre doit déclarer les trois plaquettes comme gérables."""

    def test_les_trois_plaquettes_sont_editables(self):
        for slug in SLUGS:
            with self.subTest(slug=slug):
                self.assertTrue(
                    REGISTRE[slug]['editable'],
                    f'{slug} devrait être gérable comme les autres',
                )

    def test_le_champ_libelle_est_correctement_declare(self):
        """Le modèle ne nomme pas toujours son intitulé « libelle »."""
        self.assertEqual(REGISTRE['formations']['champ_libelle'], 'intitule')
        self.assertEqual(
            REGISTRE['volumes-modules']['champ_libelle'], 'intitule_module')
        self.assertEqual(REGISTRE['modules-officiels']['champ_libelle'], 'libelle')

    def test_le_tableau_de_bord_les_annonce_editables(self):
        self.client = APIClient()
        self.client.force_authenticate(_utilisateur('tdb_plaquettes'))
        res = self.client.get('/api/referentiels/tableau-de-bord/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        entrees = {
            e['slug']: e
            for c in res.data['categories'] for e in c['entrees']
        }
        for slug in SLUGS:
            with self.subTest(slug=slug):
                self.assertTrue(entrees[slug]['editable'])


class CycleCompletTests(TestCase):
    """Créer, lire, modifier, archiver, réactiver, supprimer sur les trois."""

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(_utilisateur('cycle_plaquettes'))
        self.cycle = RefFormation.objects.create(
            code='CYCLE-PLAQUETTES', intitule='Cycle de test plaquettes',
            type_diplome='LICENCE',
        )

    def _creer(self, slug, libelle, code='PLAQ-TEST'):
        """Crée une valeur en JSON, comme le fait l'écran du Hub."""
        corps = {'libelle': libelle}
        if slug == 'formations':
            corps['code'] = code
        else:
            corps['formation'] = self.cycle.id
        return self.client.post(
            f'/api/referentiels/{slug}/', corps, format='json')

    def test_creation_lecture_modification(self):
        for slug in SLUGS:
            with self.subTest(slug=slug):
                res = self._creer(slug, f'Valeur test {slug}')
                self.assertEqual(
                    res.status_code, status.HTTP_201_CREATED, res.data)
                pk = res.data['id']
                detail = self.client.get(f'/api/referentiels/{slug}/{pk}/')
                self.assertEqual(detail.status_code, status.HTTP_200_OK)
                modif = self.client.patch(
                    f'/api/referentiels/{slug}/{pk}/', {'libelle': f'Modifié {slug}'})
                self.assertEqual(modif.status_code, status.HTTP_200_OK)

    def test_archivage_et_reactivation(self):
        for slug in SLUGS:
            with self.subTest(slug=slug):
                pk = self._creer(slug, f'A archiver {slug}').data['id']
                res = self.client.post(
                    f'/api/referentiels/{slug}/{pk}/archiver/', format='json')
                self.assertEqual(res.status_code, status.HTTP_200_OK)
                self.assertTrue(res.data['archive'])
                retour = self.client.post(
                    f'/api/referentiels/{slug}/{pk}/reactiver/', format='json')
                self.assertEqual(retour.status_code, status.HTTP_200_OK)
                self.assertFalse(retour.data['archive'])

    def test_activation_et_desactivation(self):
        for slug in SLUGS:
            with self.subTest(slug=slug):
                pk = self._creer(slug, f'A desactiver {slug}').data['id']
                res = self.client.post(
                    f'/api/referentiels/{slug}/{pk}/desactiver/', format='json')
                self.assertEqual(res.status_code, status.HTTP_200_OK)
                self.assertFalse(res.data['actif'])
                retour = self.client.post(
                    f'/api/referentiels/{slug}/{pk}/activer/', format='json')
                self.assertEqual(retour.status_code, status.HTTP_200_OK)
                self.assertTrue(retour.data['actif'])

    def test_suppression_reversible(self):
        """La suppression archive : la valeur n'est jamais détruite."""
        for slug in SLUGS:
            with self.subTest(slug=slug):
                pk = self._creer(slug, f'A supprimer {slug}').data['id']
                sans = self.client.post(
                    f'/api/referentiels/{slug}/{pk}/supprimer/')
                self.assertEqual(sans.status_code, status.HTTP_400_BAD_REQUEST)
                res = self.client.post(
                    f'/api/referentiels/{slug}/{pk}/supprimer/',
                    {'confirmation': 'confirmer'}, format='json')
                self.assertIn(
                    res.status_code,
                    (status.HTTP_200_OK, status.HTTP_204_NO_CONTENT),
                )
                self.assertTrue(
                    type(self)._modele(slug).objects.filter(
                        pk=pk, archive=True).exists()
                )

    @staticmethod
    def _modele(slug):
        return {
            'formations': RefFormation,
            'modules-officiels': RefModuleOfficiel,
            'volumes-modules': RefVolumeHoraireFormation,
        }[slug]


class ExportPlaquettesTests(TestCase):
    """Les quatre formats d'export, sur les trois plaquettes."""

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(_utilisateur('export_plaquettes'))

    def test_export_des_quatre_formats(self):
        for slug in SLUGS:
            for format_cible in FORMATS_EXPORT:
                with self.subTest(slug=slug, format=format_cible):
                    res = self.client.get(
                        f'/api/referentiels/{slug}/exporter/',
                        {'export': format_cible},
                    )
                    self.assertEqual(
                        res.status_code, status.HTTP_200_OK, res.content[:200])
                    self.assertIn(
                        'attachment',
                        res.headers.get('Content-Disposition', ''),
                    )

    def test_format_non_pris_en_charge_refuse(self):
        res = self.client.get(
            '/api/referentiels/formations/exporter/', {'export': 'rtf'})
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)


class ImportPlaquettesTests(TestCase):
    """Import Excel et CSV, sur les trois plaquettes."""

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(_utilisateur('import_plaquettes'))
        self.cycle = RefFormation.objects.create(
            code='CYCLE-IMPORT', intitule='Cycle pour import',
            type_diplome='LICENCE',
        )

    def _csv(self, slug):
        if slug == 'formations':
            return b'Code;Libell\xc3\xa9\nIMP-CSV;Formation import\xc3\xa9e CSV\n'
        if slug == 'modules-officiels':
            return (b'Libell\xc3\xa9;Formation\n'
                    + f'Module import\xc3\xa9 CSV;{self.cycle.id}\n'.encode())
        return (b'Libell\xc3\xa9;Formation;Heures CM\n'
                + f'Volume import\xc3\xa9 CSV;{self.cycle.id};15\n'.encode())

    def _xlsx(self, slug):
        from openpyxl import Workbook

        classeur = Workbook()
        feuille = classeur.active
        if slug == 'formations':
            feuille.append(['Code', 'Libellé'])
            feuille.append(['IMP-XLSX', 'Formation importée XLSX'])
        elif slug == 'modules-officiels':
            feuille.append(['Libellé', 'Formation'])
            feuille.append(['Module importé XLSX', self.cycle.id])
        else:
            feuille.append(['Libellé', 'Formation', 'Heures CM'])
            feuille.append(['Volume importé XLSX', self.cycle.id, 12])
        tampon = BytesIO()
        classeur.save(tampon)
        return tampon.getvalue()

    def _importer(self, slug, contenu, nom):
        fichier = SimpleUploadedFile(nom, contenu)
        analyse = self.client.post(
            f'/api/referentiels/{slug}/importer/analyse/',
            {'fichier': fichier, 'a_entete': 'true'},
            format='multipart',
        )
        self.assertEqual(analyse.status_code, status.HTTP_200_OK, analyse.data)
        fichier.seek(0)
        return self.client.post(
            f'/api/referentiels/{slug}/importer/',
            {'fichier': fichier, 'a_entete': 'true', 'mode': 'les_deux'},
            format='multipart',
        )

    def test_import_csv(self):
        for slug in SLUGS:
            with self.subTest(slug=slug):
                res = self._importer(slug, self._csv(slug), 'import.csv')
                self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
                self.assertEqual(res.data['lignes_rejetees'], 0)
                self.assertEqual(res.data['crees'], 1)

    def test_import_xlsx(self):
        for slug in SLUGS:
            with self.subTest(slug=slug):
                res = self._importer(slug, self._xlsx(slug), 'import.xlsx')
                self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
                self.assertEqual(res.data['crees'], 1)


class FiltresDeclaresTests(TestCase):
    """Les filtres de l'ancienne route dédiée restent disponibles."""

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(_utilisateur('filtres_plaquettes'))
        self.cycle = RefFormation.objects.create(
            code='CYCLE-FILTRES', intitule='Cycle pour filtres',
            type_diplome='LICENCE',
        )

    def test_filtre_filiere_et_semestre(self):
        """« ?filiere= » filtre ``filiere_code`` : le paramètre garde son nom métier."""
        RefModuleOfficiel.objects.create(
            formation=self.cycle, filiere_code='EM', semestre='S1',
            libelle='Biomécanique', ordre=1,
        )
        RefModuleOfficiel.objects.create(
            formation=self.cycle, filiere_code='APA', semestre='S1',
            libelle='Physiologie', ordre=1,
        )
        res = self.client.get(
            '/api/referentiels/modules-officiels/', {'filiere': 'EM'})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['count'], 1)
        self.assertEqual(res.data['results'][0]['libelle'], 'Biomécanique')

        res = self.client.get(
            '/api/referentiels/modules-officiels/',
            {'filiere': 'EM', 'semestre': 'S9'},
        )
        self.assertEqual(res.data['count'], 0)

    def test_filtre_formation(self):
        autre = RefFormation.objects.create(
            code='AUTRE-CYCLE', intitule='Autre cycle', type_diplome='MASTER')
        RefVolumeHoraireFormation.objects.create(
            formation=self.cycle, intitule_module='Volume A')
        RefVolumeHoraireFormation.objects.create(
            formation=autre, intitule_module='Volume B')
        res = self.client.get(
            '/api/referentiels/volumes-modules/', {'formation': self.cycle.id})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['count'], 1)
        self.assertEqual(res.data['results'][0]['libelle'], 'Volume A')
