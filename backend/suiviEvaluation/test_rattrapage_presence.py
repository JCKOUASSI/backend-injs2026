"""Crédit des rattrapages inter-cohorte dans le calcul de présence académique."""
from datetime import time
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from formations.models import Formation, Module, ModuleParticipant, Participant, SessionModule
from presences.models import Rattrapage
from presences.rattrapage_service import generer_presence_rattrapage

from .services import (
    _presence_minutes_map,
    calculer_decision,
    calculer_presence_module,
)


def _cohorte(formation, groupe, matricule):
    module = Module.objects.create(
        formation=formation,
        intitule='Droit',
        grade='A4',
        groupe=groupe,
        duree_prevue_heures=Decimal('5'),
        statut=Module.Statut.EN_COURS,
    )
    seance = SessionModule.objects.create(
        module=module,
        date_journee=timezone.localdate(),
        numero=1,
        heure_debut_prevue=time(8, 0),
        heure_fin_prevue=time(13, 0),
    )
    participant = Participant.objects.create(
        matricule=matricule,
        nom='Nom',
        prenom=matricule,
        grade='A4',
        groupe=groupe,
    )
    ModuleParticipant.objects.create(module=module, participant=participant)
    return module, seance, participant


class RattrapagePresenceEvaluationTest(TestCase):
    def setUp(self):
        self.formation = Formation.objects.create(formation='Cycle A')
        self.mod_a, self.seance_a, self.p = _cohorte(self.formation, 'GROUPE 1', 'P001')
        self.mod_b, self.seance_b, self.q = _cohorte(self.formation, 'GROUPE 2', 'Q001')

    def _make_rattrapage(self, *, module_origine=None, seance_manquee=None):
        return Rattrapage.objects.create(
            participant=self.p,
            seance_rattrapage=self.seance_b,
            module_origine=module_origine if module_origine is not None else self.mod_a,
            seance_manquee=seance_manquee if seance_manquee is not None else self.seance_a,
            motif='Absence justifiée',
        )

    def test_rattrapage_credite_module_origine_explicite(self):
        rattrapage = self._make_rattrapage()
        generer_presence_rattrapage(rattrapage)

        hp_origine, _, taux_origine = calculer_presence_module(self.mod_a, self.p)
        hp_accueil, _, _ = calculer_presence_module(self.mod_b, self.p)

        self.assertGreater(hp_origine, 0)
        self.assertIsNotNone(taux_origine)
        self.assertGreater(hp_accueil, 0)

    def test_rattrapage_credite_via_seance_manquee_sans_module_origine(self):
        rattrapage = Rattrapage.objects.create(
            participant=self.p,
            seance_rattrapage=self.seance_b,
            seance_manquee=self.seance_a,
            motif='Absence justifiée',
        )
        generer_presence_rattrapage(rattrapage)

        hp, _, taux = calculer_presence_module(self.mod_a, self.p)
        self.assertGreater(hp, 0)
        self.assertIsNotNone(taux)

    def test_rattrapage_inferé_par_intitulé_sans_origine_explicite(self):
        rattrapage = Rattrapage.objects.create(
            participant=self.p,
            seance_rattrapage=self.seance_b,
            motif='Absence justifiée',
        )
        generer_presence_rattrapage(rattrapage)

        hp, _, taux = calculer_presence_module(self.mod_a, self.p)
        self.assertGreater(hp, 0)
        self.assertIsNotNone(taux)

    def test_rattrapage_inferé_par_cohorte_auditeur(self):
        """Deux modules « Droit » inscrits : crédit sur celui du grade/groupe de l'auditeur."""
        mod_alt = Module.objects.create(
            formation=self.formation,
            intitule='Droit',
            grade='A3',
            groupe='GROUPE 1',
            duree_prevue_heures=Decimal('5'),
            statut=Module.Statut.EN_COURS,
        )
        ModuleParticipant.objects.create(module=mod_alt, participant=self.p)

        rattrapage = Rattrapage.objects.create(
            participant=self.p,
            seance_rattrapage=self.seance_b,
            motif='Absence justifiée',
        )
        generer_presence_rattrapage(rattrapage)

        hp_origine, _, _ = calculer_presence_module(self.mod_a, self.p)
        hp_alt, _, _ = calculer_presence_module(mod_alt, self.p)
        self.assertGreater(hp_origine, 0)
        self.assertEqual(hp_alt, 0)

    def test_presence_map_inclut_rattrapage_pour_decision(self):
        rattrapage = self._make_rattrapage()
        generer_presence_rattrapage(rattrapage)

        presence_map = _presence_minutes_map(self.formation)
        self.assertGreater(presence_map.get((self.mod_a.id, self.p.id), 0), 0)

        decision = calculer_decision(
            self.p,
            self.formation,
            modules=[self.mod_a, self.mod_b],
            presence_map=presence_map,
        )
        self.assertGreater(decision.total_heures_presence or 0, 0)
        self.assertIsNotNone(decision.taux_presence)

    def test_rattrapage_planifie_non_credite(self):
        self._make_rattrapage()
        hp, hprev, taux = calculer_presence_module(self.mod_a, self.p)
        self.assertEqual(hp, 0)
        self.assertGreater(hprev, 0)
        self.assertEqual(taux, 0.0)
