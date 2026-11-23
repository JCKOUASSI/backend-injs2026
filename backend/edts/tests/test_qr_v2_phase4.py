"""Contrat QR v2 sur scénarios fictifs, sans personne réelle ni production."""
from dataclasses import replace

from django.test import TestCase, override_settings
from django.utils import timezone

from edts.models import AffectationCreneau, InscriptionImportee
from edts.models_interop import (SalleGeolocalisation, SeanceEvenement,
    SeanceHistorique, SeanceInstantaneAttendus, SeanceRegistre)
from edts.moteur.application_v2 import (appliquer_ligne, deplacer_ligne,
    proposer_ligne, reprogrammer_ligne)
from edts.moteur.interop_presences import transitionner
from edts.moteur.qr_v2 import IntegrationQRBloquee, assurer_occurrence, BASE_IMPORTEE
from presences.models import Pointage
from edts.tests.test_moteur_v2_phase3 import MoteurV2BenchTests


@override_settings(DEBUG=True, GETINJS_V2_EXPERIMENTAL_WRITE=True)
class IntegrationQRV2Tests(TestCase):
    def setUp(self):
        # Reprendre exclusivement la fixture fictive déjà testée en phase 3.
        MoteurV2BenchTests.setUp(self)

    def _inscrire(self, numero, *, statut='INSCRIT'):
        return InscriptionImportee.objects.create(
            annee_academique=self.annee, ref_formation=self.formation,
            niveau=self.niveau, groupe=self.groupe,
            matricule=f'BENCH-ETU-{numero}', nom='FICTIF', prenoms=f'Numéro {numero}',
            statut=statut, fichier='BENCH_NON_IMPORTABLE')

    def _autre_jour(self, proposition):
        # Le tie-break dépend des PK : sous PostgreSQL les séquences ne sont
        # pas remises à zéro entre TestCase. Toujours choisir un autre dimanche.
        return self.cible if proposition.jour != self.cible else self.jour

    def _placer(self):
        p = proposer_ligne(self.travail, revision=1)
        self.assertEqual(appliquer_ligne(self.travail, p, revision=1).statut, 'PLACEE')
        return p, AffectationCreneau.objects.get(cle_occurrence_v2=self.travail.cle())

    def test_cree_registre_et_instantane_sans_faux_participants_et_rejeu(self):
        self._inscrire(1)
        self._inscrire(2)
        self._inscrire(3, statut='RADIE')
        p, aff = self._placer()
        registre = SeanceRegistre.objects.get(affectation=aff)
        self.assertEqual(registre.cle_metier, self.travail.cle())
        self.assertEqual(registre.statut, 'BROUILLON')
        self.assertIsNone(registre.seance_origine_id)
        instantane = registre.instantanes.get()
        self.assertEqual((instantane.date_seance, instantane.effectif, instantane.base_calculee),
                         (p.jour, 2, BASE_IMPORTEE))
        self.assertEqual(instantane.participants, [])  # aucun participant_id inventé
        avant = (registre.uuid, SeanceHistorique.objects.count(), SeanceEvenement.objects.count())
        self.assertEqual(appliquer_ligne(self.travail, p, revision=1).statut, 'PLACEE')
        registre.refresh_from_db()
        self.assertEqual((registre.uuid, SeanceHistorique.objects.count(),
                          SeanceEvenement.objects.count()), avant)
        self.assertEqual(SeanceInstantaneAttendus.objects.count(), 1)
        self.assertEqual(AffectationCreneau.objects.count(), 1)

    def test_effectif_change_mais_instantane_historique_ne_change_pas(self):
        self._inscrire(1)
        p, aff = self._placer()
        registre = SeanceRegistre.objects.get(affectation=aff)
        self._inscrire(2)
        resultat = assurer_occurrence(aff)
        self.assertIn('QR_INSTANTANE_FIGE_EFFECTIF_CHANGE', resultat.anomalies)
        self.assertEqual(registre.instantanes.get().effectif, 1)
        self.assertEqual(registre.instantanes.count(), 1)

    def test_geolocalisation_absente_est_anomalie_explicite(self):
        _, aff = self._placer()
        resultat = assurer_occurrence(aff)
        self.assertIn('QR_GEOLOCALISATION_NON_CONFIGUREE', resultat.anomalies)
        SalleGeolocalisation.objects.create(salle=self.salle, actif=True,
            statut_configuration='CONFIGUREE', latitude='5.1234567', longitude='-4.1234567')
        self.assertNotIn('QR_GEOLOCALISATION_NON_CONFIGUREE',
                         assurer_occurrence(aff).anomalies)

    def test_ancien_point_entree_qr_conserve_la_cle_v2(self):
        from edts.moteur.interop_presences import assurer_registre, reconcilier_emploi_du_temps
        _, aff = self._placer()
        registre = SeanceRegistre.objects.get(affectation=aff)
        repris, cree = assurer_registre(aff)
        self.assertFalse(cree)
        self.assertEqual(repris.uuid, registre.uuid)
        reconcilier_emploi_du_temps(aff.emploi_du_temps)
        self.assertEqual(SeanceRegistre.objects.count(), 1)
        self.assertEqual(registre.cle_metier, aff.cle_occurrence_v2)

    def test_seance_sans_salle_signalee_sans_creer_de_faux_gps(self):
        from edts.models import EmploiDuTemps
        edt = EmploiDuTemps.objects.create(annee_academique=self.annee,
            population_type='GROUPE', population_id=self.groupe.pk,
            statut='BROUILLON', semaine_debut=1, semaine_fin=1)
        aff = AffectationCreneau.objects.create(emploi_du_temps=edt,
            creneau_template=self.slot, semaine_debut=1, semaine_fin=1,
            groupe=self.groupe, date_seance=self.jour,
            cle_occurrence_v2='c' * 64, minute_debut=480, minute_fin=600)
        resultat = assurer_occurrence(aff)
        self.assertIn('QR_SALLE_ABSENTE', resultat.anomalies)
        self.assertEqual(SeanceRegistre.objects.count(), 1)

    def test_publication_v2_refuse_meme_force_sans_rapprochement(self):
        from edts.moteur.publication import publier_emploi_du_temps
        _, aff = self._placer()
        registre = SeanceRegistre.objects.get(affectation=aff)
        res = publier_emploi_du_temps(aff.emploi_du_temps_id, force=True)
        self.assertFalse(res['publie'])
        self.assertEqual(res['motif_echec'], 'QR_V2_NON_PUBLIABLE')
        self.assertIn('QR_V2_PARTICIPANTS_NON_RAPPROCHES', res['detail']['anomalies'])
        aff.emploi_du_temps.refresh_from_db()
        registre.refresh_from_db()
        self.assertEqual(aff.emploi_du_temps.statut, 'BROUILLON')
        self.assertEqual(registre.statut, 'BROUILLON')

    def test_collision_avec_registre_orphelin_ne_reaffecte_rien(self):
        ancien = SeanceRegistre.objects.create(cle_metier=self.travail.cle())
        p = proposer_ligne(self.travail, revision=1)
        with self.assertRaises(IntegrationQRBloquee):
            appliquer_ligne(self.travail, p, revision=1)
        ancien.refresh_from_db()
        self.assertIsNone(ancien.affectation_id)
        self.assertFalse(AffectationCreneau.objects.exists())
        self.assertEqual(SeanceRegistre.objects.count(), 1)
        self.assertFalse(SeanceInstantaneAttendus.objects.exists())

    def test_registre_legacy_attache_n_est_pas_reecrit(self):
        p, aff = self._placer()
        registre = SeanceRegistre.objects.get(affectation=aff)
        ancien_uuid = registre.uuid
        registre.cle_metier = 'a' * 64
        registre.save(update_fields=['cle_metier'])
        with self.assertRaises(IntegrationQRBloquee):
            appliquer_ligne(self.travail, p, revision=1)
        registre.refresh_from_db()
        self.assertEqual((registre.uuid, registre.cle_metier), (ancien_uuid, 'a' * 64))
        self.assertEqual(AffectationCreneau.objects.count(), 1)

    def test_deplacement_brouillon_garde_uuid_et_historique(self):
        self._inscrire(1)
        p, aff = self._placer()
        registre = SeanceRegistre.objects.get(affectation=aff)
        avant = (registre.uuid, registre.instantanes.count(), registre.historique.count())
        cible = proposer_ligne(self.travail, revision=1, jour=self._autre_jour(p),
                               exclure_cle=self.travail.cle())
        self.assertEqual(deplacer_ligne(self.travail, cible, revision=1).statut, 'PLACEE')
        registre.refresh_from_db()
        self.assertEqual(registre.uuid, avant[0])
        self.assertEqual(registre.affectation_id, aff.pk)
        self.assertEqual(registre.version, 2)
        self.assertEqual(registre.instantanes.count(), avant[1] + 1)
        self.assertEqual(registre.historique.count(), avant[2] + 2)
        self.assertEqual(AffectationCreneau.objects.count(), 1)

    def test_pointage_et_publication_interdisent_modification_sans_perte(self):
        p, aff = self._placer()
        registre = SeanceRegistre.objects.get(affectation=aff)
        Pointage.objects.create(seance_edt=aff, timestamp_entree=timezone.now(),
                                date_journee=p.jour, statut='EN_COURS')
        cible = proposer_ligne(self.travail, revision=1, jour=self.cible,
                               exclure_cle=self.travail.cle())
        avant = (registre.uuid, aff.date_seance, registre.historique.count(),
                 SeanceEvenement.objects.count(), Pointage.objects.count())
        self.assertEqual(deplacer_ligne(self.travail, cible, revision=1).code, 'QR_PROTEGE')
        aff.refresh_from_db()
        self.assertEqual((registre.uuid, aff.date_seance, registre.historique.count(),
                          SeanceEvenement.objects.count(), Pointage.objects.count()), avant)
        # Même sans nouveau pointage, une publication doit verrouiller le lieu.
        registre.statut = SeanceRegistre.Statut.PUBLIEE
        registre.save(update_fields=['statut'])
        self.assertEqual(deplacer_ligne(self.travail, cible, revision=1).code, 'QR_PROTEGE')

    def test_reprogrammation_cree_une_seance_liee_sans_effacer_origine(self):
        p, aff = self._placer()
        origine = SeanceRegistre.objects.get(affectation=aff)
        pointage = Pointage.objects.create(seance_edt=aff, timestamp_entree=timezone.now(),
                                           date_journee=p.jour, statut='TERMINE')
        transitionner(origine, 'ANNULEE', motif='Fermeture fictive du test')
        origine.refresh_from_db()
        ancien_uuid = origine.uuid
        nb_hist = origine.historique.count()
        nouveau_travail = replace(self.travail, ordinal=2)
        proposition = proposer_ligne(nouveau_travail, revision=1, jour=self._autre_jour(p))
        self.assertEqual(proposition.statut, 'PLACEE', proposition.code)
        decision = reprogrammer_ligne(ancien_uuid, nouveau_travail, proposition,
                                      revision=1, motif='Rattrapage fictif')
        self.assertEqual(decision.statut, 'PLACEE', decision.code)
        nouveau = SeanceRegistre.objects.exclude(pk=origine.pk).get()
        self.assertEqual(nouveau.seance_origine_id, origine.pk)
        self.assertNotEqual(nouveau.uuid, ancien_uuid)
        self.assertEqual(AffectationCreneau.objects.count(), 2)
        self.assertFalse(SeanceRegistre.objects.filter(affectation__isnull=True).exists())
        self.assertEqual(origine.historique.count(), nb_hist)
        self.assertEqual(origine.uuid, ancien_uuid)
        aff.refresh_from_db()
        pointage.refresh_from_db()
        self.assertEqual((aff.date_seance, pointage.seance_edt_id), (p.jour, aff.pk))
        self.assertEqual(origine.instantanes.count(), 1)
        self.assertEqual(nouveau.evenements.filter(type='SEANCE_REPROGRAMMEE').count(), 1)
        self.assertEqual(reprogrammer_ligne(ancien_uuid, nouveau_travail, proposition,
                           revision=1, motif='Rattrapage fictif').code,
                         'DEJA_REPROGRAMMEE_QR_A_REVOIR')
        self.assertEqual(SeanceEvenement.objects.filter(type='SEANCE_REPROGRAMMEE').count(), 1)

    def test_origine_non_terminale_refuse_reprogrammation(self):
        _, aff = self._placer()
        origine = SeanceRegistre.objects.get(affectation=aff)
        nouveau = replace(self.travail, ordinal=2)
        p = proposer_ligne(nouveau, revision=1, jour=self.cible)
        self.assertEqual(reprogrammer_ligne(origine.uuid, nouveau, p,
                         revision=1, motif='Test').code, 'QR_ORIGINE_NON_REPROGRAMMABLE')
        self.assertEqual(SeanceRegistre.objects.count(), 1)
        self.assertEqual(AffectationCreneau.objects.count(), 1)

    def test_persisteur_heritage_direct_refuse_annee_v2_sans_desactiver_qr(self):
        """Le verrouillage HTTP seul ne protège pas les appels directs du moteur."""
        from edts.models import EmploiDuTemps
        from edts.moteur.publication import persister_plan

        _, aff = self._placer()
        registre = SeanceRegistre.objects.get(affectation=aff)
        uuid_avant = registre.uuid
        legacy = EmploiDuTemps.objects.create(annee_academique=self.annee,
            population_type='GROUPE', population_id=self.groupe2.pk,
            statut='BROUILLON', semaine_debut=1, semaine_fin=1)
        for edt in (aff.emploi_du_temps, legacy):
            for remplacer in (True, False):
                with self.assertRaisesRegex(ValueError, 'QR_V2_CHEMIN_HERITE_REFUSE'):
                    persister_plan(edt, [], remplacer=remplacer)
        aff.refresh_from_db()
        registre.refresh_from_db()
        self.assertTrue(aff.actif)
        self.assertEqual((registre.affectation_id, registre.uuid), (aff.pk, uuid_avant))
        self.assertEqual(SeanceRegistre.objects.count(), 1)
        self.assertEqual(AffectationCreneau.objects.count(), 1)

    def test_base_instantane_modifiee_ne_valide_pas_une_identite_qr(self):
        from edts.moteur.publication import publier_emploi_du_temps
        from edts.moteur.qr_v2 import anomalies_publication_v2
        _, aff = self._placer()
        instantane = SeanceInstantaneAttendus.objects.get()
        instantane.base_calculee = 'PARTICIPANTS_PRETENDUMENT_ATTESTES'
        instantane.save(update_fields=['base_calculee'])
        anomalies = anomalies_publication_v2(aff.emploi_du_temps)
        self.assertEqual(anomalies['QR_V2_ATTESTATION_NON_PROUVEE'], 1)
        resultat = publier_emploi_du_temps(aff.emploi_du_temps_id, force=True)
        self.assertEqual(resultat['motif_echec'], 'QR_V2_NON_PUBLIABLE')
        self.assertFalse(resultat['publie'])

    def test_ponts_vers_presences_refusent_v2_non_attestee_meme_statut_force(self):
        from django.contrib.auth import get_user_model
        from rest_framework.test import APIClient
        from edts.moteur.interop_presences import peut_ouvrir_session_presence
        from presences.seances_edt_services import est_seance_du_jour
        p, aff = self._placer()
        registre = SeanceRegistre.objects.get(affectation=aff)
        transitionner(registre, 'EN_ATTENTE_VALIDATION')
        transitionner(registre, 'VALIDEE')
        with self.assertRaisesRegex(ValueError, 'QR_V2_NON_PUBLIABLE'):
            transitionner(registre, 'PUBLIEE')
        registre.refresh_from_db()
        self.assertEqual(registre.statut, 'VALIDEE')
        self.assertFalse(SeanceEvenement.objects.filter(type='SEANCE_PUBLIEE').exists())
        # Simule une écriture ORM hors workflow, sans lui conférer de légitimité.
        aff.emploi_du_temps.statut = 'PUBLIE'
        aff.emploi_du_temps.save(update_fields=['statut'])
        client = APIClient()
        admin = get_user_model().objects.create_user(username='bench-qr-forced',
            password='x', role=get_user_model().Role.ADMIN)
        client.force_authenticate(user=admin)
        refus = client.post(f'/api/edts/interop/emplois/{aff.emploi_du_temps_id}/reconcilier/')
        self.assertEqual(refus.status_code, 409)
        registre.refresh_from_db()
        self.assertEqual(registre.statut, 'VALIDEE')
        self.assertFalse(SeanceEvenement.objects.filter(type='SEANCE_PUBLIEE').exists())
        registre.statut = 'PUBLIEE'
        registre.save(update_fields=['statut'])
        self.assertFalse(peut_ouvrir_session_presence(registre))
        self.assertFalse(est_seance_du_jour(aff, p.jour))
        liste = client.get('/api/edts/interop/seances-publiees/')
        self.assertEqual(liste.status_code, 200)
        self.assertEqual(liste.data['count'], 0)
        self.assertFalse(Pointage.objects.exists())

    def test_v2_inactive_ne_peut_publier_ni_apparaitre_dans_interop(self):
        from edts.moteur.interop_presences import peut_ouvrir_session_presence
        _, aff = self._placer()
        registre = SeanceRegistre.objects.get(affectation=aff)
        transitionner(registre, 'EN_ATTENTE_VALIDATION')
        transitionner(registre, 'VALIDEE')
        aff.actif = False
        aff.save(update_fields=['actif'])
        aff.emploi_du_temps.statut = 'PUBLIE'
        aff.emploi_du_temps.save(update_fields=['statut'])
        with self.assertRaisesRegex(ValueError, 'QR_V2_NON_PUBLIABLE'):
            transitionner(registre, 'PUBLIEE')
        registre.statut = 'PUBLIEE'  # simulation explicite d'un statut forcé
        registre.save(update_fields=['statut'])
        self.assertFalse(peut_ouvrir_session_presence(registre))
        self.assertFalse(SeanceEvenement.objects.filter(type='SEANCE_PUBLIEE').exists())
