"""Tests bilans — récupération des présences (alignement effectifs.py)."""
from datetime import time, timedelta

from django.test import TestCase
from django.utils import timezone

from formations.models import Formation, Module, ModuleParticipant, Participant, SessionModule
from presences.models import Pointage
from statistiques.bilans import compute_bilan_effectifs_module, _taux_presence_formation


class BilansPresenceTest(TestCase):
    def setUp(self):
        self.formation = Formation.objects.create(formation='FAB bilan')
        self.module = Module.objects.create(
            formation=self.formation,
            intitule='Module test',
            grade='A3',
            date_debut=timezone.localdate() - timedelta(days=1),
            statut=Module.Statut.EN_COURS,
        )
        self.jour = timezone.localdate()
        self.session = SessionModule.objects.create(
            module=self.module,
            date_journee=self.jour,
            numero=1,
            heure_debut_prevue=time(8, 0),
            heure_fin_prevue=time(12, 0),
        )
        self.p_present = Participant.objects.create(
            matricule='BIL-PRES', nom='Present', prenom='Un', categorie='A',
            sexe=Participant.Sexe.MASCULIN,
        )
        self.p_absent = Participant.objects.create(
            matricule='BIL-ABS', nom='Absent', prenom='Un', categorie='A',
            sexe=Participant.Sexe.FEMININ,
        )
        self.p_invalid = Participant.objects.create(
            matricule='BIL-INV', nom='Invalid', prenom='Statut', categorie='A',
        )
        for p in (self.p_present, self.p_absent, self.p_invalid):
            ModuleParticipant.objects.create(module=self.module, participant=p)

        Pointage.objects.create(
            participant=self.p_present,
            session=self.session,
            date_journee=self.jour,
            timestamp_entree=timezone.now(),
            timestamp_sortie=timezone.now(),
            duree_presence_minutes=120,
            statut=Pointage.Statut.TERMINE,
        )
        Pointage.objects.create(
            participant=self.p_invalid,
            session=self.session,
            date_journee=self.jour,
            timestamp_entree=timezone.now(),
            statut=Pointage.Statut.ABSENT_NON_BADGE,
        )

    def test_bilan_module_compte_presence_valide_uniquement(self):
        data = compute_bilan_effectifs_module(self.module.id, annee=self.jour.year)
        self.assertEqual(data['effectifs_auditeurs'], 3)
        self.assertEqual(data['effectifs_presents'], 1)
        self.assertEqual(data['absents'], 2)
        self.assertEqual(data['masculin'], 1)
        self.assertEqual(data['feminin'], 0)

    def test_bilan_module_filtre_par_calendrier(self):
        autre_jour = self.jour + timedelta(days=10)
        SessionModule.objects.create(
            module=self.module,
            date_journee=autre_jour,
            numero=2,
            heure_debut_prevue=time(14, 0),
            heure_fin_prevue=time(18, 0),
        )
        data_jour = compute_bilan_effectifs_module(
            self.module.id, calendrier=self.jour.isoformat(),
        )
        self.assertEqual(data_jour['effectifs_presents'], 1)

        data_vide = compute_bilan_effectifs_module(
            self.module.id, calendrier=autre_jour.isoformat(),
        )
        self.assertIsNone(data_vide)

    def test_bilan_fac_taux_presence_aligne_places(self):
        pres = _taux_presence_formation(
            self.formation.id, annee=self.jour.year,
        )
        self.assertEqual(pres['nb_presents'], 1)
        self.assertEqual(pres['nb_absents'], 2)
        self.assertAlmostEqual(pres['taux_presence'], 1 / 3, places=4)

    def test_bilan_sans_seance_comptabilisable_retourne_none(self):
        formation = Formation.objects.create(formation='FAB futur bilan')
        future = timezone.localdate() + timedelta(days=90)
        module = Module.objects.create(
            formation=formation,
            intitule='Module futur',
            grade='A4',
            groupe='GROUPE 10',
            date_debut=future,
            statut=Module.Statut.PLANIFIEE,
        )
        for i in range(3):
            p = Participant.objects.create(
                matricule=f'FUT-{i}', nom=f'Aud{i}', prenom='Test', categorie='A',
                sexe=Participant.Sexe.MASCULIN if i < 2 else Participant.Sexe.FEMININ,
            )
            ModuleParticipant.objects.create(module=module, participant=p)

        SessionModule.objects.create(
            module=module,
            date_journee=future,
            numero=1,
            heure_debut_prevue=time(8, 0),
            heure_fin_prevue=time(12, 0),
        )

        data = compute_bilan_effectifs_module(module.id, annee=future.year)
        self.assertIsNone(data)
