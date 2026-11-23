"""Cohorte étudiante de démonstration : idempotente et cohérente (L1)."""
from django.core.management import call_command
from django.test import TestCase

from formations.models import Participant, RefFormation
from scolarite.models import (
    AnneeAcademique, DossierEtudiant, InscriptionAdministrative, Maquette,
    Niveau, Semestre, StatutEtudiant,
)


class PeuplerEtudiantsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.annee = AnneeAcademique.objects.create(
            libelle='2026-2027', date_debut='2026-10-01',
            date_fin='2027-07-31', courante=True,
        )
        cls.niveau = Niveau.objects.create(code='L1', libelle='Licence 1', ordre=1)
        Semestre.objects.create(niveau=cls.niveau, numero=1, libelle='S1')
        StatutEtudiant.objects.create(code='ACTIF', libelle='Actif', actif=True)
        cls.formation = RefFormation.objects.create(
            code='STAPS', intitule='LICENCE STAPS',
        )
        Maquette.objects.create(
            ref_formation=cls.formation, annee_academique=cls.annee,
            niveau=cls.niveau, statut=Maquette.Statut.ACTIVE, version=1,
        )

    def test_cree_cohorte_validee_puis_idempotent(self):
        call_command('peupler_etudiants_injs', '--par-formation', '5')
        self.assertEqual(Participant.objects.filter(matricule__startswith='INJS26-').count(), 5)
        self.assertEqual(DossierEtudiant.objects.count(), 5)
        inscriptions = InscriptionAdministrative.objects.all()
        self.assertEqual(inscriptions.count(), 5)
        for inscription in inscriptions:
            self.assertEqual(inscription.statut, InscriptionAdministrative.Statut.VALIDEE)
            self.assertEqual(inscription.niveau, self.niveau)
            self.assertEqual(inscription.ref_formation, self.formation)
            self.assertEqual(
                inscription.etudiant.statut.code, 'ACTIF',
            )
        # Idempotence : une seconde exécution ne crée rien.
        call_command('peupler_etudiants_injs', '--par-formation', '5')
        self.assertEqual(Participant.objects.count(), 5)
        self.assertEqual(InscriptionAdministrative.objects.count(), 5)

    def test_purge_retire_la_cohorte(self):
        call_command('peupler_etudiants_injs', '--par-formation', '3')
        call_command('peupler_etudiants_injs', '--purger')
        self.assertEqual(Participant.objects.filter(matricule__startswith='INJS26-').count(), 0)
        self.assertEqual(InscriptionAdministrative.objects.count(), 0)
