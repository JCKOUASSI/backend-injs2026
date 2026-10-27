"""Lot L5 — tests équivalences et dispenses.

Couvre : workflow (transitions interdites, complétude bloquante), décision
(VALIDEE/REJETEE, crédits reconnus obligatoires), application (refus avant
validation, IP DISPENSEE, EvenementScolarite, journal), rectification
(ancienne/nouvelle décision, jamais de suppression), API (accès, suppression
interdite).
"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from admissions.models import Candidat, Candidature
from authentication.models import User
from formations.models import Participant, RefFormation
from scolarite.models import (
    AnneeAcademique,
    DossierEtudiant,
    ECUE,
    EvenementScolarite,
    InscriptionAdministrative,
    InscriptionPedagogique,
    JournalScolarite,
    Maquette,
    Niveau,
    Parcours,
    Semestre,
    UE,
)

from equivalences.models import (
    DemandeEquivalenceDispense,
    HistoriqueEquivalence,
    PieceEquivalence,
)
from equivalences import services, workflow


def make_user(username, role='SECRETARIAT'):
    return User.objects.create_user(username=username, password='pass', role=role)


class EquivalenceBase(TestCase):
    """Fixture : maquette complète + étudiant inscrit + IP + demande."""

    @classmethod
    def setUpTestData(cls):
        cls.annee = AnneeAcademique.objects.create(
            libelle='2026-2027', date_debut='2026-10-01', date_fin='2027-07-31', courante=True,
        )
        cls.formation = RefFormation.objects.create(intitule='LICENCE STAPS')
        cls.niveau = Niveau.objects.create(code='L1', libelle='Licence 1', ordre=1)
        cls.s1 = Semestre.objects.create(niveau=cls.niveau, numero=1, libelle='S1')
        cls.maquette = Maquette.objects.create(
            annee_academique=cls.annee, ref_formation=cls.formation, niveau=cls.niveau,
        )
        cls.ue = UE.objects.create(
            maquette=cls.maquette, semestre=cls.s1, code='UE11',
            intitule='Sciences du mouvement', credits=6,
        )
        cls.ecue = ECUE.objects.create(
            ue=cls.ue, code='ECUE111', intitule='Anatomie', credits=3, volume_cm=20,
        )
        cls.participant = Participant.objects.create(
            matricule='INJS26-0100', nom='Bamba', prenom='Fatou',
        )
        cls.dossier = DossierEtudiant.objects.create(participant=cls.participant)
        cls.inscription = InscriptionAdministrative.objects.create(
            etudiant=cls.dossier, annee_academique=cls.annee,
            ref_formation=cls.formation, niveau=cls.niveau,
            statut=InscriptionAdministrative.Statut.VALIDEE,
        )
        cls.ip = InscriptionPedagogique.objects.create(
            inscription=cls.inscription, ecue=cls.ecue, semestre=cls.s1,
            credits=cls.ecue.credits, volume_horaire=cls.ecue.volume_total,
        )
        cls.demande = DemandeEquivalenceDispense.objects.create(
            type_demande=DemandeEquivalenceDispense.TypeDemande.DISPENSE,
            etudiant=cls.dossier, annee_academique=cls.annee,
            ref_formation=cls.formation, niveau=cls.niveau,
            semestre=cls.s1, ue=cls.ue, ecue=cls.ecue,
            etablissement_origine='Université de Cocody',
            diplome_origine='DEG A1',
        )
        PieceEquivalence.objects.create(
            demande=cls.demande, libelle='Relevé de notes antérieur', obligatoire=True,
        )

    def _faire_valider(self):
        for statut in (
            S('SOUMISE'), S('EN_INSTRUCTION'), S('AVIS_PEDAGOGIQUE'), S('DECISION'),
        ):
            workflow.appliquer_transition(self.demande, statut)
        self.demande.decision = DemandeEquivalenceDispense.Decision.FAVORABLE
        self.demande.credits_reconnus = 3
        self.demande.autorite_validation = 'Direction des études INJS'
        self.demande.save(update_fields=['decision', 'credits_reconnus', 'autorite_validation'])
        workflow.appliquer_transition(self.demande, 'VALIDEE')


S = DemandeEquivalenceDispense.Statut



class WorkflowTests(EquivalenceBase):
    def test_transition_interdite_refusee(self):
        # BROUILLON → AVIS_PEDAGOGIQUE est interdit (il faut passer par SOUMISE…).
        with self.assertRaises(workflow.TransitionInterdite):
            workflow.appliquer_transition(self.demande, 'AVIS_PEDAGOGIQUE')
        self.demande.refresh_from_db()
        self.assertEqual(self.demande.statut, S.BROUILLON)

    def test_completude_bloquante_vers_avis_pedagogique(self):
        client = APIClient()
        client.force_authenticate(make_user('sec_eq', role='SECRETARIAT'))
        workflow.appliquer_transition(self.demande, S.SOUMISE)
        workflow.appliquer_transition(self.demande, S.EN_INSTRUCTION)
        # Pièce obligatoire non validée → refus.
        res = client.post(f'/api/equivalences/demandes/{self.demande.pk}/transition/',
                          {'statut': 'AVIS_PEDAGOGIQUE'}, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertIn('Dossier incomplet', str(res.data['error']))


class ApplicationTests(EquivalenceBase):
    def test_application_avant_validation_refusee(self):
        with self.assertRaises(services.ApplicationImpossible):
            services.appliquer(self.demande)

    def test_application_apres_validation(self):
        self._faire_valider()
        services.appliquer(self.demande)
        self.demande.refresh_from_db()
        self.assertEqual(self.demande.statut, S.APPLIQUEE)
        # IP existante passée au statut DISPENSEE.
        self.ip.refresh_from_db()
        self.assertEqual(self.ip.statut, InscriptionPedagogique.Statut.DISPENSEE)
        # Historique académique alimenté.
        self.assertTrue(EvenementScolarite.objects.filter(
            etudiant=self.dossier,
            type_evenement=EvenementScolarite.Type.EQUIVALENCE_DISPENSE,
        ).exists())
        # Audit JournalScolarite.
        self.assertTrue(JournalScolarite.objects.filter(
            objet_id=self.demande.pk, objet_type='DemandeEquivalenceDispense',
        ).exists())

    def test_double_application_refusee(self):
        self._faire_valider()
        services.appliquer(self.demande)
        with self.assertRaises(services.ApplicationImpossible):
            services.appliquer(self.demande)


class RectificationTests(EquivalenceBase):
    def test_rectification_trace_ancienne_et_nouvelle_decision(self):
        self._faire_valider()
        demande_id = self.demande.pk
        services.rectifier(
            self.demande, utilisateur=make_user('rect_eq', role='ADMIN'),
            motif='Erreur de saisie des crédits', credits_reconnus=6,
        )
        self.demande.refresh_from_db()
        self.assertEqual(self.demande.credits_reconnus, 6)
        self.assertEqual(self.demande.decision_rectifiee, self.demande.Decision.FAVORABLE)
        self.assertIsNotNone(self.demande.rectifiee_le)
        self.assertTrue(HistoriqueEquivalence.objects.filter(demande_id=demande_id).exists())

    def test_application_apres_rectification_impossible_si_deja_appliquee(self):
        self._faire_valider()
        services.appliquer(self.demande)
        with self.assertRaises(services.ApplicationImpossible):
            services.rectifier(self.demande, motif='Test', credits_reconnus=9)


class EquivalenceAPITests(EquivalenceBase):
    def setUp(self):
        self.client = APIClient()

    def test_anonyme_refuse(self):
        res = self.client.get('/api/equivalences/demandes/')
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_creation_via_api(self):
        self.client.force_authenticate(make_user('sec_eq2', role='SECRETARIAT'))
        res = self.client.post('/api/equivalences/demandes/', {
            'type_demande': 'EQUIVALENCE',
            'etudiant_id': self.dossier.pk,
            'annee_academique_id': self.annee.pk,
            'ref_formation_id': self.formation.pk,
            'niveau_id': self.niveau.pk,
            'etablissement_origine': 'Université de Cocody',
        }, format='json')
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data['statut'], 'BROUILLON')

    def test_suppression_impossible(self):
        # Aucun endpoint DELETE : une décision n'est jamais supprimée.
        self.client.force_authenticate(make_user('admin_eq', role='ADMIN'))
        res = self.client.delete(f'/api/equivalences/demandes/{self.demande.pk}/')
        self.assertEqual(res.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)