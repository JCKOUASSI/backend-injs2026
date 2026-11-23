"""Test transverse : le parcours complet, de la candidature à l'emploi du temps.

Vérifie l'enchaînement réel des lots et, surtout, que l'existant n'est pas
touché : les modules opérationnels, les présences et les inscriptions saisies
manuellement restent intacts.
"""

from datetime import date, timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from admissions import admission_services, services as candidature_services, workflow
from admissions.models import Admission, Candidat, Candidature, PieceCandidature, TypePiece
from authentication.models import User
from formations.models import (
    Formation,
    Module,
    ModuleParticipant,
    Participant,
    RefCategorie,
    RefFormation,
    RefGrade,
    RefModule,
)
from scolarite import (
    groupes_services,
    inscription_services,
    passerelle_services,
    pedagogie_services,
)
from scolarite.models import (
    AnneeAcademique,
    DossierEtudiant,
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


class ParcoursCompletTests(TestCase):
    """Un candidat traverse toute la chaîne, jusqu'à apparaître dans l'export EDT."""

    @classmethod
    def setUpTestData(cls):
        cls.annee = AnneeAcademique.objects.create(
            libelle='2026-2027', date_debut=date(2026, 10, 1), date_fin=date(2027, 9, 30),
            courante=True,
        )
        cls.annee_suivante = AnneeAcademique.objects.create(
            libelle='2027-2028', date_debut=date(2027, 10, 1), date_fin=date(2028, 9, 30),
        )
        cls.ref_formation = RefFormation.objects.create(intitule='LICENCE STAPS')
        cls.l1 = Niveau.objects.create(code='L1', libelle='Licence 1', ordre=1)
        cls.l2 = Niveau.objects.create(code='L2', libelle='Licence 2', ordre=2)
        cls.s1 = Semestre.objects.create(niveau=cls.l1, numero=1, libelle='S1')
        cls.parcours = Parcours.objects.create(
            ref_formation=cls.ref_formation, code='EM', intitule='Éducation et Motricité',
        )
        cls.categorie, _ = RefCategorie.objects.get_or_create(libelle='A')
        cls.grade, _ = RefGrade.objects.get_or_create(categorie=cls.categorie, libelle='A3')
        StatutEtudiant.objects.create(code='ACTIF', libelle='Actif')
        TypePiece.objects.create(code='DIPLOME', libelle='Diplôme', obligatoire_par_defaut=True)
        TypePiece.objects.create(code='CV', libelle='CV', obligatoire_par_defaut=False)

        cls.groupe = Groupe.objects.create(
            annee_academique=cls.annee, ref_formation=cls.ref_formation, niveau=cls.l1,
            nom='L1-G1', capacite_max=25,
        )

        maquette = Maquette.objects.create(
            annee_academique=cls.annee, ref_formation=cls.ref_formation, niveau=cls.l1,
        )
        ue = UE.objects.create(
            maquette=maquette, semestre=cls.s1, code='UE11', intitule='Bases', credits=6,
        )
        cls.ref_module = RefModule.objects.create(intitule='ANATOMIE')
        cls.ecue = ECUE.objects.create(
            ue=ue, code='ECUE111', intitule='Anatomie', credits=6,
            volume_cm=30, ref_module=cls.ref_module,
        )
        # Lot L1 (R4) : activation après création des UE/ECUE.
        maquette.statut = Maquette.Statut.ACTIVE
        maquette.save()

        # Existant opérationnel, antérieur au module Scolarité.
        cls.formation_operationnelle = Formation.objects.create(formation='LICENCE STAPS 2026')
        cls.module = Module.objects.create(
            formation=cls.formation_operationnelle, intitule='Anatomie fonctionnelle',
            ref_module=cls.ref_module,
        )
        cls.participant_historique = Participant.objects.create(
            matricule='ANCIEN-0001', nom='Historique', prenom='Étudiant', categorie='B',
        )
        cls.inscription_historique = ModuleParticipant.objects.create(
            module=cls.module, participant=cls.participant_historique,
        )

    def setUp(self):
        self.acteur = User.objects.create_user(
            username='scolarite', password='pass', role='INJS_ADMIN',
        )
        self.client = APIClient()
        self.client.force_authenticate(self.acteur)

    def test_parcours_complet(self):
        # 1. Candidature et dépôt du dossier.
        candidat = Candidat.objects.create(
            nom='Traoré', prenom='Fatou', sexe='F', email='fatou@example.ci',
        )
        candidature = candidature_services.creer_candidature(
            candidat, acteur=self.acteur, annee_academique=self.annee,
            ref_formation=self.ref_formation, parcours=self.parcours, niveau=self.l1,
        )
        self.assertEqual(candidature.numero, 'CAND-2026-2027-0001')
        self.assertEqual(candidature.pieces.count(), 2)
        self.assertFalse(candidature.dossier_complet)

        # 2. Vérification des pièces, puis instruction du dossier.
        for piece in candidature.pieces_obligatoires:
            candidature_services.verifier_piece(
                piece, PieceCandidature.Statut.VALIDEE, acteur=self.acteur,
            )
        self.assertTrue(candidature.dossier_complet)

        for statut in (
            Candidature.Statut.SOUMISE,
            Candidature.Statut.EN_ATTENTE_DE_VERIFICATION,
            Candidature.Statut.PIECES_VALIDEES,
            Candidature.Statut.EN_ETUDE,
            Candidature.Statut.ADMISSIBLE,
        ):
            workflow.appliquer_transition(candidature, statut, acteur=self.acteur)

        # 3. Admission et décision.
        admission = admission_services.creer_admission(
            candidature, acteur=self.acteur,
            categorie_id=self.categorie.id, grade_id=self.grade.id,
        )
        admission_services.prononcer_decision(
            admission, Admission.Decision.ADMIS, acteur=self.acteur,
            reference='DEC-2026-001',
            date_limite=timezone.localdate() + timedelta(days=30),
        )
        candidature.refresh_from_db()
        self.assertEqual(candidature.statut, Candidature.Statut.ADMIS)
        self.assertTrue(admission.permet_inscription)

        # 4. Conversion en étudiant inscrit.
        inscription = inscription_services.convertir_admission_en_inscription(
            admission, acteur=self.acteur, valider=True,
        )
        etudiant = inscription.etudiant
        self.assertEqual(etudiant.matricule, 'INJS26-0001')
        self.assertTrue(inscription.est_valide)
        self.assertEqual(etudiant.participant.categorie, 'A')

        # 5. Programme pédagogique et affectation de groupe.
        creees = pedagogie_services.generer_inscriptions_pedagogiques(
            inscription, acteur=self.acteur,
        )
        self.assertEqual(len(creees), 1)
        groupes_services.affecter_groupe(inscription, self.groupe, acteur=self.acteur)
        self.assertEqual(
            inscription.inscriptions_pedagogiques.first().groupe, self.groupe,
        )

        # 6. Passerelle vers le module opérationnel.
        resultat = passerelle_services.synchroniser(
            inscription, self.formation_operationnelle, acteur=self.acteur,
        )
        self.assertEqual(resultat['creees'], 1)
        self.assertTrue(
            ModuleParticipant.objects.filter(
                module=self.module, participant=etudiant.participant,
            ).exists()
        )

        # 7. L'étudiant apparaît dans le contrat de données de l'emploi du temps.
        enseignements = self.client.get('/api/scolarite/edt/enseignements/').json()['resultats']
        self.assertEqual(len(enseignements), 1)
        self.assertEqual(enseignements[0]['effectif'], 1)
        self.assertEqual(enseignements[0]['groupe'], 'L1-G1')

        etudiants = self.client.get('/api/scolarite/edt/etudiants/').json()['resultats']
        self.assertEqual([e['matricule'] for e in etudiants], ['INJS26-0001'])

        # 8. Réinscription l'année suivante : même dossier, même matricule.
        suivante = groupes_services.reinscrire(
            etudiant, self.annee_suivante, self.l2, acteur=self.acteur, valider=True,
        )
        etudiant.refresh_from_db()
        self.assertEqual(etudiant.matricule, 'INJS26-0001')
        self.assertEqual(DossierEtudiant.objects.count(), 1)
        self.assertEqual(etudiant.inscriptions.count(), 2)
        self.assertEqual(suivante.niveau, self.l2)
        self.assertTrue(
            EvenementScolarite.objects.filter(
                type_evenement=EvenementScolarite.Type.PASSAGE,
            ).exists()
        )

        # 9. Chaque étape sensible a laissé une trace.
        actions = set(JournalScolarite.objects.values_list('action', flat=True))
        for attendue in (
            JournalScolarite.Action.CANDIDATURE_TRANSITION,
            JournalScolarite.Action.PIECE_VERIFIEE,
            JournalScolarite.Action.ADMISSION_CREEE,
            JournalScolarite.Action.ADMISSION_DECISION,
            JournalScolarite.Action.MATRICULE_GENERE,
            JournalScolarite.Action.INSCRIPTION_CREEE,
            JournalScolarite.Action.INSCRIPTION_PEDAGOGIQUE_GENEREE,
            JournalScolarite.Action.GROUPE_AFFECTATION,
            JournalScolarite.Action.SYNCHRONISATION_EDT,
            JournalScolarite.Action.REINSCRIPTION,
        ):
            self.assertIn(attendue, actions, f'Action non journalisée : {attendue}')

    def test_l_existant_operationnel_reste_intact(self):
        """Le parcours LMD n'altère ni les modules, ni les inscriptions préexistantes."""
        intitule_module = self.module.intitule
        participants_avant = ModuleParticipant.objects.count()

        candidat = Candidat.objects.create(nom='Kone', prenom='Ali')
        candidature = candidature_services.creer_candidature(
            candidat, annee_academique=self.annee, ref_formation=self.ref_formation,
            niveau=self.l1,
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
        inscription = inscription_services.convertir_admission_en_inscription(
            admission, valider=True,
        )
        pedagogie_services.generer_inscriptions_pedagogiques(inscription)
        passerelle_services.synchroniser(inscription, self.formation_operationnelle)

        # Le module n'a pas bougé.
        self.module.refresh_from_db()
        self.assertEqual(self.module.intitule, intitule_module)

        # L'inscription historique est toujours là, à l'identique.
        self.assertTrue(
            ModuleParticipant.objects.filter(pk=self.inscription_historique.pk).exists()
        )
        self.participant_historique.refresh_from_db()
        self.assertEqual(self.participant_historique.categorie, 'B')
        self.assertEqual(self.participant_historique.matricule, 'ANCIEN-0001')

        # Une seule ligne a été ajoutée, aucune supprimée.
        self.assertEqual(ModuleParticipant.objects.count(), participants_avant + 1)

    def test_le_matricule_importe_n_est_jamais_regenere(self):
        """Un étudiant déjà connu conserve son matricule d'origine."""
        candidat = Candidat.objects.create(nom='Historique', prenom='Étudiant')
        candidat.participant = self.participant_historique
        candidat.save(update_fields=['participant'])

        candidature = candidature_services.creer_candidature(
            candidat, annee_academique=self.annee, ref_formation=self.ref_formation,
            niveau=self.l1,
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
        inscription = inscription_services.convertir_admission_en_inscription(admission)

        self.assertEqual(inscription.etudiant.matricule, 'ANCIEN-0001')
        self.assertEqual(Participant.objects.count(), 1)

    def test_un_dossier_incomplet_bloque_toute_la_chaine(self):
        candidat = Candidat.objects.create(nom='Incomplet', prenom='Dossier')
        candidature = candidature_services.creer_candidature(
            candidat, annee_academique=self.annee, ref_formation=self.ref_formation,
            niveau=self.l1,
        )
        workflow.appliquer_transition(candidature, Candidature.Statut.SOUMISE)
        workflow.appliquer_transition(
            candidature, Candidature.Statut.EN_ATTENTE_DE_VERIFICATION,
        )
        with self.assertRaises(workflow.TransitionInterdite):
            workflow.appliquer_transition(candidature, Candidature.Statut.PIECES_VALIDEES)
        self.assertEqual(InscriptionAdministrative.objects.count(), 0)
