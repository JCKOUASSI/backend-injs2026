"""L'administration Django doit couvrir tout le domaine métier.

Constat d'audit : 41 modèles projet n'étaient pas inscrits dans l'admin, dont
des objets réellement pilotés depuis le site (campagnes d'admission, épreuves,
sessions de jury, affectations pédagogiques, organigramme, demandes d'accès).
Un administrateur ne pouvait donc pas les corriger. Inversement, une liste mal
configurée (champ inexistant, `list_display` erroné) ne casse qu'à l'ouverture :
ces tests ouvrent réellement chaque page.
"""

from django.apps import apps
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

# Les pages d'administration référencent `{% static %}`. En production le
# manifeste est produit par `collectstatic` ; un test ne doit pas dépendre de
# cet artefact de build (déjà consigné L4-05 dans docs/audit/permissions.md).
STORAGE_DE_TEST = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}

LABELS = (
    'authentication', 'formations', 'presences', 'statistiques',
    'suiviEvaluation', 'evaluations', 'scolarite', 'admissions', 'parametres',
    'referentiels', 'equivalences', 'jurys', 'graduation',
    'finances_etudiantes', 'stages', 'administrations', 'ressources_humaines',
    'patrimoine', 'edts', 'core', 'habilitations',
)


def _modeles_projet():
    for label in LABELS:
        yield from apps.get_app_config(label).get_models()


@override_settings(STORAGES=STORAGE_DE_TEST)
class CouvertureAdministrationTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.admin_user = get_user_model().objects.create_superuser(
            'admin_tests', 'admin@example.com', 'MotDePasse#2026',
        )

    def setUp(self):
        self.client.force_login(self.admin_user)

    def test_tous_les_modeles_metier_sont_administrables(self):
        manquants = [
            f'{m._meta.app_label}.{m.__name__}'
            for m in _modeles_projet() if not admin.site.is_registered(m)
        ]
        self.assertEqual(
            manquants, [],
            'Modèles absents de l\'administration (aucune gestion possible) : '
            f'{manquants}',
        )

    def test_chaque_liste_d_administration_s_ouvre(self):
        """Une liste mal configurée ne casse qu'à l'ouverture : on l'ouvre."""
        en_echec = []
        for modele in _modeles_projet():
            if not admin.site.is_registered(modele):
                continue
            url = f'/admin/{modele._meta.app_label}/{modele._meta.model_name}/'
            with self.subTest(modele=url):
                try:
                    reponse = self.client.get(url)
                except Exception as erreur:  # noqa: BLE001 — diagnostic
                    en_echec.append((url, repr(erreur)[:120]))
                    continue
                if reponse.status_code != 200:
                    en_echec.append((url, reponse.status_code))
        self.assertEqual(en_echec, [], f'Listes en échec : {en_echec[:5]}')

    def test_les_valeurs_calculees_ne_sont_pas_modifiables(self):
        """Une synthèse ou un historique ne doit pas être édité à la main."""
        from core.admin_completion import LECTURE_SEULE

        fautifs = []
        for reference in LECTURE_SEULE:
            try:
                modele = apps.get_model(reference)
            except LookupError:
                continue
            if modele is None or not admin.site.is_registered(modele):
                continue
            cl = admin.site._registry[modele]
            if cl.has_add_permission(None) or cl.has_change_permission(None):
                fautifs.append(reference)
        self.assertEqual(fautifs, [], f'Modèles techniques modifiables : {fautifs}')

    def test_les_modeles_operationnels_ont_recherche_et_filtres(self):
        sans_recherche = []
        for reference in (
            'admissions.CampagneAdmission', 'admissions.Epreuve',
            'jurys.SessionJury', 'scolarite.AffectationPedagogique',
            'administrations.Direction', 'habilitations.DemandeAcces',
        ):
            try:
                modele = apps.get_model(reference)
            except LookupError:
                continue
            cl = admin.site._registry.get(modele)
            if cl is None:
                continue
            if not cl.search_fields:
                sans_recherche.append(reference)
        self.assertEqual(
            sans_recherche, [],
            f'Modèles opérationnels sans recherche : {sans_recherche}',
        )

    def test_les_listes_a_cle_etrangere_sont_prechargees(self):
        """`list_display` exposant une FK sans `select_related` = N+1 en admin."""
        fautifs = []
        for modele in _modeles_projet():
            cl = admin.site._registry.get(modele)
            if cl is None or cl.list_select_related:
                continue
            for nom in cl.list_display:
                try:
                    champ = modele._meta.get_field(nom)
                except Exception:
                    continue
                if champ.is_relation and not champ.many_to_many:
                    fautifs.append(f'{modele.__name__}.{nom}')
                    break
        self.assertEqual(
            fautifs, [],
            'Listes exposant une clé étrangère sans select_related (N+1) : '
            f'{fautifs[:10]}',
        )

    def test_l_index_d_administration_repond(self):
        self.assertEqual(self.client.get(reverse('admin:index')).status_code, 200)
