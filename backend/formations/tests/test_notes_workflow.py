"""Tests du workflow de validation des notes de module (lot L1).

Couverture : saisie → brouillon → soumission → validation (verrouillage) →
correction auditée (motif, append-only, AuditLog, JournalScolarite,
notification) ; cas limites (note > max, étudiant non inscrit, arrondis,
motif manquant, valeur identique) ; permissions.
"""
from decimal import Decimal

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from authentication.models import User
from formations.models import (
    CorrectionNoteModule,
    Formation,
    Module,
    ModuleParticipant,
    NoteModule,
    NoteModuleColonne,
    NotificationModificationNote,
    Participant,
)
from presences.models import AuditLog
from scolarite.models import JournalScolarite


def make_user(username, role='SECRETARIAT', **kw):
    return User.objects.create_user(username=username, password='pass', role=role, **kw)


class NotesWorkflowTests(TestCase):
    def setUp(self):
        self.admin = make_user('admin_note', role='ADMIN', first_name='Admin', last_name='Test')
        self.direction = make_user('dir_note', role='DIRECTION', first_name='Dir', last_name='Test')
        self.secretariat = make_user('sec_note', role='SECRETARIAT')
        self.finance = make_user('fin_note', role='FINANCE')
        self.auditeur = make_user('aud_note', role='AUDITEUR')
        self.formation = Formation.objects.create(formation='Formation test')
        self.module = Module.objects.create(formation=self.formation, intitule='Module A')
        self.participant = Participant.objects.create(nom='Dupont', prenom='Jean', matricule='M001')
        self.non_inscrit = Participant.objects.create(nom='Martin', prenom='Paul', matricule='M002')
        ModuleParticipant.objects.create(module=self.module, participant=self.participant)
        self.colonne = NoteModuleColonne.objects.create(
            module=self.module, libelle='Contrôle 1', note_max=20,
        )
        self.client = APIClient()
        self.bulk_url = f'/api/formations/{self.formation.pk}/modules/{self.module.pk}/notes/bulk/'
        self.wf_url = f'/api/formations/{self.formation.pk}/modules/{self.module.pk}/notes/workflow/'
        self.hist_url = f'/api/formations/{self.formation.pk}/modules/{self.module.pk}/notes/historique/'

    def _bulk(self, note, user=None):
        self.client.force_authenticate(user or self.admin)
        return self.client.post(
            self.bulk_url,
            {'notes': [{'participant_id': self.participant.pk, 'colonne_id': self.colonne.pk, 'note': note}]},
            format='json',
        )

    def _workflow(self, action, items, user=None):
        self.client.force_authenticate(user or self.admin)
        return self.client.post(
            self.wf_url, {'action': action, 'items': items}, format='json',
        )

    def _obj(self):
        return NoteModule.objects.get(colonne=self.colonne, participant=self.participant)


    def test_cycle_complet_avec_correction_auditee(self):
        # 1. Saisie initiale (brouillon)
        res = self._bulk('12.00')
        self.assertEqual(res.data['saved'], 1)
        note = self._obj()
        self.assertEqual(note.statut_validation, 'BROUILLON')
        self.assertFalse(note.verrouillee)

        # 2. Soumission
        res = self._workflow('soumettre', [
            {'participant_id': self.participant.pk, 'colonne_id': self.colonne.pk},
        ])
        self.assertEqual(res.data['traites'], 1)
        note.refresh_from_db()
        self.assertEqual(note.statut_validation, 'SOUMISE')
        self.assertEqual(AuditLog.objects.filter(action='NOTE_SOUMISE').count(), 1)

        # 3. Validation → verrouillage
        res = self._workflow('valider', [
            {'participant_id': self.participant.pk, 'colonne_id': self.colonne.pk},
        ])
        self.assertEqual(res.data['traites'], 1)
        note.refresh_from_db()
        self.assertEqual(note.statut_validation, 'VALIDEE')
        self.assertTrue(note.verrouillee)
        self.assertEqual(note.validation_par, self.admin)
        self.assertIsNotNone(note.validation_le)
        self.assertEqual(AuditLog.objects.filter(action='NOTE_VALIDEE').count(), 1)

        # 4. Une note verrouillée n'est plus modifiable directement par le bulk
        res = self._bulk('14.00')
        self.assertGreater(len(res.data['errors']), 0)
        note.refresh_from_db()
        self.assertEqual(note.note, Decimal('12.00'))
        self.assertTrue(note.verrouillee)


# 5. Correction sans motif → refusée
        res = self._workflow('corriger', [
            {'participant_id': self.participant.pk, 'colonne_id': self.colonne.pk, 'note': '13.50'},
        ])
        self.assertGreater(len(res.data['errors']), 0)

        # 6. Correction auditée (motif obligatoire, trace append-only)
        res = self._workflow('corriger', [
            {
                'participant_id': self.participant.pk,
                'colonne_id': self.colonne.pk,
                'note': '13.50',
                'motif': 'Erreur de saisie corrigée par le secrétariat',
            },
        ])
        self.assertEqual(res.data['traites'], 1)
        note.refresh_from_db()
        self.assertEqual(note.note, Decimal('13.50'))
        self.assertTrue(note.verrouillee)  # la correction ne déverrouille pas
        corr = CorrectionNoteModule.objects.get()
        self.assertEqual(corr.ancienne_valeur, Decimal('12.00'))
        self.assertEqual(corr.nouvelle_valeur, Decimal('13.50'))
        self.assertIn('secrétariat', corr.motif)
        self.assertEqual(AuditLog.objects.filter(action='NOTE_CORRIGEE').count(), 1)
        self.assertEqual(JournalScolarite.objects.filter(objet_type='NoteModule').count(), 1)
        self.assertEqual(
            NotificationModificationNote.objects.filter(destinataire=self.direction).count(), 1,
        )

        # 7. Historique append-only exposé en lecture
        self.client.force_authenticate(self.admin)
        res = self.client.get(self.hist_url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data['corrections']), 1)
        self.assertEqual(float(res.data['corrections'][0]['nouvelle_valeur']), 13.5)

        # 8. Déverrouillage → nouvelle saisie possible
        res = self._workflow('deverrouiller', [
            {'participant_id': self.participant.pk, 'colonne_id': self.colonne.pk},
        ])
        self.assertEqual(res.data['traites'], 1)
        note.refresh_from_db()
        self.assertFalse(note.verrouillee)
        self.assertEqual(note.statut_validation, 'SOUMISE')
        res = self._bulk('15.00')
        self.assertEqual(res.data['saved'], 1)
        self.assertEqual(self._obj().note, Decimal('15.00'))


    def test_annulation_soumission_retour_brouillon(self):
        self._bulk('10.00')
        self._workflow('soumettre', [
            {'participant_id': self.participant.pk, 'colonne_id': self.colonne.pk},
        ])
        res = self._workflow('annuler', [
            {'participant_id': self.participant.pk, 'colonne_id': self.colonne.pk},
        ])
        self.assertEqual(res.data['traites'], 1)
        self.assertEqual(self._obj().statut_validation, 'BROUILLON')
        # Annuler un brouillon → erreur
        res = self._workflow('annuler', [
            {'participant_id': self.participant.pk, 'colonne_id': self.colonne.pk},
        ])
        self.assertGreater(len(res.data['errors']), 0)

    def test_correction_cas_limites(self):
        self._bulk('10.00')
        self._workflow('valider', [
            {'participant_id': self.participant.pk, 'colonne_id': self.colonne.pk},
        ])
        # Étudiant non inscrit
        res = self._workflow('corriger', [
            {
                'participant_id': self.non_inscrit.pk,
                'colonne_id': self.colonne.pk,
                'note': '12.00',
                'motif': 'test',
            },
        ])
        self.assertIn('non inscrit', res.data['errors'][0]['detail'])
        # Note > note maximale (20)
        res = self._workflow('corriger', [
            {
                'participant_id': self.participant.pk,
                'colonne_id': self.colonne.pk,
                'note': '20.50',
                'motif': 'test',
            },
        ])
        self.assertIn('entre 0 et 20', res.data['errors'][0]['detail'])
        # Valeur strictement identique → refusée
        res = self._workflow('corriger', [
            {
                'participant_id': self.participant.pk,
                'colonne_id': self.colonne.pk,
                'note': '10.00',
                'motif': 'test',
            },
        ])
        self.assertIn('identique', res.data['errors'][0]['detail'])
        # Arrondi à 2 décimales
        res = self._workflow('corriger', [
            {
                'participant_id': self.participant.pk,
                'colonne_id': self.colonne.pk,
                'note': '14.556',
                'motif': 'arrondi à appliquer',
            },
        ])
        self.assertEqual(res.data['traites'], 1)
        self.assertEqual(self._obj().note, Decimal('14.56'))

    def test_suppression_note_verrouillee_refusee(self):
        self._bulk('10.00')
        self._workflow('valider', [
            {'participant_id': self.participant.pk, 'colonne_id': self.colonne.pk},
        ])
        self.client.force_authenticate(self.admin)
        res = self.client.post(
            self.bulk_url,
            {'notes': [{'participant_id': self.participant.pk, 'colonne_id': self.colonne.pk, 'note': None}]},
            format='json',
        )
        self.assertGreater(len(res.data['errors']), 0)
        self.assertEqual(self._obj().note, Decimal('10.00'))

    def test_workflow_permissions(self):
        self._bulk('10.00')
        # Auditeur : accès refusé (IsGestionNotes)
        res = self._workflow('valider', [
            {'participant_id': self.participant.pk, 'colonne_id': self.colonne.pk},
        ], user=self.auditeur)
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        # Finance : blocage opérationnel
        res = self._workflow('valider', [
            {'participant_id': self.participant.pk, 'colonne_id': self.colonne.pk},
        ], user=self.finance)
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        # Historique : finance bloqué aussi
        self.client.force_authenticate(self.finance)
        res = self.client.get(self.hist_url)
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_action_invalide_rejetee(self):
        self._bulk('10.00')
        self.client.force_authenticate(self.admin)
        res = self.client.post(self.wf_url, {'action': 'exploser', 'items': []}, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)