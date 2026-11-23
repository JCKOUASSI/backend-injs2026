from datetime import date

from django.test import TestCase
from rest_framework.test import APIClient

from admissions import admission_services, services as candidature_services, workflow
from admissions.models import Admission, Candidat, Candidature, PieceCandidature, TypePiece
from authentication.models import User
from formations.models import RefFormation
from scolarite import groupes_services, inscription_services, pedagogie_services
from scolarite.models import (
    AnneeAcademique,
    ECUE,
    Groupe,
    Maquette,
    Niveau,
    Semestre,
    StatutEtudiant,
    UE,
)


def make_user(username, role='INJS_ADMIN', **kwargs):
    return User.objects.create_user(username=username, password='pass', role=role, **kwargs)


class ExportEDTFixture:
    """Deux étudiants inscrits, affectés à un groupe, avec un programme généré."""

    @classmethod
    def setUpTestData(cls):
        cls.annee = AnneeAcademique.objects.create(
            libelle='2026-2027', date_debut=date(2026, 10, 1), date_fin=date(2027, 9, 30),
            courante=True,
        )
        cls.formation = RefFormation.objects.create(intitule='LICENCE STAPS')
        cls.niveau = Niveau.objects.create(code='L1', libelle='Licence 1', ordre=1)
        cls.semestre = Semestre.objects.create(niveau=cls.niveau, numero=1, libelle='S1')
        StatutEtudiant.objects.create(code='ACTIF', libelle='Actif')
        TypePiece.objects.create(code='DIPLOME', libelle='Diplôme', obligatoire_par_defaut=True)

        cls.groupe = Groupe.objects.create(
            annee_academique=cls.annee, ref_formation=cls.formation, niveau=cls.niveau,
            nom='L1-G1', capacite_max=30,
        )
        maquette = Maquette.objects.create(
            annee_academique=cls.annee, ref_formation=cls.formation, niveau=cls.niveau,
        )
        ue = UE.objects.create(
            maquette=maquette, semestre=cls.semestre, code='UE11',
            intitule='Bases scientifiques', credits=6,
        )
        ECUE.objects.create(
            ue=ue, code='ECUE111', intitule='Anatomie', credits=3, volume_cm=20, volume_td=10,
        )
        ECUE.objects.create(
            ue=ue, code='ECUE112', intitule='Pratique', credits=3, volume_tp=30,
        )
        # Lot L1 (R4) : activation après création des UE/ECUE.
        maquette.statut = Maquette.Statut.ACTIVE
        maquette.save()

    def setUp(self):
        self.acteur = make_user('agent_edt')
        self.client = APIClient()
        self.client.force_authenticate(self.acteur)
        self.inscriptions = [self.inscrire('Yao', 'Kouadio'), self.inscrire('Kone', 'Ali')]
        for inscription in self.inscriptions:
            pedagogie_services.generer_inscriptions_pedagogiques(inscription)
            groupes_services.affecter_groupe(inscription, self.groupe)

    def inscrire(self, nom, prenom):
        candidat = Candidat.objects.create(nom=nom, prenom=prenom)
        candidature = candidature_services.creer_candidature(
            candidat, annee_academique=self.annee, ref_formation=self.formation,
            niveau=self.niveau,
        )
        for piece in candidature.pieces_obligatoires:
            candidature_services.verifier_piece(piece, PieceCandidature.Statut.VALIDEE)
        for statut in (
            Candidature.Statut.SOUMISE,
            Candidature.Statut.EN_ATTENTE_DE_VERIFICATION,
            Candidature.Statut.PIECES_VALIDEES,
            Candidature.Statut.EN_ETUDE,
            Candidature.Statut.ADMISSIBLE,
        ):
            workflow.appliquer_transition(candidature, statut)
        admission = admission_services.creer_admission(candidature)
        admission_services.prononcer_decision(admission, Admission.Decision.ADMIS)
        return inscription_services.convertir_admission_en_inscription(
            admission, acteur=self.acteur, valider=True,
        )


class ContratTests(ExportEDTFixture, TestCase):

    def test_description_du_contrat(self):
        response = self.client.get('/api/scolarite/edt/')
        self.assertEqual(response.status_code, 200)
        donnees = response.json()
        self.assertEqual(donnees['version'], '1.1')
        self.assertEqual(donnees['annee_academique']['libelle'], '2026-2027')
        self.assertEqual(donnees['volumetrie']['inscriptions_validees'], 2)

    def test_ressources_publiees(self):
        response = self.client.get('/api/scolarite/edt/')
        self.assertIn('enseignements', response.json()['ressources'])


class GroupesExportTests(ExportEDTFixture, TestCase):

    def test_effectif_reel(self):
        response = self.client.get('/api/scolarite/edt/groupes/')
        self.assertEqual(response.status_code, 200)
        ligne = response.json()['resultats'][0]
        self.assertEqual(ligne['groupe'], 'L1-G1')
        self.assertEqual(ligne['effectif'], 2)
        self.assertEqual(ligne['capacite_max'], 30)

    def test_export_csv(self):
        response = self.client.get('/api/scolarite/edt/groupes/', {'export': 'csv'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/csv', response['Content-Type'])
        self.assertIn('L1-G1', response.content.decode('utf-8'))


class EnseignementsExportTests(ExportEDTFixture, TestCase):

    def test_une_ligne_par_enseignement(self):
        response = self.client.get('/api/scolarite/edt/enseignements/')
        self.assertEqual(response.status_code, 200)
        resultats = response.json()['resultats']
        self.assertEqual(len(resultats), 2)

    def test_effectif_agrege(self):
        response = self.client.get('/api/scolarite/edt/enseignements/')
        anatomie = next(r for r in response.json()['resultats'] if r['ecue_code'] == 'ECUE111')
        self.assertEqual(anatomie['effectif'], 2)
        self.assertEqual(anatomie['groupe'], 'L1-G1')

    def test_volumes_horaires_publies(self):
        response = self.client.get('/api/scolarite/edt/enseignements/')
        anatomie = next(r for r in response.json()['resultats'] if r['ecue_code'] == 'ECUE111')
        self.assertEqual(anatomie['volume_cm'], 20)
        self.assertEqual(anatomie['volume_td'], 10)
        self.assertEqual(anatomie['volume_total'], 30)

    def test_filtre_par_niveau(self):
        response = self.client.get('/api/scolarite/edt/enseignements/', {'niveau_id': self.niveau.id})
        self.assertEqual(len(response.json()['resultats']), 2)

    def test_filtre_sans_correspondance(self):
        autre = Niveau.objects.create(code='L3', libelle='Licence 3', ordre=3)
        response = self.client.get('/api/scolarite/edt/enseignements/', {'niveau_id': autre.id})
        self.assertEqual(response.json()['resultats'], [])

    def test_export_csv(self):
        response = self.client.get('/api/scolarite/edt/enseignements/', {'export': 'csv'})
        contenu = response.content.decode('utf-8')
        self.assertIn('ecue_code', contenu)
        self.assertIn('ECUE111', contenu)


class EtudiantsExportTests(ExportEDTFixture, TestCase):

    def test_liste_nominative(self):
        response = self.client.get('/api/scolarite/edt/etudiants/')
        self.assertEqual(response.status_code, 200)
        resultats = response.json()['resultats']
        self.assertEqual(len(resultats), 2)
        self.assertTrue(all(ligne['groupe'] == 'L1-G1' for ligne in resultats))

    def test_filtre_par_groupe(self):
        response = self.client.get('/api/scolarite/edt/etudiants/', {'groupe_id': self.groupe.id})
        self.assertEqual(len(response.json()['resultats']), 2)

    def test_inscription_non_validee_exclue(self):
        inscription = self.inscriptions[0]
        inscription.statut = inscription.Statut.SUSPENDUE
        inscription.save(update_fields=['statut'])
        response = self.client.get('/api/scolarite/edt/etudiants/')
        self.assertEqual(len(response.json()['resultats']), 1)

    def test_export_csv(self):
        response = self.client.get('/api/scolarite/edt/etudiants/', {'export': 'csv'})
        self.assertIn('matricule', response.content.decode('utf-8'))


class AccesTests(ExportEDTFixture, TestCase):

    def test_acces_anonyme_refuse(self):
        self.assertEqual(APIClient().get('/api/scolarite/edt/').status_code, 401)

    def test_role_non_habilite_refuse(self):
        client = APIClient()
        client.force_authenticate(make_user('auditeur_edt', role='AUDITEUR'))
        self.assertEqual(client.get('/api/scolarite/edt/').status_code, 403)

    def test_contrat_en_lecture_seule(self):
        """Le contrat n'expose aucune écriture."""
        for url in (
            '/api/scolarite/edt/',
            '/api/scolarite/edt/groupes/',
            '/api/scolarite/edt/enseignements/',
            '/api/scolarite/edt/etudiants/',
        ):
            self.assertEqual(self.client.post(url, {}, format='json').status_code, 405)
