"""Tests de la tâche planifiée de clôture des occurrences EDT/LMD."""
from datetime import timedelta
from io import StringIO

from django.core.management import call_command, CommandError
from django.test import TestCase
from django.utils import timezone

from formations.models import QRToken
from presences.models import AuditLog, Pointage
from presences.seances_edt_services import CLE_NOTIFIER_CLOTURE
from parametres.models import Parametre

from .test_seances_edt_mobile import MobileSeanceEdtMixin


class AutoCloseSeancesEdtCommandTests(MobileSeanceEdtMixin, TestCase):
    def setUp(self):
        super().setUp()
        now_local = timezone.localtime(timezone.now())
        self.template.heure_debut = (now_local - timedelta(minutes=90)).time()
        self.template.heure_fin = (now_local - timedelta(minutes=30)).time()
        self.template.save(update_fields=['heure_debut', 'heure_fin'])
        Parametre.objects.create(
            cle=CLE_NOTIFIER_CLOTURE, libelle='Notifier à la clôture (test)',
            categorie='presences', type='integer', valeur='0', valeur_defaut='1',
        )

    def test_dry_run_est_sans_ecriture_et_cloture_puis_reprise_idempotente(self):
        sortie = StringIO()
        call_command('auto_close_seances_edt', '--dry-run', stdout=sortie)
        self.assertIn(f'#{self.affectation.pk}', sortie.getvalue())
        self.assertFalse(Pointage.objects.filter(seance_edt=self.affectation).exists())
        self.assertTrue(QRToken.objects.get(seance_edt=self.affectation).actif)

        call_command('auto_close_seances_edt', stdout=StringIO())
        self.assertEqual(Pointage.objects.filter(
            seance_edt=self.affectation,
            statut=Pointage.Statut.ABSENT_NON_BADGE,
        ).count(), len(self.participants))
        self.assertFalse(QRToken.objects.get(seance_edt=self.affectation).actif)
        self.assertEqual(AuditLog.objects.filter(
            action=AuditLog.Action.CLOSE_SESSION,
            cible_type='seance_edt', cible_numero=str(self.affectation.pk),
        ).count(), 1)

        # Rejouer le job après succès ne duplique ni absences ni journal.
        call_command('auto_close_seances_edt', stdout=StringIO())
        self.assertEqual(Pointage.objects.filter(
            seance_edt=self.affectation,
            statut=Pointage.Statut.ABSENT_NON_BADGE,
        ).count(), len(self.participants))
        self.assertEqual(AuditLog.objects.filter(
            action=AuditLog.Action.CLOSE_SESSION,
            cible_type='seance_edt', cible_numero=str(self.affectation.pk),
        ).count(), 1)

    def test_ne_cloture_pas_un_edt_non_publie(self):
        self.edt.statut = 'BROUILLON'
        self.edt.save(update_fields=['statut'])
        call_command('auto_close_seances_edt', stdout=StringIO())
        self.assertFalse(Pointage.objects.filter(seance_edt=self.affectation).exists())
        self.assertTrue(QRToken.objects.get(seance_edt=self.affectation).actif)

    def test_refuse_date_future_et_format_invalide(self):
        with self.assertRaises(CommandError):
            call_command('auto_close_seances_edt', date='pas-une-date', stdout=StringIO())
        with self.assertRaises(CommandError):
            call_command(
                'auto_close_seances_edt',
                date=(timezone.localdate() + timedelta(days=1)).isoformat(),
                stdout=StringIO(),
            )
