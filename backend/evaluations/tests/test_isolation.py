"""C1 — Isolation de périmètre ENCADRANT (test obligatoire A ≠ B).

Un encadrant ne voit et ne modifie que les évaluations rattachées à **ses**
affectations pédagogiques. Le filtrage est vérifié **côté serveur** : un
encadrant ne doit jamais contourner le périmètre en devinant un identifiant
d'une autre affectation.
"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models import ProtectedError
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from evaluations.models import (
    Evaluation,
    EvaluationComponent,
    EvaluationParticipant,
    SessionEvaluation,
    TypeEvaluation,
)
from evaluations.tests import factories as f

BASE = '/api/evaluations-academiques'


class TestIsolationEncadrant(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user_a = f.creer_compte('ENCADRANT', 'encadrant-a')
        cls.user_b = f.creer_compte('ENCADRANT', 'encadrant-b')
        cls.type_eval = TypeEvaluation.objects.create(code='EXAMEN', libelle='Examen')
        # Deux périmètres LMD indépendants (deux maquettes) : rien n'est
        # partagé entre A et B.
        cls.ctx_a = f.base_lmd_complete(formateur_user=cls.user_a, suffixe='A')
        cls.ctx_b = f.base_lmd_complete(formateur_user=cls.user_b, suffixe='B')

        cls.session_a = SessionEvaluation.objects.create(
            annee_academique=cls.ctx_a['annee'],
            ref_formation=cls.ctx_a['ref_formation'],
            niveau=cls.ctx_a['niveau'], semestre=cls.ctx_a['semestre'],
            maquette=cls.ctx_a['maquette'], libelle='Session A',
        )
        cls.session_b = SessionEvaluation.objects.create(
            annee_academique=cls.ctx_b['annee'],
            ref_formation=cls.ctx_b['ref_formation'],
            niveau=cls.ctx_b['niveau'], semestre=cls.ctx_b['semestre'],
            maquette=cls.ctx_b['maquette'], libelle='Session B',
        )
        cls.evaluation_a = Evaluation.objects.create(
            session=cls.session_a, ecue=cls.ctx_a['ecue'],
            affectation_pedagogique=cls.ctx_a['affectation'],
            type_evaluation=cls.type_eval, libelle='Épreuve A',
        )
        cls.evaluation_b = Evaluation.objects.create(
            session=cls.session_b, ecue=cls.ctx_b['ecue'],
            affectation_pedagogique=cls.ctx_b['affectation'],
            type_evaluation=cls.type_eval, libelle='Épreuve B',
        )
        cls.composant_b = EvaluationComponent.objects.create(
            evaluation=cls.evaluation_b, code='EXAMEN', libelle='Examen B',
            poids=Decimal('100.00'), bareme=Decimal('20.00'),
        )

    def api(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def test_listings_ne_montrent_que_le_son_perimetre(self):
        for user, attendu, interdit in (
            (self.user_a, self.evaluation_a, self.evaluation_b),
            (self.user_b, self.evaluation_b, self.evaluation_a),
        ):
            reponse = self.api(user).get(f'{BASE}/evaluations/')
            self.assertEqual(reponse.status_code, status.HTTP_200_OK)
            ids = [r['id'] for r in reponse.json()['results']]
            self.assertIn(attendu.pk, ids)
            self.assertNotIn(interdit.pk, ids, 'fuite inter-affectations')

    def test_detail_d_un_autre_perimetre_404(self):
        reponse = self.api(self.user_a).get(
            f'{BASE}/evaluations/{self.evaluation_b.pk}/',
        )
        self.assertEqual(reponse.status_code, status.HTTP_404_NOT_FOUND)

    def test_creation_sur_affectation_tierce_refusee(self):
        reponse = self.api(self.user_a).post(
            f'{BASE}/evaluations/create/',
            {
                'session': self.session_b.pk, 'ecue': self.ctx_b['ecue'].pk,
                'affectation_pedagogique': self.ctx_b['affectation'].pk,
                'type_evaluation': self.type_eval.pk, 'libelle': 'Intrusion',
            },
            format='json',
        )
        self.assertEqual(reponse.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            reponse.json()['code'], 'EVALUATION_AFFECTATION_HORS_PERIMETRE',
        )

    def test_saisie_de_notes_hors_perimetre_404(self):
        reponse = self.api(self.user_a).put(
            f'{BASE}/composants/{self.composant_b.pk}/notes/',
            [{'evaluation_participant_id': 1, 'valeur': '18.00'}],
            format='json',
        )
        self.assertEqual(reponse.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(reponse.json()['code'], 'COMPOSANT_INTROUVABLE')

    def test_sessions_liste_respecte_le_perimetre(self):
        for user, attendue, interdite in (
            (self.user_a, self.session_a, self.session_b),
            (self.user_b, self.session_b, self.session_a),
        ):
            reponse = self.api(user).get(f'{BASE}/sessions/')
            ids = [r['id'] for r in reponse.json()['results']]
            self.assertIn(attendue.pk, ids)
            self.assertNotIn(interdite.pk, ids)

    def test_scolarite_voit_tout(self):
        secretariat = f.creer_compte('SECRETARIAT', 'secretariat-iso')
        reponse = self.api(secretariat).get(f'{BASE}/evaluations/')
        ids = [r['id'] for r in reponse.json()['results']]
        self.assertIn(self.evaluation_a.pk, ids)
        self.assertIn(self.evaluation_b.pk, ids)


class TestProtectionReferentiels(TestCase):
    """Un référentiel référencé par des données académiques n'est pas supprimable.

    Deux barrières complémentaires sont vérifiées : le garde-fou de
    ``scolarite`` (maquette immuable → ``ValidationError``) et l'
    ``on_delete=PROTECT`` du socle (``ProtectedError``). Les deux sont des
    refus de suppression : aucune donnée académique n'est jamais effacée.
    """

    @classmethod
    def setUpTestData(cls):
        cls.ctx = f.base_lmd_complete()
        cls.type_eval = TypeEvaluation.objects.create(code='EXAMEN', libelle='Examen')
        cls.session = SessionEvaluation.objects.create(
            annee_academique=cls.ctx['annee'], ref_formation=cls.ctx['ref_formation'],
            niveau=cls.ctx['niveau'], semestre=cls.ctx['semestre'],
            maquette=cls.ctx['maquette'],
        )
        cls.evaluation = Evaluation.objects.create(
            session=cls.session, ecue=cls.ctx['ecue'],
            affectation_pedagogique=cls.ctx['affectation'],
            type_evaluation=cls.type_eval, libelle='Épreuve',
        )
        # Un participant rattache l'inscription pédagogique à l'évaluation :
        # c'est ce lien qui rend l'inscription administrative intouchable.
        EvaluationParticipant.objects.create(
            evaluation=cls.evaluation,
            inscription_pedagogique=cls.ctx['inscription_pedagogique'],
        )

    def test_ecue_reference_non_supprimable(self):
        with self.assertRaises((ValidationError, ProtectedError)):
            self.ctx['ecue'].delete()

    def test_ue_referencee_non_supprimable(self):
        with self.assertRaises((ValidationError, ProtectedError)):
            self.ctx['ue'].delete()

    def test_inscription_administrative_referencee_non_supprimable(self):
        with self.assertRaises((ValidationError, ProtectedError)):
            self.ctx['inscription'].delete()

    def test_annee_referencee_non_supprimable(self):
        with self.assertRaises((ValidationError, ProtectedError)):
            self.ctx['annee'].delete()

    def test_affectation_referencee_non_supprimable(self):
        with self.assertRaises((ValidationError, ProtectedError)):
            self.ctx['affectation'].delete()