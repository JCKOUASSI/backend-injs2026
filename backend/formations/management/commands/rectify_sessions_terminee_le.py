"""
Commande : python manage.py rectify_sessions_terminee_le

Rectifie ``terminee_le`` des SessionModule **déjà clôturées** dont la valeur
dépasse l'heure de fin prévue. Pour chaque session avec ``heure_fin_prevue``
renseignée :

    terminee_le := min(terminee_le, date_journee + heure_fin_prevue)

Cela neutralise l'inflation du volume horaire effectif qui peut résulter d'une
clôture paresseuse tardive (la session est marquée terminée plusieurs heures /
jours après la fin réelle, sans rectification du timestamp).

Usage :
  python manage.py rectify_sessions_terminee_le --dry-run
  python manage.py rectify_sessions_terminee_le
  python manage.py rectify_sessions_terminee_le --depuis 2026-01-01

Sécurité : on ne rectifie **jamais** ``demarree_le``. On ne descend pas
``terminee_le`` en dessous de ``demarree_le`` (la nouvelle valeur est plafonnée
inférieurement par ``demarree_le`` pour préserver une durée >= 0).
"""

from datetime import datetime, timezone as dt_timezone
from zoneinfo import ZoneInfo

from django.core.management.base import BaseCommand
from django.utils import timezone

from formations.models import SessionModule


TZ_LOCALE = ZoneInfo('Africa/Abidjan')


class Command(BaseCommand):
    help = (
        "Recale terminee_le sur min(terminee_le, date_journee + heure_fin_prevue) "
        "pour les SessionModule déjà clôturées, afin de corriger les durées gonflées."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help="Affiche les rectifications sans les appliquer.",
        )
        parser.add_argument(
            '--depuis',
            type=str,
            default=None,
            help="Ne traiter que les séances dont date_journee >= cette date (YYYY-MM-DD).",
        )
        parser.add_argument(
            '--seuil-minutes',
            type=int,
            default=1,
            help="Ne rectifier que si l'écart dépasse ce seuil en minutes (défaut : 1).",
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        depuis_raw = options['depuis']
        seuil = max(0, options['seuil_minutes'])

        qs = SessionModule.objects.filter(
            terminee_le__isnull=False,
            heure_fin_prevue__isnull=False,
        ).select_related('module')

        if depuis_raw:
            try:
                depuis = datetime.strptime(depuis_raw, '%Y-%m-%d').date()
            except ValueError:
                self.stderr.write("--depuis doit être au format YYYY-MM-DD.")
                return
            qs = qs.filter(date_journee__gte=depuis)

        rectifiees = 0
        ignorees = 0
        total = 0
        gain_minutes_total = 0.0

        for sess in qs:
            total += 1
            fin_prevue_local = datetime.combine(
                sess.date_journee, sess.heure_fin_prevue, tzinfo=TZ_LOCALE,
            )
            fin_prevue_utc = fin_prevue_local.astimezone(dt_timezone.utc)

            if sess.terminee_le <= fin_prevue_utc:
                ignorees += 1
                continue

            nouvelle_terminee_le = fin_prevue_utc
            # Plancher inférieur : ne jamais descendre sous demarree_le.
            if sess.demarree_le and nouvelle_terminee_le < sess.demarree_le:
                nouvelle_terminee_le = sess.demarree_le

            ecart_min = (sess.terminee_le - nouvelle_terminee_le).total_seconds() / 60.0
            if ecart_min < seuil:
                ignorees += 1
                continue

            label = (
                f"#{sess.pk} module={sess.module.intitule} "
                f"date={sess.date_journee} fin_prevue={sess.heure_fin_prevue} "
                f"terminee_le={timezone.localtime(sess.terminee_le).strftime('%Y-%m-%d %H:%M')} "
                f"-> {timezone.localtime(nouvelle_terminee_le).strftime('%Y-%m-%d %H:%M')} "
                f"(gain {ecart_min:.0f} min)"
            )
            gain_minutes_total += ecart_min

            if dry_run:
                self.stdout.write(f"[dry-run] {label}")
            else:
                sess.terminee_le = nouvelle_terminee_le
                sess.save(update_fields=['terminee_le'])
                self.stdout.write(self.style.SUCCESS(label))
            rectifiees += 1

        gain_heures = gain_minutes_total / 60.0
        suffixe = " (dry-run)" if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"\nTerminé{suffixe}. Examinées : {total} | "
                f"Rectifiées : {rectifiees} | Ignorées : {ignorees} | "
                f"Gain total : {gain_minutes_total:.0f} min ({gain_heures:.1f} h)"
            )
        )
