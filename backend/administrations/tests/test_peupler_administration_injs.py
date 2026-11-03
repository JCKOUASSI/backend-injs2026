"""Peuplement Administration INJS : organigramme, comptes fictifs, archives.

La commande est volontairement déterministe (données fictives étiquetées
« démo ») : ces tests verrouillent ses compteurs, son idempotence et la
chaîne des archives pédagogiques (notes validées + cahier d'appel).
"""
from django.core.management import call_command
from django.test import TestCase

from administrations.models import (
    Courrier, Departement, Direction, DocumentOfficiel, Mission,
    ReunionCommission,
)
from authentication.models import User
from formations.models import (
    Module, NoteModule, Participant, Secretariat, SessionModule,
)
from presences.models import Pointage
from ressources_humaines.models import Agent, Service


class PeuplerAdministrationInjsTests(TestCase):
    def test_peuplement_complet_et_idempotent(self):
        call_command('peupler_administration_injs')
        call_command('peupler_administration_injs')  # seconde passe : aucun doublon

        self.assertEqual(Direction.objects.count(), 8)
        self.assertEqual(Departement.objects.count(), 15)
        self.assertEqual(Service.objects.count(), 16)
        self.assertEqual(Secretariat.objects.count(), 3)
        self.assertEqual(Courrier.objects.count(), 14)
        self.assertEqual(DocumentOfficiel.objects.count(), 10)
        self.assertEqual(ReunionCommission.objects.count(), 10)
        self.assertEqual(Mission.objects.count(), 8)
        # Aucun montant inventé.
        self.assertEqual(Mission.objects.exclude(budget=0).count(), 0)

        # Profils fictifs : rôles couverts et responsables désignés.
        self.assertEqual(
            User.objects.filter(username__startswith='demo.').count(), 47)
        self.assertEqual(
            Direction.objects.filter(responsable__isnull=False).count(), 8)
        directeur = User.objects.get(username='demo.dir.dg')
        self.assertEqual(directeur.role, User.Role.DIRECTION)
        self.assertTrue(directeur.check_password('DemoInjs2026!'))
        self.assertTrue(directeur.groups.exists())

        # Personnels RH rattachés.
        self.assertEqual(
            Agent.objects.filter(matricule__startswith='PERS-DEMO-').count(), 45)

        # Archives pédagogiques : modules archivés, notes validées
        # verrouillées et cahier d'appel (séances + pointages).
        modules = Module.objects.filter(archived=True)
        self.assertEqual(modules.count(), 2)
        self.assertEqual(Participant.objects.filter(
            matricule__startswith='DEMO-ARCH-').count(), 12)
        self.assertEqual(SessionModule.objects.filter(module__in=modules).count(), 12)
        self.assertEqual(Pointage.objects.filter(session__module__in=modules).count(), 144)
        notes = NoteModule.objects.filter(colonne__module__in=modules)
        self.assertEqual(notes.count(), 48)
        self.assertEqual(notes.filter(verrouillee=True,
                                      statut_validation='VALIDEE').count(), 48)
