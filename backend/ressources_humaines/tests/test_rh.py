"""Tests smoke du lot L7 — Ressources Humaines.

Couverture : création agent (matricule unique), affectation historisée,
indisponibilité chevauchante refusée, service/fonction.
"""
import datetime as dt

from django.core.exceptions import ValidationError
from django.test import TestCase

from ressources_humaines import services
from ressources_humaines.models import Agent, DisponibiliteAgent, Fonction, Service


class TestServicesFonctions(TestCase):
    def test_creation_service_fonction(self):
        s = Service.objects.create(nom='Secrétariat')
        f = Fonction.objects.create(intitule='Secrétaire', service=s)
        self.assertEqual(str(f), 'Secrétaire (Secrétariat)')

    def test_creation_agent(self):
        a = services.creer_agent(matricule='RH-001', nom='Kouassi', prenom='Jean')
        self.assertEqual(a.statut, Agent.Statut.ACTIF)
        self.assertEqual(str(a), 'Kouassi Jean')

    def test_matricule_unique(self):
        services.creer_agent(matricule='RH-002', nom='A', prenom='B')
        with self.assertRaises(Exception):
            services.creer_agent(matricule='RH-002', nom='C', prenom='D')


class TestDisponibilites(TestCase):
    def setUp(self):
        self.agent = services.creer_agent(matricule='RH-010', nom='Konan', prenom='Léa')

    def test_indisponibilite_chevauchement_refuse(self):
        services.ajouter_indisponibilite(
            self.agent, DisponibiliteAgent.TypeIndispo.CONGE,
            dt.date(2026, 6, 1), dt.date(2026, 6, 15),
        )
        with self.assertRaises(ValidationError):
            services.ajouter_indisponibilite(
                self.agent, DisponibiliteAgent.TypeIndispo.FORMATION,
                dt.date(2026, 6, 10), dt.date(2026, 6, 20),
            )

    def test_indisponibilite_dates_inverses_refuse(self):
        dispo = DisponibiliteAgent(
            agent=self.agent, type_indispo=DisponibiliteAgent.TypeIndispo.CONGE,
            date_debut=dt.date(2026, 7, 20), date_fin=dt.date(2026, 7, 1),
        )
        with self.assertRaises(ValidationError):
            dispo.full_clean()

    def test_deux_indisponibilites_distinctes_ok(self):
        services.ajouter_indisponibilite(
            self.agent, DisponibiliteAgent.TypeIndispo.CONGE,
            dt.date(2026, 6, 1), dt.date(2026, 6, 15),
        )
        services.ajouter_indisponibilite(
            self.agent, DisponibiliteAgent.TypeIndispo.MISSION,
            dt.date(2026, 7, 1), dt.date(2026, 7, 5),
        )
        self.assertEqual(self.agent.disponibilites.count(), 2)


class TestAffectation(TestCase):
    def test_affectation_historisée(self):
        agent = services.creer_agent(matricule='RH-020', nom='Doe', prenom='Jane')
        service = Service.objects.create(nom='DFRC')
        fonction = Fonction.objects.create(intitule='Chef DFRC', service=service)
        aff1 = services.affecter_agent(agent, fonction, dt.date(2026, 1, 1))
        aff2 = services.affecter_agent(agent, fonction, dt.date(2026, 9, 1))
        self.assertEqual(agent.affectations.count(), 2)
        self.assertEqual(aff2.date_debut, dt.date(2026, 9, 1))