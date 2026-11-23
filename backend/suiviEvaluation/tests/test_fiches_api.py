"""Fiches individuelles auditeur / enseignant : contrat d'API et permissions.

Ces écrans étaient routés côté site mais servis par aucune vue Django. Les
tests vérifient le contrat attendu par le frontend (noms de champs), la
distinction verdict pédagogique / décision officielle, les exports et le
contrôle d'accès (une fiche porte des notes nominatives).
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from formations.models import Formateur, Formation, Module, ModuleParticipant, Participant, SessionModule
from suiviEvaluation.models import DecisionPedagogique, MoyenneModule

User = get_user_model()


class BaseFicheTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.formation = Formation.objects.create(formation='Formation test fiche')
        cls.autre_formation = Formation.objects.create(formation='Autre formation test')
        cls.participant = Participant.objects.create(
            matricule='TEST-FICHE-1', nom='KOUAME', prenom='Aya',
        )
        cls.module = Module.objects.create(
            formation=cls.formation, intitule='Déontologie', ordre=1,
        )
        ModuleParticipant.objects.create(module=cls.module, participant=cls.participant)
        cls.formateur = Formateur.objects.create(
            numerobadge='BADGE-FICHE-1', nom='YAO', prenom='Serge',
        )
        cls.module.formateur = cls.formateur
        cls.module.save(update_fields=['formateur'])
        cls.moyenne = MoyenneModule.objects.create(
            module=cls.module, participant=cls.participant,
            moyenne=15, nb_notes=3, heures_presence=18, heures_prevues=20,
            taux_presence=90,
        )
        cls.decision = DecisionPedagogique.objects.create(
            formation=cls.formation, participant=cls.participant,
            moyenne_generale=15, taux_presence=90,
            decision=DecisionPedagogique.TypeDecision.ADMIS,
            mention=DecisionPedagogique.Mention.BIEN,
            appreciation='Travail régulier.',
        )
        cls.admin = User.objects.create_superuser('admin_fiche', 'a@example.com', 'MotDePasse#2026')

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def url_auditeur(self, participant=None, formation=None):
        return (
            f'/api/evaluations/auditeurs/{(participant or self.participant).id}'
            f'/formations/{(formation or self.formation).id}/fiche/'
        )

    def url_formateur(self, formateur=None, module=None):
        return (
            f'/api/evaluations/formateurs/{(formateur or self.formateur).id}'
            f'/modules/{(module or self.module).id}/fiche/'
        )


class FicheAuditeurTests(BaseFicheTest):

    def test_contrat_de_la_fiche(self):
        reponse = self.client.get(self.url_auditeur())
        self.assertEqual(reponse.status_code, 200)
        donnees = reponse.json()
        self.assertEqual(donnees['participant_nom'], 'KOUAME Aya')
        self.assertEqual(donnees['formation_libelle'], 'Formation test fiche')
        self.assertEqual(donnees['moyenne_generale'], 15.0)
        self.assertEqual(donnees['classement'], 1)
        self.assertEqual(donnees['classement_sur'], 1)
        module = donnees['suivi_modules'][0]
        for cle in ('id', 'module_intitule', 'nb_epreuves', 'heures_presence',
                    'heures_prevues', 'taux_presence', 'moyenne_module'):
            self.assertIn(cle, module)
        self.assertEqual(module['nb_epreuves'], 3)
        self.assertEqual(module['taux_presence'], 90.0)

    def test_le_verdict_pedagogique_n_est_pas_la_decision_officielle(self):
        donnees = self.client.get(self.url_auditeur()).json()
        verdict = donnees['decision_finale_detail']
        self.assertEqual(verdict['nature'], 'pedagogique')
        self.assertEqual(verdict['decision_display'], 'Admis')
        self.assertEqual(verdict['mention_display'], 'Bien')
        # Aucune décision de jury n'existe : l'écran doit afficher « — », pas
        # recopier le verdict interne.
        self.assertIsNone(donnees['decision_officielle'])

    def test_auditeur_d_une_autre_formation_renvoie_404(self):
        reponse = self.client.get(self.url_auditeur(formation=self.autre_formation))
        self.assertEqual(reponse.status_code, 404)

    def test_auditeur_inconnu_renvoie_404(self):
        self.assertEqual(
            self.client.get('/api/evaluations/auditeurs/999999/formations/%s/fiche/'
                            % self.formation.id).status_code, 404,
        )

    def test_exports_pdf_et_xlsx(self):
        for fmt, mime in (
            ('pdf', 'application/pdf'),
            ('xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
        ):
            with self.subTest(fmt=fmt):
                reponse = self.client.get(self.url_auditeur() + f'export/{fmt}/')
                self.assertEqual(reponse.status_code, 200)
                self.assertEqual(reponse['Content-Type'], mime)
                self.assertGreater(len(reponse.content), 500)
                self.assertIn('attachment;', reponse['Content-Disposition'])

    def test_format_d_export_inconnu_renvoie_404(self):
        self.assertEqual(
            self.client.get(self.url_auditeur() + 'export/docx/').status_code, 404,
        )


class FicheFormateurTests(BaseFicheTest):

    def test_contrat_de_la_fiche(self):
        donnees = self.client.get(self.url_formateur()).json()
        self.assertEqual(donnees['formateur_nom'], 'YAO Serge')
        self.assertEqual(donnees['module_intitule'], 'Déontologie')
        self.assertEqual(donnees['taux_presence'], 90.0)
        # Aucune séance tenue : les heures effectuées valent 0, pas une estimation.
        self.assertEqual(donnees['heures_effectuees'], 0.0)

    def test_heures_effectuees_suivent_les_seances_tenues(self):
        """Une séance de 2 h réellement tenue compte 2 h, pas une estimation."""
        from datetime import timedelta

        from django.utils import timezone

        debut = timezone.now() - timedelta(hours=5)
        SessionModule.objects.create(
            module=self.module, intitule='Séance tenue',
            date_journee=timezone.localdate(), numero=2,
            heure_debut_prevue='08:00', heure_fin_prevue='10:00',
            demarree_le=debut, terminee_le=debut + timedelta(hours=2),
        )
        donnees = self.client.get(self.url_formateur()).json()
        self.assertEqual(donnees['heures_effectuees'], 2.0)

        # Une séance prévue mais non démarrée ne crédite aucune heure.
        SessionModule.objects.create(
            module=self.module, intitule='Séance non tenue',
            date_journee=timezone.localdate(), numero=3,
            heure_debut_prevue='10:00', heure_fin_prevue='12:00',
        )
        self.assertEqual(
            self.client.get(self.url_formateur()).json()['heures_effectuees'], 2.0,
        )

    def test_module_d_un_autre_enseignant_renvoie_404(self):
        autre = Formateur.objects.create(numerobadge='BADGE-FICHE-2', nom='DIALLO', prenom='Awa')
        self.assertEqual(
            self.client.get(self.url_formateur(formateur=autre)).status_code, 404,
        )

    def test_exports(self):
        for fmt in ('pdf', 'xlsx'):
            reponse = self.client.get(self.url_formateur() + f'export/{fmt}/')
            self.assertEqual(reponse.status_code, 200)
            self.assertGreater(len(reponse.content), 500)


class AccesFichesTests(BaseFicheTest):
    """Une fiche contient des notes nominatives : pas d'accès anonyme."""

    def test_anonyme_refuse(self):
        self.client.force_authenticate(None)
        self.assertIn(self.client.get(self.url_auditeur()).status_code, (401, 403))

    def test_role_sans_consultation_refuse(self):
        auditeur = User.objects.create_user('auditeur_fiche', password='MotDePasse#2026')
        self.client.force_authenticate(auditeur)
        self.assertEqual(self.client.get(self.url_auditeur()).status_code, 403)

    def test_enseignant_consulte(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get(self.url_formateur()).status_code, 200)
