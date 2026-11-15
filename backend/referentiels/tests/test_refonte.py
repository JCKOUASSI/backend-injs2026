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

    def test_modules_officiels_declare_en_gestion_complete(self):
        entree = REGISTRE['modules-officiels']
        self.assertTrue(entree['editable'])
        self.assertEqual(modele_de(entree), RefModuleOfficiel)
        self.assertEqual(entree['route_ui'], '/referentiels/gestion/modules-officiels')
        for slug in ('formations', 'modules-officiels', 'volumes-modules'):
            self.assertTrue(REGISTRE[slug]['editable'], slug)
            self.assertEqual(
                REGISTRE[slug]['route_ui'], f'/referentiels/gestion/{slug}',
            )


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
        res = self.client.post('/api/referentiels/ue-ecue/', {'libelle': 'X'})
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

    def test_filtres_filiere_semestre_et_formation(self):
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
        par_formation = self.client.get(f'/api/referentiels/modules-officiels/?formation={cycle.pk}')
        self.assertEqual(par_formation.data['count'], 1)

    def test_creation_modification_archivage_via_le_socle_generique(self):
        from formations.models import RefFormation

        cycle = RefFormation.objects.create(
            intitule='ÉDUCATION ET MOTRICITÉ — LICENCE',
            type_diplome='LICENCE', filiere_code='F01',
        )
        res = self.client.post('/api/referentiels/modules-officiels/', {
            'libelle': 'Biomécanique',
            'formation': cycle.pk,
            'filiere_code': 'EM',
            'semestre': 'S1',
            'ordre': 1,
            'etat_ventilation': 'A_VENTILER',
            'fiabilite': 'OFFICIEL',
        })
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        module_id = res.data['id']
        # Sans formation, le rattachement est impossible : la création échoue.
        res_sans = self.client.post('/api/referentiels/modules-officiels/', {'libelle': 'X'})
        self.assertEqual(res_sans.status_code, status.HTTP_400_BAD_REQUEST)
        # Modification
        res_patch = self.client.patch(
            f'/api/referentiels/modules-officiels/{module_id}/', {'ordre': 3},
        )
        self.assertEqual(res_patch.status_code, status.HTTP_200_OK, res_patch.data)
        self.assertEqual(res_patch.data['ordre'], 3)
        # Archivage réversible (règle 2) puis réactivation
        res_arch = self.client.post(f'/api/referentiels/modules-officiels/{module_id}/archiver/')
        self.assertEqual(res_arch.status_code, status.HTTP_200_OK)
        module = RefModuleOfficiel.objects.get(pk=module_id)
        self.assertTrue(module.archive)
        self.assertFalse(module.actif)
        res_react = self.client.post(f'/api/referentiels/modules-officiels/{module_id}/reactiver/')
        self.assertEqual(res_react.status_code, status.HTTP_200_OK)
        module.refresh_from_db()
        self.assertFalse(module.archive)
        self.assertTrue(module.actif)
        # Journal append-only : création + modification + archivage + réactivation
        actions = ReferentielJournal.objects.filter(object_id=module_id).values_list('action', flat=True)
        self.assertIn('CREATION', actions)
        self.assertIn('MODIFICATION', actions)
        self.assertIn('ARCHIVAGE', actions)
        self.assertIn('REACTIVATION', actions)

    def test_volumes_horaires_lecture(self):
        res = self.client.get('/api/referentiels/volumes-modules/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        # Alias historique conservé pour compatibilité
        alias = self.client.get('/api/referentiels/volumes-horaires/')
        self.assertEqual(alias.status_code, status.HTTP_200_OK)


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


class EchangesReferentielsTests(TestCase):
    """Export (docx/xlsx/csv/pdf) et import (xlsx/csv) des référentiels."""

    def setUp(self):
        self.client = APIClient()
        self.admin = make_user('admin_echanges', role='ADMIN')
        self.client.force_authenticate(self.admin)
        self.cycle = RefFormation.objects.create(
            intitule='ÉDUCATION ET MOTRICITÉ — LICENCE',
            code='EM-LIC', type_diplome='LICENCE', filiere_code='F01',
        )
        self.module = RefModuleOfficiel.objects.create(
            formation=self.cycle, filiere_code='EM', semestre='S1',
            libelle='Biomécanique', ordre=1,
            fiabilite='OFFICIEL', source_document='Formations et Modules INJS',
        )
        from referentiels.models import RefVolumeHoraireFormation as _VH
        self.volume = _VH.objects.create(
            formation=self.cycle, intitule_module='Biomécanique',
            heures_cm=30, heures_td=15, heures_total=45,
            fiabilite='MODELISE', source_document='Modéliser les volumes horaires',
        )

    # ── Export ────────────────────────────────────────────────────────────
    def test_export_quatre_formats(self):
        signatures = {
            'xlsx': ('PK\x03\x04', 'spreadsheetml'),
            'csv': ('\ufeff', 'text/csv'),
            'docx': ('PK\x03\x04', 'wordprocessingml'),
            'pdf': ('%PDF', 'application/pdf'),
        }
        for slug in ('formations', 'modules-officiels', 'volumes-modules'):
            for fmt, (signature, ctype) in signatures.items():
                with self.subTest(slug=slug, format=fmt):
                    res = self.client.get(f'/api/referentiels/{slug}/export/?fmt={fmt}')
                    self.assertEqual(res.status_code, status.HTTP_200_OK, res.content)
                    self.assertIn('attachment', res['Content-Disposition'])
                    self.assertIn(ctype, res['Content-Type'])
                    debut = res.content[:len(signature)]
                    if signature.startswith('P') or signature.startswith('%'):
                        self.assertTrue(res.content.startswith(signature.encode()), fmt)
                    else:
                        self.assertTrue(res.content.decode('utf-8-sig').startswith(signature.replace('﻿', '')), fmt)

    def test_export_csv_contenu_et_filtres(self):
        res = self.client.get('/api/referentiels/modules-officiels/export/?fmt=csv')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        texte = res.content.decode('utf-8-sig')
        lignes = [l for l in texte.strip().splitlines() if l.strip()]
        self.assertEqual(lignes[0].split(';')[0], 'Libellé')
        self.assertIn('Biomécanique', texte)
        self.assertIn('Formation (cycle)', texte)
        # Archivé par défaut : masqué ; archives=1 : présent
        self.module.archive = True
        self.module.actif = False
        self.module.save(update_fields=['archive', 'actif'])
        cache = self.client.get('/api/referentiels/modules-officiels/export/?fmt=csv')
        self.assertNotIn('Biomécanique', cache.content.decode('utf-8-sig'))
        avec = self.client.get('/api/referentiels/modules-officiels/export/?fmt=csv&archives=1')
        self.assertIn('Biomécanique', avec.content.decode('utf-8-sig'))

    def test_export_format_inconnu(self):
        res = self.client.get('/api/referentiels/modules-officiels/export/?fmt=ods')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_export_inconnu(self):
        res = self.client.get('/api/referentiels/inconnu-ici/export/?fmt=csv')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    # ── Import ────────────────────────────────────────────────────────────
    def _csv_bytes(self, texte):
        from django.core.files.uploadedfile import SimpleUploadedFile
        return SimpleUploadedFile('import.csv', texte.encode('utf-8-sig'))

    def test_import_csv_aller_retour(self):
        export = self.client.get('/api/referentiels/volumes-modules/export/?fmt=csv')
        fichier = self._csv_bytes(export.content.decode('utf-8-sig'))
        res = self.client.post('/api/referentiels/volumes-modules/import/', {'fichier': fichier})
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.content)
        self.assertEqual(res.data['created'], 0)
        self.assertEqual(res.data['updated'], 1)
        self.assertEqual(RefVolumeHoraireFormation.objects.count(), 1)

    def test_import_csv_creation_et_mise_a_jour(self):
        contenu = (
            'Libellé;Heures CM;Heures TD;Heures TP;Heures stage;Total;Formation (cycle)\r\n'
            'Physiologie;20;10;;;30;ÉDUCATION ET MOTRICITÉ — LICENCE\r\n'
        )
        res = self.client.post(
            '/api/referentiels/volumes-modules/import/', {'fichier': self._csv_bytes(contenu)},
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.content)
        self.assertEqual(res.data['created'], 1)
        from referentiels.models import RefVolumeHoraireFormation as _VH
        self.assertEqual(_VH.objects.get(intitule_module='Physiologie').heures_total, 30)
        # Rejouer le même import met à jour, ne duplique pas.
        res2 = self.client.post(
            '/api/referentiels/volumes-modules/import/', {'fichier': self._csv_bytes(contenu)},
        )
        self.assertEqual(res2.status_code, status.HTTP_200_OK, res2.content)
        self.assertEqual(res2.data['updated'], 1)
        self.assertEqual(_VH.objects.filter(intitule_module='Physiologie').count(), 1)

    def test_import_xlsx_creation_module_officiel(self):
        from io import BytesIO

        from openpyxl import Workbook

        from django.core.files.uploadedfile import SimpleUploadedFile

        classer = Workbook()
        feuille = classer.active
        feuille.append(['Libellé', 'Filière', 'Semestre', 'Ordre', 'État de ventilation', 'Formation (cycle)'])
        feuille.append(['Physiologie', 'EM', 'S2', 2, 'À ventiler en maquette', 'ÉDUCATION ET MOTRICITÉ — LICENCE'])
        tampon = BytesIO()
        classer.save(tampon)
        fichier = SimpleUploadedFile('modules.xlsx', tampon.getvalue())
        res = self.client.post('/api/referentiels/modules-officiels/import/', {'fichier': fichier})
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.content)
        self.assertEqual(res.data['created'], 1)
        module = RefModuleOfficiel.objects.get(libelle='Physiologie', semestre='S2')
        self.assertEqual(module.etat_ventilation, 'A_VENTILER')
        self.assertEqual(module.ordre, 2)
        self.assertEqual(module.formation, self.cycle)

    def test_import_ligne_invalide_rejette_tout(self):
        contenu = (
            'Libellé;Heures CM;Formation (cycle)\r\n'
            'Physiologie;20;ÉDUCATION ET MOTRICITÉ — LICENCE\r\n'
            'Erreur;abc;ÉDUCATION ET MOTRICITÉ — LICENCE\r\n'
        )
        from referentiels.models import RefVolumeHoraireFormation as _VH
        avant = _VH.objects.count()
        res = self.client.post(
            '/api/referentiels/volumes-modules/import/', {'fichier': self._csv_bytes(contenu)},
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('erreurs', res.data)
        self.assertEqual(_VH.objects.count(), avant)

    def test_import_formation_introuvable(self):
        contenu = (
            'Libellé;Heures CM;Formation (cycle)\r\n'
            'Physiologie;20;CYCLE QUI N’EXISTE PAS\r\n'
        )
        res = self.client.post(
            '/api/referentiels/volumes-modules/import/', {'fichier': self._csv_bytes(contenu)},
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(any('introuvable' in e for e in res.data.get('erreurs', [])))

    def test_import_format_refuse_et_referencement_non_editable(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        res = self.client.post(
            '/api/referentiels/volumes-modules/import/',
            {'fichier': SimpleUploadedFile('import.pdf', b'%PDF')},
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        # Un référentiel historisé se corrige via la source documentaire,
        # jamais par import : 403 (comme le socle CRUD, en lecture seule).
        csv_ue = SimpleUploadedFile('ue.csv', 'Libellé\r\nX\r\n'.encode('utf-8'))
        res_ue = self.client.post('/api/referentiels/ue-ecue/import/', {'fichier': csv_ue})
        self.assertEqual(res_ue.status_code, status.HTTP_403_FORBIDDEN)

    def test_import_reserve_aux_roles_de_gestion(self):
        self.client.force_authenticate(make_user('aud_imp', role='AUDITEUR'))
        res = self.client.post(
            '/api/referentiels/volumes-modules/import/',
            {'fichier': self._csv_bytes('Libellé\r\nX\r\n')},
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_import_journalise(self):
        contenu = (
            'Libellé;Heures CM;Formation (cycle)\r\n'
            'Physiologie;25;ÉDUCATION ET MOTRICITÉ — LICENCE\r\n'
        )
        res = self.client.post(
            '/api/referentiels/volumes-modules/import/', {'fichier': self._csv_bytes(contenu)},
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.content)
        from referentiels.models import RefVolumeHoraireFormation as _VH
        objet = _VH.objects.get(intitule_module='Physiologie')
        journal = ReferentielJournal.objects.filter(
            object_id=objet.pk, action=ReferentielJournal.Action.CREATION,
        )
        self.assertEqual(journal.count(), 1)
        self.assertEqual(journal.first().detail.get('import'), 'import.csv')
