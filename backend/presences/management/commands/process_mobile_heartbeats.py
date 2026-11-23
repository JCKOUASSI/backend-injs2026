"""
Commande : python manage.py process_mobile_heartbeats

Surveille les pointages mobiles ouverts et applique les sanctions heartbeat :
  - après MOBILE_HEARTBEAT_SUSPECT_TIMEOUT_MINUTES (défaut 60) :
    statut HORS_LIGNE_SUSPECT + e-mail à l'encadrant ;
  - après MOBILE_HEARTBEAT_AUTO_EXIT_TIMEOUT_MINUTES (défaut 120) :
    sortie automatique (SORTIE_AUTO).

À planifier via cron toutes les 5 minutes :
  */5 * * * * /path/to/venv/bin/python /path/to/manage.py process_mobile_heartbeats
"""

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from presences.heartbeat_sanctions import (
    AUTO_EXIT_TIMEOUT_MINUTES,
    SUSPECT_TIMEOUT_MINUTES,
    process_mobile_heartbeat_sanctions,
)


class Command(BaseCommand):
    help = (
        "Surveille les heartbeats mobiles : alerte encadrant (suspect) "
        "puis sortie automatique si le signal GPS cesse."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help="Affiche les pointages concernés sans les modifier.",
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        local_now = timezone.localtime(timezone.now())

        if getattr(settings, 'MOBILE_HEARTBEAT_DISABLED', False):
            self.stdout.write(
                self.style.WARNING(
                    f'[{local_now.strftime("%Y-%m-%d %H:%M")}] '
                    'Sanctions heartbeat désactivées (MOBILE_HEARTBEAT_DISABLED=true).'
                )
            )
            return

        traites = process_mobile_heartbeat_sanctions(
            dry_run=dry_run,
            write=self.stdout.write,
        )

        label = "simulés" if dry_run else "traités"
        self.stdout.write(
            self.style.SUCCESS(
                f'[{local_now.strftime("%Y-%m-%d %H:%M")}] '
                f'{traites} pointage(s) heartbeat {label} '
                f'(suspect={SUSPECT_TIMEOUT_MINUTES} min, '
                f'sortie auto={AUTO_EXIT_TIMEOUT_MINUTES} min).'
            )
        )
