from django.test import TestCase, override_settings

from authentication.models import User
from formations.models import Formateur, Participant, Secretariat
from formations.views import _resolve_secretariat_from_matricule


@override_settings(PUBLIC_QR_SCAN_ENABLED=False)
class PublicBadgePageDisabledTest(TestCase):
    def test_badge_page_returns_disabled_message(self):
        res = self.client.get('/dashboard/badge/')
        self.assertEqual(res.status_code, 403)
        self.assertContains(res, 'Badgeage web indisponible', status_code=403)

    def test_login_page_hides_badge_link(self):
        res = self.client.get('/dashboard/login/')
        self.assertNotContains(res, 'Page de badgeage')


@override_settings(PUBLIC_QR_SCAN_ENABLED=True)
class PublicBadgePageEnabledTest(TestCase):
    def test_badge_page_renders_form(self):
        res = self.client.get('/dashboard/badge/')
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'Badgeage')

    def test_login_page_shows_badge_link(self):
        res = self.client.get('/dashboard/login/')
        self.assertContains(res, 'Page de badgeage')


class DashboardParticipantDispatchByMatriculeTest(TestCase):
    def setUp(self):
        self.sec_fab = Secretariat.objects.create(nom='FAB')
        self.sec_fac = Secretariat.objects.create(nom='FAC')

    def test_fnce_matricule_resolves_to_fab(self):
        sec = _resolve_secretariat_from_matricule('FNCE26-001')
        self.assertIsNotNone(sec)
        self.assertEqual(sec.id, self.sec_fab.id)

    def test_fncp_matricule_resolves_to_fac(self):
        sec = _resolve_secretariat_from_matricule('FNCP26-001')
        self.assertIsNotNone(sec)
        self.assertEqual(sec.id, self.sec_fac.id)

    def test_non_matching_matricule_returns_none(self):
        sec = _resolve_secretariat_from_matricule('ABCD26-001')
        self.assertIsNone(sec)


from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model

User = get_user_model()


class DashboardEngineAPITests(APITestCase):
    """Tests automatisés du Dashboard Engine INJS-LMD 2026."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='admin_test',
            password='password123',
            role=User.Role.ADMIN,
            is_staff=True,
        )
        self.client.force_authenticate(user=self.user)

    def test_overview_endpoint(self):
        res = self.client.get('/api/dashboard/overview/')
        self.assertEqual(res.status_code, 200)
        self.assertIn('kpis', res.data)
        self.assertIn('pipeline', res.data)
        self.assertIn('charts', res.data)
        self.assertIn('alerts', res.data)
        self.assertIn('quick_actions', res.data)

    def test_scolarite_endpoint(self):
        res = self.client.get('/api/dashboard/scolarite/')
        self.assertEqual(res.status_code, 200)
        self.assertIn('kpis', res.data)
        self.assertIn('total_inscrits', res.data['kpis'])

    def test_pedagogie_endpoint(self):
        res = self.client.get('/api/dashboard/pedagogie/')
        self.assertEqual(res.status_code, 200)
        self.assertIn('kpis', res.data)
        self.assertIn('enseignants_actifs', res.data['kpis'])

    def test_presences_endpoint(self):
        res = self.client.get('/api/dashboard/presences/')
        self.assertEqual(res.status_code, 200)
        self.assertIn('kpis', res.data)

    def test_finances_endpoint(self):
        res = self.client.get('/api/dashboard/finances/')
        self.assertEqual(res.status_code, 200)
        self.assertIn('kpis', res.data)
        self.assertIn('total_facture_xof', res.data['kpis'])

    def test_examens_endpoint(self):
        res = self.client.get('/api/dashboard/examens/')
        self.assertEqual(res.status_code, 200)
        self.assertIn('kpis', res.data)
        self.assertIn('diplomes_sha256', res.data['kpis'])

    def test_jurys_alias_endpoint(self):
        """Alias frontend : /api/dashboard/jurys/ → examens_dashboard."""
        res = self.client.get('/api/dashboard/jurys/')
        self.assertEqual(res.status_code, 200)
        self.assertIn('kpis', res.data)
        self.assertIn('sessions_ouvertes', res.data['kpis'])
        self.assertIn('diplomes_sha256', res.data['kpis'])

    def test_etudiant_endpoint(self):
        res = self.client.get('/api/dashboard/etudiant/')
        self.assertEqual(res.status_code, 200)
        self.assertIn('kpis', res.data)

    def test_enseignant_endpoint(self):
        res = self.client.get('/api/dashboard/enseignant/')
        self.assertEqual(res.status_code, 200)
        self.assertIn('kpis', res.data)

    def test_logistique_endpoint(self):
        res = self.client.get('/api/dashboard/logistique/')
        self.assertEqual(res.status_code, 200)
        self.assertIn('kpis', res.data)
        self.assertIn('equipements_inventories', res.data['kpis'])

    def test_unauthenticated_request_rejected(self):
        self.client.force_authenticate(user=None)
        res = self.client.get('/api/dashboard/overview/')
        self.assertEqual(res.status_code, 401)



class TableauDeBordSansDonneesInventeesTests(TestCase):
    """Le tableau de bord ne sert jamais les données d'un tiers ni un repli inventé.

    Défauts corrigés (constatés en production d'aperçu) :
      * ``DossierEtudiant.objects.first()`` / ``Formateur.objects.first()``
        affichaient le dossier ou l'identité d'une **autre** personne au compte
        qui n'en avait pas ;
      * moyenne « 13.38 / 20 », assiduité « 96% », solde « 0 FCFA (À jour) »,
        120 h / 85 h / 96 étudiants / 3 groupes étaient des constantes ;
      * l'année académique retombait sur « 2026-2027 » quand aucune n'existait.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username='compte_sans_dossier', password='password123', role=User.Role.FORMATEUR,
        )

    def test_etudiant_sans_dossier_ne_voit_aucune_donnee(self):
        from dashboard.services import get_etudiant_dashboard

        Participant.objects.create(matricule='INJS-T-001', nom='Autre', prenom='Etudiant')
        data = get_etudiant_dashboard(self.user)
        self.assertIsNone(data['etudiant'])
        self.assertIsNone(data['matricule'])
        self.assertIsNone(data['moyenne_generale'])
        self.assertIsNone(data['kpis']['moyenne_generale'])
        self.assertIsNone(data['kpis']['assiduite'])
        self.assertIsNone(data['kpis']['credits_obtenus'])
        self.assertNotIn('13.38', str(data))
        self.assertNotIn('96%', str(data))
        self.assertNotIn('INJS26-0001', str(data))

    def test_enseignant_ne_voit_pas_les_modules_d_un_autre_formateur(self):
        """Le compte FORMATEUR a bien sa fiche (créée par `profile_sync`), mais
        aucun module : l'ancien repli `Formateur.objects.first()` lui servait
        les cours, les 96 étudiants et les 120 h d'un autre enseignant."""
        from dashboard.services import get_enseignant_dashboard

        autre = Formateur.objects.create(numerobadge='F-001', nom='DIALLO', prenom='Mamadou')
        data = get_enseignant_dashboard(self.user)
        self.assertNotIn('DIALLO', str(data))
        self.assertEqual(data['kpis']['cours_assignes'], 0)
        self.assertEqual(data['kpis']['heures_prevues'], 0.0)
        self.assertIsNone(data['kpis']['heures_realisees'])
        self.assertEqual(data['kpis']['etudiants'], 0)
        self.assertNotEqual(data['enseignant'], f"{autre.nom} {autre.prenom}")

    def test_annee_academique_absente_n_est_pas_inventee(self):
        from dashboard.services import libelle_annee_courante

        self.assertIsNone(libelle_annee_courante())


class AnneeAcademiqueNonInventeeAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='admin_annee', password='password123', role=User.Role.ADMIN, is_staff=True,
        )
        self.client.force_authenticate(user=self.user)

    def test_overview_sans_annee_ne_renvoie_pas_de_libelle(self):
        res = self.client.get('/api/dashboard/overview/')
        self.assertEqual(res.status_code, 200)
        self.assertIsNone(res.data['annee_academique'])


class VueEnsembleCoherenceTests(TestCase):
    """Vue d'ensemble : widgets alimentés, compteurs cohérents, zéro repli.

    Défauts corrigés (Capture 2026-11-03) : légendes de formations en
    double (« ACTIVITÉS PHYSIQUES » x2, intitulés tronqués à 20 caractères)
    totalisant 1 322 pour 3 516 inscrits ; étape « Évaluation » comptant
    les Module hérités (6) au lieu des évaluations académiques ; 60
    « diplômes délivrés » dont aucun validé ; taux/activité/sexe/charge/
    finances jamais fournis ; constantes inventées dans les onglets
    (310 h / 245 h / 79 %, 960 000 XOF soldés, mentions 3/3, `or 5`…).
    """

    def setUp(self):
        from rest_framework.test import APIClient
        self.user = User.objects.create_user(
            username='pilotage_test', password='password123',
            role=User.Role.ADMIN, is_staff=True,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_overview_structure_et_coherence(self):
        res = self.client.get('/api/dashboard/overview/')
        self.assertEqual(res.status_code, 200)
        data = res.data

        # Étapes du parcours : les 8 identifiants canoniques, dans l'ordre.
        self.assertEqual(
            [p['id'] for p in data['pipeline']],
            ['candidature', 'selection', 'admission', 'inscription',
             'cours', 'evaluation', 'jury', 'diplome'],
        )

        charts = data['charts']
        for cle in ('repartition_formations', 'repartition_sexe',
                    'evolution_effectifs', 'charge_enseignement'):
            self.assertIn(cle, charts)

        # Légendes de filières : jamais deux libellés identiques.
        labels = [r['label'] for r in charts['repartition_formations']]
        self.assertEqual(len(labels), len(set(labels)))

        # Évolution : labels et cumul alignés, cumul non décroissant.
        evo = charts['evolution_effectifs']
        self.assertEqual(len(evo['labels']), len(evo['inscrits_cumul']))
        self.assertEqual(evo['inscrits_cumul'], sorted(evo['inscrits_cumul']))

        # Taux : nombres calculés ou None — la diplomation n'est pas mesurée.
        taux = data['taux']
        self.assertIsNone(taux['diplomation'])
        for cle in ('reussite', 'abandon'):
            self.assertTrue(taux[cle] is None or isinstance(taux[cle], float))

        # Finances : impayé = attendu - encaissé (base échéanciers).
        finances = data['finances']
        self.assertAlmostEqual(
            finances['montant_impaye'],
            finances['montant_attendu'] - finances['montant_encaisse'],
            places=2,
        )
        if finances['montant_attendu'] == 0:
            self.assertIsNone(finances['taux_recouvrement'])

        self.assertIsInstance(data['activite_recente'], list)

    def test_onglets_sans_constantes_inventees(self):
        from finances_etudiantes.models import LigneEcheancier
        from jurys.models import PVJury
        from graduation.models import Diplome
        from stages.models import OrganismeAccueil

        ped = self.client.get('/api/dashboard/pedagogie/').data['kpis']
        # Heures « exécutées » sans source : None (jamais 245 h / 79,0 %).
        self.assertIsNone(ped['heures_executees'])
        self.assertIsNone(ped['taux_realisation_vh'])

        fin = self.client.get('/api/dashboard/finances/').data['kpis']
        if not LigneEcheancier.objects.exists():
            self.assertEqual(fin['total_facture_xof'], '0 XOF')
            self.assertIsNone(fin['taux_recouvrement'])

        exa = self.client.get('/api/dashboard/examens/').data['kpis']
        self.assertEqual(exa['pv_scelles'], PVJury.objects.count())
        self.assertEqual(
            exa['diplomes_certifies'],
            Diplome.objects.filter(statut=Diplome.Statut.VALIDATED).count(),
        )

        log = self.client.get('/api/dashboard/logistique/').data['kpis']
        self.assertIsNone(log['installations_sportives'])
        self.assertEqual(
            log['organismes_partenaires'], OrganismeAccueil.objects.count())
