"""Tests Lot C — workflow générique de demandes d'accès.

Machine d'états, séparation demandeur/approbateur, alimentation de la file
de provisionnement EXISTANTE à l'approbation (sans exécution), garde CURP.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APITestCase

from habilitations.models import (
    DemandeAcces,
    JournalHabilitation,
    PropositionProvisionnement,
)
from habilitations.services import demandes_acces as svc

from . import helpers as fx
from . import _u5_fixtures as fxu5

User = get_user_model()
FLAG_CLE = 'flag.curp_ui_admin'
URL = '/api/habilitations/demandes/'


class DemandesAccesServiceTests(TestCase):
    def setUp(self):
        self.demandeur = fx.creer_user('dem-agent')
        self.validateur = fx.creer_user('dem-chef')
        self.role = fx.creer_role('ROLE_DEM', 'Rôle demandé')
        self.compte = fx.creer_compte()

    def creer(self, **kwargs):
        return svc.creer_demande(
            self.demandeur,
            type_demande=DemandeAcces.Type.ATTRIBUTION_ROLE,
            justification=kwargs.pop('justification', 'Besoin opérationnel.'),
            compte_cible=kwargs.pop('compte_cible', self.compte),
            role=kwargs.pop('role', self.role),
            **kwargs,
        )

    def test_creation_justification_obligatoire(self):
        with self.assertRaises(ValueError):
            self.creer(justification='   ')
        demande = self.creer()
        self.assertEqual(demande.statut, DemandeAcces.Statut.BROUILLON)
        self.assertTrue(JournalHabilitation.objects.filter(
            type_evenement='DEMANDE_ACCES_CREEE').exists())

    def test_chemin_nominal_jusqua_approbation(self):
        demande = self.creer()
        svc.appliquer_transition(demande, 'SOUMISE', acteur=self.demandeur)
        svc.appliquer_transition(demande, 'EN_REVUE', acteur=self.validateur)
        svc.appliquer_transition(
            demande, 'APPROUVEE', acteur=self.validateur,
            motif_decision='Validé en commission.',
        )
        demande.refresh_from_db()
        self.assertEqual(demande.statut, DemandeAcces.Statut.APPROUVEE)
        self.assertEqual(demande.approbateur, self.validateur)
        # L'approbation alimente la file EXISTANTE, sans l'exécuter.
        self.assertEqual(demande.proposition.statut,
                         PropositionProvisionnement.Statut.EN_ATTENTE)
        self.assertEqual(demande.proposition.action_proposee,
                         PropositionProvisionnement.Action.ATTRIBUTUER_ROLE
                         if hasattr(PropositionProvisionnement.Action,
                                    'ATTRIBUTUER_ROLE')
                         else PropositionProvisionnement.Action.ATTRIBUER_ROLE)
        self.assertEqual(
            PropositionProvisionnement.objects.count(), 1,
        )

    def test_transitions_interdites(self):
        demande = self.creer()
        with self.assertRaises(svc.TransitionIllegale):
            svc.appliquer_transition(demande, 'APPROUVEE', acteur=self.validateur)
        svc.appliquer_transition(demande, 'SOUMISE', acteur=self.demandeur)
        with self.assertRaises(svc.TransitionIllegale):
            # BROUILLON impossible depuis SOUMISE.
            svc.appliquer_transition(demande, 'BROUILLON',
                                     acteur=self.demandeur)
        svc.appliquer_transition(demande, 'ANNULEE', acteur=self.demandeur)
        with self.assertRaises(svc.TransitionIllegale):
            # État terminal : aucune re-transition (idempotence par refus).
            svc.appliquer_transition(demande, 'SOUMISE', acteur=self.demandeur)

    def test_auto_approbation_interdite(self):
        demande = self.creer()
        svc.appliquer_transition(demande, 'SOUMISE', acteur=self.demandeur)
        with self.assertRaises(ValueError):
            svc.appliquer_transition(demande, 'APPROUVEE',
                                     acteur=self.demandeur)

    def test_refus_sans_motif_interdit(self):
        demande = self.creer()
        svc.appliquer_transition(demande, 'SOUMISE', acteur=self.demandeur)
        with self.assertRaises(ValueError):
            svc.appliquer_transition(demande, 'REFUSEE',
                                     acteur=self.validateur)
        svc.appliquer_transition(demande, 'REFUSEE', acteur=self.validateur,
                                 motif_decision='Non conforme au besoin.')
        demande.refresh_from_db()
        self.assertEqual(demande.statut, DemandeAcces.Statut.REFUSEE)
        self.assertTrue(JournalHabilitation.objects.filter(
            type_evenement='DEMANDE_ACCES_REFUSEE').exists())

    def test_permission_directe_approuvee_sans_provisionnement(self):
        perm = fx.creer_permission('scol', 'note', 'valider',
                                   criticite='CRITIQUE')
        demande = svc.creer_demande(
            self.demandeur,
            type_demande=DemandeAcces.Type.PERMISSION_DIRECTE,
            justification='Substitution ponctuelle.',
            compte_cible=self.compte,
            permission=perm,
        )
        svc.appliquer_transition(demande, 'SOUMISE', acteur=self.demandeur)
        svc.appliquer_transition(demande, 'APPROUVEE', acteur=self.validateur,
                                 motif_decision='OK.')
        demande.refresh_from_db()
        # Aucune proposition de provisionnement pour une permission directe :
        # l'application passe par l'écran Dérogations existant.
        self.assertIsNone(demande.proposition)
        self.assertEqual(PropositionProvisionnement.objects.count(), 0)


class DemandesAccesApiTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin-dem', password='Mot#2026x', role='ADMIN',
        )
        self.admin2 = User.objects.create_user(
            username='admin-dem-2', password='Mot#2026x', role='ADMIN',
        )
        self.simple = User.objects.create_user(
            username='simple-dem', password='Mot#2026x', role='SECRETARIAT',
        )
        fxu5.positionner_flag(FLAG_CLE, True)
        self.role = fx.creer_role('ROLE_API_DEM', 'Rôle API demandes')
        self.compte = fx.creer_compte()

    def tearDown(self):
        from django.core.cache import cache
        cache.clear()
        super().tearDown()

    def test_garde_401_et_403(self):
        self.assertEqual(self.client.get(URL).status_code, 401)
        self.client.force_authenticate(self.simple)
        self.assertEqual(self.client.get(URL).status_code, 403)

    def test_cycle_complet_via_api(self):
        self.client.force_authenticate(self.admin)
        creee = self.client.post(URL, {
            'type_demande': 'ATTRIBUTION_ROLE',
            'justification': 'Remplacement durant congé.',
            'compte_cible': self.compte.pk,
            'role': self.role.pk,
        }, format='json')
        self.assertEqual(creee.status_code, 201)
        identifiant = creee.json()['id']

        soumise = self.client.post(f'{URL}{identifiant}/action/',
                                   {'action': 'soumettre'}, format='json')
        self.assertEqual(soumise.json()['statut'], 'SOUMISE')

        # En revue, revenir à SOUMISE est interdit → 409.
        self.client.post(f'{URL}{identifiant}/action/',
                         {'action': 'revue'}, format='json')
        illegale = self.client.post(f'{URL}{identifiant}/action/',
                                    {'action': 'soumettre'}, format='json')
        self.assertEqual(illegale.status_code, 409)

        # Un SECOND validateur décide (auto-approbation interdite).
        self.client.force_authenticate(self.admin2)
        approuvee = self.client.post(f'{URL}{identifiant}/action/', {
            'action': 'approuver', 'motif_decision': 'Validé.',
        }, format='json')
        self.assertEqual(approuvee.status_code, 200)
        self.assertEqual(approuvee.json()['statut'], 'APPROUVEE')
        self.assertIsNotNone(approuvee.json()['provisionnement'])

        # Détail + liste filtrée.
        detail = self.client.get(f'{URL}{identifiant}/')
        self.assertEqual(detail.json()['role'], 'ROLE_API_DEM')
        liste = self.client.get(f'{URL}?statut=APPROUVEE')
        self.assertEqual(liste.json()['count'], 1)

    def test_action_inconnue_400_et_creation_invalide_400(self):
        self.client.force_authenticate(self.admin)
        raz = self.client.post(URL, {
            'type_demande': 'ATTRIBUTION_ROLE', 'justification': 'x',
            'role': self.role.pk, 'compte_cible': self.compte.pk,
        }, format='json')
        identifiant = raz.json()['id']
        inconnue = self.client.post(f'{URL}{identifiant}/action/',
                                    {'action': 'zapper'}, format='json')
        self.assertEqual(inconnue.status_code, 400)
        invalide = self.client.post(URL, {
            'type_demande': 'ATTRIBUTION_ROLE', 'justification': 'x',
        }, format='json')
        self.assertEqual(invalide.status_code, 400)

    def test_demande_inconnue_404(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get(f'{URL}999999/').status_code, 404)
