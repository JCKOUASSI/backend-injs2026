"""Finalisation « Présences QR + géolocalisation » — compléments.

Ne duplique aucune couverture existante (`test_seances_edt*`,
`test_qr_isolation`, sanctions heartbeat…) : ce fichier prouve les
**écarts traités** par la finalisation —
endpoint de sortie volontaire, mode/motif de badgeage, type de sortie,
catalogue de motifs du badgeage manuel unitaire, habilitation explicite
des encadrants, codes d'erreur normalisés, évaluation de position du
heartbeat — et les parcours de bout en bout Étudiant sur le canal LMD.
"""
import uuid
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from authentication.models import User
from formations.models import QRToken
from presences import seances_edt_services as service
from presences.models import AuditLog, EncadrantSeance, Pointage

from .test_seances_edt_mobile import MobileSeanceEdtMixin

JOURS = ['LUNDI', 'MARDI', 'MERCREDI', 'JEUDI', 'VENDREDI', 'SAMEDI', 'DIMANCHE']


class SortieVolontaireTests(MobileSeanceEdtMixin, TestCase):
    """POST /api/scan/secure/exit/ — LOT 3."""

    def _sortie(self, user, **extra):
        self.client.force_authenticate(user)
        charge = {'token_qr': self.token, 'device_id': 'device-mobile-01'}
        charge.update(extra)
        return self.client.post('/api/scan/secure/exit/', charge, format='json')

    def test_parcours_complet_etudiant_qr(self):
        """Entrée → heartbeat → sortie volontaire : un seul Pointage tracé."""
        entree = self._scan(self.auditeurs[0], **self._dans_la_zone())
        self.assertEqual(entree.status_code, 201, entree.data)
        self.assertEqual(entree.data['action'], 'ENTREE')
        self.assertEqual(entree.data['mode'], 'QR_AUTOMATIQUE')

        hb = self._heartbeat(self.auditeurs[0], **self._dans_la_zone())
        self.assertEqual(hb.status_code, 200, hb.data)
        self.assertEqual(hb.data['evaluation'], 'DANS_PERIMETRE')

        sortie = self._sortie(self.auditeurs[0], **self._dans_la_zone())
        self.assertEqual(sortie.status_code, 200, sortie.data)
        self.assertEqual(sortie.data['action'], 'SORTIE')
        self.assertEqual(sortie.data['type_sortie'], 'SORTIE_QR')

        self.assertEqual(Pointage.objects.count(), 1)
        pointage = Pointage.objects.get()
        self.assertEqual(pointage.statut, Pointage.Statut.TERMINE)
        self.assertEqual(pointage.mode, Pointage.Mode.QR_AUTOMATIQUE)
        self.assertEqual(pointage.type_sortie,
                         Pointage.TypeSortie.SORTIE_QR)
        self.assertIsNotNone(pointage.duree_presence_minutes)

        actions = list(AuditLog.objects.order_by('timestamp')
                       .values_list('action', flat=True))
        self.assertIn(AuditLog.Action.SCAN_SECURE_ENTREE, actions)
        self.assertIn(AuditLog.Action.SCAN_SECURE_SORTIE, actions)
        audit_sortie = AuditLog.objects.get(
            action=AuditLog.Action.SCAN_SECURE_SORTIE)
        self.assertEqual(audit_sortie.extra.get('type_sortie'), 'SORTIE_QR')
        self.assertEqual(audit_sortie.extra.get('source_position'),
                         'BADGE_SORTIE')

    def test_sortie_sans_entree_refusee_sans_creation(self):
        reponse = self._sortie(self.auditeurs[0])
        self.assertEqual(reponse.status_code, 400, reponse.data)
        self.assertEqual(reponse.data['code_normalise'], 'SORTIE_SANS_ENTREE')
        self.assertEqual(Pointage.objects.count(), 0)

    def test_sortie_exige_une_authentification(self):
        client = APIClient()
        reponse = client.post('/api/scan/secure/exit/',
                              {'token_qr': self.token}, format='json')
        self.assertIn(reponse.status_code, (401, 403))

    def test_double_entree_bloquee_avec_code_normalise(self):
        self.assertEqual(
            self._scan(self.auditeurs[0], **self._dans_la_zone()).status_code, 201)
        self.assertEqual(
            self._scan(self.auditeurs[0], **self._dans_la_zone()).data['action'],
            'SORTIE')
        troisieme = self._scan(self.auditeurs[0], **self._dans_la_zone())
        self.assertEqual(troisieme.status_code, 400, troisieme.data)
        self.assertEqual(troisieme.data['code'], 'ALREADY_SCANNED')  # legacy inchangé
        self.assertEqual(troisieme.data['code_normalise'], 'DOUBLE_ENTREE')
        self.assertIn('action_recommandee', troisieme.data)
        self.assertEqual(Pointage.objects.count(), 1)

    def test_qr_inconnu_rejete(self):
        self.client.force_authenticate(self.auditeurs[0])
        reponse = self.client.post(
            '/api/scan/secure/exit/',
            {'token_qr': str(uuid.uuid4()), 'device_id': 'device-mobile-01'},
            format='json')
        self.assertEqual(reponse.status_code, 400, reponse.data)
        self.assertEqual(reponse.data['code_normalise'], 'QR_INVALIDE')

    def test_inside_geofence_client_ignore(self):
        """Le client ne décide jamais : `inside_geofence: true` hors zone = refus."""
        reponse = self._scan(self.auditeurs[0], inside_geofence=True,
                             **self._hors_zone())
        self.assertEqual(reponse.status_code, 400, reponse.data)
        self.assertEqual(reponse.data['code'], 'OUT_OF_GEOFENCE')
        self.assertEqual(reponse.data['code_normalise'], 'HORS_GEOFENCE')
        self.assertEqual(Pointage.objects.count(), 0)

    def test_etudiant_hors_groupe_refuse_403(self):
        intrus = User.objects.create_user(
            username='intrus', password='x', role='AUDITEUR')
        reponse = self._scan(intrus, **self._dans_la_zone())
        self.assertEqual(reponse.status_code, 403, reponse.data)

    def test_seance_annulee_refusee(self):
        type(self.affectation).objects.filter(pk=self.affectation.pk).update(actif=False)
        reponse = self._scan(self.auditeurs[0], **self._dans_la_zone())
        self.assertEqual(reponse.status_code, 400, reponse.data)
        # Une séance annulée invalide son QR (is_valid) : refus, aucune
        # présence créée — le jeton est traité comme expiré.
        self.assertEqual(reponse.data['code_normalise'], 'QR_EXPIRE')
        self.assertEqual(Pointage.objects.count(), 0)


class HeartbeatEvaluationTests(MobileSeanceEdtMixin, TestCase):
    def test_position_imprecise_signalee_sans_invalider(self):
        self.assertEqual(
            self._scan(self.auditeurs[0], **self._dans_la_zone()).status_code, 201)
        hb = self._heartbeat(self.auditeurs[0], accuracy_m=999,
                             **{k: v for k, v in self._dans_la_zone().items()
                                if k != 'accuracy_m'})
        self.assertEqual(hb.status_code, 200, hb.data)
        self.assertEqual(hb.data['evaluation'], 'POSITION_IMPRECISE')
        pointage = Pointage.objects.get()
        # Règle MOBILE existante : position non conforme = présence
        # conservée mais suspecte (récupérable), jamais invalidée.
        self.assertEqual(pointage.statut, Pointage.Statut.HORS_LIGNE_SUSPECT)
        self.assertIsNone(pointage.timestamp_sortie)
        recupere = self._heartbeat(self.auditeurs[0], **self._dans_la_zone())
        self.assertEqual(recupere.data['evaluation'], 'DANS_PERIMETRE')
        pointage.refresh_from_db()
        self.assertEqual(pointage.statut, Pointage.Statut.EN_COURS)

    def test_hors_perimetre_puis_sortie_automatique_typee(self):
        self.assertEqual(
            self._scan(self.auditeurs[0], **self._dans_la_zone()).status_code, 201)
        premier = self._heartbeat(self.auditeurs[0], **self._hors_zone())
        self.assertEqual(premier.data['evaluation'], 'HORS_PERIMETRE')
        second = self._heartbeat(self.auditeurs[0], **self._hors_zone())
        self.assertEqual(second.data['action'], 'SORTIE_AUTO')
        pointage = Pointage.objects.get()
        self.assertEqual(pointage.statut, Pointage.Statut.SORTIE_AUTO)
        self.assertEqual(
            pointage.type_sortie,
            Pointage.TypeSortie.SORTIE_AUTOMATIQUE_FIN_SEANCE)

    def test_heartbeat_sans_entree_refuse(self):
        reponse = self._heartbeat(self.auditeurs[0], **self._dans_la_zone())
        self.assertEqual(reponse.status_code, 400, reponse.data)
        self.assertEqual(reponse.data['code_normalise'], 'SORTIE_SANS_ENTREE')


class EncadrantSeanceTests(MobileSeanceEdtMixin, TestCase):
    """LOT 7 — habilitation explicite, jamais d'assimilation à l'enseignant."""

    def setUp(self):
        super().setUp()
        self.encadrant = User.objects.create_user(
            username='encadrant-s1', password='x', role='ENCADRANT')

    def test_encadrant_non_habilite_refuse(self):
        reponse = self._scan(self.encadrant, **self._dans_la_zone())
        self.assertEqual(reponse.status_code, 403, reponse.data)
        self.assertEqual(reponse.data['code_normalise'],
                         'ACTIVITE_NON_AUTORISEE')
        self.assertEqual(Pointage.objects.count(), 0)

    def test_encadrant_habilite_badge(self):
        EncadrantSeance.objects.create(
            encadrant=self.encadrant, seance_edt=self.affectation, actif=True)
        reponse = self._scan(self.encadrant, **self._dans_la_zone())
        self.assertEqual(reponse.status_code, 201, reponse.data)
        self.assertEqual(reponse.data['type_personne'], 'encadrant')
        pointage = Pointage.objects.get()
        self.assertEqual(pointage.mode, Pointage.Mode.QR_AUTOMATIQUE)

    def test_habilitation_desactivee_refusee(self):
        EncadrantSeance.objects.create(
            encadrant=self.encadrant, seance_edt=self.affectation, actif=False)
        reponse = self._scan(self.encadrant, **self._dans_la_zone())
        self.assertEqual(reponse.status_code, 403, reponse.data)


class EmargementUnitaireTests(MobileSeanceEdtMixin, TestCase):
    def _unitaire(self, user, charge):
        self.client.force_authenticate(user)
        return self.client.post(
            f'/api/presences/seances-edt/{self.affectation.pk}'
            f'/emargement/unitaire/?date={self.date_seance.isoformat()}',
            charge, format='json')

    def test_badgeage_manuel_unitaire_trace(self):
        reponse = self._unitaire(self.enseignant, {
            'participant': self.participants[0].pk,
            'motif': 'QR_NON_LISIBLE',
        })
        self.assertEqual(reponse.status_code, 201, reponse.data)
        self.assertEqual(reponse.data['mode'], 'MANUEL')
        pointage = Pointage.objects.get()
        self.assertEqual(pointage.mode, Pointage.Mode.MANUEL)
        self.assertEqual(pointage.motif_manuel, 'QR_NON_LISIBLE')
        self.assertEqual(pointage.statut_assiduite,
                         Pointage.StatutAssiduite.PRESENT)

        # La présence manuelle est identifiable sans ambiguïté côté écran.
        self.client.force_authenticate(self.enseignant)
        liste = self.client.get(
            f'/api/presences/seances-edt/{self.affectation.pk}/presences/'
            f'?date={self.date_seance.isoformat()}')
        self.assertEqual(liste.data['presences_manuelles'], 1)
        ligne = next(l for l in liste.data['lignes']
                     if l['participant'] == self.participants[0].pk)
        self.assertEqual(ligne['mode'], 'MANUEL')
        self.assertEqual(ligne['motif_manuel'], 'QR_NON_LISIBLE')

    def test_motif_obligatoire(self):
        reponse = self._unitaire(self.enseignant, {
            'participant': self.participants[0].pk,
        })
        self.assertEqual(reponse.status_code, 400, reponse.data)
        self.assertEqual(reponse.data['code'], 'MOTIF_MANUEL_REQUIS')
        self.assertEqual(Pointage.objects.count(), 0)

    def test_motif_hors_catalogue_refuse(self):
        reponse = self._unitaire(self.enseignant, {
            'participant': self.participants[0].pk, 'motif': 'PARCE_QUE',
        })
        self.assertEqual(reponse.status_code, 400, reponse.data)
        self.assertEqual(reponse.data['code'], 'MOTIF_MANUEL_INCONNU')
        self.assertEqual(Pointage.objects.count(), 0)

    def test_autre_sans_commentaire_refuse(self):
        reponse = self._unitaire(self.enseignant, {
            'participant': self.participants[0].pk, 'motif': 'AUTRE',
        })
        self.assertEqual(reponse.status_code, 400, reponse.data)
        self.assertEqual(reponse.data['code'], 'COMMENTAIRE_MANUEL_REQUIS')
        self.assertEqual(Pointage.objects.count(), 0)

    def test_autre_avec_commentaire_accepte(self):
        reponse = self._unitaire(self.enseignant, {
            'participant': self.participants[0].pk, 'motif': 'AUTRE',
            'commentaire': 'Badge oublié, identité vérifiée sur pièce.',
        })
        self.assertEqual(reponse.status_code, 201, reponse.data)
        pointage = Pointage.objects.get()
        self.assertEqual(pointage.commentaire_manuel,
                         'Badge oublié, identité vérifiée sur pièce.')

    def test_participant_hors_groupe_refuse(self):
        reponse = self._unitaire(self.enseignant, {
            'participant': 999999, 'motif': 'GPS_INDISPONIBLE',
        })
        self.assertEqual(reponse.status_code, 403, reponse.data)
        self.assertEqual(reponse.data['code'], 'NOT_IN_GROUP')

    def test_sans_permission_refuse_403(self):
        reponse = self._unitaire(self.auditeurs[0], {
            'participant': self.participants[0].pk, 'motif': 'GPS_INDISPONIBLE',
        })
        self.assertEqual(reponse.status_code, 403, reponse.data)

    def test_correction_d_un_badge_qr(self):
        """Corriger une présence QR existante exige aussi le motif (unitaire)."""
        self.assertEqual(
            self._scan(self.auditeurs[0], **self._dans_la_zone()).status_code, 201)
        reponse = self._unitaire(self.enseignant, {
            'participant': self.participants[0].pk, 'statut': 'RETARD',
            'motif': 'PROBLEME_TECHNIQUE',
        })
        self.assertEqual(reponse.status_code, 201, reponse.data)
        self.assertTrue(reponse.data['corrige'])
        pointage = Pointage.objects.get()
        self.assertEqual(pointage.statut_assiduite,
                         Pointage.StatutAssiduite.RETARD)
        self.assertEqual(pointage.mode, Pointage.Mode.MANUEL)
        journal = AuditLog.objects.filter(
            action__in=[AuditLog.Action.FORCE_ENTREE, AuditLog.Action.FORCE_SORTIE])
        self.assertTrue(journal.exists())
        self.assertTrue(any(
            (log.extra or {}).get('avant') and (log.extra or {}).get('apres')
            for log in journal))

    def test_emargement_de_masse_pose_le_mode_manuel(self):
        """Le geste de masse conserve sa sémantique (motif libre) mais pose le mode."""
        self.client.force_authenticate(self.enseignant)
        reponse = self.client.post(
            f'/api/presences/seances-edt/{self.affectation.pk}/emargement/'
            f'?date={self.date_seance.isoformat()}',
            {'entries': [{'participant': self.participants[1].pk,
                          'statut': 'PRESENT', 'motif': 'oubli de badge'}]},
            format='json')
        self.assertEqual(reponse.status_code, 201, reponse.data)
        pointage = Pointage.objects.get(participant=self.participants[1])
        self.assertEqual(pointage.mode, Pointage.Mode.MANUEL)


class AutoclotureEtHistoriqueTests(MobileSeanceEdtMixin, TestCase):
    def test_autocloture_type_les_sorties(self):
        self.assertEqual(
            self._scan(self.auditeurs[0], **self._dans_la_zone()).status_code, 201)
        resume = service.auto_clore(None, self.affectation, self.date_seance)
        self.assertEqual(resume['pointages_clotures'], 1)
        pointage = Pointage.objects.get(participant=self.participants[0])
        self.assertEqual(pointage.statut, Pointage.Statut.SORTIE_AUTO)
        self.assertEqual(
            pointage.type_sortie,
            Pointage.TypeSortie.SORTIE_AUTOMATIQUE_FIN_SEANCE)
        absent = Pointage.objects.get(participant=self.participants[1])
        self.assertEqual(absent.statut_assiduite,
                         Pointage.StatutAssiduite.ABSENT)
        self.assertIsNone(absent.type_sortie)
        self.assertIsNone(absent.mode)  # ligne système : pas un badgeage

    def test_seances_du_jour_sans_authentification(self):
        reponse = APIClient().get(
            f'/api/presences/seances-edt/du-jour/?date={self.date_seance.isoformat()}')
        self.assertIn(reponse.status_code, (401, 403))

    def test_historique_personnel_contient_la_seance(self):
        self.assertEqual(
            self._scan(self.auditeurs[0], **self._dans_la_zone()).status_code, 201)
        self.client.force_authenticate(self.auditeurs[0])
        reponse = self.client.get('/api/me/historique/')
        self.assertEqual(reponse.status_code, 200, reponse.data)
        pointages = reponse.data.get('pointages') or []
        self.assertTrue(any(
            ligne.get('canal') == 'EDT_LMD' and ligne.get('statut') == 'EN_COURS'
            for ligne in pointages), reponse.data)


class JournalAuditLimiteTests(TestCase):
    """GET /api/audit-logs/?limite= — plafond d'extraction explicite.

    L'écran d'audit du hub « Présences QR » charge explicitement
    200 événements ; le défaut historique (500) reste inchangé pour les
    autres consommateurs (tableau de bord : comptages, derniers
    pointages).
    """

    def setUp(self):
        self.client = APIClient()
        self.dfrc = User.objects.create_user(
            username='admin-audit', password='x', role='ADMIN')
        for i in range(5):
            AuditLog.objects.create(
                action=AuditLog.Action.SCAN_HEARTBEAT,
                acteur_label='Test', cible_numero=f'MAT{i:03d}')

    def _get(self, suffixe=''):
        self.client.force_authenticate(self.dfrc)
        return self.client.get(f'/api/audit-logs/{suffixe}')

    def test_limite_explicite_200_et_plafonds(self):
        reponse = self._get('?limite=2')
        self.assertEqual(reponse.status_code, 200, reponse.data)
        self.assertEqual(reponse.data['count'], 2)
        self.assertEqual(len(reponse.data['results']), 2)

        # Défaut historique inchangé : tout le journal (plafond 500).
        reponse = self._get()
        self.assertEqual(reponse.data['count'], 5)

        # Valeur invalide ignorée, valeur excessive plafonnée — jamais d'erreur.
        self.assertEqual(self._get('?limite=abc').data['count'], 5)
        self.assertEqual(self._get('?limite=9999').data['count'], 5)
