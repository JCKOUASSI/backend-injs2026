"""Gestion générique des années académiques, alignée sur le processus INJS.

La plaquette « Années académiques » suit les mêmes normes que les autres :
bouton « Gérer », provenance suivie (source, fiabilité, description),
journal d'audit, suppression impossible. Le processus de l'Institut y est
appliqué : calendrier 1er octobre → 31 juillet au format AAAA-AAAA, une
seule année courante (la désigner bascule l'ancienne, comme le workflow
de réouverture de la scolarité), une année clôturée jamais courante, une
date de fin postérieure au début — en contraintes de base, pas seulement
dans les formulaires.
"""
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from referentiels.models import ReferentielJournal
from scolarite.models import AnneeAcademique

from .test_refonte import make_user


class GestionAnneesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('importer_referentiels_injs', '--sans-cycles')

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(make_user('admin_annees', role='ADMIN'))

    def _annee(self, libelle):
        return AnneeAcademique.objects.get(libelle=libelle)

    def test_creation_annee_planifiee_sans_code_distinct(self):
        res = self.client.post('/api/referentiels/annees/', {
            'libelle': '2029-2030',
            'date_debut': '2029-10-01', 'date_fin': '2030-07-31',
            'courante': False, 'cloturee': False,
            'description': 'Prévision à trois ans',
            'source_document': 'Calendrier de la Direction des études',
            'fiabilite': 'CADRAGE',
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        # Le libellé tient lieu de code dans le contrat unifié.
        self.assertEqual(res.data['code'], '2029-2030')
        annee = self._annee('2029-2030')
        self.assertEqual(str(annee.date_debut), '2029-10-01')
        self.assertEqual(annee.fiabilite, 'CADRAGE')
        self.assertTrue(
            ReferentielJournal.objects.filter(
                content_type=ContentType.objects.get_for_model(
                    AnneeAcademique),
                object_id=annee.pk,
                action=ReferentielJournal.Action.CREATION).exists())

    def test_bascule_de_l_annee_courante(self):
        planifiee = self._annee('2027-2028')
        res = self.client.patch(f'/api/referentiels/annees/{planifiee.id}/', {
            'courante': True,
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
        self.assertEqual(
            AnneeAcademique.objects.filter(courante=True).count(), 1)
        self.assertEqual(
            AnneeAcademique.courante_ou_none().libelle, '2027-2028')
        self.assertFalse(self._annee('2026-2027').courante)

    def test_regles_de_processus_rejetees_en_400(self):
        cas = {
            'format de libellé': {
                'libelle': 'Année 2030',
                'date_debut': '2030-10-01', 'date_fin': '2031-07-31'},
            'fin avant début': {
                'libelle': '2030-2031',
                'date_debut': '2031-07-31', 'date_fin': '2030-10-01'},
            'clôturée et courante': {
                'libelle': '2030-2031',
                'date_debut': '2030-10-01', 'date_fin': '2031-07-31',
                'courante': True, 'cloturee': True,
                'date_cloture': '2031-07-31'},
            'doublon': {
                'libelle': '2026-2027',
                'date_debut': '2026-10-01', 'date_fin': '2027-07-31'},
        }
        for nom, corps in cas.items():
            with self.subTest(cas=nom):
                res = self.client.post(
                    '/api/referentiels/annees/', corps, format='json')
                self.assertEqual(
                    res.status_code, status.HTTP_400_BAD_REQUEST, res.data)
        self.assertEqual(AnneeAcademique.objects.count(), 8)

    def test_provenance_importee_par_statut(self):
        self.assertFalse(
            AnneeAcademique.objects.filter(
                fiabilite='A_RENSEIGNER').exists())
        self.assertFalse(
            AnneeAcademique.objects.filter(source_document='').exists())
        self.assertFalse(
            AnneeAcademique.objects.filter(description='').exists())
        self.assertEqual(
            AnneeAcademique.objects.filter(fiabilite='OFFICIEL').count(), 6)
        planifiees = AnneeAcademique.objects.filter(fiabilite='CADRAGE')
        self.assertEqual(
            set(planifiees.values_list('libelle', flat=True)),
            {'2027-2028', '2028-2029'})

    def test_archivage_non_supporte_delete_interdit_auditeur_lecture(self):
        annee = self._annee('2026-2027')
        res = self.client.post(f'/api/referentiels/annees/{annee.id}/archiver/')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        res = self.client.delete(f'/api/referentiels/annees/{annee.id}/')
        self.assertEqual(res.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.client.force_authenticate(make_user('aud_annees', role='AUDITEUR'))
        res = self.client.post('/api/referentiels/annees/', {
            'libelle': '2030-2031',
            'date_debut': '2030-10-01', 'date_fin': '2031-07-31',
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)


class TableauDeBordAnneesTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(make_user('carto_annees', role='ADMIN'))

    def test_carte_annees_aux_normes(self):
        res = self.client.get('/api/referentiels/tableau-de-bord/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        entree = next(
            e for c in res.data['categories'] for e in c['entrees']
            if e['slug'] == 'annees'
        )
        self.assertTrue(entree['editable'])
        self.assertEqual(entree['route_ui'], '/referentiels/gestion/annees')
        self.assertTrue(entree['provenance_suivie'])
        self.assertTrue(entree['a_une_description'])
        self.assertFalse(entree['a_un_code'])
        self.assertFalse(entree['archivage_supporte'])
        self.assertEqual(
            entree['champs_dates'],
            ['date_debut', 'date_fin', 'date_cloture'])
