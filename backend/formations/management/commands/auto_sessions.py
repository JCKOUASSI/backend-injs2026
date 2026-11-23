"""
Management command: auto_sessions
Auto-start and auto-close SessionModule based on heure_debut_prevue / heure_fin_prevue.

Usage (run every minute via cron):
    * * * * * /path/to/venv/bin/python manage.py auto_sessions

Crontab example:
    */5 * * * * cd /path/to/project && venv/bin/python manage.py auto_sessions >> /tmp/auto_sessions.log 2>&1
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from formations.models import Formation
from formations.session_views import _auto_manage_sessions


class Command(BaseCommand):
    help = 'Auto-start and auto-close module sessions based on scheduled times'

    def handle(self, *args, **options):
        local_now = timezone.localtime(timezone.now())
        formations = (
            Formation.objects.filter(modules__sessions__isnull=False)
            .distinct()
            .prefetch_related('modules__sessions')
        )

        count = 0
        for formation in formations:
            _auto_manage_sessions(formation)
            count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'[{local_now.strftime("%Y-%m-%d %H:%M")}] '
                f'auto_sessions exécuté sur {count} formation(s).'
            )
        )
