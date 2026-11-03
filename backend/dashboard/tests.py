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

        # Taux : nombres calculés ou None (dénominateur absent). Quand un
        # taux est mesuré, sa fraction explicite l'accompagne : un « 0 % »
        # doit prouver qu'il est une mesure, pas un widget vide.
        taux = data['taux']
        for cle in ('reussite', 'abandon', 'diplomation'):
            valeur = taux[cle]
            self.assertTrue(valeur is None or isinstance(valeur, float))
            if valeur is not None:
                self.assertIn('sur', taux[f'{cle}_base'] or '')

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


class MesurePresenceTests(TestCase):
    def test_seules_seances_terminees_avec_effectif_connu_sont_mesurees(self):
        from dashboard.services import _mesure_presence
        seance = {'statut': 'TERMINEE', 'effectif_attendu': 4,
                  'presences': {'presents': 2, 'retards': 1}}
        taux, detail, presents, attendus, nb = _mesure_presence([
            seance,
            {**seance, 'statut': 'A_VENIR', 'effectif_attendu': 100},
            {**seance, 'statut': 'EN_COURS', 'effectif_attendu': 100},
            {**seance, 'effectif_attendu': None},
        ])
        self.assertEqual((taux, presents, attendus, nb), (75.0, 3, 4, 1))
        self.assertIn('retards inclus', detail)

    def test_aucune_seance_termineee_reste_non_mesuree(self):
        from dashboard.services import get_presences_dashboard
        data = get_presences_dashboard()
        self.assertIsNone(data['kpis']['taux_assiduite_moyen'])
        self.assertEqual(data['kpis']['presence_attendus'], 0)
        self.assertIn('Aucune séance terminée', data['kpis']['presence_detail'])


class AccueilAdminAlignementLMDTests(TestCase):
    """Accueil admin Django aligné sur la chaîne LMD (Capture 2026-11-03).

    Défauts corrigés : les cartes comptaient les modèles hérités
    (``Formation``/``Module`` — 0 et 0 sur une base LMD) pendant que le
    tableau de bord web affiche 16 formations, 779 ECUE et 3 516
    inscrits ; le taux de présence mensuel affichait « 0,0 % » pour des
    mois sans aucun pointage (dénominateur absent présenté comme une
    mesure) ; les « séances » venaient des SessionModule héritées.
    """

    @classmethod
    def setUpTestData(cls):
        from formations.models import RefFormation
        from scolarite.models import (
            AnneeAcademique, ECUE, Maquette, Niveau, Semestre, UE,
        )

        cls.user = User.objects.create_user(
            username='admin_accueil', password='password123',
            role=User.Role.ADMIN, is_staff=True, is_superuser=True,
        )
        cls.formation = RefFormation.objects.create(
            intitule='ANDRAGOGIE — LICENCE')
        cls.annee = AnneeAcademique.objects.create(
            libelle='2026-2027', date_debut='2026-10-01',
            date_fin='2027-07-31', courante=True,
        )
        cls.niveau = Niveau.objects.create(
            code='L1', libelle='Licence 1', ordre=1)
        cls.semestre = Semestre.objects.create(niveau=cls.niveau, numero=1)
        cls.maquette = Maquette.objects.create(
            annee_academique=cls.annee, ref_formation=cls.formation,
            niveau=cls.niveau, statut=Maquette.Statut.BROUILLON,
        )
        cls.ue = UE.objects.create(
            maquette=cls.maquette, semestre=cls.semestre,
            code='UE1', intitule='Fondamentaux', credits=6,
        )
        ECUE.objects.create(ue=cls.ue, code='EC1', intitule='A', credits=3)
        ECUE.objects.create(ue=cls.ue, code='EC2', intitule='B', credits=3)
        # Maquette ACTIVE immuable : activation après création des ECUE.
        cls.maquette.statut = Maquette.Statut.ACTIVE
        cls.maquette.save(update_fields=['statut'])

    def _contexte(self):
        from django.test import RequestFactory

        from config.admin_dashboard import admin_dashboard_callback

        requete = RequestFactory().get('/admin/')
        requete.user = self.user
        return admin_dashboard_callback(requete, {})

    def test_cartes_alignees_sur_la_chaine_lmd(self):
        from formations.models import RefFormation

        stats = {str(s['label']): s['value']
                 for s in self._contexte()['admin_stats']}
        self.assertEqual(
            stats['Formations LMD'],
            RefFormation.objects.filter(actif=True).count(),
        )
        self.assertEqual(stats['ECUE enseignés'], 2)
        self.assertIn('Étudiants inscrits', stats)

    def test_taux_presence_sans_pointage_est_non_mesure(self):
        taux = self._contexte()['admin_charts']['taux_presence']
        self.assertTrue(all(r['display'] == '—' for r in taux))
        # Histogrammes vides → état vide du gabarit, pas de barres fantômes.
        charts = self._contexte()['admin_charts']
        self.assertIsNone(charts['pointages_mensuels'])
        self.assertIsNone(charts['sessions_mensuelles'])

    def test_taux_presence_calcule_sur_statut_assiduite(self):
        from django.utils import timezone

        from formations.models import Participant
        from presences.models import Pointage

        participant = Participant.objects.create(
            matricule='INJS-T-PRES', nom='Diallo', prenom='Awa')
        aujourdhui = timezone.localdate()
        for statut in ('PRESENT', 'RETARD', 'ABSENT'):
            Pointage.objects.create(
                participant=participant, date_journee=aujourdhui,
                timestamp_entree=timezone.now(), statut_assiduite=statut,
            )
        taux = self._contexte()['admin_charts']['taux_presence']
        courant = taux[-1]
        # Présent + retard = présents (2) ; absent = 1 → 66,7 %.
        self.assertEqual(courant['presents'], 2)
        self.assertEqual(courant['absents'], 1)
        self.assertEqual(courant['display'], '66,7%')

    def test_index_admin_affiche_les_cartes_lmd(self):
        from django.urls import reverse

        self.client.force_login(self.user)
        res = self.client.get(reverse('admin:index'))
        self.assertContains(res, 'Formations LMD')
        self.assertContains(res, 'ECUE enseignés')
        self.assertContains(res, 'Séances EDT par mois')
        self.assertNotContains(res, '0,0%')
