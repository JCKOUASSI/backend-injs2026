from datetime import date

from django.test import TestCase
from rest_framework.test import APIClient

from admissions import admission_services, services as candidature_services, workflow
from admissions.models import Admission, Candidat, Candidature, PieceCandidature, TypePiece
from authentication.models import User
from formations.models import RefFormation
from scolarite import groupes_services, inscription_services, pedagogie_services
from scolarite.models import (
    AffectationGroupe,
    AnneeAcademique,
    ECUE,
    EvenementScolarite,
    Groupe,
    InscriptionAdministrative,
    JournalScolarite,
    Maquette,
    Niveau,
    Parcours,
    Semestre,
    StatutEtudiant,
    UE,
)


def make_user(username, role='INJS_ADMIN', **kwargs):
    return User.objects.create_user(username=username, password='pass', role=role, **kwargs)


class GroupeFixture:

    @classmethod
    def setUpTestData(cls):
        cls.annee = AnneeAcademique.objects.create(
            libelle='2026-2027', date_debut=date(2026, 10, 1), date_fin=date(2027, 9, 30),
            courante=True,
        )
        cls.annee_suivante = AnneeAcademique.objects.create(
            libelle='2027-2028', date_debut=date(2027, 10, 1), date_fin=date(2028, 9, 30),
        )
        cls.formation = RefFormation.objects.create(intitule='LICENCE STAPS')
        cls.autre_formation = RefFormation.objects.create(intitule='MASTER APAS')
        cls.niveau = Niveau.objects.create(code='L1', libelle='Licence 1', ordre=1)
        cls.niveau_l2 = Niveau.objects.create(code='L2', libelle='Licence 2', ordre=2)
        cls.actif = StatutEtudiant.objects.create(code='ACTIF', libelle='Actif')
        cls.exclu = StatutEtudiant.objects.create(
            code='EXCLU', libelle='Exclu', bloque_inscription=True,
        )
        TypePiece.objects.create(code='DIPLOME', libelle='Diplôme', obligatoire_par_defaut=True)

        cls.groupe_a = Groupe.objects.create(
            annee_academique=cls.annee, ref_formation=cls.formation, niveau=cls.niveau,
            nom='L1-G1', capacite_max=2,
        )
        cls.groupe_b = Groupe.objects.create(
            annee_academique=cls.annee, ref_formation=cls.formation, niveau=cls.niveau,
            nom='L1-G2', capacite_max=2,
        )

    def setUp(self):
        self.acteur = make_user('agent_groupes')
        self.inscription = self.inscrire('Yao', 'Kouadio')

    def inscrire(self, nom, prenom, valider=True):
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
            admission, acteur=self.acteur, valider=valider,
        )


class AffectationTests(GroupeFixture, TestCase):

    def test_affectation_nominale(self):
        affectation = groupes_services.affecter_groupe(
            self.inscription, self.groupe_a, acteur=self.acteur,
        )
        self.assertTrue(affectation.active)
        self.assertEqual(groupes_services.effectif_groupe(self.groupe_a), 1)

    def test_places_restantes(self):
        self.assertEqual(groupes_services.places_restantes(self.groupe_a), 2)
        groupes_services.affecter_groupe(self.inscription, self.groupe_a)
        self.assertEqual(groupes_services.places_restantes(self.groupe_a), 1)

    def test_groupe_sans_capacite_illimite(self):
        groupe = Groupe.objects.create(
            annee_academique=self.annee, ref_formation=self.formation,
            niveau=self.niveau, nom='L1-G3',
        )
        self.assertIsNone(groupes_services.places_restantes(groupe))

    def test_groupe_complet_refuse(self):
        groupes_services.affecter_groupe(self.inscription, self.groupe_a)
        groupes_services.affecter_groupe(self.inscrire('A', 'B'), self.groupe_a)
        with self.assertRaises(groupes_services.AffectationImpossible):
            groupes_services.affecter_groupe(self.inscrire('C', 'D'), self.groupe_a)

    def test_depassement_de_capacite_forcable(self):
        groupes_services.affecter_groupe(self.inscription, self.groupe_a)
        groupes_services.affecter_groupe(self.inscrire('A', 'B'), self.groupe_a)
        affectation = groupes_services.affecter_groupe(
            self.inscrire('C', 'D'), self.groupe_a, ignorer_capacite=True,
        )
        self.assertTrue(affectation.active)

    def test_groupe_d_une_autre_formation_refuse(self):
        groupe = Groupe.objects.create(
            annee_academique=self.annee, ref_formation=self.autre_formation,
            niveau=self.niveau, nom='M1-G1',
        )
        with self.assertRaises(groupes_services.AffectationImpossible):
            groupes_services.affecter_groupe(self.inscription, groupe)

    def test_groupe_d_un_autre_niveau_refuse(self):
        groupe = Groupe.objects.create(
            annee_academique=self.annee, ref_formation=self.formation,
            niveau=self.niveau_l2, nom='L2-G1',
        )
        with self.assertRaises(groupes_services.AffectationImpossible):
            groupes_services.affecter_groupe(self.inscription, groupe)

    def test_groupe_d_une_autre_annee_refuse(self):
        groupe = Groupe.objects.create(
            annee_academique=self.annee_suivante, ref_formation=self.formation,
            niveau=self.niveau, nom='L1-G1-2027',
        )
        with self.assertRaises(groupes_services.AffectationImpossible):
            groupes_services.affecter_groupe(self.inscription, groupe)

    def test_groupe_inactif_refuse(self):
        self.groupe_a.actif = False
        self.groupe_a.save(update_fields=['actif'])
        with self.assertRaises(groupes_services.AffectationImpossible):
            groupes_services.affecter_groupe(self.inscription, self.groupe_a)

    def test_inscription_non_validee_refusee(self):
        inscription = self.inscrire('E', 'F', valider=False)
        with self.assertRaises(groupes_services.AffectationImpossible):
            groupes_services.affecter_groupe(inscription, self.groupe_a)

    def test_reaffectation_au_meme_groupe_refusee(self):
        groupes_services.affecter_groupe(self.inscription, self.groupe_a)
        with self.assertRaises(groupes_services.AffectationImpossible):
            groupes_services.affecter_groupe(self.inscription, self.groupe_a)

    def test_changement_de_groupe_cloture_le_precedent(self):
        groupes_services.affecter_groupe(self.inscription, self.groupe_a)
        groupes_services.affecter_groupe(
            self.inscription, self.groupe_b, acteur=self.acteur, motif='Rééquilibrage',
        )
        affectations = self.inscription.affectations.order_by('id')
        self.assertEqual(affectations.count(), 2)
        self.assertFalse(affectations[0].active)
        self.assertIsNotNone(affectations[0].date_fin)
        self.assertTrue(affectations[1].active)
        self.assertEqual(groupes_services.effectif_groupe(self.groupe_a), 0)

    def test_changement_de_groupe_genere_un_evenement(self):
        groupes_services.affecter_groupe(self.inscription, self.groupe_a)
        groupes_services.affecter_groupe(self.inscription, self.groupe_b, acteur=self.acteur)
        evenement = EvenementScolarite.objects.get(
            type_evenement=EvenementScolarite.Type.CHANGEMENT_GROUPE,
        )
        self.assertEqual(evenement.ancienne_valeur, 'L1-G1')
        self.assertEqual(evenement.nouvelle_valeur, 'L1-G2')

    def test_une_seule_affectation_active(self):
        groupes_services.affecter_groupe(self.inscription, self.groupe_a)
        groupes_services.affecter_groupe(self.inscription, self.groupe_b)
        self.assertEqual(
            AffectationGroupe.objects.filter(inscription=self.inscription, active=True).count(), 1,
        )

    def test_retrait_du_groupe(self):
        groupes_services.affecter_groupe(self.inscription, self.groupe_a)
        groupes_services.retirer_du_groupe(self.inscription, acteur=self.acteur)
        self.assertEqual(groupes_services.effectif_groupe(self.groupe_a), 0)

    def test_retrait_sans_affectation_refuse(self):
        with self.assertRaises(groupes_services.AffectationImpossible):
            groupes_services.retirer_du_groupe(self.inscription)

    def test_affectation_journalisee(self):
        groupes_services.affecter_groupe(self.inscription, self.groupe_a, acteur=self.acteur)
        self.assertTrue(
            JournalScolarite.objects.filter(
                action=JournalScolarite.Action.GROUPE_AFFECTATION,
            ).exists()
        )


class PropagationPedagogiqueTests(GroupeFixture, TestCase):

    def setUp(self):
        super().setUp()
        maquette = Maquette.objects.create(
            annee_academique=self.annee, ref_formation=self.formation, niveau=self.niveau,
        )
        semestre = Semestre.objects.create(niveau=self.niveau, numero=1, libelle='S1')
        ue = UE.objects.create(
            maquette=maquette, semestre=semestre, code='UE11', intitule='Bases', credits=6,
        )
        ECUE.objects.create(ue=ue, code='ECUE111', intitule='Anatomie', credits=6, volume_cm=30)
        # Lot L1 (R4) : activation après création des UE/ECUE.
        maquette.statut = Maquette.Statut.ACTIVE
        maquette.save()
        pedagogie_services.generer_inscriptions_pedagogiques(self.inscription)

    def test_le_groupe_se_propage_aux_inscriptions_pedagogiques(self):
        groupes_services.affecter_groupe(self.inscription, self.groupe_a)
        ligne = self.inscription.inscriptions_pedagogiques.first()
        self.assertEqual(ligne.groupe, self.groupe_a)

    def test_le_changement_de_groupe_se_propage(self):
        groupes_services.affecter_groupe(self.inscription, self.groupe_a)
        groupes_services.affecter_groupe(self.inscription, self.groupe_b)
        ligne = self.inscription.inscriptions_pedagogiques.first()
        self.assertEqual(ligne.groupe, self.groupe_b)

    def test_le_retrait_se_propage(self):
        groupes_services.affecter_groupe(self.inscription, self.groupe_a)
        groupes_services.retirer_du_groupe(self.inscription)
        ligne = self.inscription.inscriptions_pedagogiques.first()
        self.assertIsNone(ligne.groupe)


class RepartitionAutomatiqueTests(GroupeFixture, TestCase):

    def test_repartition_equilibree(self):
        inscriptions = [self.inscription] + [self.inscrire(f'N{i}', 'P') for i in range(3)]
        realisees, echecs = groupes_services.repartir_automatiquement(
            inscriptions, [self.groupe_a, self.groupe_b], acteur=self.acteur,
        )
        self.assertEqual(len(realisees), 4)
        self.assertEqual(echecs, [])
        self.assertEqual(groupes_services.effectif_groupe(self.groupe_a), 2)
        self.assertEqual(groupes_services.effectif_groupe(self.groupe_b), 2)

    def test_echec_signale_quand_les_groupes_sont_pleins(self):
        inscriptions = [self.inscription] + [self.inscrire(f'M{i}', 'P') for i in range(4)]
        realisees, echecs = groupes_services.repartir_automatiquement(
            inscriptions, [self.groupe_a, self.groupe_b],
        )
        self.assertEqual(len(realisees), 4)
        self.assertEqual(len(echecs), 1)


class ReinscriptionTests(GroupeFixture, TestCase):

    def test_reinscription_nominale(self):
        etudiant = self.inscription.etudiant
        suivante = groupes_services.reinscrire(
            etudiant, self.annee_suivante, self.niveau_l2, acteur=self.acteur, valider=True,
        )
        self.assertEqual(suivante.type_inscription, InscriptionAdministrative.Type.REINSCRIPTION)
        self.assertEqual(suivante.niveau, self.niveau_l2)
        self.assertEqual(suivante.ref_formation, self.formation)
        self.assertTrue(suivante.est_valide)

    def test_le_dossier_et_le_matricule_sont_conserves(self):
        etudiant = self.inscription.etudiant
        matricule = etudiant.matricule
        groupes_services.reinscrire(etudiant, self.annee_suivante, self.niveau_l2)
        etudiant.refresh_from_db()
        self.assertEqual(etudiant.matricule, matricule)
        self.assertEqual(etudiant.inscriptions.count(), 2)

    def test_redoublement(self):
        etudiant = self.inscription.etudiant
        suivante = groupes_services.reinscrire(
            etudiant, self.annee_suivante, self.niveau,
            type_inscription=InscriptionAdministrative.Type.REDOUBLEMENT,
        )
        self.assertEqual(suivante.niveau, self.niveau)
        self.assertTrue(
            EvenementScolarite.objects.filter(
                type_evenement=EvenementScolarite.Type.REDOUBLEMENT,
            ).exists()
        )

    def test_evenement_de_passage_enregistre(self):
        groupes_services.reinscrire(
            self.inscription.etudiant, self.annee_suivante, self.niveau_l2,
        )
        evenement = EvenementScolarite.objects.get(
            type_evenement=EvenementScolarite.Type.PASSAGE,
        )
        self.assertEqual(evenement.nouvelle_valeur, '2027-2028 / L2')

    def test_statut_bloquant_refuse_la_reinscription(self):
        etudiant = self.inscription.etudiant
        etudiant.statut = self.exclu
        etudiant.save(update_fields=['statut'])
        with self.assertRaises(groupes_services.ReinscriptionImpossible):
            groupes_services.reinscrire(etudiant, self.annee_suivante, self.niveau_l2)

    def test_reinscription_refusee_sans_inscription_anterieure(self):
        inscription = self.inscrire('Sans', 'Historique', valider=False)
        with self.assertRaises(groupes_services.ReinscriptionImpossible):
            groupes_services.reinscrire(
                inscription.etudiant, self.annee_suivante, self.niveau_l2,
            )

    def test_double_reinscription_refusee(self):
        etudiant = self.inscription.etudiant
        groupes_services.reinscrire(
            etudiant, self.annee_suivante, self.niveau_l2, valider=True,
        )
        with self.assertRaises(groupes_services.ReinscriptionImpossible):
            groupes_services.reinscrire(etudiant, self.annee_suivante, self.niveau_l2)

    def test_reinscription_journalisee(self):
        groupes_services.reinscrire(
            self.inscription.etudiant, self.annee_suivante, self.niveau_l2, acteur=self.acteur,
        )
        self.assertTrue(
            JournalScolarite.objects.filter(
                action=JournalScolarite.Action.REINSCRIPTION,
            ).exists()
        )


class GroupeAPITests(GroupeFixture, TestCase):

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.client.force_authenticate(self.acteur)

    def test_effectifs_des_groupes(self):
        groupes_services.affecter_groupe(self.inscription, self.groupe_a)
        response = self.client.get('/api/scolarite/groupes/effectifs/')
        self.assertEqual(response.status_code, 200)
        groupe = next(g for g in response.json() if g['nom'] == 'L1-G1')
        self.assertEqual(groupe['effectif'], 1)
        self.assertEqual(groupe['places_restantes'], 1)

    def test_affectation_via_api(self):
        response = self.client.post(
            f'/api/scolarite/inscriptions/{self.inscription.id}/affectations/',
            {'groupe_id': self.groupe_a.id}, format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)

    def test_affectation_incompatible_renvoie_409(self):
        groupe = Groupe.objects.create(
            annee_academique=self.annee, ref_formation=self.formation,
            niveau=self.niveau_l2, nom='L2-G9',
        )
        response = self.client.post(
            f'/api/scolarite/inscriptions/{self.inscription.id}/affectations/',
            {'groupe_id': groupe.id}, format='json',
        )
        self.assertEqual(response.status_code, 409)

    def test_historique_des_affectations(self):
        groupes_services.affecter_groupe(self.inscription, self.groupe_a)
        groupes_services.affecter_groupe(self.inscription, self.groupe_b)
        response = self.client.get(
            f'/api/scolarite/inscriptions/{self.inscription.id}/affectations/',
        )
        self.assertEqual(len(response.json()), 2)

    def test_retrait_via_api(self):
        groupes_services.affecter_groupe(self.inscription, self.groupe_a)
        response = self.client.post(
            f'/api/scolarite/inscriptions/{self.inscription.id}/retirer-groupe/',
            {}, format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['active'])

    def test_repartition_via_api(self):
        self.inscrire('Rep', 'Un')
        response = self.client.post('/api/scolarite/groupes/repartition/', {
            'annee_academique_id': self.annee.id,
            'ref_formation_id': self.formation.id,
            'niveau_id': self.niveau.id,
        }, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['affectations'], 2)

    def test_reinscription_via_api(self):
        response = self.client.post('/api/scolarite/reinscriptions/', {
            'etudiant_id': self.inscription.etudiant_id,
            'annee_academique_id': self.annee_suivante.id,
            'niveau_id': self.niveau_l2.id,
            'valider': True,
        }, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['type_inscription'], 'REINSCRIPTION')
        self.assertEqual(response.json()['statut'], 'VALIDEE')

        # Test consultation GET
        get_response = self.client.get('/api/scolarite/reinscriptions/')
        self.assertEqual(get_response.status_code, 200)
        self.assertEqual(len(get_response.json()), 1)
        self.assertEqual(get_response.json()[0]['type_inscription'], 'REINSCRIPTION')

    def test_reinscription_bloquee_renvoie_409(self):
        etudiant = self.inscription.etudiant
        etudiant.statut = self.exclu
        etudiant.save(update_fields=['statut'])
        response = self.client.post('/api/scolarite/reinscriptions/', {
            'etudiant_id': etudiant.id,
            'annee_academique_id': self.annee_suivante.id,
            'niveau_id': self.niveau_l2.id,
        }, format='json')
        self.assertEqual(response.status_code, 409)

    def test_chronologie_des_evenements(self):
        etudiant_id = self.inscription.etudiant_id
        response = self.client.post(
            f'/api/scolarite/etudiants/{etudiant_id}/evenements/',
            {'type_evenement': 'SUSPENSION', 'commentaire': 'Congé maladie'}, format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)
        self.assertEqual(response.json()[0]['type_evenement'], 'SUSPENSION')

    def test_type_d_evenement_inconnu_renvoie_400(self):
        response = self.client.post(
            f'/api/scolarite/etudiants/{self.inscription.etudiant_id}/evenements/',
            {'type_evenement': 'INEXISTANT'}, format='json',
        )
        self.assertEqual(response.status_code, 400)
