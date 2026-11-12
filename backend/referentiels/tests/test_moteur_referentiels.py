"""Tests du moteur commun Référentiels (mission « Référentiels »).

Ces tests couvrent les exigences transverses : les quatre formats d'export,
l'import en cinq étapes, et la distinction activer / archiver / supprimer.
Ils s'exécutent réellement (aucun mock du moteur de fichiers).
"""

import io

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from referentiels.moteur import colonnes as moteur_colonnes
from referentiels.moteur import exportations as moteur_exports
from referentiels.moteur import importations as moteur_imports
from referentiels.models import RefEcole, RefFiliere, RefTypeEvaluation

Utilisateur = get_user_model()


class BaseReferentiels(TestCase):
    """Utilisateur habilité à la gestion des référentiels."""

    def setUp(self):
        self.client = APIClient()
        self.utilisateur = Utilisateur.objects.create_user(
            username='gest.ref', password='passe12345', role='ADMIN',
        )
        self.client.force_authenticate(self.utilisateur)


class TestExportReferentiel(BaseReferentiels):
    """Les quatre formats d'export doivent être réellement générés."""

    def setUp(self):
        super().setUp()
        RefTypeEvaluation.objects.create(code='EXAM', libelle='Examen')
        RefTypeEvaluation.objects.create(code='CC', libelle='Contrôle continu')

    def _colonnes(self):
        return moteur_colonnes.champs_exportables(RefTypeEvaluation)

    def test_quatre_formats_generes(self):
        """CSV, Excel, Word et PDF sont produits avec le bon type MIME."""
        lignes = list(RefTypeEvaluation.objects.all())
        for format_cible, type_mime in moteur_exports.TYPES_MIME.items():
            with self.subTest(format=format_cible):
                contenu, mime, nom = moteur_exports.generer_export(
                    slug='types-evaluation', referentiel="Types d’évaluation", colonnes=self._colonnes(),
                    lignes=lignes, format_cible=format_cible,
                )
                self.assertTrue(contenu, f'{format_cible} : contenu vide')
                self.assertEqual(mime, type_mime)
                self.assertTrue(nom.endswith(f'.{format_cible}'))
                self.assertIn('types-evaluation_', nom)

    def test_csv_utf8_et_separateur_francophone(self):
        """Le CSV est UTF-8 (BOM) avec le séparateur « ; » et les accents."""
        contenu, _, _ = moteur_exports.generer_export(
            slug='types-evaluation', referentiel="Types d’évaluation", colonnes=self._colonnes(),
            lignes=list(RefTypeEvaluation.objects.all()), format_cible='csv',
        )
        texte = contenu.decode('utf-8-sig')
        self.assertIn('INSTITUT NATIONAL DE LA JEUNESSE', texte)
        self.assertIn('Libellé', texte)  # accents préservés
        self.assertIn(';', texte)  # séparateur francophone
        self.assertIn('Total : 2', texte)

    def test_pdf_multipage_avec_entetes(self):
        """Le PDF est un document valide et multi-pages si nécessaire."""
        contenu, mime, _ = moteur_exports.generer_export(
            slug='types-evaluation', referentiel="Types d’évaluation", colonnes=self._colonnes(),
            lignes=list(RefTypeEvaluation.objects.all()), format_cible='pdf',
        )
        self.assertTrue(contenu.startswith(b'%PDF'))
        self.assertEqual(mime, 'application/pdf')

    def test_export_via_api(self):
        """La route d'export répond et respecte le format demandé."""
        for format_cible in ('csv', 'xlsx', 'docx', 'pdf'):
            with self.subTest(format=format_cible):
                reponse = self.client.get(f'/api/referentiels/types-evaluation/exporter/?export={format_cible}')
                self.assertEqual(reponse.status_code, 200, reponse.content[:400])
                self.assertIn('attachment; filename=', reponse['Content-Disposition'])
                self.assertEqual(reponse['X-Total-Export'], '2')

    def test_format_inconnu_refuse(self):
        reponse = self.client.get('/api/referentiels/types-evaluation/exporter/?export=rtf')
        self.assertEqual(reponse.status_code, 400)

    def test_export_respecte_les_filtres(self):
        """Le périmètre exporté est celui affiché : une recherche restreint l'export."""
        reponse = self.client.get('/api/referentiels/types-evaluation/exporter/?search=CC&export=csv')
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse['X-Total-Export'], '1')

    def test_export_refuse_sans_authentification(self):
        client = APIClient()
        reponse = client.get('/api/referentiels/types-evaluation/exporter/?export=csv')
        self.assertIn(reponse.status_code, (401, 403))


class FichierCSV:
    """Faux fichier téléversé (respecte l'interface de Django)."""

    def __init__(self, contenu, nom='fichier.csv'):
        self.contenu = contenu.encode('utf-8') if isinstance(contenu, str) else contenu
        self.name = nom
        self.size = len(self.contenu)

    def read(self):
        return self.contenu

    def seek(self, position, whence=0):
        return 0

    def tell(self):
        return 0


class TestImportReferentiel(BaseReferentiels):
    """L'import en 5 étapes : contrôle, prévisualisation, validation, import."""

    CSV_VALIDE = (
        'Code;Libellé;Description\n'
        'EXAM;Examen;Filière informatique\n'
        'STAPS;STAPS;Sciences et techniques\n'
    )
    CSV_ERREURS = (
        'Code;Libellé;Description\n'
        'EXAM;Examen;OK\n'
        ';Sans code;Code obligatoire manquant\n'
    )

    def test_controle_fichier_extension(self):
        with self.assertRaises(moteur_imports.ErreurImport):
            moteur_imports.controler_fichier(FichierCSV('x', 'malware.exe'))

    def test_controle_fichier_vide(self):
        with self.assertRaises(moteur_imports.ErreurImport):
            moteur_imports.controler_fichier(FichierCSV('', 'vide.csv'))

    def test_previsualisation_sans_ecriture(self):
        """L'étape 2 n'écrit rien en base."""
        champs = moteur_colonnes.champs_importables(RefTypeEvaluation)
        apercu = moteur_imports.previsualiser(
            fichier=FichierCSV(self.CSV_VALIDE), extension='csv', champs_importables=champs,
        )
        self.assertEqual(apercu['total_lignes'], 2)
        self.assertEqual(RefTypeEvaluation.objects.count(), 0)  # aucune écriture
        reconnues = {c['cle'] for c in apercu['colonnes_reconnues']}
        self.assertIn('code', reconnues)
        self.assertIn('libelle', reconnues)

    def test_doublons_detectes(self):
        champs = moteur_colonnes.champs_importables(RefTypeEvaluation)
        apercu = moteur_imports.previsualiser(
            fichier=FichierCSV(
                'Code;Libellé\nA;Alpha\nA;Alpha bis\n'),
            extension='csv', champs_importables=champs,
        )
        self.assertTrue(apercu['doublons'])
        self.assertEqual(apercu['doublons'][0]['valeur'], 'A')

    def test_validation_rapporte_les_erreurs_par_ligne(self):
        champs = moteur_colonnes.champs_importables(RefTypeEvaluation)
        apercu = moteur_imports.previsualiser(
            fichier=FichierCSV(self.CSV_ERREURS), extension='csv', champs_importables=champs,
        )
        apercu['_colonnes_importables'] = champs
        rapport = moteur_imports.valider(
            previsualisation=apercu, modele=RefTypeEvaluation,
            champ_libelle='libelle', queryset=RefTypeEvaluation.objects.all(),
        )
        self.assertEqual(rapport['lignes_valides'], 1)
        numeros = {e['ligne'] for e in rapport['erreurs']}
        self.assertIn(3, numeros)  # ligne 3 : code manquant
        self.assertEqual(RefTypeEvaluation.objects.count(), 0)

    def test_import_transactionnel_ajoute(self):
        """L'import crée les lignes valides et journalise."""
        champs = moteur_colonnes.champs_importables(RefTypeEvaluation)
        apercu = moteur_imports.previsualiser(
            fichier=FichierCSV(self.CSV_ERREURS), extension='csv', champs_importables=champs,
        )
        apercu['_colonnes_importables'] = champs
        validation = moteur_imports.valider(
            previsualisation=apercu, modele=RefTypeEvaluation,
            champ_libelle='libelle', queryset=RefTypeEvaluation.objects.all(),
        )
        rapport = moteur_imports.importer(
            validation=validation, modele=RefTypeEvaluation, champ_libelle='libelle',
            mode='ajouter', queryset=RefTypeEvaluation.objects.all(), slug='types-evaluation',
        )
        self.assertEqual(rapport['crees'], 1)
        self.assertTrue(RefTypeEvaluation.objects.filter(code='EXAM').exists())
        self.assertIn('duree_secondes', rapport)

    def test_import_met_a_jour(self):
        RefTypeEvaluation.objects.create(code='EXAM', libelle='Ancien libellé')
        champs = moteur_colonnes.champs_importables(RefTypeEvaluation)
        apercu = moteur_imports.previsualiser(
            fichier=FichierCSV('Code;Libellé\nEXAM;Examen\n'),
            extension='csv', champs_importables=champs,
        )
        apercu['_colonnes_importables'] = champs
        validation = moteur_imports.valider(
            previsualisation=apercu, modele=RefTypeEvaluation,
            champ_libelle='libelle', queryset=RefTypeEvaluation.objects.all(),
        )
        rapport = moteur_imports.importer(
            validation=validation, modele=RefTypeEvaluation, champ_libelle='libelle',
            mode='mettre_a_jour', queryset=RefTypeEvaluation.objects.all(), slug='types-evaluation',
        )
        self.assertEqual(rapport['mis_a_jour'], 1)
        self.assertEqual(RefTypeEvaluation.objects.get(code='EXAM').libelle, 'Examen')

    def test_api_analyse(self):
        """L'étape d'analyse est exposée et n'écrit rien."""
        reponse = self.client.post(
            '/api/referentiels/types-evaluation/importer/analyse/',
            {'fichier': FichierCSV(self.CSV_VALIDE)}, format='multipart',
        )
        self.assertEqual(reponse.status_code, 200, reponse.content[:500])
        self.assertEqual(reponse.data['etape'], 'validation')
        self.assertEqual(RefTypeEvaluation.objects.count(), 0)
        self.assertIn('previsualisation', reponse.data)
        self.assertIn('modes_disponibles', reponse.data)

    def test_api_import_complet(self):
        reponse = self.client.post(
            '/api/referentiels/types-evaluation/importer/',
            {'fichier': FichierCSV(self.CSV_VALIDE), 'mode': 'ajouter'},
            format='multipart',
        )
        self.assertEqual(reponse.status_code, 200, reponse.content[:500])
        self.assertEqual(reponse.data['crees'], 2)
        self.assertEqual(RefTypeEvaluation.objects.count(), 2)

    def test_api_import_refuse_sans_fichier(self):
        reponse = self.client.post(
            '/api/referentiels/types-evaluation/importer/', {'mode': 'ajouter'}, format='multipart',
        )
        self.assertEqual(reponse.status_code, 400)

    def test_api_import_mode_inconnu(self):
        reponse = self.client.post(
            '/api/referentiels/types-evaluation/importer/',
            {'fichier': FichierCSV(self.CSV_VALIDE), 'mode': 'detruire'}, format='multipart',
        )
        self.assertEqual(reponse.status_code, 400)


class TestCycleDeVie(BaseReferentiels):
    """Activer ≠ désactiver ≠ archiver ≠ supprimer : quatre actions distinctes."""

    def setUp(self):
        super().setUp()
        self.filiere = RefTypeEvaluation.objects.create(code='EXAM', libelle='Examen')

    def test_activer_et_desactiver_sont_distincts_de_archiver(self):
        url = f'/api/referentiels/types-evaluation/{self.filiere.pk}'
        # Désactivation : la valeur reste présente et non archivée
        reponse = self.client.post(f'{url}/desactiver/')
        self.assertEqual(reponse.status_code, 200)
        self.filiere.refresh_from_db()
        self.assertFalse(self.filiere.actif)
        self.assertFalse(self.filiere.archive)
        # Réactivation
        self.assertEqual(self.client.post(f'{url}/activer/').status_code, 200)
        self.filiere.refresh_from_db()
        self.assertTrue(self.filiere.actif)
        self.assertFalse(self.filiere.archive)

    def test_archivage_reversible(self):
        url = f'/api/referentiels/types-evaluation/{self.filiere.pk}'
        self.assertEqual(self.client.post(f'{url}/archiver/').status_code, 200)
        self.filiere.refresh_from_db()
        self.assertTrue(self.filiere.archive)
        self.assertEqual(self.client.post(f'{url}/reactiver/').status_code, 200)
        self.filiere.refresh_from_db()
        self.assertFalse(self.filiere.archive)

    def test_activer_une_valeur_archiver_est_refuse(self):
        self.filiere.archiver(self.utilisateur)
        reponse = self.client.post(f'/api/referentiels/types-evaluation/{self.filiere.pk}/activer/')
        self.assertEqual(reponse.status_code, 400)

    def test_suppression_exige_confirmation(self):
        url = f'/api/referentiels/types-evaluation/{self.filiere.pk}/supprimer/'
        reponse = self.client.post(url, {})
        self.assertEqual(reponse.status_code, 400)  # pas de confirmation
        self.filiere.refresh_from_db()
        self.assertFalse(self.filiere.archive)

    def test_suppression_securisee_archive_sans_detruire(self):
        url = f'/api/referentiels/types-evaluation/{self.filiere.pk}/supprimer/'
        reponse = self.client.post(url, {'confirmation': 'confirmer', 'motif': 'doublon'})
        self.assertEqual(reponse.status_code, 200, reponse.content[:300])
        self.filiere.refresh_from_db()
        self.assertTrue(self.filiere.archive)
        self.assertTrue(RefTypeEvaluation.objects.filter(pk=self.filiere.pk).exists())


class TestSecuriteReferentiels(TestCase):
    """Chaque opération est protégée individuellement côté backend."""

    def setUp(self):
        self.client = APIClient()
        self.utilisateur = Utilisateur.objects.create_user(
            username='simple.utilisateur', password='passe12345', role='AUDITEUR',
        )
        self.client.force_authenticate(self.utilisateur)
        self.filiere = RefTypeEvaluation.objects.create(code='EXAM', libelle='Examen')

    def test_lecture_autorisee_a_tout_authentifie(self):
        self.assertEqual(self.client.get('/api/referentiels/types-evaluation/').status_code, 200)

    def test_ecriture_refusee_sans_role(self):
        """Un utilisateur sans rôle de gestion ne peut ni créer ni exporter ni importer."""
        self.assertEqual(
            self.client.post('/api/referentiels/types-evaluation/', {'code': 'X', 'libelle': 'Y'}).status_code,
            403,
        )
        self.assertIn(
            self.client.get('/api/referentiels/types-evaluation/exporter/?export=csv').status_code,
            (401, 403),
        )
        self.assertIn(
            self.client.post('/api/referentiels/types-evaluation/importer/', {'mode': 'ajouter'},
                             format='multipart').status_code,
            (401, 403),
        )

    def test_anonyme_refuse(self):
        client = APIClient()
        self.assertIn(client.get('/api/referentiels/types-evaluation/').status_code, (401, 403))
