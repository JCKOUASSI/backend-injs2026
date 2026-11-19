"""Gestion des trois plaquettes de l'offre, échanges et droits."""
import csv
from io import BytesIO, StringIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from openpyxl import load_workbook
from rest_framework.test import APIClient

from authentication.models import User
from formations.models import RefFormation
from referentiels.models import RefModuleOfficiel, RefVolumeHoraireFormation, ReferentielJournal

PREFIX = '/api/referentiels/gestion-donnees/'


class GestionOffreTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='gestion_offre', password='test', role='ADMIN')
        self.lecteur = User.objects.create_user(username='lecteur_offre', password='test', role='AUDITEUR')
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def test_catalogue_gestion_et_cycle_vie_des_trois_plaquettes(self):
        catalogue = self.client.get('/api/referentiels/tableau-de-bord/').data
        for slug in ('formations', 'modules-officiels', 'volumes-modules'):
            entry = next(e for cat in catalogue['categories'] for e in cat['entrees'] if e['slug'] == slug)
            self.assertTrue(entry['editable'])
            self.assertEqual(entry['libelle_bouton'], 'Gérer')
            self.assertEqual(entry['route_ui'], f'/referentiels/gestion/{slug}')
            self.assertTrue(entry['archivage_supporte'])
            self.assertEqual(entry['route_gestion'], f'/referentiels/gestion-donnees/{slug}/')

        formation = self.client.post(PREFIX + 'formations/', {
            'code': 'LIC-TEST', 'libelle': 'Licence test', 'type_diplome': 'LICENCE',
        })
        self.assertEqual(formation.status_code, 201, formation.data)
        fid = formation.data['id']
        for slug, data, model in (
            ('modules-officiels', {'libelle': 'Biomécanique', 'formation': fid, 'semestre': 'S1', 'ordre': 1}, RefModuleOfficiel),
            ('volumes-modules', {'libelle': 'Athlétisme', 'formation': fid, 'heures_cm': '12.50'}, RefVolumeHoraireFormation),
        ):
            base = PREFIX + slug + '/'
            create = self.client.post(base, data)
            self.assertEqual(create.status_code, 201, create.data)
            pk = create.data['id']
            self.assertEqual(self.client.get(base + str(pk) + '/').status_code, 200)
            self.assertEqual(self.client.patch(base + str(pk) + '/', {'libelle': data['libelle'] + ' II'}).status_code, 200)
            self.assertEqual(self.client.post(base + str(pk) + '/archiver/').status_code, 200)
            self.assertFalse(model.objects.get(pk=pk).actif)
            self.assertEqual(self.client.get(base).data['count'], 0)
            self.assertEqual(self.client.get(base + '?archives=1').data['count'], 1)
            self.assertEqual(self.client.post(base + str(pk) + '/reactiver/').status_code, 200)
            self.assertTrue(model.objects.get(pk=pk).actif)
        self.assertEqual(self.client.post(PREFIX + f'formations/{fid}/archiver/').status_code, 200)
        self.assertEqual(self.client.get('/api/formations/ref/formations/').data, [])

    def test_suppression_isolee_et_archivage_si_utilise(self):
        base = PREFIX + 'formations/'
        libre = RefFormation.objects.create(intitule='Cycle libre', code='LIBRE')
        libre_pk = libre.pk
        self.assertEqual(self.client.delete(base + str(libre_pk) + '/').status_code, 204)
        self.assertFalse(RefFormation.objects.filter(pk=libre_pk).exists())
        self.assertTrue(ReferentielJournal.objects.filter(
            object_id=libre_pk, detail__suppression_definitive=True,
        ).exists())

        lie = RefFormation.objects.create(intitule='Cycle utilisé', code='LIE')
        RefModuleOfficiel.objects.create(formation=lie, libelle='Module lié')
        response = self.client.delete(base + str(lie.pk) + '/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data['archive'])
        lie.refresh_from_db()
        self.assertTrue(lie.archive)
        self.assertTrue(RefModuleOfficiel.objects.filter(formation=lie).exists())
        self.assertEqual(self.client.post(base + str(lie.pk) + '/reactiver/').status_code, 200)

    def test_suppression_interdite_au_lecteur(self):
        libre = RefFormation.objects.create(intitule='Cycle à protéger', code='PROT')
        self.client.force_authenticate(self.lecteur)
        self.assertEqual(self.client.delete(PREFIX + f'formations/{libre.pk}/').status_code, 403)
        self.assertTrue(RefFormation.objects.filter(pk=libre.pk).exists())

    def test_lot_statuts_et_suppression_mixte_sans_cascade(self):
        base = PREFIX + 'formations/'
        libres = [RefFormation.objects.create(intitule=f'Libre {n}', code=f'L{n}')
                  for n in (1, 2)]
        lie = RefFormation.objects.create(intitule='Lié', code='L3')
        module = RefModuleOfficiel.objects.create(formation=lie, libelle='Conservé')
        ids = [libres[0].pk, libres[1].pk]
        res = self.client.post(base + 'lot/', {'ids': ids, 'action': 'desactiver'}, format='json')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(set(RefFormation.objects.filter(pk__in=ids, actif=False)
                             .values_list('pk', flat=True)), set(ids))
        res = self.client.post(base + 'lot/', {'ids': ids, 'action': 'activer'}, format='json')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(RefFormation.objects.filter(pk__in=ids, actif=True).count(), 2)
        res = self.client.post(base + 'lot/', {
            'ids': [*ids, lie.pk], 'action': 'supprimer',
        }, format='json')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual([r['resultat'] for r in res.data['resultats']],
                         ['supprime', 'supprime', 'archive'])
        self.assertFalse(RefFormation.objects.filter(pk__in=ids).exists())
        lie.refresh_from_db()
        self.assertTrue(lie.archive)
        self.assertTrue(RefModuleOfficiel.objects.filter(pk=module.pk, formation=lie).exists())

    def test_lot_atome_refus_et_droits(self):
        base = PREFIX + 'formations/'
        libres = [RefFormation.objects.create(intitule=f'Contrôle {n}', code=f'C{n}')
                  for n in (1, 2)]
        ids = [obj.pk for obj in libres]
        for valeurs in ([ids[0], 999999], [ids[0], ids[0]]):
            res = self.client.post(base + 'lot/', {
                'ids': valeurs, 'action': 'supprimer',
            }, format='json')
            self.assertEqual(res.status_code, 400, res.data)
            self.assertTrue(RefFormation.objects.filter(pk__in=ids).count() == 2)
        self.client.force_authenticate(self.lecteur)
        res = self.client.post(base + 'lot/', {
            'ids': ids, 'action': 'archiver',
        }, format='json')
        self.assertEqual(res.status_code, 403, res.data)
        self.assertEqual(RefFormation.objects.filter(pk__in=ids, archive=False).count(), 2)

    def test_lot_archivage_atome_si_modele_non_compatible(self):
        base = '/api/referentiels/niveaux/lot/'
        from scolarite.models import Niveau
        n = Niveau.objects.create(code='TEMP', libelle='Niveau temporaire')
        res = self.client.post(base, {'ids': [n.pk], 'action': 'archiver'}, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertTrue(Niveau.objects.filter(pk=n.pk, actif=True).exists())

    def test_exports_quatre_formats_et_import_roundtrip_csv_xlsx(self):
        formation = RefFormation.objects.create(intitule='Licence Sports', code='LS')
        for slug, obj, label in (
            ('formations', formation, 'Licence Sports'),
            ('modules-officiels', RefModuleOfficiel.objects.create(formation=formation, libelle='Test module'), 'Test module'),
            ('volumes-modules', RefVolumeHoraireFormation.objects.create(formation=formation, intitule_module='Test volume'), 'Test volume'),
        ):
            base = PREFIX + slug + '/'
            contenu = {}
            for ext, signature in (('csv', b'\xef\xbb\xbf'), ('xlsx', b'PK'), ('docx', b'PK'), ('pdf', b'%PDF')):
                res = self.client.get(base + 'export/?export=' + ext)
                self.assertEqual(res.status_code, 200, res.content[:200])
                self.assertTrue(res.content.startswith(signature))
                self.assertIn(f'{slug}.{ext}', res['Content-Disposition'])
                contenu[ext] = res.content
            reader = csv.DictReader(StringIO(contenu['csv'].decode('utf-8-sig')), delimiter=';')
            self.assertIn(label, [row['libelle'] for row in reader])
            self.assertEqual(load_workbook(BytesIO(contenu['xlsx'])).active['A1'].value, 'id')
            from docx import Document
            self.assertEqual(Document(BytesIO(contenu['docx'])).tables[0].rows[0].cells[0].text, 'id')
            # Le même fichier est réimportable ; l'id identifie une mise à jour.
            for ext, mime in (('csv', 'text/csv'), ('xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')):
                file = SimpleUploadedFile('offre.' + ext, contenu[ext], content_type=mime)
                res = self.client.post(base + 'import/', {'fichier': file}, format='multipart')
                self.assertEqual(res.status_code, 200, res.data)
                self.assertEqual(res.data['modifies'], 1)
            self.assertTrue(obj.__class__.objects.filter(pk=obj.pk).exists())

    def test_export_securise_formules_et_entetes_import(self):
        RefFormation.objects.create(intitule='=HYPERLINK("evil")', code='FOO')
        base = PREFIX + 'formations/'
        res = self.client.get(base + 'export/?export=csv')
        self.assertIn("'=HYPERLINK", res.content.decode('utf-8-sig'))
        res = self.client.get(base + 'export/?export=xlsx')
        ws = load_workbook(BytesIO(res.content)).active
        self.assertEqual(ws['C2'].data_type, 's')
        res = self.client.post(base + 'import/', {
            'fichier': SimpleUploadedFile('faux.xlsx', b'pas une archive zip')}, format='multipart')
        self.assertEqual(res.status_code, 400)
        res = self.client.post(base + 'import/', {
            'fichier': SimpleUploadedFile('faux.csv', b'inconnu\nX')}, format='multipart')
        self.assertEqual(res.status_code, 400)

    def test_import_atomique_et_permissions(self):
        base = PREFIX + 'modules-officiels/'
        formation = RefFormation.objects.create(intitule='Licence', code='LIC')
        csv_file = f'libelle;formation;semestre\nModule A;{formation.pk};S1\nModule B;999999;S1\n'
        res = self.client.post(base + 'import/', {
            'fichier': SimpleUploadedFile('modules.csv', csv_file.encode())}, format='multipart')
        self.assertEqual(res.status_code, 400, res.data)
        self.assertFalse(RefModuleOfficiel.objects.filter(libelle='Module A').exists())
        self.client.force_authenticate(self.lecteur)
        self.assertEqual(self.client.get(base).status_code, 200)
        self.assertEqual(self.client.get(base + 'export/?export=pdf').status_code, 200)
        self.assertEqual(self.client.post(base, {'libelle': 'Interdit', 'formation': formation.pk}).status_code, 403)
        self.assertEqual(self.client.post(base + 'import/', {
            'fichier': SimpleUploadedFile('x.csv', csv_file.encode())}, format='multipart').status_code, 403)
