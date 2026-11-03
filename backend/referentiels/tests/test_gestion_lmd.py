"""Gestion générique des référentiels LMD de la scolarité (Système LMD).

Niveaux, semestres, parcours et types de formation sont gérés par le CRUD
générique du module Référentiels alors que leurs modèles n'héritent pas du
socle (pas de provenance, pas d'archivage, ``intitule`` au lieu de
``libelle``, semestre sans colonne code). Le contrat d'API reste unifié :
``code`` / ``libelle`` partout, journalisation, anti-doublon, pas de DELETE.
Les UE/ECUE, elles, restent pilotées par le module Maquettes (cycle de
vie) : leur carte y renvoie via le bouton « Gérer ».
"""
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from formations.models import RefFormation
from referentiels.models import ReferentielJournal
from referentiels.registre import REGISTRE
from scolarite.models import Niveau, Parcours, Semestre, TypeFormation

from .test_refonte import make_user


class GestionNiveauxTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = make_user('admin_lmd', role='ADMIN')
        self.client.force_authenticate(self.admin)

    def test_creation_lecture_modification_d_un_niveau(self):
        res = self.client.post('/api/referentiels/niveaux/', {
            'code': 'D1', 'libelle': 'Doctorat — 1re année',
            'cycle': 'DOCTORAT', 'ordre': 6, 'credits_requis': 60,
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        self.assertEqual(res.data['cycle'], 'DOCTORAT')
        niveau = Niveau.objects.get(code='D1')
        self.assertEqual(niveau.credits_requis, 60)
        self.assertFalse(Niveau.objects.filter(code='d1').exists())

        res = self.client.patch(
            f'/api/referentiels/niveaux/{niveau.id}/',
            {'libelle': 'Doctorat — première année'}, format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
        niveau.refresh_from_db()
        self.assertEqual(niveau.libelle, 'Doctorat — première année')

    def test_code_immuable_et_doublon_de_libelle_refuses(self):
        niveau = Niveau.objects.create(code='L1', libelle='Licence 1', ordre=1)
        res = self.client.patch(
            f'/api/referentiels/niveaux/{niveau.id}/',
            {'code': 'L9', 'libelle': 'Licence 1'}, format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
        niveau.refresh_from_db()
        self.assertEqual(niveau.code, 'L1')

        res = self.client.post('/api/referentiels/niveaux/', {
            'code': 'L2', 'libelle': ' licence 1 ', 'ordre': 2,
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_archivage_non_supporte_et_delete_interdit(self):
        niveau = Niveau.objects.create(code='M1', libelle='Master 1', ordre=4)
        res = self.client.post(f'/api/referentiels/niveaux/{niveau.id}/archiver/')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        res = self.client.delete(f'/api/referentiels/niveaux/{niveau.id}/')
        self.assertEqual(res.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_journalisation_sur_modele_hors_socle(self):
        res = self.client.post('/api/referentiels/niveaux/', {
            'code': 'M2', 'libelle': 'Master 2', 'cycle': 'MASTER', 'ordre': 5,
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        journal = ReferentielJournal.objects.filter(
            action=ReferentielJournal.Action.CREATION,
        )
        self.assertTrue(journal.exists())

    def test_auditeur_en_lecture_seule(self):
        auditeur = make_user('auditeur_lmd', role='AUDITEUR')
        self.client.force_authenticate(auditeur)
        res = self.client.post('/api/referentiels/niveaux/', {
            'code': 'L3', 'libelle': 'Licence 3', 'ordre': 3,
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)


class GestionSemestresTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(make_user('admin_sem', role='ADMIN'))
        self.niveau = Niveau.objects.create(code='L1', libelle='Licence 1', ordre=1)

    def test_creation_sans_code_et_alias_en_lecture(self):
        res = self.client.post('/api/referentiels/semestres/', {
            'libelle': 'S1', 'numero': 1, 'niveau': self.niveau.id,
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        # Le libellé tient lieu de code dans le contrat unifié.
        self.assertEqual(res.data['code'], 'S1')
        self.assertEqual(res.data['niveau_libelle'], 'Licence 1')
        semestre = Semestre.objects.get(libelle='S1')
        self.assertEqual(semestre.numero, 1)

    def test_semestre_sans_niveau_refuse(self):
        res = self.client.post('/api/referentiels/semestres/', {
            'libelle': 'SX', 'numero': 99,
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)


class GestionParcoursEtTypesTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(make_user('admin_parc', role='ADMIN'))
        self.cycle = RefFormation.objects.create(
            code='LIC-EM', intitule='Licence Éducation et Motricité',
        )

    def test_type_de_formation_generique(self):
        res = self.client.post('/api/referentiels/types-formation/', {
            'code': 'LICENCE', 'libelle': 'Licence',
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        self.assertTrue(TypeFormation.objects.filter(code='LICENCE').exists())

    def test_parcours_contrat_code_libelle_sur_intitule(self):
        type_formation = TypeFormation.objects.create(code='LICENCE', libelle='Licence')
        res = self.client.post('/api/referentiels/parcours/', {
            'code': 'EM', 'libelle': 'Éducation et Motricité',
            'ref_formation': self.cycle.id,
            'type_formation': type_formation.id,
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        parcours = Parcours.objects.get(code='EM')
        self.assertEqual(parcours.intitule, 'Éducation et Motricité')
        # Libellé de la FK résolu depuis `intitule` du modèle cible.
        self.assertEqual(res.data['ref_formation_libelle'], self.cycle.intitule)
        self.assertEqual(res.data['type_formation_libelle'], 'Licence')

        res = self.client.patch(
            f'/api/referentiels/parcours/{parcours.id}/',
            {'libelle': 'Éducation et motricité'}, format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
        parcours.refresh_from_db()
        self.assertEqual(parcours.intitule, 'Éducation et motricité')

    def test_doublon_code_meme_cycle_refuse(self):
        Parcours.objects.create(
            code='EM', intitule='Éducation et Motricité', ref_formation=self.cycle,
        )
        res = self.client.post('/api/referentiels/parcours/', {
            'code': 'em', 'libelle': 'Autre intitulé',
            'ref_formation': self.cycle.id,
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)


class TableauDeBordLMDTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(make_user('carto_lmd', role='ADMIN'))

    def _entree(self, slug):
        res = self.client.get('/api/referentiels/tableau-de-bord/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        return next(
            e for c in res.data['categories'] for e in c['entrees']
            if e['slug'] == slug
        )

    def test_metadonnees_d_adaptation_de_l_ecran_generique(self):
        niveaux = self._entree('niveaux')
        self.assertTrue(niveaux['editable'])
        self.assertFalse(niveaux['archivage_supporte'])
        self.assertTrue(niveaux['a_un_code'])
        self.assertFalse(niveaux['provenance_suivie'])
        self.assertEqual(
            niveaux['champs_choix']['cycle'][0]['value'], 'LICENCE',
        )
        self.assertIn('credits_requis', niveaux['champs_numeriques'])

        semestres = self._entree('semestres')
        self.assertFalse(semestres['a_un_code'])
        self.assertEqual(
            semestres['selecteurs_routes']['niveau']['route'],
            '/referentiels/niveaux/',
        )

        parcours = self._entree('parcours')
        self.assertEqual(
            parcours['selecteurs_routes']['ref_formation']['route'],
            '/formations/ref/formations/',
        )
        self.assertEqual(
            parcours['selecteurs_routes']['type_formation']['route'],
            '/referentiels/types-formation/',
        )

    def test_carte_ue_ecue_gerer_vers_les_maquettes(self):
        entree = self._entree('ue-ecue')
        self.assertFalse(entree['editable'])
        self.assertEqual(entree['route_ui'], '/scolarite/maquettes')
        self.assertEqual(entree['libelle_bouton'], 'Gérer')
        # Le CRUD générique ne doit pas écraser le cycle de vie des UE.
        self.assertFalse(REGISTRE['ue-ecue']['editable'])
        res = self.client.post('/api/referentiels/ue-ecue/', {'libelle': 'X'})
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
