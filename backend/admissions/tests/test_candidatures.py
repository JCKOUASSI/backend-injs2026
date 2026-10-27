import tempfile
from datetime import date, timedelta
from io import StringIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db.utils import IntegrityError
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from admissions import services, workflow
from admissions.models import (
    Candidat,
    Candidature,
    PieceCandidature,
    ReglePiece,
    TypePiece,
)
from authentication.models import User
from formations.models import RefFormation
from scolarite.models import AnneeAcademique, JournalScolarite, Niveau, Parcours, TypeFormation


def make_user(username, role='INJS_ADMIN', **kwargs):
    return User.objects.create_user(username=username, password='pass', role=role, **kwargs)


# Les tests qui déposent des fichiers écrivent dans un dossier temporaire,
# jamais dans le MEDIA_ROOT du projet.
media_temporaire = override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix='test-admissions-'))


class AdmissionFixture:
    """Jeu de données minimal : année, formation, niveau, candidat et types de pièces."""

    @classmethod
    def setUpTestData(cls):
        cls.annee = AnneeAcademique.objects.create(
            libelle='2026-2027', date_debut=date(2026, 10, 1), date_fin=date(2027, 9, 30),
            courante=True,
        )
        cls.formation = RefFormation.objects.create(intitule='LICENCE STAPS')
        cls.niveau = Niveau.objects.create(code='L1', libelle='Licence 1', ordre=1)
        cls.candidat = Candidat.objects.create(nom='Kouassi', prenom='Ama', email='ama@example.ci')
        cls.piece_obligatoire = TypePiece.objects.create(
            code='DIPLOME', libelle='Diplôme requis', obligatoire_par_defaut=True,
        )
        cls.piece_facultative = TypePiece.objects.create(
            code='CV', libelle='Curriculum vitae', obligatoire_par_defaut=False,
        )

    def creer_candidature(self, **surcharges):
        champs = {
            'annee_academique': self.annee,
            'ref_formation': self.formation,
            'niveau': self.niveau,
        }
        champs.update(surcharges)
        return services.creer_candidature(self.candidat, **champs)


class NumeroCandidatureTests(AdmissionFixture, TestCase):

    def test_numero_sequentiel_par_annee(self):
        premiere = self.creer_candidature()
        self.assertEqual(premiere.numero, 'CAND-2026-2027-0001')

        autre_candidat = Candidat.objects.create(nom='Diallo', prenom='Moussa')
        deuxieme = services.creer_candidature(
            autre_candidat, annee_academique=self.annee,
            ref_formation=self.formation, niveau=self.niveau,
        )
        self.assertEqual(deuxieme.numero, 'CAND-2026-2027-0002')

    def test_numero_independant_par_annee(self):
        self.creer_candidature()
        autre_annee = AnneeAcademique.objects.create(
            libelle='2027-2028', date_debut=date(2027, 10, 1), date_fin=date(2028, 9, 30),
        )
        candidature = services.creer_candidature(
            self.candidat, annee_academique=autre_annee,
            ref_formation=self.formation, niveau=self.niveau,
        )
        self.assertEqual(candidature.numero, 'CAND-2027-2028-0001')

    def test_pas_deux_candidatures_actives_identiques(self):
        self.creer_candidature()
        with self.assertRaises(IntegrityError):
            Candidature.objects.create(
                candidat=self.candidat, annee_academique=self.annee,
                ref_formation=self.formation, niveau=self.niveau,
            )

    def test_candidature_annulee_libere_la_contrainte(self):
        premiere = self.creer_candidature()
        premiere.statut = Candidature.Statut.ANNULE
        premiere.save(update_fields=['statut'])
        seconde = self.creer_candidature()
        self.assertNotEqual(premiere.pk, seconde.pk)


@media_temporaire
class PiecesTests(AdmissionFixture, TestCase):

    def test_initialisation_des_pieces_attendues(self):
        candidature = self.creer_candidature()
        self.assertEqual(candidature.pieces.count(), 2)
        self.assertEqual(candidature.pieces_obligatoires.count(), 1)

    def test_initialisation_idempotente(self):
        candidature = self.creer_candidature()
        services.initialiser_pieces(candidature)
        self.assertEqual(candidature.pieces.count(), 2)

    def test_regle_specifique_a_la_formation_prime(self):
        ReglePiece.objects.create(
            type_piece=self.piece_facultative, ref_formation=self.formation, obligatoire=True,
        )
        candidature = self.creer_candidature()
        self.assertEqual(candidature.pieces_obligatoires.count(), 2)

    def test_regle_par_type_de_formation(self):
        type_formation = TypeFormation.objects.create(code='LICENCE', libelle='Licence')
        parcours = Parcours.objects.create(
            ref_formation=self.formation, code='EM', intitule='Éducation et Motricité',
            type_formation=type_formation,
        )
        ReglePiece.objects.create(
            type_piece=self.piece_obligatoire, type_formation=type_formation, obligatoire=False,
        )
        candidature = self.creer_candidature(parcours=parcours)
        self.assertEqual(candidature.pieces_obligatoires.count(), 0)

    def test_taux_de_completude(self):
        candidature = self.creer_candidature()
        self.assertEqual(candidature.taux_completude, 0)
        self.assertFalse(candidature.dossier_complet)

        piece = candidature.pieces.get(type_piece=self.piece_obligatoire)
        services.verifier_piece(piece, PieceCandidature.Statut.VALIDEE)
        candidature.refresh_from_db()
        self.assertEqual(candidature.taux_completude, 100)
        self.assertTrue(candidature.dossier_complet)

    def test_depot_place_la_piece_en_verification(self):
        candidature = self.creer_candidature()
        piece = candidature.pieces.first()
        services.deposer_piece(
            piece, fichier=SimpleUploadedFile('diplome.pdf', b'contenu'), numero_document='D-42',
        )
        piece.refresh_from_db()
        self.assertEqual(piece.statut, PieceCandidature.Statut.EN_VERIFICATION)
        self.assertEqual(piece.numero_document, 'D-42')

    def test_piece_expiree_est_detectee(self):
        candidature = self.creer_candidature()
        piece = candidature.pieces.get(type_piece=self.piece_obligatoire)
        piece.statut = PieceCandidature.Statut.VALIDEE
        piece.date_expiration = timezone.localdate() - timedelta(days=1)
        piece.save()

        self.assertEqual(services.rafraichir_pieces_expirees(candidature), 1)
        piece.refresh_from_db()
        self.assertEqual(piece.statut, PieceCandidature.Statut.EXPIREE)

    def test_une_seule_piece_par_type_et_candidature(self):
        candidature = self.creer_candidature()
        with self.assertRaises(IntegrityError):
            PieceCandidature.objects.create(
                candidature=candidature, type_piece=self.piece_obligatoire,
            )


class WorkflowTests(AdmissionFixture, TestCase):

    def setUp(self):
        self.candidature = self.creer_candidature()
        self.acteur = make_user('agent_scolarite')

    def valider_le_dossier(self):
        for piece in self.candidature.pieces_obligatoires:
            services.verifier_piece(piece, PieceCandidature.Statut.VALIDEE)

    def test_transition_nominale(self):
        workflow.appliquer_transition(self.candidature, Candidature.Statut.SOUMISE, acteur=self.acteur)
        self.assertEqual(self.candidature.statut, Candidature.Statut.SOUMISE)

    def test_transition_interdite(self):
        with self.assertRaises(workflow.TransitionInterdite):
            workflow.appliquer_transition(self.candidature, Candidature.Statut.ADMIS)

    def test_transition_vers_le_meme_statut_refusee(self):
        with self.assertRaises(workflow.TransitionInterdite):
            workflow.appliquer_transition(self.candidature, Candidature.Statut.BROUILLON)

    def test_pieces_validees_exige_un_dossier_complet(self):
        workflow.appliquer_transition(self.candidature, Candidature.Statut.SOUMISE)
        workflow.appliquer_transition(self.candidature, Candidature.Statut.EN_ATTENTE_DE_VERIFICATION)
        with self.assertRaises(workflow.TransitionInterdite):
            workflow.appliquer_transition(self.candidature, Candidature.Statut.PIECES_VALIDEES)

    def test_dossier_complet_autorise_la_validation(self):
        self.valider_le_dossier()
        workflow.appliquer_transition(self.candidature, Candidature.Statut.SOUMISE)
        workflow.appliquer_transition(self.candidature, Candidature.Statut.EN_ATTENTE_DE_VERIFICATION)
        workflow.appliquer_transition(self.candidature, Candidature.Statut.PIECES_VALIDEES)
        self.assertEqual(self.candidature.statut, Candidature.Statut.PIECES_VALIDEES)

    def test_forcage_du_dossier_incomplet(self):
        workflow.appliquer_transition(self.candidature, Candidature.Statut.SOUMISE)
        workflow.appliquer_transition(self.candidature, Candidature.Statut.EN_ATTENTE_DE_VERIFICATION)
        workflow.appliquer_transition(
            self.candidature, Candidature.Statut.PIECES_VALIDEES, forcer_dossier=True,
        )
        self.assertEqual(self.candidature.statut, Candidature.Statut.PIECES_VALIDEES)

    def test_decision_horodatee_et_attribuee(self):
        self.valider_le_dossier()
        for statut in (
            Candidature.Statut.SOUMISE,
            Candidature.Statut.EN_ATTENTE_DE_VERIFICATION,
            Candidature.Statut.PIECES_VALIDEES,
            Candidature.Statut.EN_ETUDE,
            Candidature.Statut.ADMISSIBLE,
            Candidature.Statut.ADMIS,
        ):
            workflow.appliquer_transition(self.candidature, statut, acteur=self.acteur)
        self.assertIsNotNone(self.candidature.date_decision)
        self.assertEqual(self.candidature.decide_par, self.acteur)

    def test_statut_annule_est_terminal(self):
        workflow.appliquer_transition(self.candidature, Candidature.Statut.ANNULE)
        self.assertEqual(workflow.transitions_possibles(self.candidature), [])

    def test_transition_journalisee(self):
        workflow.appliquer_transition(self.candidature, Candidature.Statut.SOUMISE, acteur=self.acteur)
        entree = JournalScolarite.objects.filter(
            action=JournalScolarite.Action.CANDIDATURE_TRANSITION,
        ).first()
        self.assertIsNotNone(entree)
        self.assertEqual(entree.ancienne_valeur, Candidature.Statut.BROUILLON)
        self.assertEqual(entree.nouvelle_valeur, Candidature.Statut.SOUMISE)
        self.assertEqual(entree.acteur, self.acteur)


@media_temporaire
class CandidatureAPITests(AdmissionFixture, TestCase):

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(make_user('admin_admissions'))

    def test_creation_candidature(self):
        response = self.client.post('/api/admissions/candidatures/', {
            'candidat_id': self.candidat.id,
            'annee_academique_id': self.annee.id,
            'ref_formation_id': self.formation.id,
            'niveau_id': self.niveau.id,
        }, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['numero'], 'CAND-2026-2027-0001')
        self.assertEqual(len(response.json()['pieces']), 2)

    def test_creation_avec_candidat_inconnu(self):
        response = self.client.post('/api/admissions/candidatures/', {
            'candidat_id': 99999,
            'annee_academique_id': self.annee.id,
            'ref_formation_id': self.formation.id,
            'niveau_id': self.niveau.id,
        }, format='json')
        self.assertEqual(response.status_code, 400)

    def test_liste_et_filtre_par_statut(self):
        self.creer_candidature()
        response = self.client.get('/api/admissions/candidatures/', {'statut': 'BROUILLON'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)

    def test_recherche_par_numero(self):
        candidature = self.creer_candidature()
        response = self.client.get('/api/admissions/candidatures/', {'q': candidature.numero})
        self.assertEqual(len(response.json()), 1)

    def test_transition_via_api(self):
        candidature = self.creer_candidature()
        response = self.client.post(
            f'/api/admissions/candidatures/{candidature.id}/transition/',
            {'statut': 'SOUMISE'}, format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['statut'], 'SOUMISE')

    def test_transition_interdite_renvoie_409(self):
        candidature = self.creer_candidature()
        response = self.client.post(
            f'/api/admissions/candidatures/{candidature.id}/transition/',
            {'statut': 'ADMIS'}, format='json',
        )
        self.assertEqual(response.status_code, 409)

    def test_statut_inconnu_renvoie_400(self):
        candidature = self.creer_candidature()
        response = self.client.post(
            f'/api/admissions/candidatures/{candidature.id}/transition/',
            {'statut': 'INEXISTANT'}, format='json',
        )
        self.assertEqual(response.status_code, 400)

    def test_le_patch_ne_modifie_pas_le_statut(self):
        candidature = self.creer_candidature()
        response = self.client.patch(
            f'/api/admissions/candidatures/{candidature.id}/',
            {'statut': 'ADMIS', 'observations': 'Note interne'}, format='json',
        )
        self.assertEqual(response.status_code, 200)
        candidature.refresh_from_db()
        self.assertEqual(candidature.statut, Candidature.Statut.BROUILLON)
        self.assertEqual(candidature.observations, 'Note interne')

    def test_pieces_et_completude(self):
        candidature = self.creer_candidature()
        response = self.client.get(f'/api/admissions/candidatures/{candidature.id}/pieces/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['pieces_obligatoires'], 1)
        self.assertEqual(response.json()['taux_completude'], 0)

    def test_depot_et_verification_de_piece(self):
        candidature = self.creer_candidature()
        piece = candidature.pieces.get(type_piece=self.piece_obligatoire)

        depot = self.client.post(
            f'/api/admissions/pieces/{piece.id}/deposer/',
            {'fichier': SimpleUploadedFile('diplome.pdf', b'contenu'), 'numero_document': 'D-1'},
            format='multipart',
        )
        self.assertEqual(depot.status_code, 200)
        self.assertEqual(depot.json()['statut'], 'EN_VERIFICATION')

        verification = self.client.post(
            f'/api/admissions/pieces/{piece.id}/verifier/',
            {'statut': 'VALIDEE'}, format='json',
        )
        self.assertEqual(verification.status_code, 200)
        self.assertEqual(verification.json()['statut'], 'VALIDEE')

    def test_telechargement_protege(self):
        candidature = self.creer_candidature()
        piece = candidature.pieces.first()
        services.deposer_piece(piece, fichier=SimpleUploadedFile('cv.pdf', b'contenu'))

        self.assertEqual(
            APIClient().get(f'/api/admissions/pieces/{piece.id}/fichier/').status_code, 401,
        )
        response = self.client.get(f'/api/admissions/pieces/{piece.id}/fichier/')
        self.assertEqual(response.status_code, 200)

    def test_statistiques_par_statut(self):
        self.creer_candidature()
        response = self.client.get('/api/admissions/candidatures/stats/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['total'], 1)
        self.assertEqual(response.json()['par_statut']['BROUILLON'], 1)

    def test_role_non_habilite_refuse(self):
        client = APIClient()
        client.force_authenticate(make_user('auditeur_adm', role='AUDITEUR'))
        self.assertEqual(client.get('/api/admissions/candidatures/').status_code, 403)

    def test_direction_en_lecture_seule(self):
        client = APIClient()
        client.force_authenticate(make_user('direction_adm', role='DIRECTION'))
        self.assertEqual(client.get('/api/admissions/candidatures/').status_code, 200)
        creation = client.post('/api/admissions/candidatures/', {
            'candidat_id': self.candidat.id,
            'annee_academique_id': self.annee.id,
            'ref_formation_id': self.formation.id,
            'niveau_id': self.niveau.id,
        }, format='json')
        self.assertEqual(creation.status_code, 403)


class InitReferentielsAdmissionTests(TestCase):

    def test_creation_et_idempotence(self):
        call_command('init_referentiels_admission', stdout=StringIO())
        total_pieces = TypePiece.objects.count()
        self.assertEqual(total_pieces, 10)

        call_command('init_referentiels_admission', stdout=StringIO())
        self.assertEqual(TypePiece.objects.count(), total_pieces)
