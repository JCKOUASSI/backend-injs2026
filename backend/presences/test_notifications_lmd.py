"""Rapport de refonte, écart n°2 — l'alerte d'absence naît de la séance LMD.

Avant ce lot, les absences d'émargement LMD n'étaient que traçables ; la
génération de notifications restait le fait du déclenchement manuel global
(POST stats/notifications/). Désormais, la clôture automatique vérifie le
cumul d'absences de chaque absent (seuils ConfigAlerteSeuil, comme le flux
legacy) et notifie immédiatement la chaîne Direction/Secrétariat — une fois
par séance, étudiant et niveau (contrainte d'unicité en base).
"""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from parametres.models import Parametre
from presences.models import NotificationAbsence, Pointage
from statistiques.models import ConfigAlerteSeuil

from .test_seances_edt import SeanceEdtFixtureMixin


class AlerteAbsenceClotureTests(SeanceEdtFixtureMixin, TestCase):
    def setUp(self):
        self.client = APIClient()
        ConfigAlerteSeuil.objects.create(
            indicateur=ConfigAlerteSeuil.Indicateur.TAUX_ABSENCE,
            seuil_avertissement=30, seuil_critique=60, actif=True,
        )

    def _absences_passees(self, participant, nb, statut=Pointage.Statut.ABSENT_NON_BADGE):
        """Des lignes d'assiduité antérieures (autres séances de la semaine)."""
        for i in range(nb):
            entree = timezone.now() - timedelta(days=i + 1, hours=8)
            Pointage.objects.create(
                participant=participant, seance_edt=self.affectation,
                date_journee=self.date_seance - timedelta(days=i + 1),
                timestamp_entree=entree,
                timestamp_sortie=None if statut == Pointage.Statut.ABSENT_NON_BADGE
                else entree + timedelta(hours=1),
                statut=statut,
                statut_assiduite=(Pointage.StatutAssiduite.ABSENT
                                  if statut == Pointage.Statut.ABSENT_NON_BADGE
                                  else Pointage.StatutAssiduite.PRESENT),
                annee_academique=self.annee, groupe_lmd=self.groupe,
            )

    def _autoclore(self):
        self.client.force_authenticate(self.admin)
        return self.client.post(
            f'/api/presences/seances-edt/{self.affectation.pk}/autoclore/')

    def test_l_alerte_nait_a_la_cloture(self):
        # MAT000 cumule 2 absences passées ; la clôture en ajoute une (3/3 =
        # 100 % d'absence → CRITIQUE au-delà de 60).
        self._absences_passees(self.participants[0], 2)
        reponse = self._autoclore()
        self.assertEqual(reponse.status_code, 200, reponse.data)
        self.assertGreaterEqual(reponse.data['alertes_absence'], 1)
        notif = NotificationAbsence.objects.filter(
            seance_edt=self.affectation,
            etudiant__participant=self.participants[0]).first()
        self.assertIsNotNone(notif)
        self.assertEqual(notif.niveau, 'CRITIQUE')
        self.assertIn(self.participants[0].matricule, notif.message)
        self.assertIn('Physique appliquée', notif.message)
        # Destinataires : la chaîne habilitée reçoit, pas l'admin (hors liste).
        self.assertTrue(NotificationAbsence.objects.filter(
            destinataire=self.secretaire).exists())
        self.assertFalse(NotificationAbsence.objects.filter(
            destinataire=self.admin).exists())

    def test_seuil_avertissement_vs_critique(self):
        # participants[0] : 2 séances terminées (présent) + l'absence du jour
        # = 33,33 % d'absence → AVERTISSEMENT (≥ 30) mais pas CRITIQUE (< 60).
        # participants[1] : seule l'absence du jour (100 %) → pas d'alerte du
        # tout (aucun passé présent ? non : 1/1 absent → 100 % → CRITIQUE ;
        # on vérifie donc la graduations par étudiant, pas une absence totale).
        self._absences_passees(self.participants[0], 2, statut=Pointage.Statut.TERMINE)
        reponse = self._autoclore()
        self.assertEqual(reponse.status_code, 200, reponse.data)
        notif = NotificationAbsence.objects.filter(
            seance_edt=self.affectation,
            etudiant__participant=self.participants[0]).first()
        self.assertIsNotNone(notif)
        self.assertEqual(notif.niveau, 'AVERTISSEMENT')

    def test_aucun_seuil_config_rien_ne_notifie(self):
        ConfigAlerteSeuil.objects.all().delete()
        self._absences_passees(self.participants[0], 5)
        reponse = self._autoclore()
        self.assertEqual(reponse.status_code, 200, reponse.data)
        self.assertEqual(reponse.data['alertes_absence'], 0)
        self.assertFalse(NotificationAbsence.objects.filter(
            seance_edt=self.affectation).exists())

    def test_idempotence_de_l_alerte(self):
        self._absences_passees(self.participants[0], 2)
        self._autoclore()
        premier = NotificationAbsence.objects.filter(seance_edt=self.affectation).count()
        # Deuxième clôture de la même séance (double clic opérateur) : aucune
        # ligne d'alerte en doublon.
        self._autoclore()
        self.assertEqual(
            NotificationAbsence.objects.filter(seance_edt=self.affectation).count(),
            premier)

    def test_parametre_desactive_l_alerte(self):
        Parametre.objects.create(
            cle='presences.edt.notifier_a_cloture', libelle='Notifier à la clôture',
            categorie='presences', type='bool', valeur='0',
        )
        self._absences_passees(self.participants[0], 2)
        reponse = self._autoclore()
        self.assertEqual(reponse.status_code, 200, reponse.data)
        self.assertEqual(reponse.data['alertes_absence'], 0)
        self.assertFalse(NotificationAbsence.objects.filter(
            seance_edt=self.affectation).exists())


class ReceptionAlertesTests(SeanceEdtFixtureMixin, TestCase):
    """La cloche de l'utilisateur : GET/PATCH /stats/notifications/recues/."""

    def setUp(self):
        self.client = APIClient()
        ConfigAlerteSeuil.objects.create(
            indicateur=ConfigAlerteSeuil.Indicateur.TAUX_ABSENCE,
            seuil_avertissement=30, seuil_critique=60, actif=True,
        )
        for i in range(3):
            Pointage.objects.create(
                participant=self.participants[0], seance_edt=self.affectation,
                date_journee=self.date_seance - timedelta(days=i + 1),
                timestamp_entree=timezone.now() - timedelta(days=i + 1, hours=8),
                statut=Pointage.Statut.ABSENT_NON_BADGE,
                statut_assiduite=Pointage.StatutAssiduite.ABSENT,
                annee_academique=self.annee, groupe_lmd=self.groupe,
            )
        self.client.force_authenticate(self.admin)
        self.client.post(f'/api/presences/seances-edt/{self.affectation.pk}/autoclore/')
        self.client.force_authenticate(self.secretaire)

    def test_liste_recue_et_marquage_lu(self):
        reponse = self.client.get('/api/stats/notifications/recues/')
        self.assertEqual(reponse.status_code, 200)
        self.assertGreaterEqual(len(reponse.data['notifications']), 1)
        self.assertGreaterEqual(reponse.data['non_lues'], 1)
        notif = next(n for n in reponse.data['notifications']
                     if self.participants[0].matricule in n['message'])
        self.assertEqual(notif['niveau'], 'CRITIQUE')
        self.assertIn('created_at', notif)
        identifiant = notif['id']
        marque = self.client.patch(
            '/api/stats/notifications/recues/', {'ids': [identifiant]},
            format='json')
        self.assertEqual(marque.status_code, 200)
        self.assertEqual(marque.data['marquees'], 1)
        # On ne peut marquer que SES propres notifications.
        self.client.force_authenticate(self.enseignant)
        hors_portee = self.client.patch(
            '/api/stats/notifications/recues/', {'ids': [identifiant]},
            format='json')
        self.assertEqual(hors_portee.data['marquees'], 0)

    def test_tout_marquer_lu(self):
        # « Tout marquer lu » de la cloche : PATCH {tout: true} sur la source
        # présences — même contrat que les autres sources.
        avant = self.client.get('/api/stats/notifications/recues/')
        self.assertGreaterEqual(avant.data['non_lues'], 1)
        reponse = self.client.patch('/api/stats/notifications/recues/',
                                    {'tout': True}, format='json')
        self.assertGreaterEqual(reponse.data['marquees'], 1)
        apres = self.client.get('/api/stats/notifications/recues/')
        self.assertEqual(apres.data['non_lues'], 0)
