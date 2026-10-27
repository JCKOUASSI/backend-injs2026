"""Empilement canal mobile : QR de séance LMD servi par les endpoints existants.

Les endpoints mobiles historiques (``/api/scan/secure/``,
``/api/scan/secure/heartbeat/``, ``/api/scan/secure/check-status/``) et le canal
EDT/LMD (``/api/presences/seances-edt/``) ne forment qu'**un seul dispositif** :
un ``QRToken`` rattaché à une séance planifiée (``seance_edt``) est pris en
charge par le service des séances LMD, sans seconde route ni second heartbeat.
"""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from authentication.models import User
from edts.models import AffectationCreneau
from formations.models import Formateur, QRToken, RefSalle, RefSite
from presences.models import AuditLog, Pointage

from .test_seances_edt import LAT_INJS_MARCORY, LON_INJS_MARCORY, SeanceEdtFixtureMixin


class MobileSeanceEdtMixin(SeanceEdtFixtureMixin):
    """Séance LMD du jour + QR ouvert + site géolocalisé (salle « Amphi 1 »)."""

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.enseignant)
        self.token = self.client.post(
            f'/api/presences/seances-edt/{self.affectation.pk}/qr/').data['token']
        self.site = RefSite.objects.create(
            nom='INJS MARCORY — TEST MOBILE',
            geofence_latitude=LAT_INJS_MARCORY,
            geofence_longitude=LON_INJS_MARCORY,
            geofence_rayon_m=200,
        )
        RefSalle.objects.create(site=self.site, nom='Amphi 1')

    # ── positions de test ──
    def _dans_la_zone(self):
        return {'latitude': LAT_INJS_MARCORY + 0.0002, 'longitude': LON_INJS_MARCORY,
                'accuracy_m': 10}

    def _hors_zone(self):
        return {'latitude': LAT_INJS_MARCORY + 0.010, 'longitude': LON_INJS_MARCORY,
                'accuracy_m': 10}

    # ── appels mobiles ──
    def _scan(self, user, device='device-mobile-01', **extra):
        self.client.force_authenticate(user)
        charge = {'token_qr': self.token, **extra}
        if device is not None:
            charge['device_id'] = device
        return self.client.post('/api/scan/secure/', charge, format='json')

    def _heartbeat(self, user, device='device-mobile-01', **extra):
        self.client.force_authenticate(user)
        charge = {'token_qr': self.token, **extra}
        if device is not None:
            charge['device_id'] = device
        return self.client.post('/api/scan/secure/heartbeat/', charge, format='json')

    def _check_status(self, user, **params):
        self.client.force_authenticate(user)
        requete = '&'.join(f'{cle}={valeur}' for cle, valeur in params.items())
        url = f'/api/scan/secure/check-status/?token_qr={self.token}'
        if requete:
            url = f'{url}&{requete}'
        return self.client.get(url)


class ScanMobileSeanceEdtTests(MobileSeanceEdtMixin, TestCase):
    """Badgeage automatique par l'API mobile sur une séance planifiée."""

    def test_auditeur_entree_puis_sortie(self):
        entree = self._scan(self.auditeurs[0], **self._dans_la_zone())
        self.assertEqual(entree.status_code, 201, entree.data)
        self.assertEqual(entree.data['action'], 'ENTREE')
        self.assertEqual(entree.data['canal'], 'EDT_LMD')
        self.assertEqual(entree.data['type_personne'], 'participant')
        self.assertEqual(entree.data['participant']['numero'],
                         self.participants[0].matricule)
        self.assertIsNotNone(entree.data['heure_entree'])

        sortie = self._scan(self.auditeurs[0], **self._dans_la_zone())
        self.assertEqual(sortie.status_code, 200, sortie.data)
        self.assertEqual(sortie.data['action'], 'SORTIE')

        pointage = Pointage.objects.get(pk=entree.data['pointage_id'])
        self.assertEqual(pointage.seance_edt_id, self.affectation.pk)
        self.assertIsNone(pointage.session_id, 'la séance LMD ne porte pas de SessionModule')
        self.assertEqual(pointage.statut, Pointage.Statut.TERMINE)
        self.assertEqual(pointage.annee_academique_id, self.annee.pk)
        self.assertEqual(pointage.groupe_lmd_id, self.groupe.pk)

    def test_auditeur_hors_groupe_refuse(self):
        dehors = User.objects.create_user(username='dehors-mobile', password='x',
                                          role='AUDITEUR')
        reponse = self._scan(dehors, **self._dans_la_zone())
        self.assertEqual(reponse.status_code, 403, reponse.data)
        self.assertEqual(reponse.data['code'], 'NOT_IN_LIST')
        self.assertFalse(Pointage.objects.filter(seance_edt=self.affectation).exists())

    def test_dispositif_oblige_pour_l_auditeur(self):
        # device_id omis → défaut vide → le service réclame le verrou appareil.
        reponse = self._scan(self.auditeurs[0], device=None, **self._dans_la_zone())
        self.assertEqual(reponse.status_code, 400, reponse.data)
        self.assertEqual(reponse.data['code'], 'DEVICE_REQUIRED')

    def test_enseignant_affecte_peut_badger(self):
        """Le compte désigné sur le créneau badge son propre créneau."""
        self.assertEqual(self.affectation.enseignant_id, self.enseignant.pk)
        # Pas de verrou appareil pour l'encadrant : device_id omis.
        reponse = self._scan(self.enseignant, device=None, **self._dans_la_zone())
        self.assertEqual(reponse.status_code, 201, reponse.data)
        self.assertEqual(reponse.data['action'], 'ENTREE')
        self.assertEqual(reponse.data['type_personne'], 'encadrant')
        pointage = Pointage.objects.get(pk=reponse.data['pointage_id'])
        self.assertEqual(pointage.encadrant_id, self.enseignant.pk)
        self.assertIsNone(pointage.participant_id)
        self.assertIsNone(pointage.formateur_id)

    def test_formateur_reference_du_creneau_peut_badger(self):
        """Utilisateur → fiche Formateur → créneau (référence explicite)."""
        utilisateur = User.objects.create_user(username='form-creneau', password='x',
                                               role='FORMATEUR')
        # La synchro de profil crée la fiche Formateur d'office (badge = username).
        fiche = Formateur.objects.get(user=utilisateur)
        AffectationCreneau.objects.filter(pk=self.affectation.pk).update(formateur=fiche)

        reponse = self._scan(utilisateur, device='device-form-01', **self._dans_la_zone())
        self.assertEqual(reponse.status_code, 201, reponse.data)
        self.assertEqual(reponse.data['type_personne'], 'formateur')
        pointage = Pointage.objects.get(pk=reponse.data['pointage_id'])
        self.assertEqual(pointage.formateur_id, fiche.pk)
        self.assertIsNone(pointage.participant_id)

    def test_encadrant_non_affecte_refuse(self):
        autre = User.objects.create_user(username='encadrant-autre', password='x',
                                         role='ENCADRANT')
        reponse = self._scan(autre, device=None, **self._dans_la_zone())
        self.assertEqual(reponse.status_code, 403, reponse.data)
        self.assertEqual(reponse.data['code'], 'UTILISATEUR_NON_AUTORISE')

    def test_hors_perimetre_refuse_sans_pointage(self):
        reponse = self._scan(self.auditeurs[0], **self._hors_zone())
        self.assertEqual(reponse.status_code, 400, reponse.data)
        self.assertEqual(reponse.data['code'], 'OUT_OF_GEOFENCE')
        self.assertFalse(Pointage.objects.filter(seance_edt=self.affectation).exists())
        self.assertTrue(
            AuditLog.objects.filter(action=AuditLog.Action.OUT_OF_GEOFENCE).exists())

    def test_position_absente_refusee_si_site_geolocalise(self):
        reponse = self._scan(self.auditeurs[0])
        self.assertEqual(reponse.status_code, 400, reponse.data)
        self.assertEqual(reponse.data['code'], 'LOCATION_REQUIRED')

    def test_qr_expire_refuse(self):
        QRToken.objects.filter(seance_edt=self.affectation).update(
            expire_at=timezone.now() - timedelta(minutes=1))
        reponse = self._scan(self.auditeurs[0], **self._dans_la_zone())
        self.assertEqual(reponse.status_code, 400, reponse.data)
        self.assertEqual(reponse.data['code'], 'TOKEN_EXPIRED')

    def test_token_inconnu_refuse(self):
        self.client.force_authenticate(self.auditeurs[0])
        reponse = self.client.post('/api/scan/secure/', {
            'token_qr': '11111111-2222-3333-4444-555555555555',
            'device_id': 'device-mobile-01',
        }, format='json')
        self.assertEqual(reponse.status_code, 400, reponse.data)
        self.assertEqual(reponse.data['code'], 'INVALID_TOKEN')


class HeartbeatMobileSeanceEdtTests(MobileSeanceEdtMixin, TestCase):
    """Heartbeat géolocalisé d'un pointage de séance LMD (endpoint existant)."""

    def test_heartbeat_conforme_enregistre_la_position(self):
        self._scan(self.auditeurs[0], **self._dans_la_zone())
        # On simule un dernier heartbeat antérieur : le journal n'écrit un
        # SCAN_HEARTBEAT conforme que périodiquement (interval 600 s).
        Pointage.objects.filter(participant=self.participants[0]).update(
            last_heartbeat_at=timezone.now() - timedelta(minutes=11))
        reponse = self._heartbeat(self.auditeurs[0], **self._dans_la_zone())
        self.assertEqual(reponse.status_code, 200, reponse.data)
        self.assertEqual(reponse.data['canal'], 'EDT_LMD')
        self.assertEqual(reponse.data['statut'], Pointage.Statut.EN_COURS)
        self.assertEqual(reponse.data['outside_geofence_count'], 0)
        pointage = Pointage.objects.get(participant=self.participants[0])
        self.assertIsNotNone(pointage.last_heartbeat_at)
        self.assertIsNotNone(pointage.last_latitude)
        journal = AuditLog.objects.filter(
            action=AuditLog.Action.SCAN_HEARTBEAT).latest('id')
        self.assertEqual(journal.extra['canal'], 'EDT_LMD')

    def test_heartbeat_hors_perimetre_conserve_la_presence(self):
        """Une sortie temporaire du périmètre ne supprime pas la présence."""
        self._scan(self.auditeurs[0], **self._dans_la_zone())
        premier = self._heartbeat(self.auditeurs[0], **self._hors_zone())
        self.assertEqual(premier.status_code, 200, premier.data)
        self.assertEqual(premier.data['geofence_code'], 'OUT_OF_GEOFENCE')
        pointage = Pointage.objects.get(participant=self.participants[0])
        self.assertIsNone(pointage.timestamp_sortie, 'présence conservée')
        self.assertEqual(pointage.statut, Pointage.Statut.HORS_LIGNE_SUSPECT)
        self.assertEqual(pointage.outside_geofence_count, 1)
        self.assertTrue(
            AuditLog.objects.filter(action=AuditLog.Action.SCAN_HEARTBEAT).exists())

        # 2e confirmation consécutive hors zone → sortie automatique (seuil = 2).
        second = self._heartbeat(self.auditeurs[0], **self._hors_zone())
        self.assertEqual(second.status_code, 200, second.data)
        self.assertEqual(second.data['action'], 'SORTIE_AUTO')
        pointage.refresh_from_db()
        self.assertEqual(pointage.statut, Pointage.Statut.SORTIE_AUTO)
        self.assertIsNotNone(pointage.timestamp_sortie)
        self.assertTrue(
            AuditLog.objects.filter(action=AuditLog.Action.OUT_OF_GEOFENCE).exists())
        self.assertTrue(AuditLog.objects.filter(action=AuditLog.Action.AUTO_EXIT).exists())

    def test_heartbeat_sans_entree_refuse(self):
        reponse = self._heartbeat(self.auditeurs[0], **self._dans_la_zone())
        self.assertEqual(reponse.status_code, 400, reponse.data)
        self.assertEqual(reponse.data['code'], 'NO_OPEN_SESSION')

    def test_heartbeat_enseignant_affecte(self):
        self._scan(self.enseignant, device=None, **self._dans_la_zone())
        reponse = self._heartbeat(self.enseignant, device=None, **self._dans_la_zone())
        self.assertEqual(reponse.status_code, 200, reponse.data)
        pointage = Pointage.objects.get(encadrant=self.enseignant)
        self.assertIsNotNone(pointage.last_heartbeat_at)


class CheckStatusMobileSeanceEdtTests(MobileSeanceEdtMixin, TestCase):
    """État de badgeage d'une séance LMD (contrat de l'app mobile)."""

    def test_cycle_absent_en_salle_termine(self):
        absent = self._check_status(self.auditeurs[0], **self._dans_la_zone())
        self.assertEqual(absent.status_code, 200, absent.data)
        self.assertEqual(absent.data['statut'], 'ABSENT')
        self.assertEqual(absent.data['action_suivante'], 'ENTREE')
        self.assertEqual(absent.data['seance_intitule'], 'Physique appliquée')
        self.assertTrue(absent.data['geofence_configured'])
        self.assertTrue(absent.data['in_geofence'])
        self.assertTrue(absent.data['accuracy_ok'])

        self._scan(self.auditeurs[0], **self._dans_la_zone())
        en_salle = self._check_status(self.auditeurs[0], **self._dans_la_zone())
        self.assertEqual(en_salle.data['statut'], 'EN_SALLE')
        self.assertEqual(en_salle.data['action_suivante'], 'SORTIE')
        self.assertIsNotNone(en_salle.data['heure_entree'])

        self._scan(self.auditeurs[0], **self._dans_la_zone())
        termine = self._check_status(self.auditeurs[0])
        self.assertEqual(termine.data['statut'], 'TERMINE')
        self.assertIsNone(termine.data['action_suivante'])

    def test_hors_perimetre_signale_au_client(self):
        reponse = self._check_status(self.auditeurs[0], **self._hors_zone())
        self.assertFalse(reponse.data['in_geofence'])
        self.assertGreater(reponse.data['distance_m'], 200)


class HistoriqueEtDashboardSeanceEdtTests(MobileSeanceEdtMixin, TestCase):
    """Historique mobile (canal EDT/LMD) et compteurs de séance."""

    def test_historique_personnel_expose_le_canal_lmd(self):
        self._scan(self.auditeurs[0], **self._dans_la_zone())
        self.client.force_authenticate(self.auditeurs[0])
        reponse = self.client.get('/api/me/historique/')
        self.assertEqual(reponse.status_code, 200, reponse.data)
        pointages = reponse.data['pointages']
        self.assertEqual(len(pointages), 1)
        item = pointages[0]
        self.assertEqual(item['canal'], 'EDT_LMD')
        self.assertEqual(item['seance_intitule'], 'Physique appliquée')
        self.assertEqual(item['seance_edt']['id'], self.affectation.pk)
        self.assertEqual(item['seance_edt']['groupe'], 'L1-G1')
        self.assertIsNotNone(item['last_heartbeat_at'])

    def test_compteurs_de_seance(self):
        self._scan(self.auditeurs[0], **self._dans_la_zone())
        self.client.force_authenticate(self.enseignant)
        reponse = self.client.get(
            f'/api/presences/seances-edt/{self.affectation.pk}/presences/')
        self.assertEqual(reponse.status_code, 200, reponse.data)
        self.assertEqual(reponse.data['attendus'], 3)
        self.assertEqual(reponse.data['effectif'], 3)
        self.assertEqual(reponse.data['presents'], 1)
        self.assertEqual(reponse.data['non_pointes'], 2)
        self.assertEqual(reponse.data['presences_manuelles'], 0)
        self.assertEqual(reponse.data['anomalies_gps'], 0)

    def test_compteurs_apres_emargement_manuel(self):
        self.client.force_authenticate(self.enseignant)
        reponse = self.client.post(
            f'/api/presences/seances-edt/{self.affectation.pk}/emargement/',
            {'entries': [{'participant': self.participants[0].pk, 'statut': 'PRESENT'},
                         {'participant': self.participants[1].pk, 'statut': 'ABSENT'}],
             'motif': 'Saisie de rentrée (panne réseau)'},
            format='json')
        self.assertEqual(reponse.status_code, 201, reponse.data)

        compteurs = self.client.get(
            f'/api/presences/seances-edt/{self.affectation.pk}/presences/')
        self.assertEqual(compteurs.data['presents'], 1)
        self.assertEqual(compteurs.data['absents'], 1)
        self.assertEqual(compteurs.data['presences_manuelles'], 2)

    def test_emargement_refuse_a_un_auditeur(self):
        self.client.force_authenticate(self.auditeurs[0])
        reponse = self.client.post(
            f'/api/presences/seances-edt/{self.affectation.pk}/emargement/',
            {'entries': [{'participant': self.participants[0].pk, 'statut': 'PRESENT'}],
             'motif': 'Tentative non autorisée'},
            format='json')
        self.assertEqual(reponse.status_code, 403, reponse.data)

    def test_correction_manuelle_sans_motif_refusee(self):
        self._scan(self.auditeurs[0], **self._dans_la_zone())
        self.client.force_authenticate(self.enseignant)
        reponse = self.client.post(
            f'/api/presences/seances-edt/{self.affectation.pk}/emargement/',
            {'entries': [{'participant': self.participants[0].pk, 'statut': 'ABSENT'}]},
            format='json')
        self.assertEqual(reponse.status_code, 400, reponse.data)
        self.assertEqual(reponse.data['code'], 'EMARGEMENT_REFUSE')
        self.assertIn('motif obligatoire', reponse.data['detail'])
