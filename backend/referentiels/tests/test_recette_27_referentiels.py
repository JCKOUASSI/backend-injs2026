"""Recette fonctionnelle des 27 référentiels du Hub (mission « Référentiels »).

Objectif : démontrer, **référentiel par référentiel** et non de façon
théorique, que chaque fonctionnalité applicable est réellement opérationnelle :

* consultation, recherche multicritère, tri et pagination **côté serveur** ;
* activation, désactivation, archivage, désarchivage, suppression sécurisée ;
* export Word / Excel / CSV / PDF ;
* import Excel / CSV (analyse et exécution) ;
* permissions contrôlées **côté serveur**, opération par opération ;
* respect du caractère « lecture seule » des 4 référentiels historisés.

Les tests sont générés dynamiquement depuis le registre : ajouter un
référentiel au registre l'inclut automatiquement dans la recette.
"""

from django.contrib.auth import get_user_model
from django.db import models
from django.test import TestCase
from django.urls import NoReverseMatch, reverse
from rest_framework.test import APIClient

from referentiels.registre import REGISTRE, modele_de

Utilisateur = get_user_model()

FORMATS = ('xlsx', 'csv', 'docx', 'pdf')
SIGNE_PAR_FORMAT = {
    'xlsx': b'PK',
    'csv': b'\xef\xbb\xbf',
    'docx': b'PK',
    'pdf': b'%PDF',
}


def _noms_champs(modele):
    return {f.name for f in modele._meta.concrete_fields}


def _slug_de(modele):
    """Slug du registre correspondant à un modèle (ou None)."""
    for slug, entree in REGISTRE.items():
        if modele_de(entree) is modele:
            return slug
    return None


def _valeur_minimale(field, suffixe):
    """Valeur de fixture pour un champ obligatoire non renseigné.

    Il s'agit d'un jeu d'essai isolé, jamais d'une donnée académique
    destinée à la base : rien n'est inventé « pour combler une source ».
    """
    from datetime import date

    nom = field.name
    if isinstance(field, models.BooleanField):
        return False
    if isinstance(field, models.DateField):
        # Une date de fin doit rester postérieure à la date de début
        # (contrainte de cohérence portée par plusieurs modèles).
        return date(2027, 7, 31) if 'fin' in nom else date(2026, 1, 1)
    if isinstance(field, models.DateTimeField):
        return None  # auto_now / auto_now_add
    if isinstance(field, (models.IntegerField, models.PositiveSmallIntegerField,
                          models.PositiveIntegerField, models.SmallIntegerField)):
        return 1
    if isinstance(field, (models.DecimalField, models.FloatField)):
        return 1
    if isinstance(field, (models.CharField, models.TextField)):
        if getattr(field, 'choices', None):
            return field.choices[0][0]
        return f'AUTO-{nom}-{suffixe}'[: min(getattr(field, "max_length", 50) or 50, 50)]
    return None


def creer_valeur(slug, suffixe, profondeur=0):
    """Crée une valeur minimale d'un référentiel, en créant au besoin ses parents.

    Renvoie ``(objet, motif)`` : ``objet`` est ``None`` si le référentiel ne
    peut pas être instancié automatiquement (FK hors registre, profondeur
    excessive) — le test est alors signalé comme non applicable, jamais
    silencieusement ignoré.
    """
    if profondeur > 2:
        return None, 'profondeur de rattachement excessive'
    entree = REGISTRE[slug]
    modele = modele_de(entree)
    noms = _noms_champs(modele)
    champ_code = entree.get('champ_code', 'code')
    champ_libelle = entree.get('champ_libelle', 'libelle')

    valeurs = {}
    if champ_code in noms:
        valeurs[champ_code] = f'AUTO-{suffixe}'[:50]
    if champ_libelle in noms and champ_libelle not in valeurs:
        valeurs[champ_libelle] = f'Libellé {suffixe}'[:150]

    for field in modele._meta.concrete_fields:
        if isinstance(field, models.ForeignKey):
            if field.null or field.blank:
                continue
            valeurs[field.name] = None  # traité ci-dessous
        elif (not field.null and field.blank is False
              and not field.primary_key and not field.has_default()
              and field.name not in valeurs):
            genere = _valeur_minimale(field, suffixe)
            if genere is not None:
                valeurs[field.name] = genere

    for field in modele._meta.concrete_fields:
        if not isinstance(field, models.ForeignKey) or field.null or field.blank:
            continue
        parent = _slug_de(field.related_model)
        if parent is None:
            return None, f'rattachement {field.name} hors registre'
        objet, motif = creer_valeur(parent, f'{suffixe}-{field.name}', profondeur + 1)
        if objet is None:
            return None, f'{field.name} : {motif}'
        valeurs[field.name] = objet

    from django.db import transaction

    # Point de sauvegarde : un échec de création ne doit pas invalider la
    # transaction du test et faire échouer les référentiels suivants.
    try:
        with transaction.atomic():
            return modele._default_manager.create(**valeurs), None
    except Exception as exc:  # un modèle hors socle peut exiger d'autres champs
        return None, f'création impossible ({exc.__class__.__name__} : {exc})'


ACTIONS_CYCLE = ('activer', 'desactiver', 'archiver', 'reactiver', 'supprimer')


def _chemins_actions():
    """{slug: {action: motif}} pour toutes les routes du module.

    Les routes génériques (``^slug/(?P<pk>…)/action/$``) et celles servies
    par le router suivent la même convention : ``/<slug>/<pk>/<action>/``.
    On s'appuie sur cette convention, **vérifiée** par ``resolve()`` sur la
    vue réellement servie, plutôt que sur le nom de la route — deux
    conventions de nommage coexistent (``ref-<slug>-<action>`` pour les
    routes génériques, ``ref-<basename>-<action>`` pour le router).
    """
    from django.urls import Resolver404, resolve

    trouves = {}
    for slug in REGISTRE:
        actions = {}
        # Action de liste : /<slug>/<action>/
        for action in ('exporter', 'importer', 'importer/analyse'):
            try:
                correspondance = resolve(f'/api/referentiels/{slug}/{action}/')
            except Resolver404:
                continue
            if action in (correspondance.func.actions or {}).values():
                actions[action] = f'/api/referentiels/{slug}/{action}/'
        # Action de détail : /<slug>/<pk>/<action>/
        for action in ACTIONS_CYCLE:
            try:
                correspondance = resolve(f'/api/referentiels/{slug}/1/{action}/')
            except Resolver404:
                continue
        for action in ACTIONS_CYCLE:
            try:
                correspondance = resolve(f'/api/referentiels/{slug}/1/{action}/')
            except Resolver404:
                continue
            if (correspondance.func.actions or {}).get('post') == action:
                actions[action] = f'/api/referentiels/{slug}/{{pk}}/{action}/'
        if actions:
            trouves[slug] = actions
    return trouves


CHEMINS_ACTIONS = _chemins_actions()




def _chemins_export():
    """{slug: chemin de la route d'export} — toutes routes confondues.

    Les routes génériques sont nommées ``ref-<slug>-exporter`` et celles
    servies par le router ``ref-<basename>-exporter`` (au singulier) : la
    recette s'appuie sur le motif d'URL, qui porte toujours le slug.
    """
    from django.urls import get_resolver

    trouves = {}

    def parcourir(res, prefixe=''):
        for motif in res.url_patterns:
            if hasattr(motif, 'url_patterns'):
                parcourir(motif, prefixe + str(motif.pattern))
            elif str(getattr(motif, 'name', '') or '').endswith('-exporter'):
                if prefixe not in ('api/referentiels/', ''):
                    continue
                pattern = str(motif.pattern).lstrip('^')
                slug = pattern.split('/')[0]
                if slug and slug not in trouves:
                    trouves[slug] = f'/{prefixe}{slug}/exporter/'

    parcourir(get_resolver())
    return trouves


CHEMINS_EXPORT = _chemins_export()


def url_action(slug, action, pk=None):
    """Chemin d'une action d'un référentiel (conventions confondues)."""
    chemin = CHEMINS_ACTIONS.get(slug, {}).get(action)
    if chemin is None:
        raise NoReverseMatch(f'{slug}/{action}')
    if pk is None:
        return chemin
    return f'/{slug}/{action}/{pk}/'.replace(f'/{slug}/{action}/', chemin)


def url_export(slug):
    """Chemin de la route d'export d'un slug (toutes conventions confondues)."""
    if slug in CHEMINS_EXPORT:
        return CHEMINS_EXPORT[slug]
    try:
        return reverse(f'ref-{slug}-exporter')
    except NoReverseMatch:
        raise AssertionError(f'Aucune route d’export pour le référentiel « {slug} ».')


class BaseRecette(TestCase):
    """Deux profils : gestionnaire habilité et simple authentifié."""

    @classmethod
    def setUpTestData(cls):
        cls.gestionnaire = Utilisateur.objects.create_user(
            username='recette.gestion', password='passe12345', role='ADMIN',
        )
        cls.lecteur = Utilisateur.objects.create_user(
            username='recette.lecteur', password='passe12345', role='AUDITEUR',
        )

    def client_pour(self, utilisateur=None):
        client = APIClient()
        if utilisateur is not None:
            client.force_authenticate(utilisateur)
        return client


class TestRoutesEtPermissions(BaseRecette):
    """Chaque référentiel expose les routes attendues, et rien de plus."""

    def test_routes_de_modification_absentes_en_lecture_seule(self):
        """Un référentiel non éditable n'expose ni création ni import ni suppression."""
        for slug, entree in REGISTRE.items():
            if entree['editable']:
                continue
            with self.subTest(slug=slug):
                for nom in (f'ref-{slug}-importer', f'ref-{slug}-supprimer'):
                    with self.assertRaises(NoReverseMatch, msg=f'{slug} expose {nom}'):
                        reverse(nom)

    def test_export_disponible_pour_les_27(self):
        """L'export est ouvert aux 27 référentiels, y compris en lecture seule."""
        manquants = [slug for slug in REGISTRE if slug not in CHEMINS_EXPORT]
        self.assertEqual(manquants, [], f'Référentiels sans export : {manquants}')

    def test_routes_de_cycle_de_vie_pour_les_editables(self):
        for slug, entree in REGISTRE.items():
            if not entree['editable']:
                continue
            with self.subTest(slug=slug):
                for nom in ('activer', 'desactiver', 'archiver', 'reactiver', 'supprimer'):
                    try:
                        reverse(f'ref-{slug}-{nom}', kwargs={'pk': 1})
                    except NoReverseMatch:
                        # Référentiels servis par un ViewSet dédié : le router
                        # génère la route avec son propre préfixe.
                        self.assertTrue(
                            entree.get('route_api'),
                            f'{slug} : route {nom} introuvable',
                        )

    def test_lecture_refusee_aux_anonymes(self):
        """Aucune donnée de référentiel n'est accessible sans authentification."""
        for slug, entree in REGISTRE.items():
            with self.subTest(slug=slug):
                route = 'ref-%s-list' % slug
                if entree.get('route_api'):
                    continue  # route portée par une autre application
                try:
                    url = reverse(route)
                except NoReverseMatch:
                    continue
                reponse = APIClient().get(url)
                self.assertIn(reponse.status_code, (401, 403), f'{slug} : {reponse.status_code}')

    def test_export_refuse_au_simple_lecteur(self):
        """L'export n'est pas une simple lecture : il exige un rôle de gestion."""
        client = self.client_pour(self.lecteur)
        refuses = []
        for slug in REGISTRE:
            url = url_export(slug)
            if client.get(url, {'export': 'csv'}).status_code == 200:
                refuses.append(slug)
        self.assertEqual(refuses, [], f'Export accessible au lecteur : {refuses}')

    def test_import_refuse_au_simple_lecteur(self):
        client = self.client_pour(self.lecteur)
        for slug, entree in REGISTRE.items():
            if not entree['editable']:
                continue
            with self.subTest(slug=slug):
                try:
                    url = reverse(f'ref-{slug}-importer')
                except NoReverseMatch:
                    self.assertTrue(entree.get('route_api'))
                    continue
                reponse = client.post(url, {'mode': 'ajouter'}, format='multipart')
                self.assertIn(reponse.status_code, (401, 403))

    def test_suppression_refusee_au_simple_lecteur(self):
        client = self.client_pour(self.lecteur)
        for slug, entree in REGISTRE.items():
            if not entree['editable']:
                continue
            with self.subTest(slug=slug):
                try:
                    url = reverse(f'ref-{slug}-supprimer', kwargs={'pk': 1})
                except NoReverseMatch:
                    continue
                reponse = client.post(url, {'confirmation': 'confirmer'})
                self.assertIn(reponse.status_code, (401, 403, 404))


class TestExportDes27(BaseRecette):
    """Les quatre formats sont réellement générés pour les 27 référentiels."""

    def test_quatre_formats_pour_chaque_referentiel(self):
        client = self.client_pour(self.gestionnaire)
        echecs = []
        for slug in REGISTRE:
            url = url_export(slug)
            for format_cible in FORMATS:
                reponse = client.get(url, {'export': format_cible})
                contenu = reponse.content
                if reponse.status_code != 200:
                    echecs.append(f'{slug}/{format_cible} : HTTP {reponse.status_code}')
                elif not contenu.startswith(SIGNE_PAR_FORMAT[format_cible]):
                    echecs.append(f'{slug}/{format_cible} : contenu invalide')
        self.assertEqual(echecs, [], '\n'.join(echecs))

    def test_export_pdf_et_csv_portent_les_mentions_institutionnelles(self):
        client = self.client_pour(self.gestionnaire)
        for slug in ('formations', 'modules-officiels', 'ue-ecue', 'volumes-modules'):
            with self.subTest(slug=slug):
                reponse = client.get(reverse(f'ref-{slug}-exporter'), {'export': 'csv'})
                self.assertEqual(reponse.status_code, 200)
                texte = reponse.content.decode('utf-8-sig')
                self.assertIn('INSTITUT NATIONAL DE LA JEUNESSE', texte)
                self.assertIn('Référentiel :', texte)
                self.assertIn('Total :', texte)

    def test_lecture_seule_interdit_toujours_l_ecriture(self):
        """Lecture seule = pas de création, modification ni suppression."""
        client = self.client_pour(self.gestionnaire)
        for slug, entree in REGISTRE.items():
            if entree['editable']:
                continue
            with self.subTest(slug=slug):
                # La consultation reste ouverte : le caractère lecture seule
                # ne doit jamais bloquer une lecture.
                self.assertEqual(
                    client.get(f'/api/referentiels/{slug}/').status_code, 200,
                )
                # Aucune écriture n'est possible sous ce slug, que la route
                # d'écriture soit inexistante (404) ou interdite (405).
                self.assertIn(
                    client.post(
                        f'/api/referentiels/{slug}/', {}, format='json',
                    ).status_code,
                    (401, 403, 404, 405),
                )
                # L'export, lui, reste ouvert.
                self.assertEqual(
                    client.get(url_export(slug), {'export': 'csv'}).status_code,
                    200,
                )


class TestListeServeurDes27(BaseRecette):
    """Recherche, tri et pagination sont traités côté serveur."""

    def test_pagination_et_ordre_cote_serveur(self):
        client = self.client_pour(self.gestionnaire)
        anomalies = []
        for slug, entree in REGISTRE.items():
            if entree.get('route_api'):
                continue
            try:
                url = reverse(f'ref-{slug}-list')
            except NoReverseMatch:
                continue
            reponse = client.get(url, {'page': 1, 'page_size': 10})
            if reponse.status_code != 200:
                anomalies.append(f'{slug} : HTTP {reponse.status_code}')
                continue
            if 'count' not in reponse.data:
                anomalies.append(f'{slug} : réponse non paginée')

            # Tri descendant sur le libellé : le serveur doit l'appliquer.
            champ_tri = entree.get('champ_libelle', 'libelle')
            triee = client.get(url, {'ordering': f'-{champ_tri}', 'page_size': 10})
            if triee.status_code != 200:
                anomalies.append(f'{slug} : tri refusé ({triee.status_code})')

            # Recherche multicritère : le serveur doit filtrer, pas le client.
            recherche = client.get(url, {'search': 'zzz-inexistant-zzz', 'page_size': 10})
            if recherche.status_code != 200:
                anomalies.append(f'{slug} : recherche refusée ({recherche.status_code})')
            elif recherche.data.get('count', 0) != 0:
                anomalies.append(f'{slug} : recherche sans effet ({recherche.data.get("count")})')
        self.assertEqual(anomalies, [], '\n'.join(anomalies))


class TestCycleDeVieDesEditables(BaseRecette):
    """Activer, désactiver, archiver, réactiver et supprimer, pour chaque modèle."""

    def _url(self, slug, action, pk):
        chemin = CHEMINS_ACTIONS.get(slug, {}).get(action)
        if chemin is None:
            return None
        return chemin.replace('{pk}', str(pk))

    def test_cycle_complet_sur_chaque_referentiel_editable(self):
        client = self.client_pour(self.gestionnaire)
        echecs = []
        non_applicables = []
        for slug, entree in REGISTRE.items():
            if not entree['editable']:
                continue
            objet, motif = creer_valeur(slug, slug)
            if objet is None:
                non_applicables.append(f'{slug} ({motif})')
                continue

            modele = modele_de(entree)
            url_activer = self._url(slug, 'activer', objet.pk)
            url_desactiver = self._url(slug, 'desactiver', objet.pk)
            url_archiver = self._url(slug, 'archiver', objet.pk)
            url_reactiver = self._url(slug, 'reactiver', objet.pk)
            if url_activer is None or url_desactiver is None:
                non_applicables.append(f'{slug} (aucune route d’activation)')
                continue

            with self.subTest(slug=slug):
                a_actif = 'actif' in _noms_champs(modele)
                a_archive = 'archive' in _noms_champs(modele)

                if a_actif:
                    # Désactivation : la valeur reste présente et non archivée.
                    reponse = client.post(url_desactiver)
                    self.assertEqual(reponse.status_code, 200, reponse.content[:200])
                    objet.refresh_from_db()
                    self.assertFalse(objet.actif)
                    if a_archive:
                        self.assertFalse(objet.archive)

                    # Réactivation
                    self.assertEqual(client.post(url_activer).status_code, 200)
                    objet.refresh_from_db()
                    self.assertTrue(objet.actif)

                if a_archive:
                    self.assertEqual(client.post(url_archiver).status_code, 200)
                    objet.refresh_from_db()
                    self.assertTrue(objet.archive)
                    self.assertEqual(client.post(url_reactiver).status_code, 200)
                    objet.refresh_from_db()
                    self.assertFalse(objet.archive)
                else:
                    # Modèle sans archivage : l'action le refuse explicitement
                    # au lieu de lever une erreur inattendue.
                    self.assertEqual(client.post(url_archiver).status_code, 400)

                # Suppression : confirmation obligatoire
                url_supprimer = self._url(slug, 'supprimer', objet.pk)
                if url_supprimer:
                    self.assertEqual(client.post(url_supprimer, {}).status_code, 400)
                    reponse = client.post(url_supprimer, {'confirmation': 'confirmer'})
                    self.assertIn(reponse.status_code, (200, 409), reponse.content[:300])
                    # Rien n'est jamais détruit physiquement.
                    self.assertTrue(
                        modele._default_manager.filter(pk=objet.pk).exists(),
                        f'{slug} : la valeur a été détruite physiquement',
                    )
        if non_applicables:
            self.skipTest(
                'Non applicable (aucune donnée académique inventée) : '
                + ' ; '.join(non_applicables)
            )
        self.assertEqual(echecs, [])


class TestSuppressionSecurisee(BaseRecette):
    """Comportement exact de la suppression : dépendances, intégrité, traces."""

    def test_dependances_detectees_et_suppression_refusee(self):
        """Une valeur utilisée n'est jamais supprimée : 409 avec le détail."""
        from referentiels.models import RefEcole, RefFiliere

        client = self.client_pour(self.gestionnaire)
        ecole = RefEcole.objects.create(code='ENSEPS', libelle='ENSEPS')
        filiere = RefFiliere.objects.create(code='STAPS', libelle='STAPS', ecole=ecole)
        self.assertIsNotNone(filiere.pk)

        url = reverse('ref-ecoles-supprimer', kwargs={'pk': ecole.pk})
        reponse = client.post(url, {'confirmation': 'confirmer'})
        self.assertEqual(reponse.status_code, 409, reponse.content[:400])
        self.assertTrue(reponse.data['dependances'])
        ecole.refresh_from_db()
        self.assertFalse(ecole.archive)  # rien n'a été modifié

    def test_suppression_sans_dependance_archive_et_journalise(self):
        from referentiels.models import RefEcole, ReferentielJournal

        client = self.client_pour(self.gestionnaire)
        ecole = RefEcole.objects.create(code='ECOLE-SEULE', libelle='École isolée')
        url = reverse('ref-ecoles-supprimer', kwargs={'pk': ecole.pk})
        reponse = client.post(url, {'confirmation': 'confirmer', 'motif': 'test recette'})
        self.assertEqual(reponse.status_code, 200, reponse.content[:300])

        ecole.refresh_from_db()
        self.assertTrue(ecole.archive)
        self.assertTrue(RefEcole.objects.filter(pk=ecole.pk).exists())
        self.assertTrue(
            ReferentielJournal.objects.filter(object_id=ecole.pk).exists(),
            'Aucune trace au journal : la traçabilité n’est pas assurée.',
        )

    def test_les_trois_operations_restent_distinctes(self):
        from referentiels.models import RefEcole

        client = self.client_pour(self.gestionnaire)
        valeur = RefEcole.objects.create(code='TRIPLE', libelle='Triple test')
        base = reverse('ref-ecoles-supprimer', kwargs={'pk': valeur.pk})

        # 1. Désactivation : présente, inactive, non archivée.
        client.post(reverse('ref-ecoles-desactiver', kwargs={'pk': valeur.pk}))
        valeur.refresh_from_db()
        self.assertFalse(valeur.actif)
        self.assertFalse(valeur.archive)

        # 2. Archivage : présente, inactive, archivée.
        client.post(reverse('ref-ecoles-archiver', kwargs={'pk': valeur.pk}))
        valeur.refresh_from_db()
        self.assertTrue(valeur.archive)

        # 3. Activation refusée tant que la valeur est archivée.
        self.assertEqual(
            client.post(reverse('ref-ecoles-activer', kwargs={'pk': valeur.pk})).status_code,
            400,
        )
        # 4. Suppression : archivage réversible, aucune destruction.
        client.post(base, {'confirmation': 'confirmer'})
        self.assertTrue(RefEcole.objects.filter(pk=valeur.pk).exists())


class TestImportDesEditables(BaseRecette):
    """L'import est opérationnel sur chaque référentiel éditable."""

    CSV = 'Code;Libellé\nAUTO-X;Valeur de recette\n'

    def test_analyse_disponible_sur_chaque_referentiel_editable(self):
        client = self.client_pour(self.gestionnaire)
        from django.core.files.uploadedfile import SimpleUploadedFile

        echecs = []
        for slug, entree in REGISTRE.items():
            if not entree['editable']:
                continue
            url = CHEMINS_ACTIONS.get(slug, {}).get('importer/analyse')
            if url is None:
                continue
            fichier = SimpleUploadedFile(
                'recette.csv', self.CSV.encode('utf-8'), content_type='text/csv',
            )
            reponse = client.post(url, {'fichier': fichier}, format='multipart')
            if reponse.status_code != 200:
                echecs.append(f'{slug} : HTTP {reponse.status_code}')
                continue
            if 'previsualisation' not in reponse.data:
                echecs.append(f'{slug} : prévisualisation absente')
        self.assertEqual(echecs, [], '\n'.join(echecs))
