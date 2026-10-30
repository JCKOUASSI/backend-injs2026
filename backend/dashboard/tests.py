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
