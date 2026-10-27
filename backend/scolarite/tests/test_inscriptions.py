from datetime import date, timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from admissions import admission_services, services as admission_workflow_services, workflow
from admissions.models import Admission, Candidat, Candidature, PieceCandidature, TypePiece
from authentication.models import User
from formations.models import Participant, RefCategorie, RefFormation, RefGrade, RefVague
from scolarite import inscription_services
from scolarite.matricules import generer_matricule
from scolarite.models import (
    AnneeAcademique,
    DossierEtudiant,
    InscriptionAdministrative,
    JournalScolarite,
    Niveau,
    RegimeEtudes,
    StatutEtudiant,
)


def make_user(username, role='INJS_ADMIN', **kwargs):
    return User.objects.create_user(username=username, password='pass', role=role, **kwargs)


class ConversionFixture:
    """Un candidat admis, dossier complet, prêt à être inscrit."""

    @classmethod
    def setUpTestData(cls):
        cls.annee = AnneeAcademique.objects.create(
            libelle='2026-2027', date_debut=date(2026, 10, 1), date_fin=date(2027, 9, 30),
            courante=True,
        )
        cls.formation = RefFormation.objects.create(intitule='LICENCE STAPS')
        cls.niveau = Niveau.objects.create(code='L1', libelle='Licence 1', ordre=1)
        cls.niveau_l2 = Niveau.objects.create(code='L2', libelle='Licence 2', ordre=2)
        # Certains référentiels sont pré-remplis par des migrations de données :
        # on les réutilise plutôt que de les recréer.
        cls.categorie, _ = RefCategorie.objects.get_or_create(libelle='A')
        cls.grade, _ = RefGrade.objects.get_or_create(categorie=cls.categorie, libelle='A3')
        cls.vague, _ = RefVague.objects.get_or_create(libelle='PREMIERE VAGUE')
        cls.regime = RegimeEtudes.objects.create(code='INITIAL', libelle='Formation initiale')
        StatutEtudiant.objects.create(code='ACTIF', libelle='Actif')
        TypePiece.objects.create(code='DIPLOME', libelle='Diplôme', obligatoire_par_defaut=True)

    def setUp(self):
        self.acteur = make_user('agent_inscription')
        self.candidat = Candidat.objects.create(
            nom='Traoré', prenom='Fatou', sexe='F', email='fatou@example.ci',
        )
        self.candidature = admission_workflow_services.creer_candidature(
            self.candidat, annee_academique=self.annee, ref_formation=self.formation,
            niveau=self.niveau, regime=self.regime,
        )

    def admettre(self, dossier_complet=True, **champs):
        if dossier_complet:
            for piece in self.candidature.pieces_obligatoires:
                admission_workflow_services.verifier_piece(piece, PieceCandidature.Statut.VALIDEE)
        for statut in (
            Candidature.Statut.SOUMISE,
            Candidature.Statut.EN_ATTENTE_DE_VERIFICATION,
            Candidature.Statut.PIECES_VALIDEES,
            Candidature.Statut.EN_ETUDE,
            Candidature.Statut.ADMISSIBLE,
        ):
            workflow.appliquer_transition(
                self.candidature, statut, acteur=self.acteur, forcer_dossier=not dossier_complet,
            )
        admission = admission_services.creer_admission(
            self.candidature, acteur=self.acteur,
            categorie_id=self.categorie.id, grade_id=self.grade.id, vague_id=self.vague.id,
            **champs,
        )
        admission_services.prononcer_decision(
            admission, Admission.Decision.ADMIS, acteur=self.acteur,
        )
        return admission


class MatriculeTests(ConversionFixture, TestCase):

    def test_format_du_matricule(self):
        self.assertEqual(generer_matricule(self.annee), 'INJS26-0001')

    def test_sequence_incrementale(self):
        Participant.objects.create(matricule='INJS26-0001', nom='A', prenom='B')
        self.assertEqual(generer_matricule(self.annee), 'INJS26-0002')

    def test_sequence_independante_par_annee(self):
        Participant.objects.create(matricule='INJS26-0007', nom='A', prenom='B')
        autre = AnneeAcademique.objects.create(
            libelle='2027-2028', date_debut=date(2027, 10, 1), date_fin=date(2028, 9, 30),
        )
        self.assertEqual(generer_matricule(autre), 'INJS27-0001')

    def test_matricules_importes_ignores(self):
        """Un matricule hors format ne perturbe pas la séquence."""
        Participant.objects.create(matricule='ANCIEN-123', nom='A', prenom='B')
        Participant.objects.create(matricule='45678', nom='C', prenom='D')
        self.assertEqual(generer_matricule(self.annee), 'INJS26-0001')

    def test_collision_evitee(self):
        Participant.objects.create(matricule='INJS26-0001', nom='A', prenom='B')
        Participant.objects.create(matricule='INJS26-0002', nom='C', prenom='D')
        self.assertEqual(generer_matricule(self.annee), 'INJS26-0003')


class ConversionTests(ConversionFixture, TestCase):

    def test_conversion_nominale(self):
        admission = self.admettre()
        inscription = inscription_services.convertir_admission_en_inscription(
            admission, acteur=self.acteur,
        )
        self.assertEqual(inscription.statut, InscriptionAdministrative.Statut.BROUILLON)
        self.assertEqual(inscription.niveau, self.niveau)
        self.assertEqual(inscription.admission, admission)
        self.assertEqual(inscription.regime, self.regime)

    def test_participant_cree_avec_matricule(self):
        admission = self.admettre()
        inscription = inscription_services.convertir_admission_en_inscription(admission)
        participant = inscription.etudiant.participant
        self.assertEqual(participant.matricule, 'INJS26-0001')
        self.assertEqual(participant.nom, 'Traoré')
        self.assertEqual(participant.sexe, 'FEMININ')

    def test_champs_operationnels_synchronises(self):
        """Les écrans existants lisent des champs texte : ils doivent être remplis."""
        admission = self.admettre()
        inscription = inscription_services.convertir_admission_en_inscription(admission)
        participant = inscription.etudiant.participant
        self.assertEqual(participant.categorie, 'A')
        self.assertEqual(participant.grade, 'A3')
        self.assertEqual(participant.vague, 'PREMIERE VAGUE')

    def test_participant_existant_reutilise(self):
        participant = Participant.objects.create(
            matricule='ANCIEN-001', nom='Traoré', prenom='Fatou', categorie='B',
        )
        self.candidat.participant = participant
        self.candidat.save(update_fields=['participant'])

        admission = self.admettre()
        inscription = inscription_services.convertir_admission_en_inscription(admission)
        self.assertEqual(inscription.etudiant.participant, participant)
        self.assertEqual(Participant.objects.count(), 1)

    def test_categorie_existante_non_ecrasee(self):
        participant = Participant.objects.create(
            matricule='ANCIEN-002', nom='Traoré', prenom='Fatou', categorie='B',
        )
        self.candidat.participant = participant
        self.candidat.save(update_fields=['participant'])

        admission = self.admettre()
        inscription_services.convertir_admission_en_inscription(admission)
        participant.refresh_from_db()
        self.assertEqual(participant.categorie, 'B')

    def test_dossier_etudiant_cree_une_seule_fois(self):
        admission = self.admettre()
        inscription = inscription_services.convertir_admission_en_inscription(admission)
        dossier, cree = inscription_services.creer_ou_retrouver_dossier(
            inscription.etudiant.participant,
        )
        self.assertFalse(cree)
        self.assertEqual(dossier, inscription.etudiant)
        self.assertEqual(DossierEtudiant.objects.count(), 1)

    def test_conversion_refusee_si_admission_non_prononcee(self):
        for piece in self.candidature.pieces_obligatoires:
            admission_workflow_services.verifier_piece(piece, PieceCandidature.Statut.VALIDEE)
        for statut in (
            Candidature.Statut.SOUMISE,
            Candidature.Statut.EN_ATTENTE_DE_VERIFICATION,
            Candidature.Statut.PIECES_VALIDEES,
            Candidature.Statut.EN_ETUDE,
            Candidature.Statut.ADMISSIBLE,
        ):
            workflow.appliquer_transition(self.candidature, statut)
        admission = admission_services.creer_admission(self.candidature)

        with self.assertRaises(inscription_services.InscriptionImpossible):
            inscription_services.convertir_admission_en_inscription(admission)

    def test_conversion_refusee_si_admission_expiree(self):
        admission = self.admettre()
        admission.date_limite_inscription = timezone.localdate() - timedelta(days=1)
        admission.save(update_fields=['date_limite_inscription'])
        with self.assertRaises(inscription_services.InscriptionImpossible):
            inscription_services.convertir_admission_en_inscription(admission)

    def test_conversion_refusee_si_dossier_incomplet(self):
        admission = self.admettre(dossier_complet=False)
        with self.assertRaises(inscription_services.InscriptionImpossible):
            inscription_services.convertir_admission_en_inscription(admission)

    def test_conversion_atomique(self):
        """Un échec en fin de conversion ne doit laisser ni participant ni dossier."""
        admission = self.admettre()
        with self.assertRaises(Exception):
            inscription_services.convertir_admission_en_inscription(
                admission, niveau_id=999999,
            )
        self.assertEqual(Participant.objects.count(), 0)
        self.assertEqual(DossierEtudiant.objects.count(), 0)
        self.assertEqual(InscriptionAdministrative.objects.count(), 0)

    def test_conversion_avec_validation_immediate(self):
        admission = self.admettre()
        inscription = inscription_services.convertir_admission_en_inscription(
            admission, acteur=self.acteur, valider=True,
        )
        self.assertEqual(inscription.statut, InscriptionAdministrative.Statut.VALIDEE)
        self.assertIsNotNone(inscription.date_validation)
        self.assertEqual(inscription.valide_par, self.acteur)

    def test_conversion_journalisee(self):
        admission = self.admettre()
        inscription_services.convertir_admission_en_inscription(admission, acteur=self.acteur)
        self.assertTrue(
            JournalScolarite.objects.filter(
                action=JournalScolarite.Action.MATRICULE_GENERE,
            ).exists()
        )
        self.assertTrue(
            JournalScolarite.objects.filter(
                action=JournalScolarite.Action.INSCRIPTION_CREEE,
            ).exists()
        )


class TransitionInscriptionTests(ConversionFixture, TestCase):

    def setUp(self):
        super().setUp()
        self.inscription = inscription_services.convertir_admission_en_inscription(
            self.admettre(), acteur=self.acteur,
        )

    def valider(self):
        for statut in (
            InscriptionAdministrative.Statut.EN_ATTENTE,
            InscriptionAdministrative.Statut.A_VALIDER,
            InscriptionAdministrative.Statut.VALIDEE,
        ):
            inscription_services.appliquer_transition(self.inscription, statut, acteur=self.acteur)

    def test_parcours_de_validation(self):
        self.valider()
        self.assertTrue(self.inscription.est_valide)

    def test_transition_interdite(self):
        with self.assertRaises(inscription_services.InscriptionImpossible):
            inscription_services.appliquer_transition(
                self.inscription, InscriptionAdministrative.Statut.VALIDEE,
            )

    def test_suspension_et_reprise(self):
        self.valider()
        inscription_services.appliquer_transition(
            self.inscription, InscriptionAdministrative.Statut.SUSPENDUE,
        )
        inscription_services.appliquer_transition(
            self.inscription, InscriptionAdministrative.Statut.VALIDEE,
        )
        self.assertTrue(self.inscription.est_valide)

    def test_statut_annule_terminal(self):
        inscription_services.appliquer_transition(
            self.inscription, InscriptionAdministrative.Statut.ANNULEE,
        )
        self.assertEqual(inscription_services.transitions_possibles(self.inscription), [])

    def test_pas_deux_inscriptions_validees_identiques(self):
        self.valider()
        doublon = InscriptionAdministrative.objects.create(
            etudiant=self.inscription.etudiant,
            annee_academique=self.annee,
            ref_formation=self.formation,
            niveau=self.niveau,
        )
        inscription_services.appliquer_transition(
            doublon, InscriptionAdministrative.Statut.EN_ATTENTE,
        )
        inscription_services.appliquer_transition(
            doublon, InscriptionAdministrative.Statut.A_VALIDER,
        )
        with self.assertRaises(inscription_services.InscriptionImpossible):
            inscription_services.appliquer_transition(
                doublon, InscriptionAdministrative.Statut.VALIDEE,
            )

    def test_inscription_validee_sur_un_autre_niveau_autorisee(self):
        self.valider()
        suivante = InscriptionAdministrative.objects.create(
            etudiant=self.inscription.etudiant,
            annee_academique=self.annee,
            ref_formation=self.formation,
            niveau=self.niveau_l2,
        )
        for statut in (
            InscriptionAdministrative.Statut.EN_ATTENTE,
            InscriptionAdministrative.Statut.A_VALIDER,
            InscriptionAdministrative.Statut.VALIDEE,
        ):
            inscription_services.appliquer_transition(suivante, statut)
        self.assertTrue(suivante.est_valide)


class InscriptionAPITests(ConversionFixture, TestCase):

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.client.force_authenticate(self.acteur)

    def test_inscription_depuis_admission(self):
        admission = self.admettre()
        response = self.client.post('/api/scolarite/inscriptions/depuis-admission/', {
            'admission_id': admission.id,
        }, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['matricule'], 'INJS26-0001')
        self.assertEqual(response.json()['statut'], 'BROUILLON')

    def test_inscription_immediatement_validee(self):
        admission = self.admettre()
        response = self.client.post('/api/scolarite/inscriptions/depuis-admission/', {
            'admission_id': admission.id, 'valider': True,
        }, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['statut'], 'VALIDEE')

    def test_admission_expiree_renvoie_409(self):
        admission = self.admettre()
        admission.date_limite_inscription = timezone.localdate() - timedelta(days=1)
        admission.save(update_fields=['date_limite_inscription'])
        response = self.client.post('/api/scolarite/inscriptions/depuis-admission/', {
            'admission_id': admission.id,
        }, format='json')
        self.assertEqual(response.status_code, 409)

    def test_admission_inconnue_renvoie_400(self):
        response = self.client.post('/api/scolarite/inscriptions/depuis-admission/', {
            'admission_id': 99999,
        }, format='json')
        self.assertEqual(response.status_code, 400)

    def test_transition_via_api(self):
        admission = self.admettre()
        inscription = inscription_services.convertir_admission_en_inscription(admission)
        response = self.client.post(
            f'/api/scolarite/inscriptions/{inscription.id}/transition/',
            {'statut': 'EN_ATTENTE'}, format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['statut'], 'EN_ATTENTE')

    def test_transition_interdite_renvoie_409(self):
        admission = self.admettre()
        inscription = inscription_services.convertir_admission_en_inscription(admission)
        response = self.client.post(
            f'/api/scolarite/inscriptions/{inscription.id}/transition/',
            {'statut': 'VALIDEE'}, format='json',
        )
        self.assertEqual(response.status_code, 409)

    def test_liste_etudiants_et_recherche(self):
        admission = self.admettre()
        inscription_services.convertir_admission_en_inscription(admission)
        response = self.client.get('/api/scolarite/etudiants/', {'q': 'Traoré'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)

    def test_fiche_etudiant(self):
        admission = self.admettre()
        inscription = inscription_services.convertir_admission_en_inscription(admission)
        response = self.client.get(f'/api/scolarite/etudiants/{inscription.etudiant_id}/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['inscriptions']), 1)

    def test_matricule_non_modifiable_via_api(self):
        admission = self.admettre()
        inscription = inscription_services.convertir_admission_en_inscription(admission)
        response = self.client.patch(
            f'/api/scolarite/etudiants/{inscription.etudiant_id}/',
            {'matricule': 'PIRATE-001', 'observations': 'Note'}, format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['matricule'], 'INJS26-0001')

    def test_statistiques_effectifs(self):
        admission = self.admettre()
        inscription_services.convertir_admission_en_inscription(
            admission, acteur=self.acteur, valider=True,
        )
        response = self.client.get('/api/scolarite/inscriptions/stats/')
        self.assertEqual(response.status_code, 200)
        donnees = response.json()
        self.assertEqual(donnees['inscrits'], 1)
        self.assertEqual(donnees['par_niveau']['L1'], 1)
        self.assertEqual(donnees['par_categorie']['A'], 1)

    def test_role_non_habilite_refuse(self):
        client = APIClient()
        client.force_authenticate(make_user('auditeur_insc', role='AUDITEUR'))
        self.assertEqual(client.get('/api/scolarite/inscriptions/').status_code, 403)
