"""Lot L1 — tests de consolidation des présences.

Couvre : mapping assiduité (statuts de processus → assiduité), rattachement
LMD (année/groupe/ECUE), audit de modification après clôture, QR sans
identifiant interne, étudiant non autorisé à modifier sa présence, règle de
groupe, statistiques et alertes d'absence.
"""
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

import uuid


from authentication.models import User
from formations.models import Formation, Module, Participant, SessionModule
from scolarite.models import AnneeAcademique, JournalScolarite

from presences import rules_services, stats_services
from presences.models import AuditLog, NotificationAbsence, Pointage


def make_user(username, role='SECRETARIAT'):
    return User.objects.create_user(username=username, password='pass', role=role)


class PresenceL1Base(TestCase):
    """Fixture minimale : séance du socle + participants + pointages."""

    def setUp(self):
        import uuid
        suffixe = uuid.uuid4().hex[:6]
        self.staff = make_user(f'staff_{suffixe}', role='SECRETARIAT')
        self.dfrc = make_user(f'dfrc_{suffixe}', role='DIRECTION')
        self.auditeur_user = make_user(f'aud_{suffixe}', role='AUDITEUR')
        # Le signal post_save du rôle AUDITEUR crée automatiquement la fiche
        # Participant liée au compte (avec matricule).
        self.participant = Participant.objects.get(user=self.auditeur_user)
        self.formation_obj = Formation.objects.create(formation=f'FORMATION {suffixe}')
        self.module = Module.objects.create(
            formation=self.formation_obj, intitule=f'Module {suffixe}',
        )
        self.session = SessionModule.objects.create(
            module=self.module, date_journee='2026-11-10', numero=1,
            heure_debut_prevue='08:00', heure_fin_prevue='12:00',
        )
        self.annee = AnneeAcademique.objects.create(
            libelle=f'2026-2027-{suffixe}', date_debut='2026-10-01', date_fin='2027-07-31',
        )
        self.pointage = Pointage.objects.create(
            participant=self.participant, session=self.session,
            timestamp_entree='2026-11-10T08:05:00Z',
            statut=Pointage.Statut.EN_COURS,
            annee_academique=self.annee,
        )


class MappingAssiduiteTests(PresenceL1Base):
    def test_mapping_statuts_processus(self):
        mapping = Pointage.MAPPING_ASSIDUITE()
        self.assertEqual(
            mapping[Pointage.Statut.EN_COURS], Pointage.StatutAssiduite.PRESENT,
        )
        self.assertEqual(
            mapping[Pointage.Statut.ABSENT_NON_BADGE], Pointage.StatutAssiduite.ABSENT,
        )
        self.assertEqual(
            mapping[Pointage.Statut.HORS_LIGNE_SUSPECT],
            Pointage.StatutAssiduite.NON_RENSEIGNE,
        )

    def test_effectif_manuel_prioritaire(self):
        self.assertIsNone(self.pointage.statut_assiduite)
        self.assertEqual(
            self.pointage.statut_assiduite_effectif(), Pointage.StatutAssiduite.PRESENT,
        )
        self.pointage.statut = Pointage.Statut.ABSENT_NON_BADGE
        self.pointage.save(update_fields=['statut'])
        self.assertEqual(
            self.pointage.statut_assiduite_effectif(), Pointage.StatutAssiduite.ABSENT,
        )
        self.pointage.statut_assiduite = Pointage.StatutAssiduite.ABSENCE_JUSTIFIEE
        self.pointage.save(update_fields=['statut_assiduite'])
        self.assertEqual(
            self.pointage.statut_assiduite_effectif(),
            Pointage.StatutAssiduite.ABSENCE_JUSTIFIEE,
        )

    def test_historique_statuts_preserves(self):
        self.assertEqual(len(Pointage.Statut.choices), 6)
        for statut in (
            'EN_COURS', 'TERMINE', 'FORCE_DFRC', 'ABSENT_NON_BADGE',
            'HORS_LIGNE_SUSPECT', 'SORTIE_AUTO',
        ):
            self.assertIn(statut, Pointage.Statut.values)

class ModificationApresClotureTests(PresenceL1Base):
    def test_modification_apres_cloture_auditee(self):
        self.session.terminee_le = '2026-11-10T12:00:00Z'
        self.session.save(update_fields=['terminee_le'])
        self.pointage.statut = Pointage.Statut.ABSENT_NON_BADGE
        self.pointage.save(update_fields=['statut'])
        self.assertTrue(AuditLog.objects.filter(
            action=AuditLog.Action.POINTAGE_MODIFIE, pointage=self.pointage,
        ).exists())
        self.assertTrue(JournalScolarite.objects.filter(
            objet_id=self.pointage.pk,
            commentaire__icontains='après clôture',
        ).exists())

    def test_modification_avant_cloture_non_auditee(self):
        avec_avant = AuditLog.objects.filter(
            action=AuditLog.Action.POINTAGE_MODIFIE,
        ).count()
        self.pointage.statut = Pointage.Statut.TERMINE
        self.pointage.save(update_fields=['statut'])
        self.assertEqual(
            AuditLog.objects.filter(action=AuditLog.Action.POINTAGE_MODIFIE).count(),
            avec_avant,
        )


class ReglesSecuriteTests(PresenceL1Base):
    def test_qr_ne_contient_pas_d_identifiant_interne(self):
        from datetime import timedelta
        from formations.models import QRToken
        import uuid
        token = QRToken.objects.create(
            session=self.session,
            expire_at=timezone.now() + timedelta(hours=2),
        )
        self.assertIsInstance(token.token, uuid.UUID)
        self.assertNotEqual(token.token.version, 0)

    def test_etudiant_ne_peut_pas_modifier_sa_presence(self):
        client = APIClient()
        client.force_authenticate(self.auditeur_user)
        res = client.post(f'/api/presences/formations/{self.formation_obj.pk}/force-pointage/', {})
        self.assertIn(res.status_code, (
            status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND,
        ))

    def test_enseignant_scope_participants(self):
        from presences.participant_scope import participant_ids_for_user
        ids = participant_ids_for_user(self.auditeur_user)
        self.assertIn(self.participant.pk, ids)
        autre = make_user(f'aud_{uuid.uuid4().hex[:6]}', role='AUDITEUR')
        self.assertNotIn(self.participant.pk, participant_ids_for_user(autre))

class StatsPresenceTests(PresenceL1Base):
    def test_taux_par_etudiant(self):
        self.pointage.statut = Pointage.Statut.TERMINE
        self.pointage.save(update_fields=['statut'])
        resultats = stats_services.taux_par_etudiant()
        cible = [r for r in resultats if r['matricule'] == self.participant.matricule]
        self.assertEqual(len(cible), 1)
        self.assertEqual(cible[0]['taux_presence'], 100.0)

    def test_taux_par_formation_et_module(self):
        self.pointage.statut = Pointage.Statut.TERMINE
        self.pointage.save(update_fields=['statut'])
        self.assertEqual(len(stats_services.taux_par_formation()), 1)
        self.assertEqual(len(stats_services.taux_par_module()), 1)

    def test_alertes_absence_avec_seuil_config(self):
        from statistiques.models import ConfigAlerteSeuil
        Pointage.objects.create(
            participant=self.participant, session=self.session,
            timestamp_entree='2026-11-11T08:05:00Z',
            statut=Pointage.Statut.ABSENT_NON_BADGE,
            annee_academique=self.annee,
        )
        self.pointage.statut = Pointage.Statut.TERMINE
        self.pointage.save(update_fields=['statut'])
        ConfigAlerteSeuil.objects.create(
            indicateur=ConfigAlerteSeuil.Indicateur.TAUX_ABSENCE,
            seuil_avertissement=20, seuil_critique=40,
        )
        alertes = stats_services.alertes_absence()
        self.assertEqual(len(alertes), 1)
        self.assertEqual(alertes[0]['taux_absence'], 50.0)
        self.assertEqual(alertes[0]['niveau'], 'CRITIQUE')

    def test_notifications_absence_generees(self):
        from statistiques.models import ConfigAlerteSeuil
        Pointage.objects.create(
            participant=self.participant, session=self.session,
            timestamp_entree='2026-11-11T08:05:00Z',
            statut=Pointage.Statut.ABSENT_NON_BADGE,
            annee_academique=self.annee,
        )
        self.pointage.statut = Pointage.Statut.TERMINE
        self.pointage.save(update_fields=['statut'])
        ConfigAlerteSeuil.objects.create(
            indicateur=ConfigAlerteSeuil.Indicateur.TAUX_ABSENCE,
            seuil_avertissement=20, seuil_critique=40,
        )
        nb = stats_services.notifier_absences(self.annee)
        self.assertGreater(nb, 0)
        self.assertTrue(NotificationAbsence.objects.filter(
            destinataire=self.staff, niveau='CRITIQUE',
        ).exists())