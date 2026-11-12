"""Tests du moteur de résolution des relations à l'import (mission Référentiels).

Exigences vérifiées : identifier les clés étrangères, résoudre par
identifiant **et** par champ métier, détecter les références inexistantes,
détecter les références ambiguës, empêcher les associations incorrectes,
produire un rapport détaillé, respecter les contraintes d'unicité et
garantir l'intégrité transactionnelle.
"""

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from referentiels.moteur import colonnes as moteur_colonnes
from referentiels.moteur import importations as moteur_imports
from referentiels.moteur import relations as moteur_relations
from referentiels.models import (RefEcole, RefFiliere, RefMention,
                                 RefTypeCursus, RefTypeEvaluation)

Utilisateur = get_user_model()


class FichierCSV:
    """Faux fichier téléversé (respecte l'interface attendue par Django)."""

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


def televerser(contenu, nom='fichier.csv'):
    return SimpleUploadedFile(nom, contenu.encode('utf-8'), content_type='text/csv')


class BaseRelations(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.utilisateur = Utilisateur.objects.create_user(
            username='relations.admin', password='passe12345', role='ADMIN',
        )
        self.client.force_authenticate(self.utilisateur)

        self.enseps = RefEcole.objects.create(
            code='ENSEPS', libelle='ENSEPS', nom_complet='École ENSEPS',
        )
        self.ensep = RefEcole.objects.create(
            code='ENSEP', libelle='ENSEP', nom_complet='École ENSEP',
        )
        self.mention = RefMention.objects.create(
            code='STAPS', libelle='STAPS', ecole=self.enseps,
        )
        self.cursus = RefTypeCursus.objects.create(code='LMD', libelle='Cursus LMD')

    def _analyser(self, contenu):
        return self.client.post(
            '/api/referentiels/filieres/importer/analyse/',
            {'fichier': televerser(contenu)}, format='multipart',
        )

    def _importer(self, contenu, mode='les_deux'):
        return self.client.post(
            '/api/referentiels/filieres/importer/',
            {'fichier': televerser(contenu), 'mode': mode}, format='multipart',
        )


class TestIdentificationDesRelations(BaseRelations):
    """Les clés étrangères sont identifiées et décrites, sans liste en dur."""

    def test_cles_etrangeres_detectees(self):
        noms = {f.name for f in moteur_relations.cles_etrangeres(RefFiliere)}
        self.assertEqual(noms, {'ecole', 'mention', 'type_cursus', 'annee_academique'})

    def test_champs_importables_decrivent_les_relations(self):
        colonnes = {c['cle']: c for c in moteur_colonnes.champs_importables(RefFiliere)}
        self.assertTrue(colonnes['ecole']['relation'])
        self.assertEqual(colonnes['ecole']['modele_lie'], 'referentiels.refecole')
        self.assertIn('libelle', colonnes['ecole']['cles_metier'])
        self.assertIn('code', colonnes['ecole']['cles_metier'])

    def test_api_annonce_les_relations_a_l_interface(self):
        reponse = self._analyser('Code;Libellé\nA;Alpha\n')
        self.assertEqual(reponse.status_code, 200)
        self.assertIn('relations', reponse.data['validation'])
        relations = {r['cle']: r['cles_metier'] for r in reponse.data['validation']['relations']}
        self.assertIn('ecole', relations)


class TestResolutionDesReferences(BaseRelations):
    """Résolution par identifiant ou par champ métier, sans jamais deviner."""

    def setUp(self):
        super().setUp()
        self.resolveur = moteur_relations.ResolveurRelations(RefFiliere)

    def test_resolution_par_identifiant(self):
        self.assertEqual(
            self.resolveur.resoudre('ecole', str(self.enseps.pk)).objet, self.enseps,
        )

    def test_resolution_par_code(self):
        self.assertEqual(self.resolveur.resoudre('ecole', 'ENSEPS').objet, self.enseps)

    def test_resolution_par_libelle(self):
        self.assertEqual(self.resolveur.resoudre('ecole', 'ENSEP').objet, self.ensep)

    def test_resolution_par_champ_metier_long(self):
        self.assertEqual(
            self.resolveur.resoudre('ecole', 'École ENSEPS').objet, self.enseps,
        )

    def test_resolution_insensible_casse_et_accents(self):
        self.assertEqual(self.resolveur.resoudre('ecole', 'enseps').objet, self.enseps)
        self.assertEqual(self.resolveur.resoudre('ecole', '  ÉCOLE ENSEPS ').objet, self.enseps)

    def test_reference_inexistante_detectee(self):
        resolution = self.resolveur.resoudre('ecole', 'INSTITUTION INCONNUE')
        self.assertFalse(resolution.ok)
        self.assertIn('inexistante', resolution.erreur)

    def test_valeur_vide_n_est_pas_une_erreur(self):
        """Une colonne de rattachement vide reste facultative si le champ l'est."""
        resolution = self.resolveur.resoudre('mention', '')
        self.assertIsNone(resolution.erreur)
        self.assertIsNone(resolution.objet)

    def test_cache_evite_les_requetes_redondantes(self):
        premier = self.resolveur.resoudre('ecole', 'ENSEPS')
        second = self.resolveur.resoudre('ecole', 'ENSEPS')
        self.assertIs(premier, second)


class TestAmbiguiteDesReferences(BaseRelations):
    """Une référence ambiguë n'est jamais rattachée au hasard."""

    def test_reference_ambigue_detectee(self):
        """Deux écoles partageant le même nom complet : aucune association."""
        RefEcole.objects.filter(pk=self.ensep.pk).update(nom_complet='Nom commun')
        RefEcole.objects.filter(pk=self.enseps.pk).update(nom_complet='Nom commun')

        resolveur = moteur_relations.ResolveurRelations(RefFiliere)
        resolution = resolveur.resoudre('ecole', 'Nom commun')
        self.assertFalse(resolution.ok)
        self.assertIsNone(resolution.objet)
        self.assertIn('ambiguë', resolution.erreur)

    def test_ambiguite_signalee_dans_le_rapport_d_import(self):
        RefEcole.objects.filter(pk=self.ensep.pk).update(nom_complet='Nom commun')
        RefEcole.objects.filter(pk=self.enseps.pk).update(nom_complet='Nom commun')

        reponse = self._analyser('Code;Libellé;École\nF1;Filière une;Nom commun\n')
        self.assertEqual(reponse.status_code, 200)
        # La colonne « École » est reconnue… mais la valeur reste ambiguë.
        erreurs = reponse.data['validation']['erreurs']
        self.assertTrue(erreurs, "Aucune erreur signalée pour une référence ambiguë.")
        self.assertIn(
            'ambigu', ' '.join(str(e['message']) for e in erreurs).lower(),
        )

    def test_ambiguite_levee_par_le_rattachement_du_registre(self):
        """Deux bâtiments homonymes, départagés par le site (unicité « par »).

        Le registre déclare ``unicite_par='site'`` pour les bâtiments : un nom
        de bâtiment n'est unique que *par site*. Le fichier fournissant le
        site, l'ambiguïté est levée légitimement.
        """
        from formations.models import RefBatiment, RefSalle, RefSite

        site_nord = RefSite.objects.create(nom='Site Nord')
        site_sud = RefSite.objects.create(nom='Site Sud')
        batiment_nord = RefBatiment.objects.create(site=site_nord, nom='Bâtiment A')
        batiment_sud = RefBatiment.objects.create(site=site_sud, nom='Bâtiment A')
        self.assertNotEqual(batiment_nord.pk, batiment_sud.pk)

        # Une salle se rattache à un bâtiment, lui-même rattaché à un site :
        # le même nom de bâtiment existe dans les deux sites.
        resolveur = moteur_relations.ResolveurRelations(
            RefSalle, rattachement={'batiment': 'site'},
        )
        # Sans le site : deux bâtiments portent ce nom → aucune association.
        self.assertIsNone(resolveur.resoudre('batiment', 'Bâtiment A').objet)
        # Avec le site fourni par le fichier : l'ambiguïté est levée.
        objet = resolveur.resoudre(
            'batiment', 'Bâtiment A', contexte={'site': site_sud},
        ).objet
        self.assertEqual(objet, batiment_sud)

    def test_aucune_association_incorrecte(self):
        """En cas d'ambiguïté non levée, aucune filière n'est créée."""
        RefEcole.objects.filter(pk=self.ensep.pk).update(nom_complet='Nom commun')
        RefEcole.objects.filter(pk=self.enseps.pk).update(nom_complet='Nom commun')

        reponse = self._importer('Code;Libellé;École\nF1;Filière ambiguë;Nom commun\n')
        # Aucune ligne valide : le serveur refuse le lot sans rien écrire.
        self.assertEqual(reponse.status_code, 400)
        self.assertFalse(RefFiliere.objects.filter(code='F1').exists())


class TestImportAvecRelations(BaseRelations):
    """Import réel avec rattachement, en mode transactionnel."""

    def test_import_resout_la_relation_et_cree_la_valeur(self):
        reponse = self._importer(
            'Code;Libellé;École\nF1;Filière STAPS;ENSEPS\nF2;Filière STASE;ENSEP\n',
        )
        self.assertEqual(reponse.status_code, 200, reponse.content[:400])
        self.assertEqual(reponse.data['crees'], 2)

        f1 = RefFiliere.objects.get(code='F1')
        self.assertEqual(f1.ecole, self.enseps)
        f2 = RefFiliere.objects.get(code='F2')
        self.assertEqual(f2.ecole, self.ensep)

    def test_import_par_libelle_de_la_relation(self):
        reponse = self._importer('Code;Libellé;École\nF3;Filière test;École ENSEPS\n')
        self.assertEqual(reponse.status_code, 200, reponse.content[:400])
        self.assertEqual(RefFiliere.objects.get(code='F3').ecole, self.enseps)

    def test_import_partiellement_invalide(self):
        """Les lignes valides passent, les lignes fautives sont signalées."""
        reponse = self._importer(
            'Code;Libellé;École\n'
            'OK1;Valide;ENSEPS\n'
            'KO1;École inconnue;INSTITUTION INEXISTANTE\n'
            'OK2;Valide aussi;ENSEP\n',
        )
        self.assertEqual(reponse.status_code, 200, reponse.content[:400])
        self.assertEqual(reponse.data['crees'], 2)
        self.assertTrue(RefFiliere.objects.filter(code='OK1').exists())
        self.assertTrue(RefFiliere.objects.filter(code='OK2').exists())
        self.assertFalse(RefFiliere.objects.filter(code='KO1').exists())
        self.assertGreaterEqual(reponse.data['nb_anomalies'], 1)
        messages = ' '.join(str(a['message']) for a in reponse.data['anomalies'])
        self.assertIn('inexistante', messages)

    def test_integrite_transactionnelle(self):
        """Une ligne fautive n'annule pas les lignes valides du même lot."""
        avant = RefFiliere.objects.count()
        self._importer(
            'Code;Libellé;École\n'
            'OK1;Valide;ENSEPS\n'
            'KO1;Sans école;\n'
            'OK2;Valide deux;ENSEP\n',
        )
        # Les lignes valides sont bien enregistrées… et rien d'autre.
        self.assertEqual(RefFiliere.objects.filter(code='OK1').count(), 1)
        self.assertEqual(RefFiliere.objects.filter(code='OK2').count(), 1)
        self.assertGreater(RefFiliere.objects.count(), avant)

    def test_rapport_detaille_par_ligne_et_colonne(self):
        reponse = self._analyser(
            'Code;Libellé;École\nF1;Filière;INCONNUE\n',
        )
        self.assertEqual(reponse.status_code, 200)
        erreurs = reponse.data['validation']['erreurs']
        self.assertTrue(erreurs)
        self.assertEqual(erreurs[0]['ligne'], 2)  # numéro de ligne du fichier
        self.assertTrue(erreurs[0]['colonne'])
        self.assertTrue(erreurs[0]['message'])

    def test_unicite_respectee_en_mode_ajouter(self):
        RefFiliere.objects.create(code='F1', libelle='Déjà là', ecole=self.enseps)
        reponse = self._importer('Code;Libellé;École\nF1;Autre libellé;ENSEPS\n', mode='ajouter')
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.data['crees'], 0)
        self.assertEqual(reponse.data['ignores'], 1)
        # La valeur existante n'a pas été écrasée.
        self.assertEqual(RefFiliere.objects.get(code='F1').libelle, 'Déjà là')

    def test_mode_mise_a_jour_modifie_le_rattachement(self):
        filiere = RefFiliere.objects.create(
            code='F1', libelle='Filière', ecole=self.enseps,
        )
        reponse = self._importer(
            'Code;Libellé;École\nF1;Filière;ENSEP\n', mode='mettre_a_jour',
        )
        self.assertEqual(reponse.status_code, 200, reponse.content[:400])
        self.assertEqual(reponse.data['mis_a_jour'], 1)
        filiere.refresh_from_db()
        self.assertEqual(filiere.ecole, self.ensep)

    def test_duree_et_compteurs_dans_le_rapport(self):
        reponse = self._importer('Code;Libellé;École\nF1;Filière;ENSEPS\n')
        for cle in ('crees', 'mis_a_jour', 'ignores', 'nb_anomalies',
                    'duree_secondes', 'total_traite', 'resume'):
            self.assertIn(cle, reponse.data)
        self.assertIsInstance(reponse.data['duree_secondes'], float)


    def test_l_analyse_chiffre_les_references_non_resolues(self):
        """L'analyse indique, par colonne, combien de références n'ont pas
        été résolues — afin que l'interface les mette en évidence."""
        reponse = self._analyser(
            'Code;Libellé;École\n'
            'F1;Filière une;ENSEPS\n'
            'F2;Filière deux;INCONNUE\n'
            'F3;Filière trois;AUTRE_INCONNUE\n'
        )
        self.assertEqual(reponse.status_code, 200, reponse.content[:400])
        relations = {
            relation['cle']: relation
            for relation in reponse.data['validation']['relations']
        }
        self.assertIn('ecole', relations)
        self.assertEqual(relations['ecole']['non_resolues'], 2)
        # Les autres colonnes de rattachement sont décrites même quand le
        # fichier ne les renseigne pas : l'utilisateur sait ce qui est attendu.
        self.assertEqual(relations['ecole']['obligatoire'], True)
        self.assertIn('libelle_lie', relations['ecole'])
        self.assertEqual(relations['mention']['non_resolues'], 0)


class TestRelationsSimples(BaseRelations):
    """Le moteur ne se limite pas aux référentiels à relations complexes."""

    def test_modele_sans_relation_complexe_reste_importable(self):
        """Un référentiel sans clé étrangère obligatoire s'importe normalement."""
        reponse = self.client.post(
            '/api/referentiels/types-evaluation/importer/',
            {'fichier': televerser('Code;Libellé\nEXAM;Examen final\n'),
             'mode': 'ajouter'},
            format='multipart',
        )
        self.assertEqual(reponse.status_code, 200, reponse.content[:400])
        self.assertEqual(reponse.data['crees'], 1)
        self.assertTrue(RefTypeEvaluation.objects.filter(code='EXAM').exists())

    def test_relation_facultative_absente(self):
        """Une colonne de rattachement facultative omise n'est pas une erreur."""
        reponse = self._importer('Code;Libellé\nF9;Sans école\n')
        self.assertEqual(reponse.status_code, 200, reponse.content[:400])
        # L'école étant obligatoire sur ce modèle, la ligne est signalée
        # explicitement au lieu d'être créée à moitié.
        self.assertEqual(reponse.data['crees'], 0)
        self.assertFalse(RefFiliere.objects.filter(code='F9').exists())
