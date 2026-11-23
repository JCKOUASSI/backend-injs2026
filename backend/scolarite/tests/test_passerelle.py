from datetime import date

from django.test import TestCase
from rest_framework.test import APIClient

from admissions import admission_services, services as candidature_services, workflow
from admissions.models import Admission, Candidat, Candidature, PieceCandidature, TypePiece
from authentication.models import User
from formations.models import (
    Formation,
    Module,
    ModuleParticipant,
    RefFormation,
    RefModule,
)
from scolarite import inscription_services, passerelle_services, pedagogie_services
from scolarite.models import (
    AnneeAcademique,
    ECUE,
    InscriptionAdministrative,
    JournalScolarite,
    Maquette,
    Niveau,
    Semestre,
    StatutEtudiant,
    UE,
)


def make_user(username, role='INJS_ADMIN', **kwargs):
    return User.objects.create_user(username=username, password='pass', role=role, **kwargs)


class PasserelleFixture:
    """Un étudiant inscrit avec deux ECUE, dont une seule reliée à un module opérationnel."""

    @classmethod
    def setUpTestData(cls):
        cls.annee = AnneeAcademique.objects.create(
            libelle='2026-2027', date_debut=date(2026, 10, 1), date_fin=date(2027, 9, 30),
            courante=True,
        )
        cls.ref_formation = RefFormation.objects.create(intitule='LICENCE STAPS')
        cls.niveau = Niveau.objects.create(code='L1', libelle='Licence 1', ordre=1)
        cls.semestre = Semestre.objects.create(niveau=cls.niveau, numero=1, libelle='S1')
        StatutEtudiant.objects.create(code='ACTIF', libelle='Actif')
        TypePiece.objects.create(code='DIPLOME', libelle='Diplôme', obligatoire_par_defaut=True)

        cls.ref_anatomie = RefModule.objects.create(intitule='ANATOMIE')
        cls.ref_physio = RefModule.objects.create(intitule='PHYSIOLOGIE')

        cls.maquette = Maquette.objects.create(
            annee_academique=cls.annee, ref_formation=cls.ref_formation, niveau=cls.niveau,
        )
        ue = UE.objects.create(
            maquette=cls.maquette, semestre=cls.semestre, code='UE11',
            intitule='Bases scientifiques', credits=6,
        )
        cls.ecue_reliee = ECUE.objects.create(
            ue=ue, code='ECUE111', intitule='Anatomie', credits=3,
            volume_cm=20, ref_module=cls.ref_anatomie,
        )
        cls.ecue_orpheline = ECUE.objects.create(
            ue=ue, code='ECUE112', intitule='Séminaire libre', credits=3, volume_cm=10,
        )
        # Lot L1 (R4) : activation après création des UE/ECUE.
        cls.maquette.statut = Maquette.Statut.ACTIVE
        cls.maquette.save()

        # Côté opérationnel : une formation existante et son module.
        cls.formation = Formation.objects.create(formation='LICENCE STAPS 2026')
        cls.module_anatomie = Module.objects.create(
            formation=cls.formation, intitule='Anatomie fonctionnelle',
            ref_module=cls.ref_anatomie,
        )
        cls.module_sans_ref = Module.objects.create(
            formation=cls.formation, intitule='Module historique sans référentiel',
        )

    def setUp(self):
        self.acteur = make_user('agent_passerelle')
        self.inscription = self.inscrire('Yao', 'Kouadio')
        pedagogie_services.generer_inscriptions_pedagogiques(self.inscription)

    def inscrire(self, nom, prenom, valider=True):
        candidat = Candidat.objects.create(nom=nom, prenom=prenom)
        candidature = candidature_services.creer_candidature(
            candidat, annee_academique=self.annee, ref_formation=self.ref_formation,
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


class AnalyseTests(PasserelleFixture, TestCase):

    def test_analyse_n_ecrit_rien(self):
        passerelle_services.analyser(self.inscription, self.formation)
        self.assertEqual(ModuleParticipant.objects.count(), 0)

    def test_ecue_reliee_identifiee(self):
        analyse = passerelle_services.analyser(self.inscription, self.formation)
        self.assertEqual(len(analyse['a_creer']), 1)
        self.assertEqual(analyse['a_creer'][0][1], self.module_anatomie)

    def test_ecue_sans_referentiel_signalee(self):
        analyse = passerelle_services.analyser(self.inscription, self.formation)
        self.assertEqual(len(analyse['non_rapprochees']), 1)
        self.assertEqual(analyse['non_rapprochees'][0]['ecue'], 'ECUE112')

    def test_ecue_sans_module_correspondant_signalee(self):
        # Lot L1 (R4) : la maquette étant ACTIVE, l'ECUE ne peut pas être
        # modifiée ; le signalement attendu est porté par le motif de
        # l'ECUE orpheline de la fixture (sans rattachement au référentiel).
        analyse = passerelle_services.analyser(self.inscription, self.formation)
        motifs = [n['motif'] for n in analyse['non_rapprochees']]
        self.assertTrue(any("reliée à aucun module" in motif for motif in motifs))

    def test_ecue_abandonnee_ignoree(self):
        ligne = self.inscription.inscriptions_pedagogiques.get(ecue=self.ecue_reliee)
        ligne.statut = ligne.Statut.ABANDONNEE
        ligne.save(update_fields=['statut'])
        analyse = passerelle_services.analyser(self.inscription, self.formation)
        self.assertEqual(len(analyse['a_creer']), 0)


class SynchronisationTests(PasserelleFixture, TestCase):

    def test_creation_de_l_inscription_module(self):
        resultat = passerelle_services.synchroniser(
            self.inscription, self.formation, acteur=self.acteur,
        )
        self.assertEqual(resultat['creees'], 1)
        self.assertTrue(
            ModuleParticipant.objects.filter(
                module=self.module_anatomie,
                participant=self.inscription.etudiant.participant,
            ).exists()
        )

    def test_lien_retour_enregistre(self):
        passerelle_services.synchroniser(self.inscription, self.formation)
        ligne = self.inscription.inscriptions_pedagogiques.get(ecue=self.ecue_reliee)
        self.assertIsNotNone(ligne.module_participant_id)

    def test_synchronisation_idempotente(self):
        passerelle_services.synchroniser(self.inscription, self.formation)
        resultat = passerelle_services.synchroniser(self.inscription, self.formation)
        self.assertEqual(resultat['creees'], 0)
        self.assertEqual(resultat['existantes'], 1)
        self.assertEqual(ModuleParticipant.objects.count(), 1)

    def test_inscription_module_manuelle_preexistante_respectee(self):
        """Une inscription saisie manuellement n'est ni dupliquée ni supprimée."""
        existante = ModuleParticipant.objects.create(
            module=self.module_anatomie, participant=self.inscription.etudiant.participant,
        )
        resultat = passerelle_services.synchroniser(self.inscription, self.formation)
        self.assertEqual(resultat['creees'], 0)
        self.assertTrue(ModuleParticipant.objects.filter(pk=existante.pk).exists())

    def test_aucune_suppression(self):
        """La passerelle ne retire jamais une inscription à un module."""
        autre = ModuleParticipant.objects.create(
            module=self.module_sans_ref, participant=self.inscription.etudiant.participant,
        )
        passerelle_services.synchroniser(self.inscription, self.formation)
        self.assertTrue(ModuleParticipant.objects.filter(pk=autre.pk).exists())

    def test_modules_non_modifies(self):
        intitule = self.module_anatomie.intitule
        passerelle_services.synchroniser(self.inscription, self.formation)
        self.module_anatomie.refresh_from_db()
        self.assertEqual(self.module_anatomie.intitule, intitule)

    def test_inscription_non_validee_refusee(self):
        self.inscription.statut = InscriptionAdministrative.Statut.BROUILLON
        self.inscription.save(update_fields=['statut'])
        with self.assertRaises(passerelle_services.PasserelleImpossible):
            passerelle_services.synchroniser(self.inscription, self.formation)

    def test_synchronisation_journalisee(self):
        passerelle_services.synchroniser(self.inscription, self.formation, acteur=self.acteur)
        entree = JournalScolarite.objects.filter(
            action=JournalScolarite.Action.SYNCHRONISATION_EDT,
        ).first()
        self.assertEqual(entree.nouvelle_valeur, '1')

    def test_synchronisation_par_lot(self):
        autre = self.inscrire('Kone', 'Ali')
        pedagogie_services.generer_inscriptions_pedagogiques(autre)
        resultat = passerelle_services.synchroniser_lot(
            [self.inscription, autre], self.formation, acteur=self.acteur,
        )
        self.assertEqual(resultat['inscriptions'], 2)
        self.assertEqual(resultat['creees'], 2)

    def test_echec_isole_n_interrompt_pas_le_lot(self):
        invalide = self.inscrire('Sans', 'Validation', valider=False)
        resultat = passerelle_services.synchroniser_lot(
            [self.inscription, invalide], self.formation,
        )
        self.assertEqual(resultat['inscriptions'], 1)
        self.assertEqual(len(resultat['echecs']), 1)


class PasserelleAPITests(PasserelleFixture, TestCase):

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.client.force_authenticate(self.acteur)

    def test_analyse_via_api(self):
        response = self.client.post(
            f'/api/scolarite/inscriptions/{self.inscription.id}/passerelle/analyser/',
            {'formation_id': self.formation.id}, format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['a_creer']), 1)
        self.assertEqual(ModuleParticipant.objects.count(), 0)

    def test_synchronisation_via_api(self):
        response = self.client.post(
            f'/api/scolarite/inscriptions/{self.inscription.id}/passerelle/',
            {'formation_id': self.formation.id}, format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['creees'], 1)

    def test_formation_inconnue_renvoie_400(self):
        response = self.client.post(
            f'/api/scolarite/inscriptions/{self.inscription.id}/passerelle/',
            {'formation_id': 99999}, format='json',
        )
        self.assertEqual(response.status_code, 400)

    def test_inscription_non_validee_renvoie_409(self):
        self.inscription.statut = InscriptionAdministrative.Statut.BROUILLON
        self.inscription.save(update_fields=['statut'])
        response = self.client.post(
            f'/api/scolarite/inscriptions/{self.inscription.id}/passerelle/',
            {'formation_id': self.formation.id}, format='json',
        )
        self.assertEqual(response.status_code, 409)

    def test_lot_via_api(self):
        response = self.client.post('/api/scolarite/passerelle/lot/', {
            'formation_id': self.formation.id,
            'annee_academique_id': self.annee.id,
            'niveau_id': self.niveau.id,
        }, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['creees'], 1)

    def test_role_non_habilite_refuse(self):
        client = APIClient()
        client.force_authenticate(make_user('auditeur_pass', role='AUDITEUR'))
        response = client.post('/api/scolarite/passerelle/lot/', {
            'formation_id': self.formation.id,
        }, format='json')
        self.assertEqual(response.status_code, 403)
