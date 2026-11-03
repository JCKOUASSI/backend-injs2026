"""Gestion générique des lieux et des vagues (Organisation pédagogique).

Sites, bâtiments, salles et espaces, vagues : ces quatre référentiels
historiques (modèles formations) sont gérés par le même écran générique
que les référentiels du socle — bouton « Gérer » sur la carte, contrat
code/libellé unifié malgré le champ ``nom``, unicité du nom bornée au
site pour les bâtiments et les salles, codes métier à tiret (AMP-001),
coordonnées décimales de géorepérage, périodes et effectifs des vagues.
L'API historique /formations/ref/ reste en place pour ses consommateurs.
"""
from decimal import Decimal

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from formations.models import RefBatiment, RefFormation, RefSalle, RefSite, RefVague
from referentiels.models import RefStatutVague, RefTypeEspaceSportif

from .test_refonte import make_user


class GestionLieuxBase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(make_user('admin_lieux', role='ADMIN'))
        self.site = RefSite.objects.create(nom='INJS Marcory', actif=True)
        self.batiment = RefBatiment.objects.create(
            site=self.site, nom='Bloc ENSEPS', actif=True)


class GestionSitesTests(GestionLieuxBase):
    def test_creation_sans_code_et_georeperage_decimal(self):
        res = self.client.post('/api/referentiels/sites/', {
            'libelle': 'Site annexe — Plateau sportif',
            'geofence_latitude': '5.308300',
            'geofence_longitude': '-3.982500',
            'geofence_rayon_m': 200,
            'source_document': 'Inventaire DIEM', 'fiabilite': 'MODELISE',
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        # Le nom tient lieu de code dans le contrat unifié.
        self.assertEqual(res.data['code'], 'Site annexe — Plateau sportif')
        site = RefSite.objects.get(nom='Site annexe — Plateau sportif')
        self.assertEqual(site.geofence_latitude, Decimal('5.308300'))
        self.assertEqual(site.geofence_rayon_m, 200)

    def test_doublon_de_nom_refuse(self):
        res = self.client.post('/api/referentiels/sites/', {
            'libelle': ' injs marcory ',
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)


class GestionBatimentsTests(GestionLieuxBase):
    def test_unicite_du_nom_par_site(self):
        autre_site = RefSite.objects.create(nom='Site annexe', actif=True)
        # Même nom sur un autre site : admis (contrainte unique par site).
        res = self.client.post('/api/referentiels/batiments/', {
            'libelle': 'Bloc ENSEPS', 'site': autre_site.id,
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        self.assertEqual(res.data['site_libelle'], 'Site annexe')
        # Même nom sur le même site : refusé.
        res = self.client.post('/api/referentiels/batiments/', {
            'libelle': 'Bloc ENSEPS', 'site': self.site.id,
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)


class GestionSallesTests(GestionLieuxBase):
    def setUp(self):
        super().setUp()
        self.type_gym = RefTypeEspaceSportif.objects.create(
            code='GYMNASE', libelle='Gymnase')

    def test_creation_complete_code_a_tiret_et_selecteurs(self):
        res = self.client.post('/api/referentiels/salles/', {
            'code': 'GYM-001', 'libelle': 'Gymnase 1', 'type_lieu': 'GYMNASE',
            'capacite': 120, 'equipements': 'Praticable, gradins',
            'indisponible_du': '2026-08-01', 'indisponible_au': '2026-08-31',
            'site': self.site.id, 'batiment': self.batiment.id,
            'type_espace': self.type_gym.id,
            'source_document': 'Inventaire des lieux', 'fiabilite': 'MODELISE',
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        salle = RefSalle.objects.get(code='GYM-001')
        self.assertEqual(salle.nom, 'Gymnase 1')
        self.assertEqual(salle.capacite, 120)
        self.assertEqual(str(salle.indisponible_du), '2026-08-01')
        self.assertEqual(res.data['site_libelle'], 'INJS Marcory')
        self.assertEqual(res.data['batiment_libelle'], 'Bloc ENSEPS')
        self.assertEqual(res.data['type_espace_libelle'], 'Gymnase')

    def test_type_lieu_hors_nomenclature_refuse(self):
        res = self.client.post('/api/referentiels/salles/', {
            'code': 'X-001', 'libelle': 'Salle X', 'type_lieu': 'PISCINE',
            'site': self.site.id,
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_archivage_non_supporte_et_delete_interdit(self):
        salle = RefSalle.objects.create(
            site=self.site, batiment=self.batiment, code='SC-001',
            nom='Salle de cours 1', type_lieu='COURS')
        res = self.client.post(f'/api/referentiels/salles/{salle.id}/archiver/')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        res = self.client.delete(f'/api/referentiels/salles/{salle.id}/')
        self.assertEqual(res.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


class GestionVaguesTests(GestionLieuxBase):
    def test_creation_complete_avec_rattachements(self):
        formation = RefFormation.objects.create(
            code='LIC-EM', intitule='Licence Éducation et Motricité')
        statut = RefStatutVague.objects.create(
            code='PREVISIONNELLE', libelle='Prévisionnelle', est_ouvert=False)
        res = self.client.post('/api/referentiels/vagues/', {
            'code': 'VAGUE_T1', 'libelle': 'Vague de test 1', 'ordre': 1,
            'periode_debut': '2026-10-01', 'periode_fin': '2029-06-30',
            'effectif_prevu': 120,
            'formation': formation.id, 'site': self.site.id,
            'statut': statut.id,
            'source_document': 'Vagues INJS 2026', 'fiabilite': 'OFFICIEL',
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        vague = RefVague.objects.get(code='VAGUE_T1')
        self.assertEqual(vague.effectif_prevu, 120)
        self.assertEqual(str(vague.periode_debut), '2026-10-01')
        self.assertEqual(
            res.data['formation_libelle'], 'Licence Éducation et Motricité')
        self.assertEqual(res.data['statut_libelle'], 'Prévisionnelle')

    def test_auditeur_en_lecture_seule(self):
        self.client.force_authenticate(make_user('aud_lieux', role='AUDITEUR'))
        res = self.client.post('/api/referentiels/vagues/', {
            'code': 'VAGUE_9', 'libelle': 'Vague interdite',
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)


class TableauDeBordLieuxTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(make_user('carto_lieux', role='ADMIN'))

    def _entree(self, slug):
        res = self.client.get('/api/referentiels/tableau-de-bord/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        return next(
            e for c in res.data['categories'] for e in c['entrees']
            if e['slug'] == slug
        )

    def test_quatre_cartes_editables_avec_bouton_gerer(self):
        for slug in ('sites', 'batiments', 'salles', 'vagues'):
            with self.subTest(slug=slug):
                entree = self._entree(slug)
                self.assertTrue(entree['editable'])
                self.assertEqual(
                    entree['route_ui'], f'/referentiels/gestion/{slug}')
                self.assertFalse(entree['archivage_supporte'])
                self.assertFalse(entree['a_une_description'])
                self.assertTrue(entree['provenance_suivie'])

    def test_metadonnees_salles_et_vagues(self):
        salles = self._entree('salles')
        self.assertTrue(salles['a_un_code'])
        self.assertEqual(len(salles['champs_choix']['type_lieu']), 11)
        self.assertEqual(
            salles['champs_dates'], ['indisponible_du', 'indisponible_au'])
        self.assertEqual(
            salles['selecteurs_routes']['batiment']['route'],
            '/referentiels/batiments/')
        self.assertEqual(
            salles['selecteurs_routes']['type_espace']['route'],
            '/referentiels/types-espace-sportif/')

        sites = self._entree('sites')
        self.assertFalse(sites['a_un_code'])
        self.assertIn('geofence_latitude', sites['champs_numeriques'])

        vagues = self._entree('vagues')
        self.assertEqual(
            vagues['selecteurs_routes']['formation']['route'],
            '/formations/ref/formations/')
        self.assertEqual(
            vagues['selecteurs_routes']['statut']['route'],
            '/referentiels/statuts-vague/')
        self.assertIn('effectif_prevu', vagues['champs_numeriques'])
        self.assertIn('periode_debut', vagues['champs_dates'])
