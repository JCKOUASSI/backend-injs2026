from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from admissions import admission_services, services, workflow
from admissions.models import Admission, Candidat, Candidature, PieceCandidature, TypePiece
from authentication.models import User
from formations.models import RefCategorie, RefFormation, RefGrade
from scolarite.models import AnneeAcademique, JournalScolarite, Niveau


def make_user(username, role='INJS_ADMIN', **kwargs):
    return User.objects.create_user(username=username, password='pass', role=role, **kwargs)


class AdmissionFixture:

    @classmethod
    def setUpTestData(cls):
        cls.annee = AnneeAcademique.objects.create(
            libelle='2026-2027', date_debut=date(2026, 10, 1), date_fin=date(2027, 9, 30),
            courante=True,
        )
        cls.formation = RefFormation.objects.create(intitule='LICENCE STAPS')
        cls.niveau = Niveau.objects.create(code='L1', libelle='Licence 1', ordre=1)
        cls.niveau_superieur = Niveau.objects.create(code='L2', libelle='Licence 2', ordre=2)
        cls.categorie = RefCategorie.objects.create(libelle='A')
        cls.grade = RefGrade.objects.create(categorie=cls.categorie, libelle='A3')
        cls.autre_categorie = RefCategorie.objects.create(libelle='B')
        TypePiece.objects.create(code='DIPLOME', libelle='Diplôme', obligatoire_par_defaut=True)

    def setUp(self):
        self.acteur = make_user('agent_admission')
        self.candidat = Candidat.objects.create(nom='Koné', prenom='Awa')
        self.candidature = services.creer_candidature(
            self.candidat, annee_academique=self.annee,
            ref_formation=self.formation, niveau=self.niveau,
        )

    def amener_a_admissible(self):
        for piece in self.candidature.pieces_obligatoires:
            services.verifier_piece(piece, PieceCandidature.Statut.VALIDEE)
        for statut in (
            Candidature.Statut.SOUMISE,
            Candidature.Statut.EN_ATTENTE_DE_VERIFICATION,
            Candidature.Statut.PIECES_VALIDEES,
            Candidature.Statut.EN_ETUDE,
            Candidature.Statut.ADMISSIBLE,
        ):
            workflow.appliquer_transition(self.candidature, statut, acteur=self.acteur)
        return self.candidature


class CreationAdmissionTests(AdmissionFixture, TestCase):

    def test_creation_refusee_si_candidature_en_brouillon(self):
        with self.assertRaises(admission_services.AdmissionImpossible):
            admission_services.creer_admission(self.candidature)

    def test_creation_depuis_candidature_admissible(self):
        self.amener_a_admissible()
        admission = admission_services.creer_admission(self.candidature, acteur=self.acteur)
        self.assertEqual(admission.decision, Admission.Decision.EN_ATTENTE)
        self.assertEqual(admission.niveau, self.niveau)
        self.assertEqual(admission.candidat, self.candidat)

    def test_caracteristiques_reprises_de_la_candidature(self):
        self.amener_a_admissible()
        admission = admission_services.creer_admission(self.candidature)
        self.assertEqual(admission.annee_academique, self.annee)
        self.assertEqual(admission.ref_formation, self.formation)

    def test_surcharge_du_niveau_d_entree(self):
        self.amener_a_admissible()
        admission = admission_services.creer_admission(
            self.candidature, niveau_id=self.niveau_superieur.id,
        )
        self.assertEqual(admission.niveau, self.niveau_superieur)

    def test_une_seule_admission_par_candidature(self):
        self.amener_a_admissible()
        admission_services.creer_admission(self.candidature)
        self.candidature.refresh_from_db()
        with self.assertRaises(admission_services.AdmissionImpossible):
            admission_services.creer_admission(self.candidature)

    def test_grade_incoherent_avec_la_categorie(self):
        self.amener_a_admissible()
        with self.assertRaises(ValidationError):
            admission_services.creer_admission(
                self.candidature,
                categorie_id=self.autre_categorie.id,
                grade_id=self.grade.id,
            )

    def test_creation_journalisee(self):
        self.amener_a_admissible()
        admission_services.creer_admission(self.candidature, acteur=self.acteur)
        self.assertTrue(
            JournalScolarite.objects.filter(
                action=JournalScolarite.Action.ADMISSION_CREEE,
            ).exists()
        )


class DecisionAdmissionTests(AdmissionFixture, TestCase):

    def setUp(self):
        super().setUp()
        self.amener_a_admissible()
        self.admission = admission_services.creer_admission(self.candidature, acteur=self.acteur)

    def test_decision_admis_aligne_la_candidature(self):
        admission_services.prononcer_decision(
            self.admission, Admission.Decision.ADMIS, acteur=self.acteur, reference='DEC-001',
        )
        self.candidature.refresh_from_db()
        self.assertEqual(self.candidature.statut, Candidature.Statut.ADMIS)
        self.assertEqual(self.admission.reference_decision, 'DEC-001')
        self.assertIsNotNone(self.admission.date_decision)
        self.assertEqual(self.admission.decide_par, self.acteur)

    def test_decision_refusee_aligne_la_candidature(self):
        admission_services.prononcer_decision(self.admission, Admission.Decision.REFUSEE)
        self.candidature.refresh_from_db()
        self.assertEqual(self.candidature.statut, Candidature.Statut.REFUSE)

    def test_retour_en_arriere_apres_admission_refuse(self):
        """Un candidat admis ne peut pas être renvoyé en liste d'attente."""
        admission_services.prononcer_decision(self.admission, Admission.Decision.ADMIS)
        with self.assertRaises(workflow.TransitionInterdite):
            admission_services.prononcer_decision(self.admission, Admission.Decision.EN_ATTENTE)

    def test_admis_sous_reserve_peut_devenir_admis(self):
        admission_services.prononcer_decision(self.admission, Admission.Decision.ADMIS_SOUS_RESERVE)
        admission_services.prononcer_decision(self.admission, Admission.Decision.ADMIS)
        self.candidature.refresh_from_db()
        self.assertEqual(self.candidature.statut, Candidature.Statut.ADMIS)

    def test_decision_inconnue_refusee(self):
        with self.assertRaises(admission_services.AdmissionImpossible):
            admission_services.prononcer_decision(self.admission, 'PEUT_ETRE')

    def test_decision_identique_refusee(self):
        admission_services.prononcer_decision(self.admission, Admission.Decision.ADMIS)
        with self.assertRaises(admission_services.AdmissionImpossible):
            admission_services.prononcer_decision(self.admission, Admission.Decision.ADMIS)

    def test_admission_expiree_ne_permet_pas_l_inscription(self):
        admission_services.prononcer_decision(
            self.admission, Admission.Decision.ADMIS,
            date_limite=timezone.localdate() - timedelta(days=1),
        )
        self.assertTrue(self.admission.est_expiree)
        self.assertFalse(self.admission.permet_inscription)

    def test_admission_valide_permet_l_inscription(self):
        admission_services.prononcer_decision(
            self.admission, Admission.Decision.ADMIS,
            date_limite=timezone.localdate() + timedelta(days=30),
        )
        self.assertTrue(self.admission.permet_inscription)

    def test_admis_sous_reserve_permet_l_inscription(self):
        admission_services.prononcer_decision(
            self.admission, Admission.Decision.ADMIS_SOUS_RESERVE,
        )
        self.assertTrue(self.admission.permet_inscription)

    def test_annulation(self):
        admission_services.annuler_admission(self.admission, acteur=self.acteur, motif='Désistement')
        self.candidature.refresh_from_db()
        self.assertEqual(self.admission.decision, Admission.Decision.ANNULEE)
        self.assertEqual(self.candidature.statut, Candidature.Statut.ANNULE)

    def test_double_annulation_refusee(self):
        admission_services.annuler_admission(self.admission)
        with self.assertRaises(admission_services.AdmissionImpossible):
            admission_services.annuler_admission(self.admission)

    def test_decision_journalisee(self):
        admission_services.prononcer_decision(self.admission, Admission.Decision.ADMIS)
        entree = JournalScolarite.objects.filter(
            action=JournalScolarite.Action.ADMISSION_DECISION,
        ).first()
        self.assertEqual(entree.nouvelle_valeur, Admission.Decision.ADMIS)


class AdmissionAPITests(AdmissionFixture, TestCase):

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.client.force_authenticate(self.acteur)

    def test_creation_via_api(self):
        self.amener_a_admissible()
        response = self.client.post('/api/admissions/admissions/', {
            'candidature_id': self.candidature.id,
            'categorie_id': self.categorie.id,
            'grade_id': self.grade.id,
        }, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['decision'], 'EN_ATTENTE')

    def test_creation_refusee_renvoie_409(self):
        response = self.client.post('/api/admissions/admissions/', {
            'candidature_id': self.candidature.id,
        }, format='json')
        self.assertEqual(response.status_code, 409)

    def test_candidature_inconnue_renvoie_400(self):
        response = self.client.post('/api/admissions/admissions/', {
            'candidature_id': 99999,
        }, format='json')
        self.assertEqual(response.status_code, 400)

    def test_decision_via_api(self):
        self.amener_a_admissible()
        admission = admission_services.creer_admission(self.candidature)
        response = self.client.post(
            f'/api/admissions/admissions/{admission.id}/decision/',
            {'decision': 'ADMIS', 'reference_decision': 'DEC-2026-001'}, format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['decision'], 'ADMIS')
        self.assertTrue(response.json()['permet_inscription'])

    def test_annulation_via_api(self):
        self.amener_a_admissible()
        admission = admission_services.creer_admission(self.candidature)
        response = self.client.post(
            f'/api/admissions/admissions/{admission.id}/annuler/',
            {'motif': 'Désistement'}, format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['decision'], 'ANNULEE')

    def test_liste_et_filtre_par_decision(self):
        self.amener_a_admissible()
        admission_services.creer_admission(self.candidature)
        response = self.client.get('/api/admissions/admissions/', {'decision': 'EN_ATTENTE'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)

    def test_statistiques(self):
        self.amener_a_admissible()
        admission_services.creer_admission(self.candidature)
        response = self.client.get('/api/admissions/admissions/stats/')
        self.assertEqual(response.json()['total'], 1)
        self.assertEqual(response.json()['par_decision']['EN_ATTENTE'], 1)

    def test_le_patch_ne_modifie_pas_la_decision(self):
        self.amener_a_admissible()
        admission = admission_services.creer_admission(self.candidature)
        response = self.client.patch(
            f'/api/admissions/admissions/{admission.id}/',
            {'decision': 'ADMIS', 'observations': 'Sous réserve de diplôme'}, format='json',
        )
        self.assertEqual(response.status_code, 200)
        admission.refresh_from_db()
        self.assertEqual(admission.decision, Admission.Decision.EN_ATTENTE)
        self.assertEqual(admission.observations, 'Sous réserve de diplôme')

    def test_role_non_habilite_refuse(self):
        client = APIClient()
        client.force_authenticate(make_user('auditeur_admission', role='AUDITEUR'))
        self.assertEqual(client.get('/api/admissions/admissions/').status_code, 403)
