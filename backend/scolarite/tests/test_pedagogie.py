from datetime import date

from django.test import TestCase
from rest_framework.test import APIClient

from admissions import admission_services, services as candidature_services, workflow
from admissions.models import Admission, Candidat, Candidature, PieceCandidature, TypePiece
from authentication.models import User
from formations.models import RefFormation, RefModule
from scolarite import inscription_services, pedagogie_services
from scolarite.models import (
    AnneeAcademique,
    ECUE,
    Groupe,
    InscriptionAdministrative,
    InscriptionPedagogique,
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


class PedagogieFixture:
    """Un étudiant inscrit et validé, plus une maquette L1 active avec deux semestres."""

    @classmethod
    def setUpTestData(cls):
        cls.annee = AnneeAcademique.objects.create(
            libelle='2026-2027', date_debut=date(2026, 10, 1), date_fin=date(2027, 9, 30),
            courante=True,
        )
        cls.formation = RefFormation.objects.create(intitule='LICENCE STAPS')
        cls.niveau = Niveau.objects.create(code='L1', libelle='Licence 1', ordre=1)
        cls.s1 = Semestre.objects.create(niveau=cls.niveau, numero=1, libelle='S1')
        cls.s2 = Semestre.objects.create(niveau=cls.niveau, numero=2, libelle='S2')
        StatutEtudiant.objects.create(code='ACTIF', libelle='Actif')
        TypePiece.objects.create(code='DIPLOME', libelle='Diplôme', obligatoire_par_defaut=True)

        cls.maquette = Maquette.objects.create(
            annee_academique=cls.annee, ref_formation=cls.formation, niveau=cls.niveau,
        )
        cls.ue_s1 = UE.objects.create(
            maquette=cls.maquette, semestre=cls.s1, code='UE11',
            intitule='Sciences du mouvement', credits=6,
        )
        cls.ue_s2 = UE.objects.create(
            maquette=cls.maquette, semestre=cls.s2, code='UE21',
            intitule='Physiologie', credits=4,
        )
        cls.ref_module = RefModule.objects.create(intitule='ANATOMIE FONCTIONNELLE')
        cls.ecue_cm = ECUE.objects.create(
            ue=cls.ue_s1, code='ECUE111', intitule='Anatomie', credits=3,
            volume_cm=20, volume_td=5, ref_module=cls.ref_module,
        )
        cls.ecue_tp = ECUE.objects.create(
            ue=cls.ue_s1, code='ECUE112', intitule='Pratique sportive', credits=3,
            volume_tp=30,
        )
        cls.ecue_s2 = ECUE.objects.create(
            ue=cls.ue_s2, code='ECUE211', intitule='Physiologie de l’effort', credits=4,
            volume_cm=25,
        )
        # Lot L1 (R4) : activation après création des UE/ECUE.
        cls.maquette.statut = Maquette.Statut.ACTIVE
        cls.maquette.save()

    def setUp(self):
        self.acteur = make_user('agent_pedagogie')
        candidat = Candidat.objects.create(nom='Yao', prenom='Kouadio')
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
        self.inscription = inscription_services.convertir_admission_en_inscription(
            admission, acteur=self.acteur, valider=True,
        )


class GenerationTests(PedagogieFixture, TestCase):

    def test_generation_complete(self):
        creees = pedagogie_services.generer_inscriptions_pedagogiques(
            self.inscription, acteur=self.acteur,
        )
        self.assertEqual(len(creees), 3)
        self.assertEqual(self.inscription.inscriptions_pedagogiques.count(), 3)

    def test_generation_limitee_a_un_semestre(self):
        creees = pedagogie_services.generer_inscriptions_pedagogiques(
            self.inscription, semestre=self.s1, acteur=self.acteur,
        )
        self.assertEqual(len(creees), 2)

    def test_generation_idempotente(self):
        pedagogie_services.generer_inscriptions_pedagogiques(self.inscription)
        creees = pedagogie_services.generer_inscriptions_pedagogiques(self.inscription)
        self.assertEqual(len(creees), 0)
        self.assertEqual(self.inscription.inscriptions_pedagogiques.count(), 3)

    def test_generation_incrementale_apres_evolution_maquette(self):
        pedagogie_services.generer_inscriptions_pedagogiques(self.inscription, semestre=self.s1)
        creees = pedagogie_services.generer_inscriptions_pedagogiques(self.inscription)
        self.assertEqual(len(creees), 1)

    def test_type_enseignement_deduit_des_volumes(self):
        pedagogie_services.generer_inscriptions_pedagogiques(self.inscription)
        cm = self.inscription.inscriptions_pedagogiques.get(ecue=self.ecue_cm)
        tp = self.inscription.inscriptions_pedagogiques.get(ecue=self.ecue_tp)
        self.assertEqual(cm.type_enseignement, InscriptionPedagogique.TypeEnseignement.CM)
        self.assertEqual(tp.type_enseignement, InscriptionPedagogique.TypeEnseignement.TP)

    def test_credits_et_volumes_repris(self):
        pedagogie_services.generer_inscriptions_pedagogiques(self.inscription)
        ligne = self.inscription.inscriptions_pedagogiques.get(ecue=self.ecue_cm)
        self.assertEqual(ligne.credits, 3)
        self.assertEqual(ligne.volume_horaire, 25)

    def test_generation_refusee_si_inscription_non_validee(self):
        self.inscription.statut = InscriptionAdministrative.Statut.BROUILLON
        self.inscription.save(update_fields=['statut'])
        with self.assertRaises(pedagogie_services.PedagogieImpossible):
            pedagogie_services.generer_inscriptions_pedagogiques(self.inscription)

    def test_generation_refusee_sans_maquette_active(self):
        # Lot L1 (R4) : une maquette ACTIVE ne peut pas revenir en BROUILLON ;
        # on l'archive (transition autorisée) → plus aucune maquette ACTIVE.
        self.maquette.statut = Maquette.Statut.ARCHIVEE
        self.maquette.save(update_fields=['statut'])
        with self.assertRaises(pedagogie_services.PedagogieImpossible):
            pedagogie_services.generer_inscriptions_pedagogiques(self.inscription)

    def test_maquette_du_parcours_prioritaire(self):
        parcours = Parcours.objects.create(
            ref_formation=self.formation, code='EM', intitule='Éducation et Motricité',
        )
        maquette_parcours = Maquette.objects.create(
            annee_academique=self.annee, ref_formation=self.formation, niveau=self.niveau,
            parcours=parcours,
        )
        ue = UE.objects.create(
            maquette=maquette_parcours, semestre=self.s1, code='UE11EM',
            intitule='Spécialité EM', credits=6,
        )
        ECUE.objects.create(ue=ue, code='ECUE-EM', intitule='Didactique', credits=6, volume_cm=30)
        # Lot L1 (R4) : activation après création des UE/ECUE.
        maquette_parcours.statut = Maquette.Statut.ACTIVE
        maquette_parcours.save()

        self.inscription.parcours = parcours
        self.inscription.save(update_fields=['parcours'])

        creees = pedagogie_services.generer_inscriptions_pedagogiques(self.inscription)
        self.assertEqual(len(creees), 1)
        self.assertEqual(creees[0].ecue.code, 'ECUE-EM')

    def test_generation_journalisee(self):
        pedagogie_services.generer_inscriptions_pedagogiques(self.inscription, acteur=self.acteur)
        entree = JournalScolarite.objects.filter(
            action=JournalScolarite.Action.INSCRIPTION_PEDAGOGIQUE_GENEREE,
        ).first()
        self.assertEqual(entree.nouvelle_valeur, '3')


class AjoutManuelTests(PedagogieFixture, TestCase):

    def test_ajout_manuel(self):
        ligne = pedagogie_services.ajouter_ecue(
            self.inscription, self.ecue_cm, acteur=self.acteur, motif='Dérogation',
        )
        self.assertEqual(ligne.origine, InscriptionPedagogique.Origine.MANUELLE)

    def test_ajout_en_double_refuse(self):
        pedagogie_services.ajouter_ecue(self.inscription, self.ecue_cm)
        with self.assertRaises(pedagogie_services.PedagogieImpossible):
            pedagogie_services.ajouter_ecue(self.inscription, self.ecue_cm)

    def test_ecue_hors_maquette_refusee(self):
        autre_maquette = Maquette.objects.create(
            annee_academique=self.annee, ref_formation=self.formation, niveau=self.niveau,
            version=2, statut=Maquette.Statut.BROUILLON,
        )
        ue = UE.objects.create(
            maquette=autre_maquette, semestre=self.s1, code='UEX', intitule='Hors maquette',
        )
        ecue = ECUE.objects.create(ue=ue, code='ECUEX', intitule='Intruse')
        with self.assertRaises(pedagogie_services.PedagogieImpossible):
            pedagogie_services.ajouter_ecue(self.inscription, ecue)

    def test_retrait_historise(self):
        ligne = pedagogie_services.ajouter_ecue(self.inscription, self.ecue_cm)
        pedagogie_services.retirer_ecue(ligne, acteur=self.acteur, motif='Erreur de saisie')
        self.assertEqual(self.inscription.inscriptions_pedagogiques.count(), 0)
        self.assertTrue(
            JournalScolarite.objects.filter(
                action=JournalScolarite.Action.INSCRIPTION_PEDAGOGIQUE_MANUELLE,
                nouvelle_valeur__startswith='RETRAIT',
            ).exists()
        )

    def test_recapitulatif(self):
        pedagogie_services.generer_inscriptions_pedagogiques(self.inscription)
        recap = pedagogie_services.recapitulatif(self.inscription)
        self.assertEqual(recap['total_ecues'], 3)
        self.assertEqual(recap['total_credits'], 10)
        self.assertEqual(recap['par_semestre']['S1']['nb_ecues'], 2)


class GroupeCoherenceTests(PedagogieFixture, TestCase):

    def test_groupe_d_un_autre_niveau_refuse(self):
        autre_niveau = Niveau.objects.create(code='L2', libelle='Licence 2', ordre=2)
        groupe = Groupe.objects.create(
            annee_academique=self.annee, ref_formation=self.formation,
            niveau=autre_niveau, nom='L2-G1',
        )
        with self.assertRaises(Exception):
            pedagogie_services.generer_inscriptions_pedagogiques(
                self.inscription, groupe=groupe,
            )

    def test_groupe_coherent_accepte(self):
        groupe = Groupe.objects.create(
            annee_academique=self.annee, ref_formation=self.formation,
            niveau=self.niveau, nom='L1-G1',
        )
        creees = pedagogie_services.generer_inscriptions_pedagogiques(
            self.inscription, groupe=groupe,
        )
        self.assertEqual(creees[0].groupe, groupe)


class PedagogieAPITests(PedagogieFixture, TestCase):

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.client.force_authenticate(self.acteur)

    def test_generation_via_api(self):
        response = self.client.post(
            f'/api/scolarite/inscriptions/{self.inscription.id}/pedagogie/generer/',
            {}, format='json',
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['creees'], 3)
        self.assertEqual(response.json()['recapitulatif']['total_credits'], 10)

    def test_generation_par_semestre_via_api(self):
        response = self.client.post(
            f'/api/scolarite/inscriptions/{self.inscription.id}/pedagogie/generer/',
            {'semestre_id': self.s1.id}, format='json',
        )
        self.assertEqual(response.json()['creees'], 2)

    def test_generation_refusee_renvoie_409(self):
        self.inscription.statut = InscriptionAdministrative.Statut.BROUILLON
        self.inscription.save(update_fields=['statut'])
        response = self.client.post(
            f'/api/scolarite/inscriptions/{self.inscription.id}/pedagogie/generer/',
            {}, format='json',
        )
        self.assertEqual(response.status_code, 409)

    def test_liste_avec_recapitulatif(self):
        pedagogie_services.generer_inscriptions_pedagogiques(self.inscription)
        response = self.client.get(
            f'/api/scolarite/inscriptions/{self.inscription.id}/pedagogie/',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['lignes']), 3)

    def test_filtre_par_semestre(self):
        pedagogie_services.generer_inscriptions_pedagogiques(self.inscription)
        response = self.client.get(
            f'/api/scolarite/inscriptions/{self.inscription.id}/pedagogie/',
            {'semestre_id': self.s2.id},
        )
        self.assertEqual(len(response.json()['lignes']), 1)

    def test_ajout_manuel_via_api(self):
        response = self.client.post(
            f'/api/scolarite/inscriptions/{self.inscription.id}/pedagogie/ajouter/',
            {'ecue_id': self.ecue_cm.id, 'motif': 'Dérogation'}, format='json',
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['origine'], 'MANUELLE')

    def test_ecue_inconnue_renvoie_400(self):
        response = self.client.post(
            f'/api/scolarite/inscriptions/{self.inscription.id}/pedagogie/ajouter/',
            {'ecue_id': 99999}, format='json',
        )
        self.assertEqual(response.status_code, 400)

    def test_retrait_via_api(self):
        pedagogie_services.generer_inscriptions_pedagogiques(self.inscription)
        ligne = self.inscription.inscriptions_pedagogiques.first()
        response = self.client.delete(f'/api/scolarite/pedagogie/{ligne.id}/')
        self.assertEqual(response.status_code, 204)
        self.assertEqual(self.inscription.inscriptions_pedagogiques.count(), 2)

    def test_role_non_habilite_refuse(self):
        client = APIClient()
        client.force_authenticate(make_user('auditeur_peda', role='AUDITEUR'))
        self.assertEqual(
            client.get(f'/api/scolarite/inscriptions/{self.inscription.id}/pedagogie/').status_code,
            403,
        )
