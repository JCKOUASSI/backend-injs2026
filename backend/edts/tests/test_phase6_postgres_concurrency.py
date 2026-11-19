"""Concurrence réelle PostgreSQL : à exécuter sur une base de test isolée.

SQLite n'implémente pas le verrou SELECT FOR UPDATE : le skip est volontaire
et ne doit jamais être compté comme validation de la concurrence.
"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier, Event
from unittest import skipUnless
from unittest.mock import patch

from django.db import close_old_connections, connection
from django.test import TransactionTestCase, override_settings

from edts.models import AffectationCreneau
from edts.models_interop import SeanceRegistre
from edts.moteur.application_v2 import appliquer_ligne, proposer_ligne
from edts.tests import test_moteur_v2_phase3 as fixture_module


@skipUnless(connection.vendor == 'postgresql', 'PostgreSQL de test isolé requis ; SQLite non probant')
@override_settings(DEBUG=True, GETINJS_V2_EXPERIMENTAL_WRITE=True)
class ConcurrentBenchTests(TransactionTestCase):
    def setUp(self):
        fixture_module.MoteurV2BenchTests.setUp(self)

    def test_deux_auteurs_meme_cle_un_uuid(self):
        proposition = proposer_ligne(self.travail, revision=1)
        barriere = Barrier(2)

        def tenter():
            close_old_connections()
            try:
                barriere.wait(timeout=10)
                return appliquer_ligne(self.travail, proposition, revision=1)
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futurs = [pool.submit(tenter) for _ in range(2)]
            resultats = [f.result(timeout=30) for f in futurs]
        self.assertEqual(sum(r.statut == 'PLACEE' for r in resultats), 2)
        self.assertEqual(AffectationCreneau.objects.count(), 1)
        self.assertEqual(SeanceRegistre.objects.count(), 1)
        self.assertEqual(SeanceRegistre.objects.get().instantanes.count(), 1)

    def test_deux_groupes_meme_jour_meme_ressource_un_seul_place(self):
        autre = replace(self.travail, groupe_id=self.groupe2.pk, ordinal=2)
        p1 = proposer_ligne(self.travail, revision=1, jour=self.jour)
        p2 = proposer_ligne(autre, revision=1, jour=self.jour)
        self.assertEqual((p1.creneau_id, p1.salle_id), (p2.creneau_id, p2.salle_id))
        barriere = Barrier(2)

        def tenter(travail, proposition):
            close_old_connections()
            try:
                barriere.wait(timeout=10)
                return appliquer_ligne(travail, proposition, revision=1)
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            f1 = pool.submit(tenter, self.travail, p1)
            f2 = pool.submit(tenter, autre, p2)
            resultats = [f1.result(timeout=30), f2.result(timeout=30)]
        self.assertEqual(sum(r.statut == 'PLACEE' for r in resultats), 1)
        self.assertEqual(AffectationCreneau.objects.count(), 1)
        self.assertEqual(SeanceRegistre.objects.count(), 1)

    def test_huit_auteurs_meme_jour_une_salle_sans_conflit(self):
        from scolarite.models import Groupe
        groupes = [self.groupe, self.groupe2] + [Groupe.objects.create(
            annee_academique=self.annee, ref_formation=self.formation,
            niveau=self.niveau, nom=f'BENCH-CONCURRENT-{n}') for n in range(6)]
        travaux = [replace(self.travail, groupe_id=g.pk, ordinal=n + 2)
                   for n, g in enumerate(groupes)]
        choix = [proposer_ligne(t, revision=1, jour=self.jour) for t in travaux]
        self.assertTrue(all(p.statut == 'PLACEE' for p in choix))
        barriere = Barrier(8)

        def tenter(travail, proposition):
            close_old_connections()
            try:
                barriere.wait(timeout=15)
                return appliquer_ligne(travail, proposition, revision=1)
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=8) as pool:
            futurs = [pool.submit(tenter, t, p) for t, p in zip(travaux, choix)]
            decisions = [f.result(timeout=60) for f in futurs]
        self.assertEqual(sum(d.statut == 'PLACEE' for d in decisions), 1)
        self.assertEqual(AffectationCreneau.objects.count(), 1)
        self.assertEqual(SeanceRegistre.objects.count(), 1)

    def test_deux_workers_lease_actif_interdit_double_checkpoint(self):
        from edts.models import CampagneGeneration, ExecutionCampagne, ExecutionLigne
        from edts.moteur.campagnes_v2 import executer_campagne_v2
        campagne = CampagneGeneration.objects.create(annee_academique=self.annee,
                                                     libelle='BENCH-CONCURRENT-LEASE')
        execution = ExecutionCampagne.objects.create(campagne=campagne, numero=1)
        entre, reprise = Event(), Event()

        def pause_apres_lease():
            entre.set()
            if not reprise.wait(timeout=15):
                raise TimeoutError('Premier worker figé au banc de concurrence.')
            return {}

        def tenter():
            close_old_connections()
            try:
                return executer_campagne_v2(execution.pk, travaux=[self.travail], revision=1)
            finally:
                connection.close()

        with patch('edts.moteur.contraintes.politique_souples', side_effect=pause_apres_lease):
            with ThreadPoolExecutor(max_workers=2) as pool:
                premier = pool.submit(tenter)
                self.assertTrue(entre.wait(timeout=15))
                second = pool.submit(tenter)
                try:
                    with self.assertRaisesRegex(RuntimeError, 'worker actif'):
                        second.result(timeout=15)
                finally:
                    reprise.set()
                self.assertEqual(premier.result(timeout=30)['lignes_placees'], 1)
        self.assertEqual(ExecutionLigne.objects.filter(execution=execution).count(), 1)
        self.assertEqual(AffectationCreneau.objects.count(), 1)
        self.assertEqual(SeanceRegistre.objects.count(), 1)

    def test_persistance_legacy_attend_placement_v2_puis_refuse(self):
        """Le contrôle en lecture seule ne suffisait pas contre une course SQL."""
        import time
        from django.db import transaction
        from edts.models import EmploiDuTemps
        from edts.moteur.publication import persister_plan
        from edts.moteur.qr_v2 import assurer_occurrence

        legacy = EmploiDuTemps.objects.create(annee_academique=self.annee,
            population_type='GROUPE', population_id=self.groupe2.pk,
            statut='BROUILLON', semaine_debut=1, semaine_fin=1)
        proposition = proposer_ligne(self.travail, revision=1, jour=self.jour)
        self.assertEqual(proposition.statut, 'PLACEE')
        v2_verrouille, liberation = Event(), Event()

        def pause_qr(affectation):
            # Le placement détient le verrou de l'année mais n'a pas commité.
            v2_verrouille.set()
            if not liberation.wait(timeout=15):
                raise TimeoutError('Placement v2 bloqué pendant le test.')
            return assurer_occurrence(affectation)

        def placer():
            close_old_connections()
            try:
                return appliquer_ligne(self.travail, proposition, revision=1)
            finally:
                connection.close()

        def persister():
            close_old_connections()
            try:
                with transaction.atomic():
                    return persister_plan(legacy, [], remplacer=True)
            finally:
                connection.close()

        with patch('edts.moteur.qr_v2.assurer_occurrence', side_effect=pause_qr):
            with ThreadPoolExecutor(max_workers=2) as pool:
                premier = pool.submit(placer)
                try:
                    self.assertTrue(v2_verrouille.wait(timeout=15))
                    second = pool.submit(persister)
                    # Observer le verrou PostgreSQL plutôt que supposer que le
                    # thread a démarré après un simple délai arbitraire.
                    debut = time.monotonic()
                    bloque = False
                    while time.monotonic() - debut < 8:
                        with connection.cursor() as curseur:
                            curseur.execute("SELECT EXISTS (SELECT 1 FROM pg_stat_activity "
                                "WHERE datname=current_database() AND wait_event_type='Lock')")
                            bloque = curseur.fetchone()[0]
                        if bloque or second.done():
                            break
                        time.sleep(0.05)
                    self.assertTrue(bloque, 'La persistance legacy doit attendre le verrou v2.')
                finally:
                    liberation.set()
                self.assertEqual(premier.result(timeout=20).statut, 'PLACEE')
                with self.assertRaisesRegex(ValueError, 'QR_V2_CHEMIN_HERITE_REFUSE'):
                    second.result(timeout=20)
        self.assertEqual(AffectationCreneau.objects.count(), 1)
        registre = SeanceRegistre.objects.get()
        self.assertEqual(registre.affectation_id, AffectationCreneau.objects.get().pk)
        self.assertTrue(AffectationCreneau.objects.get().actif)
