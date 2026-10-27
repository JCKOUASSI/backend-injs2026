"""Tests effectifs — séances comptabilisables et absents notoires."""
from datetime import time, timedelta

from django.test import TestCase
from django.utils import timezone

from formations.models import Formation, Module, ModuleParticipant, Participant, SessionModule
from presences.models import Pointage
from statistiques.bilans import _taux_presence_formation
from statistiques.effectifs import (
    count_sessions_comptabilisables,
    filter_sessions,
    participant_ids_notoires,
    session_ids_for_scope,
)


class FilterSessionsPlannedTest(TestCase):
    """Séances EDT planifiées (sans demarree_le) comptées si la date est atteinte."""

    def test_planned_past_session_counted_without_demarree_le(self):
        formation = Formation.objects.create(formation='FAB test')
        module = Module.objects.create(formation=formation, intitule='M1', grade='A3')
        jour = timezone.localdate()
        SessionModule.objects.create(
            module=module,
            date_journee=jour,
            numero=1,
            heure_debut_prevue=time(8, 0),
            heure_fin_prevue=time(12, 0),
        )
        ids = session_ids_for_scope([module.id], annee=jour.year, mois=jour.month)
        self.assertEqual(len(ids), 1)
        self.assertEqual(filter_sessions(module_ids=[module.id]).count(), 1)

    def test_period_filter_limits_comptabilisable_sessions(self):
        from datetime import timedelta

        formation = Formation.objects.create(formation='FAB test period')
        module = Module.objects.create(formation=formation, intitule='M1', grade='A3')
        jour = timezone.localdate()
        SessionModule.objects.create(
            module=module,
            date_journee=jour,
            numero=1,
            heure_debut_prevue=time(8, 0),
            heure_fin_prevue=time(12, 0),
        )
        future = jour + timedelta(days=30)
        SessionModule.objects.create(
            module=module,
            date_journee=future,
            numero=2,
            heure_debut_prevue=time(8, 0),
            heure_fin_prevue=time(12, 0),
        )
        self.assertEqual(count_sessions_comptabilisables(module_ids=[module.id]), 1)
        self.assertEqual(
            count_sessions_comptabilisables(
                module_ids=[module.id],
                date_debut=jour,
                date_fin=jour,
            ),
            1,
        )

    def test_module_ids_with_sessions_in_period_distinct(self):
        from statistiques.effectifs import module_ids_with_sessions_in_period

        formation = Formation.objects.create(formation='FAB distinct')
        module = Module.objects.create(formation=formation, intitule='M1', grade='A3')
        jour = timezone.localdate()
        for n in (1, 2, 3):
            SessionModule.objects.create(
                module=module,
                date_journee=jour,
                numero=n,
                heure_debut_prevue=time(8, 0),
                heure_fin_prevue=time(10, 0),
            )
        ids = module_ids_with_sessions_in_period(
            [module.id], date_debut=jour, date_fin=jour,
        )
        self.assertEqual(ids, [module.id])


class AbsentsNotoiresTest(TestCase):
    def test_notoire_jamais_badge_et_motif_explicite(self):
        formation = Formation.objects.create(formation='FAB test')
        module = Module.objects.create(formation=formation, intitule='M1', grade='A3')
        p_jamais = Participant.objects.create(
            matricule='NOT-001', nom='Jamais', prenom='Badge', categorie='A',
        )
        p_motif = Participant.objects.create(
            matricule='NOT-002', nom='Motif', prenom='Notoire', categorie='A',
            motif_notoire='Injoignable',
        )
        p_present = Participant.objects.create(
            matricule='NOT-003', nom='Present', prenom='Once', categorie='A',
        )
        ModuleParticipant.objects.create(module=module, participant=p_jamais)
        ModuleParticipant.objects.create(module=module, participant=p_motif)
        ModuleParticipant.objects.create(module=module, participant=p_present)

        jour = timezone.localdate()
        session = SessionModule.objects.create(
            module=module,
            date_journee=jour,
            numero=1,
            heure_debut_prevue=time(8, 0),
            heure_fin_prevue=time(12, 0),
        )
        Pointage.objects.create(
            participant=p_present,
            session=session,
            date_journee=jour,
            timestamp_entree=timezone.now(),
            statut=Pointage.Statut.EN_COURS,
        )

        notoires = participant_ids_notoires(module_ids=[module.id])
        self.assertIn(p_jamais.id, notoires)
        self.assertIn(p_motif.id, notoires)
        self.assertNotIn(p_present.id, notoires)

    def test_pas_notoire_si_module_pas_demarre(self):
        formation = Formation.objects.create(formation='FAB futur')
        future = timezone.localdate() + timedelta(days=30)
        module = Module.objects.create(
            formation=formation,
            intitule='M1 futur',
            grade='A3',
            date_debut=future,
            statut=Module.Statut.PLANIFIEE,
        )
        participant = Participant.objects.create(
            matricule='NOT-FUT', nom='Futur', prenom='Module', categorie='A',
        )
        ModuleParticipant.objects.create(module=module, participant=participant)

        notoires = participant_ids_notoires(module_ids=[module.id])
        self.assertNotIn(participant.id, notoires)

    def test_notoire_des_que_module_demarre_sans_presence(self):
        formation = Formation.objects.create(formation='FAB demarre')
        today = timezone.localdate()
        module = Module.objects.create(
            formation=formation,
            intitule='M1 demarre',
            grade='A3',
            date_debut=today - timedelta(days=1),
            statut=Module.Statut.EN_COURS,
        )
        participant = Participant.objects.create(
            matricule='NOT-DEM', nom='Sans', prenom='Presence', categorie='A',
        )
        ModuleParticipant.objects.create(module=module, participant=participant)

        notoires = participant_ids_notoires(module_ids=[module.id])
        self.assertIn(participant.id, notoires)


class TauxPresenceFormationTest(TestCase):
    def test_taux_presence_uses_valid_pointages_not_missing_statut(self):
        formation = Formation.objects.create(formation='FAB test')
        module = Module.objects.create(formation=formation, intitule='M1', grade='A3')
        participant = Participant.objects.create(
            matricule='PRES-001', nom='Test', prenom='Auditeur', categorie='A',
        )
        ModuleParticipant.objects.create(module=module, participant=participant)
        jour = timezone.localdate()
        session = SessionModule.objects.create(
            module=module,
            date_journee=jour,
            numero=1,
            heure_debut_prevue=time(8, 0),
            heure_fin_prevue=time(12, 0),
        )
        Pointage.objects.create(
            participant=participant,
            session=session,
            date_journee=jour,
            timestamp_entree=timezone.now(),
            statut=Pointage.Statut.TERMINE,
            timestamp_sortie=timezone.now(),
            duree_presence_minutes=60,
        )

        pres = _taux_presence_formation(formation.id, annee=jour.year, mois=jour.month)
        self.assertGreater(pres['taux_presence'], 0)
        self.assertEqual(pres['nb_presents'], 1)
