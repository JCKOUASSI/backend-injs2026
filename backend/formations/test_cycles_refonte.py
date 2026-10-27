"""Lot B refonte — cycles du référentiel (modèle 04.4) et lien D3.

Couvre l'API ``/api/formations/ref/formations/`` (champs descripteurs, unicité
du code, suppression protégée), le champ ``Formation.ref_formation`` exposé par
le sérialiseur de sessions, et la commande de réconciliation (idempotence,
création de cycles à la demande, aucune perte).
"""
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from formations.models import Formation, RefFormation

User = get_user_model()
URL_REF = '/api/formations/ref/formations/'


class RefFormationApiTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='ref-admin', password='x', role='ADMIN')
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def test_creation_complete_et_lecture(self):
        reponse = self.client.post(URL_REF, {
            'intitule': 'LICENCE PROFESSIONNELLE FINANCES', 'code': 'lic-fin',
            'type_diplome': 'licence', 'domaine': 'Finances publiques',
            'mention': 'Contrôle budgétaire', 'duree_annees': 3,
            'nb_semestres': 6, 'nb_credites': 180, 'description': 'Cycle L3.',
        }, format='json')
        self.assertEqual(reponse.status_code, 201, reponse.data)
        self.assertEqual(reponse.data['code'], 'LIC-FIN')   # normalisé majuscules
        self.assertEqual(reponse.data['type_diplome'], 'LICENCE')
        self.assertEqual(reponse.data['nb_credites'], 180)
        liste = self.client.get(URL_REF).data
        self.assertEqual(len(liste), 1)
        self.assertEqual(liste[0]['domaine'], 'Finances publiques')

    def test_code_doublon_et_type_inconnu_rejetes(self):
        RefFormation.objects.create(intitule='A', code='DUO')
        reponse = self.client.post(URL_REF, {'intitule': 'B', 'code': 'duo'}, format='json')
        self.assertEqual(reponse.status_code, 400)
        reponse = self.client.post(URL_REF, {'intitule': 'C', 'type_diplome': 'PHD'}, format='json')
        self.assertEqual(reponse.status_code, 400)

    def test_put_conserve_les_champs_absents(self):
        cycle = RefFormation.objects.create(intitule='MASTER APAS', code='MAS-APA',
                                            nb_credites=120)
        reponse = self.client.put(URL_REF + f'{cycle.pk}/', {'actif': False}, format='json')
        self.assertEqual(reponse.status_code, 200, reponse.data)
        cycle.refresh_from_db()
        self.assertEqual(cycle.code, 'MAS-APA')
        self.assertEqual(cycle.nb_credites, 120)
        self.assertFalse(cycle.actif)

    def test_suppression_protegee_si_sessions_reliees(self):
        cycle = RefFormation.objects.create(intitule='DUT SPORT')
        Formation.objects.create(formation='DUT SPORT — Vague 1', ref_formation=cycle)
        reponse = self.client.delete(URL_REF + f'{cycle.pk}/')
        self.assertEqual(reponse.status_code, 409)
        self.assertTrue(RefFormation.objects.filter(pk=cycle.pk).exists())

    def test_ecriture_reservee_dfrc(self):
        # Comportement legacy conservé : le référentiel cycles est DFRC (lecture
        # et écriture) — la refonte ajoute des champs, pas des droits nouveaux.
        secretaire = User.objects.create_user(username='ref-sec', password='x', role='SECRETARIAT')
        self.client.force_authenticate(secretaire)
        reponse = self.client.post(URL_REF, {'intitule': 'NON'}, format='json')
        self.assertEqual(reponse.status_code, 403)


class FormationLienCycleTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='lien-admin', password='x', role='ADMIN')
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def test_creation_session_avec_cycle(self):
        cycle = RefFormation.objects.create(intitule='Cycle Admin de Base')
        reponse = self.client.post('/api/formations/', {
            'formation': 'Formation en Administration de Base — Vague 3',
            'ref_formation': cycle.pk,
        }, format='json')
        self.assertEqual(reponse.status_code, 201, reponse.data)
        formation = Formation.objects.get(pk=reponse.data['id'])
        self.assertEqual(formation.ref_formation_id, cycle.pk)

    def test_session_sans_cycle_toujours_autorisee(self):
        reponse = self.client.post('/api/formations/',
                                   {'formation': 'Session autonome'}, format='json')
        self.assertEqual(reponse.status_code, 201, reponse.data)
        self.assertIsNone(reponse.data['ref_formation'])
        self.assertEqual(reponse.data['ref_formation_intitule'], '')


class ReconciliationCommandTests(TestCase):
    def test_idempotence_et_rattachement(self):
        cycle = RefFormation.objects.create(intitule='FORMATION EN ADMINISTRATION DE BASE')
        f1 = Formation.objects.create(formation='Formation en Administration de Base (FAB) — Vague 1')
        f2 = Formation.objects.create(formation='Formation sans cycle correspondant')
        call_command('reconcilier_formations_cycles', '--creer-cycles-manquants')
        f1.refresh_from_db()
        f2.refresh_from_db()
        self.assertEqual(f1.ref_formation_id, cycle.pk)   # base avant tiret → cycle existant
        self.assertIsNotNone(f2.ref_formation)             # cycle créé à la demande
        # rejouable sans effet de bord
        avant = RefFormation.objects.count()
        call_command('reconcilier_formations_cycles')
        self.assertEqual(RefFormation.objects.count(), avant)
        self.assertEqual(f1.ref_formation_id, cycle.pk)

    def test_dry_run_necrit_rien(self):
        Formation.objects.create(formation='Cycle Inexistant — Vague 9')
        call_command('reconcilier_formations_cycles', '--dry-run', '--creer-cycles-manquants')
        self.assertEqual(RefFormation.objects.count(), 0)
        self.assertFalse(Formation.objects.filter(ref_formation__isnull=False).exists())
