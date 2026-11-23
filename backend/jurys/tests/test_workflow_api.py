"""Tests du workflow des jurys (lot L3 — Prompt 13).

Cycle complet : création → membres → calcul → décisions → PV → publication,
permissions (DFRC / Secrétariat / Direction), garde-fous (session verrouillée,
décision manuelle justifiée, complétude).
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from formations.models import (
    Formation,
    Module,
    ModuleParticipant,
    NoteModule,
    NoteModuleColonne,
    Participant,
    RefFormation,
    RefModule,
)
from scolarite.models import (
    AnneeAcademique,
    DossierEtudiant,
    ECUE,
    InscriptionAdministrative,
    InscriptionPedagogique,
    Maquette,
    Niveau,
    Semestre,
    UE,
)

User = get_user_model()


def make_user(username, role):
    return User.objects.create_user(username=username, password='pass', role=role)


class JuryWorkflowBase(TestCase):
    """Session de jury + étudiant inscrit + maquette ACTIVE avec 1 UE/2 ECUE."""

    def setUp(self):
        self.dfrc = make_user('dfrc_jury', User.Role.INJS_ADMIN)
        self.secretariat = make_user('sec_jury', User.Role.SECRETARIAT)
        self.direction = make_user('dir_jury', User.Role.DIRECTION)
        self.auditeur = make_user('aud_jury', User.Role.AUDITEUR)

        self.ref_formation = RefFormation.objects.create(intitule='Licence Jury')
        self.annee = AnneeAcademique.objects.create(
            libelle='2026-2027', date_debut=date(2026, 10, 1), date_fin=date(2027, 9, 30),
        )
        self.niveau = Niveau.objects.create(code='L1J', libelle='Licence 1J', credits_requis=20)
        self.semestre = Semestre.objects.create(niveau=self.niveau, numero=1, libelle='S1')
        self.maquette = Maquette.objects.create(
            annee_academique=self.annee, ref_formation=self.ref_formation,
            niveau=self.niveau, statut=Maquette.Statut.BROUILLON,
        )
        self.ue1 = UE.objects.create(
            maquette=self.maquette, semestre=self.semestre, code='UE1', credits=20,
        )
        self.ref_a = RefModule.objects.create(intitule='Module A')
        self.ref_b = RefModule.objects.create(intitule='Module B')
        self.ecue_a = ECUE.objects.create(
            ue=self.ue1, code='ECUE-A', intitule='ECUE A', credits=10, ref_module=self.ref_a,
        )
        self.ecue_b = ECUE.objects.create(
            ue=self.ue1, code='ECUE-B', intitule='ECUE B', credits=10, ref_module=self.ref_b,
        )
        self.maquette.statut = Maquette.Statut.ACTIVE
        self.maquette.save()

        self.formation_op = Formation.objects.create(formation='Licence Jury op')
        self.participant = Participant.objects.create(nom='Dup', prenom='Jean', matricule='MJ01')
        self.dossier = DossierEtudiant.objects.create(participant=self.participant)
        self.inscription = InscriptionAdministrative.objects.create(
            etudiant=self.dossier, annee_academique=self.annee,
            ref_formation=self.ref_formation, niveau=self.niveau,
            statut=InscriptionAdministrative.Statut.VALIDEE,
        )
        self.client = APIClient()

    def _branche(self, ecue):
        module = Module.objects.create(
            formation=self.formation_op, intitule=ecue.code, ref_module=ecue.ref_module,
        )
        mp = ModuleParticipant.objects.create(module=module, participant=self.participant)
        InscriptionPedagogique.objects.create(
            inscription=self.inscription, ecue=ecue, semestre=self.semestre,
            module_participant=mp, statut=InscriptionPedagogique.Statut.VALIDEE,
        )
        return module

    def _noter(self, module, valeur):
        colonne = NoteModuleColonne.objects.create(module=module, libelle='N', note_max=20)
        return NoteModule.objects.create(
            colonne=colonne, participant=self.participant,
            note=Decimal(str(valeur)), verrouillee=True, statut_validation='VALIDEE',
        )

    def _creer_session(self):
        self.client.force_authenticate(self.dfrc)
        reponse = self.client.post('/api/juries/sessions/', {
            'annee_academique': self.annee.pk,
            'ref_formation': self.ref_formation.pk,
            'niveau': self.niveau.pk,
            'maquette': self.maquette.pk,
            'type_session': 'NORMALE',
            'libelle': 'Jury test',
        }, format='json')
        self.assertEqual(reponse.status_code, status.HTTP_201_CREATED, reponse.data)
        return reponse.data

    def _session_pk(self):
        if not hasattr(self, '_session'):
            self._session = self._creer_session()
        return self._session['id']


class JuryPermissionsTests(JuryWorkflowBase):
    """Permissions : création DFRC uniquement, accès Direction pour notifications."""

    def test_creation_session_reservee_dfrc(self):
        self.client.force_authenticate(self.dfrc)
        reponse = self.client.post('/api/juries/sessions/', {
            'annee_academique': self.annee.pk,
            'ref_formation': self.ref_formation.pk,
            'niveau': self.niveau.pk,
            'maquette': self.maquette.pk,
        }, format='json')
        self.assertEqual(reponse.status_code, status.HTTP_201_CREATED)

    def test_creation_session_interdit_secrétariat(self):
        self.client.force_authenticate(self.secretariat)
        reponse = self.client.post('/api/juries/sessions/', {
            'annee_academique': self.annee.pk,
            'ref_formation': self.ref_formation.pk,
            'niveau': self.niveau.pk,
            'maquette': self.maquette.pk,
        }, format='json')
        self.assertEqual(reponse.status_code, status.HTTP_403_FORBIDDEN)

    def test_notifications_reservees_direction(self):
        self.client.force_authenticate(self.secretariat)
        reponse = self.client.get('/api/juries/notifications/')
        self.assertEqual(reponse.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(self.direction)
        reponse = self.client.get('/api/juries/notifications/')
        self.assertEqual(reponse.status_code, status.HTTP_200_OK)


class JuryWorkflowTests(JuryWorkflowBase):
    """Cycle complet du jury + garde-fous."""

    def test_calcul_propositions(self):
        session = self._creer_session()
        module_a = self._branche(self.ecue_a)
        module_b = self._branche(self.ecue_b)
        self._noter(module_a, 12)
        self._noter(module_b, 8)

        self.client.force_authenticate(self.secretariat)
        reponse = self.client.post(
            f"/api/juries/sessions/{session['id']}/action/",
            {'action': 'calcul'}, format='json',
        )
        self.assertEqual(reponse.status_code, status.HTTP_200_OK, reponse.data)
        self.assertEqual(reponse.data['calculees'], 1)

    def test_decision_conforme_sans_justification(self):
        session = self._creer_session()
        module_a = self._branche(self.ecue_a)
        module_b = self._branche(self.ecue_b)
        self._noter(module_a, 12)
        self._noter(module_b, 8)

        self.client.force_authenticate(self.secretariat)
        self.client.post(
            f"/api/juries/sessions/{session['id']}/action/",
            {'action': 'calcul'}, format='json',
        )
        # Avancer jusqu'à DELIBERATION
        for action in ('transition', 'transition', 'transition'):
            self.client.post(
                f"/api/juries/sessions/{session['id']}/action/",
                {'action': action}, format='json',
            )

        # Décision conforme à la proposition (ADMIS) : pas de justification requise
        reponse = self.client.post(
            f"/api/juries/sessions/{session['id']}/decisions/",
            {'inscription_id': self.inscription.pk, 'decision': 'ADMIS'},
            format='json',
        )
        self.assertEqual(reponse.status_code, status.HTTP_201_CREATED, reponse.data)
        self.assertFalse(reponse.data['decision_manuelle'])

    def test_decision_manuelle_justification_obligatoire(self):
        session = self._creer_session()
        module_a = self._branche(self.ecue_a)
        module_b = self._branche(self.ecue_b)
        self._noter(module_a, 12)
        self._noter(module_b, 8)

        self.client.force_authenticate(self.secretariat)
        self.client.post(
            f"/api/juries/sessions/{session['id']}/action/",
            {'action': 'calcul'}, format='json',
        )
        for action in ('transition', 'transition', 'transition'):
            self.client.post(
                f"/api/juries/sessions/{session['id']}/action/",
                {'action': action}, format='json',
            )

        # Décision divergente (AJOURNÉ) sans justification → refusée
        reponse = self.client.post(
            f"/api/juries/sessions/{session['id']}/decisions/",
            {'inscription_id': self.inscription.pk, 'decision': 'AJOURNE'},
            format='json',
        )
        self.assertEqual(reponse.status_code, status.HTTP_400_BAD_REQUEST)

        # Avec justification → acceptée
        reponse = self.client.post(
            f"/api/juries/sessions/{session['id']}/decisions/",
            {'inscription_id': self.inscription.pk, 'decision': 'AJOURNE',
             'justification': 'Moyenne insuffisante'},
            format='json',
        )
        self.assertEqual(reponse.status_code, status.HTTP_201_CREATED, reponse.data)
        self.assertTrue(reponse.data['decision_manuelle'])

    def test_session_verrouillee_immodifiable(self):
        from jurys.models import SessionJury
        session = self._creer_session()
        # Forcer le statut VERROUILLE directement
        SessionJury.objects.filter(pk=session['id']).update(statut=SessionJury.Statut.VERROUILLE)

        self.client.force_authenticate(self.secretariat)
        # Calcul impossible sur session verrouillée
        reponse = self.client.post(
            f"/api/juries/sessions/{session['id']}/action/",
            {'action': 'calcul'}, format='json',
        )
        self.assertEqual(reponse.status_code, status.HTTP_400_BAD_REQUEST)

    def test_publication_dfrc_uniquement(self):
        session = self._creer_session()
        self.client.force_authenticate(self.secretariat)
        reponse = self.client.post(
            f"/api/juries/sessions/{session['id']}/action/",
            {'action': 'publier'}, format='json',
        )
        self.assertEqual(reponse.status_code, status.HTTP_403_FORBIDDEN)


