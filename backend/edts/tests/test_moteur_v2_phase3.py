"""Phase 3 : essais isolés BENCHMARK, aucune donnée personnelle réelle."""
from datetime import date, timedelta, time

from django.test import TestCase, override_settings

from edts.models import (AffectationCreneau, CampagneGeneration, CreneauTemplate,
                         DisponibiliteHoraire, EmploiDuTemps, ExecutionCampagne,
                         ExecutionLigne, PeriodeAcademique,
                         RevisionCalendrier)
from edts.models_interop import SeanceRegistre
from edts.moteur.application_v2 import appliquer_ligne, deplacer_ligne, proposer_ligne
from edts.moteur.campagnes_v2 import executer_campagne_v2, simuler_campagne_v2, travaux_non_attestes
from edts.moteur.planification_v2 import TravailSeance, JOURS
from formations.models import Formateur, RefFormation, RefSalle, RefSite
from scolarite.models import AnneeAcademique, Groupe, Niveau


@override_settings(DEBUG=True, GETINJS_V2_EXPERIMENTAL_WRITE=True)
class MoteurV2BenchTests(TestCase):
    def setUp(self):
        self.annee = AnneeAcademique.objects.create(
            libelle='BENCHMARK-2098-2099', date_debut=date(2098, 10, 1),
            date_fin=date(2098, 10, 31), fiabilite='A_RENSEIGNER')
        self.formation = RefFormation.objects.create(intitule='BENCH TEST',
            perimetre='INJS', filiere_code='F01', source='BENCH_FICTIF')
        self.niveau = Niveau.objects.create(code='BENCH-L1', libelle='L1 fictif')
        self.groupe = Groupe.objects.create(annee_academique=self.annee,
            ref_formation=self.formation, niveau=self.niveau, nom='BENCH-G1')
        self.groupe2 = Groupe.objects.create(annee_academique=self.annee,
            ref_formation=self.formation, niveau=self.niveau, nom='BENCH-G2')
        self.formateur = Formateur.objects.create(numerobadge='BENCH-F1', nom='FICTIF', prenom='A')
        self.site = RefSite.objects.create(nom='SITE BENCH')
        self.salle = RefSalle.objects.create(site=self.site, nom='S1', capacite=50)
        self.jour = date(2098, 10, 5)
        self.cible = self.jour + timedelta(days=7)
        self.slot = CreneauTemplate.objects.create(jour=JOURS[self.jour.weekday()],
            heure_debut=time(8), heure_fin=time(10))
        self.revision = RevisionCalendrier.objects.create(annee_academique=self.annee, numero=1)
        PeriodeAcademique.objects.create(annee_academique=self.annee,
            revision=self.revision, type='COURS', date_debut=self.annee.date_debut,
            date_fin=self.annee.date_fin, statut_validation='VALIDEE',
            fiabilite='OFFICIEL', source_document='SOURCE DE TEST FICTIVE — jamais institutionnelle')
        self.travail = TravailSeance(self.annee.pk, self.groupe.pk, 0, 'CM', 1,
            120, 20, formateur_id=self.formateur.pk,
            source_confirmee=True, source_document='BENCH FICTIF')

    def test_simulation_ne_persiste_ni_edt_ni_registre(self):
        lignes = list(simuler_campagne_v2([self.travail], revision=1))
        self.assertEqual(lignes[0].statut, 'PLACEE')
        self.assertEqual(AffectationCreneau.objects.count(), 0)
        self.assertEqual(SeanceRegistre.objects.count(), 0)

    def test_simulation_incrementale_ne_duplique_pas_une_ressource(self):
        from dataclasses import replace
        deux = replace(self.travail, groupe_id=self.groupe2.pk, ordinal=2)
        a, b = simuler_campagne_v2([self.travail, deux], revision=1)
        self.assertEqual((a.statut, b.statut), ('PLACEE', 'PLACEE'))
        self.assertNotEqual((a.jour, a.creneau_id, a.salle_id),
                            (b.jour, b.creneau_id, b.salle_id))
        self.assertFalse(AffectationCreneau.objects.exists())

    def test_ecriture_interdite_si_flag_absent(self):
        p = proposer_ligne(self.travail, revision=1)
        with override_settings(GETINJS_V2_EXPERIMENTAL_WRITE=False):
            with self.assertRaises(PermissionError):
                appliquer_ligne(self.travail, p, revision=1)
        self.assertFalse(AffectationCreneau.objects.exists())

    def test_ajout_idempotent_et_deplacement_brouillon_qr(self):
        p = proposer_ligne(self.travail, revision=1)
        self.assertEqual(appliquer_ligne(self.travail, p, revision=1).statut, 'PLACEE')
        uuid_avant = SeanceRegistre.objects.get().uuid
        self.assertEqual(appliquer_ligne(self.travail, p, revision=1).code,
                         'DEJA_PLACEE_QR_A_REVOIR')
        cible = proposer_ligne(self.travail, revision=1, jour=self.cible,
                               exclure_cle=self.travail.cle())
        self.assertEqual(cible.statut, 'PLACEE')
        self.assertEqual(deplacer_ligne(self.travail, cible, revision=1).statut, 'PLACEE')
        aff = AffectationCreneau.objects.get(cle_occurrence_v2=self.travail.cle())
        self.assertEqual(aff.date_seance, self.cible)
        self.assertEqual(AffectationCreneau.objects.count(), 1)
        self.assertEqual(SeanceRegistre.objects.get().uuid, uuid_avant)

    def test_registre_qr_interdit_le_deplacement(self):
        p = proposer_ligne(self.travail, revision=1)
        appliquer_ligne(self.travail, p, revision=1)
        aff = AffectationCreneau.objects.get(cle_occurrence_v2=self.travail.cle())
        registre = SeanceRegistre.objects.get(affectation=aff)
        registre.statut = SeanceRegistre.Statut.PUBLIEE
        registre.save(update_fields=['statut'])
        cible = proposer_ligne(self.travail, revision=1, jour=self.cible,
                               exclure_cle=self.travail.cle())
        self.assertEqual(deplacer_ligne(self.travail, cible, revision=1).code, 'QR_PROTEGE')
        aff.refresh_from_db()
        self.assertEqual(aff.date_seance, p.jour)
        self.assertEqual(SeanceRegistre.objects.count(), 1)

    def test_volume_sans_preuve_et_ancien_placement_sont_a_revoir(self):
        from dataclasses import replace
        self.assertEqual(proposer_ligne(replace(self.travail, source_confirmee=False),
                                        revision=1).code, 'VOLUME_NON_CONFIRME')
        edt = EmploiDuTemps.objects.create(annee_academique=self.annee,
            population_type='GROUPE', population_id=self.groupe.pk, statut='BROUILLON')
        AffectationCreneau.objects.create(emploi_du_temps=edt, creneau_template=self.slot,
            semaine_debut=1, semaine_fin=4, groupe=self.groupe, actif=True)
        self.assertEqual(proposer_ligne(self.travail, revision=1).code, 'PLAGE_HISTORIQUE_AUDIT')

    def test_checkpoint_interruption_reprise_sans_doublon(self):
        campagne = CampagneGeneration.objects.create(annee_academique=self.annee,
            libelle='BENCH-TEST-CAMPAGNE')
        execution = ExecutionCampagne.objects.create(campagne=campagne, numero=1)
        from dataclasses import replace
        second = replace(self.travail, groupe_id=self.groupe2.pk, ordinal=2)
        travaux = [self.travail, second]
        partiel = executer_campagne_v2(execution.pk, travaux=iter(travaux),
                                        revision=1, max_groupes=1)
        self.assertEqual(partiel['etat'], 'INTERROMPU')
        self.assertEqual(ExecutionLigne.objects.count(), 1)
        final = executer_campagne_v2(execution.pk, travaux=iter(travaux), revision=1)
        self.assertEqual(final['etat'], 'TERMINE_AVEC_ANOMALIES')
        self.assertEqual(final['lignes_placees'], 2)
        self.assertEqual(ExecutionLigne.objects.count(), 2)
        self.assertEqual(AffectationCreneau.objects.count(), 2)
        self.assertEqual(SeanceRegistre.objects.count(), 2)  # UUID stables, brouillons non publiables

    def test_erreur_dans_groupe_annule_tout_le_checkpoint(self):
        from dataclasses import replace
        campagne = CampagneGeneration.objects.create(annee_academique=self.annee,
            libelle='BENCH-ROLLBACK')
        execution = ExecutionCampagne.objects.create(campagne=campagne, numero=1)
        travail_invalide = replace(self.travail, annee_id=self.annee.pk + 500, ordinal=2)
        with self.assertRaises(ValueError):
            executer_campagne_v2(execution.pk, travaux=[self.travail, travail_invalide],
                                 revision=1)
        self.assertEqual(ExecutionLigne.objects.count(), 0)
        self.assertEqual(AffectationCreneau.objects.count(), 0)
        execution.refresh_from_db()
        self.assertEqual(execution.lignes_traitees, 0)
        self.assertEqual(executer_campagne_v2(execution.pk, travaux=[self.travail],
                          revision=1)['lignes_placees'], 1)

    def test_calendrier_et_conflit_revalides_a_l_ecriture(self):
        from dataclasses import replace
        autre = replace(self.travail, groupe_id=self.groupe2.pk, ordinal=2)
        premiere = proposer_ligne(self.travail, revision=1)
        perimee = proposer_ligne(autre, revision=1, jour=premiere.jour)
        self.assertEqual((premiere.jour, premiere.creneau_id, premiere.salle_id),
                         (perimee.jour, perimee.creneau_id, perimee.salle_id))
        self.assertEqual(appliquer_ligne(self.travail, premiere, revision=1).statut, 'PLACEE')
        self.assertNotEqual(appliquer_ligne(autre, perimee, revision=1).statut, 'PLACEE')
        self.assertEqual(AffectationCreneau.objects.count(), 1)

    def test_ferie_confirmable_refuse_jour_cible(self):
        PeriodeAcademique.objects.create(annee_academique=self.annee,
            revision=self.revision, type='FERIE', date_debut=self.jour,
            date_fin=self.jour, statut_validation='VALIDEE', fiabilite='OFFICIEL',
            source_document='Férié entièrement fictif pour test isolé')
        self.assertNotEqual(proposer_ligne(self.travail, revision=1).jour, self.jour)
        self.assertNotEqual(proposer_ligne(self.travail, revision=1, jour=self.jour).statut,
                            'PLACEE')
        self.assertFalse(AffectationCreneau.objects.exists())

    def test_indisponibilite_enseignant_est_dure(self):
        dispo = DisponibiliteHoraire.objects.create(annee_academique=self.annee,
            enseignant=self.formateur, jour=JOURS[self.jour.weekday()],
            heure_debut=time(8), heure_fin=time(10), statut='INDISPONIBLE')
        self.assertNotEqual(proposer_ligne(self.travail, revision=1, jour=self.jour).statut,
                            'PLACEE')
        dispo.statut = 'PREFERENCE'
        dispo.save()
        self.assertEqual(proposer_ligne(self.travail, revision=1, jour=self.jour).statut,
                         'PLACEE')

    def test_politique_souple_ponderee_sans_enfreindre_conflit_dur(self):
        from edts.moteur.occupation_v2 import IndexOccupation
        index = IndexOccupation()
        index.ajouter(self.jour, 480, 600, groupe_id=self.groupe.pk)
        active = {'actives': True, 'max_heures_par_jour': 3,
                  'max_heures_consecutives': 3, 'poids_trou': 2,
                  'poids_consecutif': 4, 'poids_surcharge': 5,
                  'penaliser_trous': True}
        self.assertGreater(index.score_souple(self.jour, self.groupe.pk, 660, 780, active), 0)
        self.assertEqual(index.score_souple(self.jour, self.groupe.pk, 660, 780,
                                            {'actives': False}), 0)
        self.assertEqual(index.conflits(self.jour, 590, 610,
                                         groupe_id=self.groupe.pk), ['GROUPE'])

    def test_lease_actif_refuse_un_second_worker(self):
        from django.utils import timezone
        campagne = CampagneGeneration.objects.create(annee_academique=self.annee,
            libelle='BENCH-LEASE')
        execution = ExecutionCampagne.objects.create(campagne=campagne, numero=1,
            worker_id='worker-fictif', lease_jusqua=timezone.now() + timedelta(minutes=5))
        with self.assertRaises(RuntimeError):
            executer_campagne_v2(execution.pk, travaux=[self.travail], revision=1)
        self.assertFalse(AffectationCreneau.objects.exists())

    def test_execution_sans_ligne_ne_pretend_pas_etre_complete(self):
        campagne = CampagneGeneration.objects.create(annee_academique=self.annee,
            libelle='BENCH-AUCUNE-LIGNE')
        execution = ExecutionCampagne.objects.create(campagne=campagne, numero=1)
        resultat = executer_campagne_v2(execution.pk, travaux=iter(()), revision=1)
        self.assertEqual(resultat['etat'], 'TERMINE_AVEC_ANOMALIES')
        execution.refresh_from_db()
        self.assertEqual(execution.anomalies[0]['code'], 'AUCUN_GROUPE_INJS')

    def test_source_db_non_attestee_ne_simule_pas_des_volumes(self):
        travaux = list(travaux_non_attestes(self.annee.pk))
        self.assertEqual(len(travaux), 2)
        self.assertTrue(all(not t.source_confirmee for t in travaux))
        self.assertEqual([x.code for x in simuler_campagne_v2(travaux, revision=1)],
                         ['VOLUME_NON_CONFIRME'] * 2)
        campagne = CampagneGeneration.objects.create(annee_academique=self.annee,
            libelle='BENCH-SANS-PREUVE')
        execution = ExecutionCampagne.objects.create(campagne=campagne, numero=1)
        bilan = executer_campagne_v2(execution.pk, revision=1)
        self.assertEqual(bilan['lignes_a_revoir'], 2)
        self.assertEqual(bilan['etat'], 'TERMINE_AVEC_ANOMALIES')
        self.assertFalse(AffectationCreneau.objects.exists())
