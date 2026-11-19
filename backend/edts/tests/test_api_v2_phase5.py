"""Façade HTTP v2 et séparation des routes héritées, données BENCH fictives."""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from edts.models import AffectationCreneau, CampagneGeneration, ExecutionCampagne
from edts.models_interop import SeanceRegistre
from edts.tests import test_moteur_v2_phase3 as fixture_module


@override_settings(DEBUG=True, GETINJS_V2_EXPERIMENTAL_WRITE=True)
class ApiV2BenchTests(TestCase):
    def setUp(self):
        fixture_module.MoteurV2BenchTests.setUp(self)
        self.client_api = APIClient()
        U = get_user_model()
        self.admin = U.objects.create_user(username='bench-v2-admin', password='x', role=U.Role.ADMIN)
        self.auditeur = U.objects.create_user(username='bench-v2-audit', password='x', role='AUDITEUR')
        self.client_api.force_authenticate(user=self.admin)
        self.payload = dict(annee_id=self.annee.pk, groupe_id=self.groupe.pk,
            ecue_id=0, type_seance='CM', ordinal=1, duree_minutes=120,
            effectif=20, formateur_id=self.formateur.pk, revision=1,
            source_confirmee=True, source_document='TEST FICTIF', jour=self.jour.isoformat())

    def _simuler(self, **patch):
        return self.client_api.post('/api/edts/v2/bench/simuler-ligne/',
                                    {**self.payload, **patch}, format='json')

    def test_simulation_sans_effet_et_placements_idempotents(self):
        simulation = self._simuler()
        self.assertEqual(simulation.status_code, 200)
        d = simulation.data['decision']
        self.assertEqual(d['statut'], 'PLACEE')
        self.assertFalse(AffectationCreneau.objects.exists())
        url = '/api/edts/v2/bench/placer-ligne/'
        payload = {**self.payload, 'creneau_id': d['creneau_id'], 'salle_id': d['salle_id']}
        a = self.client_api.post(url, payload, format='json')
        self.assertEqual(a.status_code, 200, a.data)
        self.assertEqual(a.data['decision']['code'], 'PLACEE_QR_A_REVOIR')
        b = self.client_api.post(url, payload, format='json')
        self.assertEqual(b.status_code, 200, b.data)
        self.assertEqual(b.data['decision']['code'], 'DEJA_PLACEE_QR_A_REVOIR')
        self.assertEqual((AffectationCreneau.objects.count(), SeanceRegistre.objects.count()), (1, 1))
        modifiee = self.client_api.post(url, {**payload, 'formateur_id': self.formateur.pk + 10}, format='json')
        self.assertEqual(modifiee.status_code, 409)
        self.assertEqual(modifiee.data['code'], 'ENTREE_MODIFIEE')

    def test_absence_de_preuve_date_et_droits_bloquent(self):
        self.assertEqual(self._simuler(source_confirmee=False).data['decision']['code'],
                         'VOLUME_NON_CONFIRME')
        self.assertEqual(self._simuler(jour='2100-01-01').status_code, 400)
        self.assertEqual(self._simuler(annee_id=9000000).status_code, 409)
        self.client_api.force_authenticate(user=self.auditeur)
        self.assertEqual(self._simuler().status_code, 403)
        self.client_api.force_authenticate(user=None)
        self.assertIn(self._simuler().status_code, (401, 403))
        self.assertFalse(AffectationCreneau.objects.exists())

    def test_flag_et_route_legacy_protegent_seance_qr(self):
        d = self._simuler().data['decision']
        payload = {**self.payload, 'creneau_id': d['creneau_id'], 'salle_id': d['salle_id']}
        with override_settings(GETINJS_V2_EXPERIMENTAL_WRITE=False):
            self.assertEqual(self.client_api.post('/api/edts/v2/bench/placer-ligne/',
                payload, format='json').status_code, 403)
        self.client_api.post('/api/edts/v2/bench/placer-ligne/', payload, format='json')
        aff = AffectationCreneau.objects.get()
        uid = SeanceRegistre.objects.get().uuid
        for route, method, body in (
            (f'/api/edts/affectations/{aff.pk}/', 'delete', None),
            (f'/api/edts/affectations/{aff.pk}/deplacer/', 'post', {'creneau_template_id': self.slot.pk}),
            (f'/api/edts/lmd/items/{aff.pk}/move/', 'post', {'creneau_template_id': self.slot.pk}),
            (f'/api/edts/lmd/items/{aff.pk}/cancel/', 'post', {'motif': 'Essai fictif'}),
            (f'/api/edts/emplois/{aff.emploi_du_temps_id}/publier/', 'post', None),
            (f'/api/edts/emplois/{aff.emploi_du_temps_id}/generer/', 'post', None),
            (f'/api/edts/emplois/{aff.emploi_du_temps_id}/', 'delete', None),
            ('/api/edts/lmd/generate-annee/', 'post',
             {'annee_academique_id': self.annee.pk, 'persister': True}),
            ('/api/edts/lmd/generate-coordinated/', 'post',
             {'annee_academique_id': self.annee.pk, 'persister': True}),
        ):
            result = getattr(self.client_api, method)(route, body or {}, format='json') if method == 'post' else self.client_api.delete(route)
            self.assertEqual(result.status_code, 409, (route, result.data))
        self.assertEqual(SeanceRegistre.objects.get().uuid, uid)
        self.assertEqual(AffectationCreneau.objects.count(), 1)

    def test_lecture_suivi_aggregate_et_non_delegation_worker(self):
        campagne = CampagneGeneration.objects.create(annee_academique=self.annee, libelle='BENCH-ETAT')
        execution = ExecutionCampagne.objects.create(campagne=campagne, numero=1,
            version_calendrier=1, lignes_lues=2, lignes_a_revoir=1)
        url = f'/api/edts/v2/bench/executions/{execution.pk}/'
        self.client_api.force_authenticate(user=self.auditeur)
        res = self.client_api.get(url)
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data['lignes_a_revoir'], 1)
        self.assertFalse(AffectationCreneau.objects.exists())

    def test_mode_production_refuse_v2_meme_flag_experimental_active(self):
        from edts.moteur.application_v2 import appliquer_ligne, proposer_ligne
        decision = proposer_ligne(self.payload_to_travail(), revision=1, jour=self.jour)
        self.assertEqual(decision.statut, 'PLACEE')
        with override_settings(DEBUG=False, GETINJS_V2_EXPERIMENTAL_WRITE=True):
            self.assertEqual(self._simuler().status_code, 403)
            res = self.client_api.post('/api/edts/v2/bench/placer-ligne/',
                {**self.payload, 'creneau_id': decision.creneau_id,
                 'salle_id': decision.salle_id}, format='json')
            self.assertEqual(res.status_code, 403)
            with self.assertRaises(PermissionError):
                appliquer_ligne(self.payload_to_travail(), decision, revision=1)
        self.assertFalse(AffectationCreneau.objects.exists())
        self.assertFalse(SeanceRegistre.objects.exists())

    def payload_to_travail(self):
        from edts.moteur.planification_v2 import TravailSeance
        return TravailSeance(self.annee.pk, self.groupe.pk, 0, 'CM', 1, 120, 20,
            formateur_id=self.formateur.pk, source_confirmee=True,
            source_document='TEST FICTIF')
