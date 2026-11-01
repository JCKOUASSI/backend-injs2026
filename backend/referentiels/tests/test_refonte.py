"""Tests de la refonte « Référentiels » (mission 53).

Trois familles :
* le registre — une seule déclaration par référentiel, aucune route fantôme ;
* l'API générique — CRUD, anti-doublon, archivage réversible, journal ;
* l'import documentaire — volumes réels, idempotence, provenance.
"""
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from authentication.models import User
from referentiels.models import (
    RefEcole,
    RefFiliere,
    RefMention,
    RefModuleOfficiel,
    RefTypeCursus,
    RefVolumeHoraireFormation,
)
from referentiels.registre import REGISTRE, modele_de


def make_user(username, role='ADMIN'):
    return User.objects.create_user(username=username, password='pass', role=role)


class RegistreTests(TestCase):
    """Le registre est la source unique de la cartographie du module."""

    def test_chaque_entree_declare_son_modele(self):
        for slug, entree in REGISTRE.items():
            self.assertEqual(entree['slug'], slug)
            self.assertIsNotNone(entree['modele'], slug)
            self.assertTrue(entree['categorie'], slug)
            self.assertTrue(entree['libelle'], slug)

    def test_aucun_doublon_de_modele(self):
        """Deux entrées sur le même modèle créeraient deux sources de vérité."""
        vus = {}
        for slug, entree in REGISTRE.items():
            modele = modele_de(entree)
            cle = f'{modele._meta.app_label}.{modele._meta.model_name}'
            self.assertNotIn(cle, vus, f'{slug} duplique {vus.get(cle)}')
            vus[cle] = slug

    def test_modules_officiels_declare_en_lecture_seule(self):
        entree = REGISTRE['modules-officiels']
        self.assertFalse(entree['editable'])
        self.assertEqual(modele_de(entree), RefModuleOfficiel)


class TableauDeBordTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(make_user('carto', role='ADMIN'))

    def test_cartographie_complete_et_tracable(self):
        RefEcole.objects.create(code='ENSEPS', libelle='ENSEPS')
        res = self.client.get('/api/referentiels/tableau-de-bord/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        slugs = {
            e['slug']
            for c in res.data['categories']
            for e in c['entrees']
        }
        self.assertEqual(slugs, set(REGISTRE))
        synthese = res.data['synthese']
        self.assertEqual(synthese['nb_referentiels'], len(REGISTRE))
        self.assertEqual(
            synthese['nb_referentiels_editables'],
            sum(1 for e in REGISTRE.values() if e['editable']),
        )

    def test_selecteurs_resolus_par_modele(self):
        """La cible d'un sélecteur est déduite du modèle, jamais du libellé."""
        res = self.client.get('/api/referentiels/tableau-de-bord/')
        filieres = next(
            e for c in res.data['categories'] for e in c['entrees']
            if e['slug'] == 'filieres'
        )
        routes = filieres['selecteurs_routes']
        self.assertEqual(routes['ecole']['route'], '/referentiels/ecoles/')
        self.assertEqual(routes['mention']['route'], '/referentiels/mentions/')
        self.assertEqual(routes['type_cursus']['route'], '/referentiels/types-cursus/')

    def test_les_referentiels_non_editables_ne_sont_pas_ecrasables(self):
        """Un référentiel déclaré en lecture seule ne répond pas au CRUD générique."""
        self.client.force_authenticate(make_user('carto2', role='ADMIN'))
        res = self.client.post('/api/referentiels/volumes-modules/', {'libelle': 'X'})
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)


class CrudGeneriqueTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = make_user('admin_gen', role='ADMIN')
        self.client.force_authenticate(self.admin)
        self.ecole = RefEcole.objects.create(code='ENSEPS', libelle='ENSEPS')

    def test_creation_puis_lecture(self):
        res = self.client.post('/api/referentiels/mentions/', {
            'code': 'STAPS',
            'libelle': 'Sciences et Techniques des APS',
            'ecole': self.ecole.pk,
            'fiabilite': 'OFFICIEL',
        })
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        self.assertEqual(res.data['ecole_libelle'], 'ENSEPS')

    def test_doublon_de_libelle_refuse(self):
        RefMention.objects.create(code='STAPS', libelle='Sciences et Techniques des APS')
        res = self.client.post('/api/referentiels/mentions/', {
            'code': 'STAPS2',
            'libelle': 'SCIENCES ET TECHNIQUES DES APS',
        })
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_code_immuable_en_modification(self):
        mention = RefMention.objects.create(code='STAPS', libelle='STAPS')
        res = self.client.patch(
            f'/api/referentiels/mentions/{mention.pk}/', {'code': 'AUTRE'},
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
        mention.refresh_from_db()
        self.assertEqual(mention.code, 'STAPS')

    def test_archivage_reversible_sans_suppression(self):
        mention = RefMention.objects.create(code='STASE', libelle='STASE')
        url = f'/api/referentiels/mentions/{mention.pk}/'
        self.assertEqual(
            self.client.post(f'{url}archiver/').status_code, status.HTTP_200_OK,
        )
        mention.refresh_from_db()
        self.assertTrue(mention.archive)
        # Masquée par défaut, présente avec ?archives=1
        self.assertEqual(self.client.get('/api/referentiels/mentions/').data['count'], 0)
        self.assertEqual(
            self.client.get('/api/referentiels/mentions/?archives=1').data['count'], 1,
        )
        self.assertEqual(
            self.client.post(f'{url}reactiver/').status_code, status.HTTP_200_OK,
        )
        mention.refresh_from_db()
        self.assertFalse(mention.archive)

    def test_delete_non_expose(self):
        mention = RefMention.objects.create(code='STASE', libelle='STASE')
        res = self.client.delete(f'/api/referentiels/mentions/{mention.pk}/')
        self.assertEqual(res.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertTrue(RefMention.objects.filter(pk=mention.pk).exists())

    def test_auditeur_en_lecture_seule(self):
        self.client.force_authenticate(make_user('aud_gen', role='AUDITEUR'))
        res = self.client.post('/api/referentiels/mentions/', {
            'code': 'X1', 'libelle': 'Test',
        })
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_filiere_expose_son_code_dossier(self):
        cursus = RefTypeCursus.objects.create(code='LMD', libelle='Cursus LMD')
        mention = RefMention.objects.create(code='STAPS', libelle='STAPS', ecole=self.ecole)
        filiere = RefFiliere.objects.create(
            code='EM', libelle='Éducation et Motricité', ecole=self.ecole,
            mention=mention, type_cursus=cursus, code_dossier='F01',
        )
        res = self.client.get(f'/api/referentiels/filieres/{filiere.pk}/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['code_dossier'], 'F01')


class ModulesOfficielsTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(make_user('mod_officiel', role='ADMIN'))

    def test_lecture_seule_et_filtres(self):
        from formations.models import RefFormation

        cycle = RefFormation.objects.create(
            intitule='ÉDUCATION ET MOTRICITÉ — LICENCE',
            type_diplome='LICENCE', filiere_code='F01',
        )
        RefModuleOfficiel.objects.create(
            formation=cycle, filiere_code='EM', semestre='S1',
            libelle='Biomécanique', ordre=1,
            fiabilite='OFFICIEL', source_document='Formations et Modules INJS',
        )
        res = self.client.get('/api/referentiels/modules-officiels/?filiere=EM&semestre=S1')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['count'], 1)
        self.assertEqual(res.data['results'][0]['libelle'], 'Biomécanique')
        autre = self.client.get('/api/referentiels/modules-officiels/?filiere=APA')
        self.assertEqual(autre.data['count'], 0)

    def test_ecriture_refusee(self):
        res = self.client.post('/api/referentiels/modules-officiels/', {'libelle': 'X'})
        self.assertEqual(res.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_volumes_horaires_lecture(self):
        res = self.client.get('/api/referentiels/volumes-horaires/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)


class ImportIdempotentTests(TestCase):
    """L'import documentaire doit être rejouable sans créer de doublon."""

    def _lancer(self):
        sortie = StringIO()
        call_command('importer_referentiels_injs', '--sans-lieux', stdout=sortie)
        return sortie.getvalue()

    def test_volumes_importes(self):
        self._lancer()
        self.assertEqual(RefEcole.objects.count(), 2)
        self.assertEqual(RefMention.objects.count(), 2)
        self.assertEqual(RefFiliere.objects.count(), 8)
        self.assertTrue(RefModuleOfficiel.objects.exists())
        self.assertEqual(
            RefModuleOfficiel.objects.filter(fiabilite='OFFICIEL').count(),
            RefModuleOfficiel.objects.count(),
        )

    def test_deuxieme_execution_ne_cree_rien(self):
        self._lancer()
        comptes = (
            RefEcole.objects.count(), RefMention.objects.count(), RefFiliere.objects.count(),
            RefModuleOfficiel.objects.count(), RefVolumeHoraireFormation.objects.count(),
        )
        self._lancer()
        self.assertEqual(comptes, (
            RefEcole.objects.count(), RefMention.objects.count(), RefFiliere.objects.count(),
            RefModuleOfficiel.objects.count(), RefVolumeHoraireFormation.objects.count(),
        ))

    def test_dry_run_ne_persiste_rien(self):
        call_command('importer_referentiels_injs', '--dry-run', stdout=StringIO())
        self.assertEqual(RefEcole.objects.count(), 0)
        self.assertEqual(RefModuleOfficiel.objects.count(), 0)

    def test_filieres_rattachees_par_code_dossier(self):
        """Le rattachement ne doit jamais dépendre d'une correspondance de libellé."""
        self._lancer()
        self.assertEqual(RefFiliere.objects.get(code='EM').code_dossier, 'F01')
        self.assertEqual(RefFiliere.objects.get(code='APA').code_dossier, 'F02')
        modules_em = RefModuleOfficiel.objects.filter(filiere_code='EM')
        self.assertTrue(modules_em.exists())
        self.assertEqual(
            set(modules_em.values_list('formation__filiere__code_dossier', flat=True)),
            {'F01'},
        )
        # Aucun module n'est rattaché à un cycle qui ne correspond pas au code
        # dossier de sa filière : le rapprochement ne se fait pas sur le libellé.
        for module in RefModuleOfficiel.objects.select_related('formation__filiere'):
            self.assertEqual(
                module.formation.filiere.code, module.filiere_code,
                f'module {module.libelle} mal rattaché',
            )
