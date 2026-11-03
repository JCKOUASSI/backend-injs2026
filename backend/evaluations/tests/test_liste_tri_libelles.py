"""Tableau de bord des évaluations — tri « récent » et libellés métier.

Le panneau « Dernières évaluations » annonçait un ordre « de la plus
récente à la plus ancienne » que l'API ne garantissait pas (tri modèle
session/code ECUE), et l'écran affichait des codes bruts (PUBLIEE,
EX-CC…) faute de libellés dans les payloads. Ces tests verrouillent
le contrat additif : `tri=recent`, `type_libelle`, `statut_display`,
`type_session_display`.
"""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from evaluations.models import Evaluation, SessionEvaluation, TypeEvaluation
from evaluations.tests import factories as f

BASE = '/api/evaluations-academiques'


class TriEtLibellesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = f.creer_compte('ADMIN', 'admin-tri')
        cls.ctx = f.base_lmd_complete(suffixe='T')
        cls.type_eval = TypeEvaluation.objects.create(
            code='CC', libelle='Contrôle continu', categorie='Contrôle',
        )
        cls.session = SessionEvaluation.objects.create(
            annee_academique=cls.ctx['annee'],
            ref_formation=cls.ctx['ref_formation'],
            niveau=cls.ctx['niveau'], semestre=cls.ctx['semestre'],
            maquette=cls.ctx['maquette'], libelle='Session normale S1',
            type_session=SessionEvaluation.TypeSession.NORMALE,
            statut='OUVERTE',
        )
        cls.ancienne = Evaluation.objects.create(
            session=cls.session, ecue=cls.ctx['ecue'],
            affectation_pedagogique=cls.ctx['affectation'],
            type_evaluation=cls.type_eval, libelle='Ancienne évaluation',
            statut='CLOTUREE',
        )
        cls.recente = Evaluation.objects.create(
            session=cls.session, ecue=cls.ctx['ecue'],
            affectation_pedagogique=cls.ctx['affectation'],
            type_evaluation=cls.type_eval, libelle='Évaluation récente',
            statut='PUBLIEE',
        )
        maintenant = timezone.now()
        Evaluation.objects.filter(pk=cls.ancienne.pk).update(
            created_at=maintenant - timedelta(days=2),
        )
        Evaluation.objects.filter(pk=cls.recente.pk).update(
            created_at=maintenant,
        )

    def api(self):
        client = APIClient()
        client.force_authenticate(user=self.admin)
        return client

    def test_tri_recent_place_la_plus_recente_en_premier(self):
        reponse = self.api().get(f'{BASE}/evaluations/', {'tri': 'recent'})
        self.assertEqual(reponse.status_code, status.HTTP_200_OK)
        ids = [l['id'] for l in reponse.data['results']]
        self.assertEqual(ids[0], self.recente.id)
        self.assertLess(ids.index(self.recente.id), ids.index(self.ancienne.id))

    def test_libelles_metier_dans_le_payload_evaluation(self):
        reponse = self.api().get(f'{BASE}/evaluations/')
        self.assertEqual(reponse.status_code, status.HTTP_200_OK)
        par_id = {l['id']: l for l in reponse.data['results']}
        self.assertEqual(par_id[self.recente.id]['type_libelle'], 'Contrôle continu')
        self.assertEqual(par_id[self.recente.id]['statut_display'], 'Publiée')
        self.assertEqual(par_id[self.ancienne.id]['statut_display'], 'Clôturée')

    def test_libelles_metier_dans_le_payload_session(self):
        reponse = self.api().get(f'{BASE}/sessions/')
        self.assertEqual(reponse.status_code, status.HTTP_200_OK)
        ligne = next(
            l for l in reponse.data['results'] if l['id'] == self.session.id
        )
        self.assertEqual(ligne['statut_display'], 'Ouverte (saisie possible)')
        self.assertEqual(ligne['type_session_display'], 'Session normale')
