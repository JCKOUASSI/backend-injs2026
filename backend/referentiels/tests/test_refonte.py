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
from formations.models import RefFormation
from referentiels.models import (
    ReferentielJournal,
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

    def test_route_api_declaree_existe_vraiment(self):
        """Une route annoncée par le registre doit répondre, pas 404.

        Le registre sert d'index au tableau de bord : une route inventée y
        enverrait l'utilisateur vers une page morte.
        """
        self.client = APIClient()
        self.client.force_authenticate(make_user('routes_ok', role='ADMIN'))
        for slug, entree in REGISTRE.items():
            route = entree.get('route_api')
            if not route:
                continue
            with self.subTest(slug=slug):
                res = self.client.get(f'/api{route}')
                self.assertNotEqual(res.status_code, status.HTTP_404_NOT_FOUND, route)

    def test_route_ui_ne_pointe_que_vers_des_ecrans_existants(self):
        """Écrans réellement déclarés dans le routeur React (App.jsx)."""
        ecrans = {
            '/referentiels', '/referentiels/edition', '/formations',
            '/scolarite/maquettes',
        }
        for slug, entree in REGISTRE.items():
            with self.subTest(slug=slug):
                if entree['editable']:
                    # L'écran générique lit le slug : il doit correspondre.
                    self.assertEqual(
                        entree['route_ui'], f'/referentiels/gestion/{slug}',
                    )
                    continue
                route = entree.get('route_ui')
                if route and route.startswith('/referentiels/gestion/'):
                    self.assertEqual(route, f'/referentiels/gestion/{slug}')
                    continue
                self.assertIn(route, ecrans | {None}, slug)

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

    def test_tracabilite_ecrite_et_relue_sur_toutes_les_routes(self):
        """`fiabilite` et `source_document` doivent faire l'aller-retour.

        Les routes historiques du routeur (types d'évaluation, modes de
        paiement…) et les routes générées du registre partagent le même écran :
        elles doivent donc exposer le même contrat. Sinon le formulaire laissait
        saisir la provenance et l'API la jetait sans le dire.
        """
        for rang, chemin in enumerate((
            '/api/referentiels/types-evaluation/',
            '/api/referentiels/mentions/',
        )):
            with self.subTest(chemin=chemin):
                res = self.client.post(chemin, {
                    'code': f'TRACE_{rang}',
                    'libelle': 'Valeur tracée',
                    'fiabilite': 'OFFICIEL',
                    'source_document': 'Arrêté 2026-001',
                })
                self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
                self.assertEqual(res.data['fiabilite'], 'OFFICIEL')
                self.assertEqual(res.data['source_document'], 'Arrêté 2026-001')
                relu = self.client.get(f"{chemin}{res.data['id']}/").data
                self.assertEqual(relu['fiabilite'], 'OFFICIEL')
                self.assertEqual(relu['source_document'], 'Arrêté 2026-001')

    def test_reactivation_remet_la_valeur_en_service(self):
        """Archiver désactive ; réactiver doit donc réactiver (règle 3).

        Sans cela la valeur revenait dans la liste des valeurs archivées puis
        disparaissait de « Actifs » et de ``usables()`` : l'écran affichait un
        succès sans effet observable.
        """
        mention = RefMention.objects.create(code='STASE', libelle='STASE')
        url = f'/api/referentiels/mentions/{mention.pk}/'
        self.client.post(f'{url}archiver/')
        mention.refresh_from_db()
        self.assertFalse(mention.actif)
        self.assertIsNotNone(mention.date_desactivation)

        res = self.client.post(f'{url}reactiver/', {'motif': 'retour en service'})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data['actif'])
        mention.refresh_from_db()
        self.assertFalse(mention.archive)
        self.assertTrue(mention.actif)
        self.assertIsNone(mention.date_desactivation)
        self.assertIn(mention, RefMention.usables())

        journal = ReferentielJournal.objects.filter(
            object_id=mention.pk,
            action=ReferentielJournal.Action.REACTIVATION,
        )
        self.assertEqual(journal.count(), 1)
        self.assertEqual(journal.first().detail, {'motif': 'retour en service'})

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


class CoherenceTests(TestCase):
    """La commande de contrôle mesure sans jamais corriger."""

    def _executer(self, *args):
        sortie = StringIO()
        call_command('verifier_coherence_referentiels', *args, stdout=sortie)
        return sortie.getvalue()

    #: Les 8 filières du référentiel tel que le code de scolarité les connaît.
    CODES = ('EM', 'APA', 'ES', 'MS', 'AND', 'LOI', 'ECJP', 'GER')

    def _filiere(self):
        ecole = RefEcole.objects.create(
            code='ENSEPS', libelle='ENSEPS',
            source_document='Formations et Modules INJS — §1', fiabilite='OFFICIEL',
        )
        for rang, code in enumerate(self.CODES):
            RefFiliere.objects.create(
                code=code, libelle=f'Filière {code}', ecole=ecole,
                source_document='Formations et Modules INJS — §1', fiabilite='OFFICIEL',
            )
        return RefFiliere.objects.get(code='EM')

    def test_rapport_nominal_sans_constat(self):
        RefFormation.objects.create(intitule='Licence STAPS', filiere=self._filiere())
        sortie = self._executer()
        self.assertIn('Provenance des valeurs', sortie)
        self.assertIn('Duplication de référentiel', sortie)
        self.assertIn('Aucun constat', sortie)

    def test_strict_signale_une_formation_sans_filiere(self):
        RefFormation.objects.create(intitule='Licence orpheline')
        sortie = StringIO()
        with self.assertRaises(SystemExit):
            call_command(
                'verifier_coherence_referentiels', '--strict', stdout=sortie,
            )
        self.assertIn('sans filière', sortie.getvalue())

    def test_divergence_de_liste_codee_en_dur_est_signalee(self):
        ecole = RefEcole.objects.create(
            code='ENSEPS', libelle='ENSEPS', fiabilite='OFFICIEL',
        )
        RefFiliere.objects.create(code='EM', libelle='Éducation et Motricité', ecole=ecole)
        sortie = self._executer()
        self.assertIn('codée en dur divergente', sortie)

    def test_valeur_sans_source_est_signalee(self):
        RefEcole.objects.create(
            code='ENSEPS', libelle='ENSEPS', source_document='', fiabilite='A_RENSEIGNER',
        )
        sortie = self._executer()
        self.assertIn('sans source', sortie)
