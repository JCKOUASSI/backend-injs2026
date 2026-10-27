"""
Commande : python manage.py auto_close_sessions

Clôt automatiquement toute SessionModule démarrée dont l'heure de fin prévue
est dépassée d'au moins ``--delai`` minutes (30 par défaut).

Particularité : ``terminee_le`` est posé à ``date_journee + heure_fin_prevue``
(et **non** à ``now``) pour empêcher l'inflation de la durée effective lorsque
la clôture intervient bien après la fin réelle de la séance.

À planifier via cron toutes les 5–15 minutes :
  */10 * * * * /path/to/venv/bin/python /path/to/manage.py auto_close_sessions
"""

from datetime import timezone as dt_timezone

from django.core.management.base import BaseCommand
from django.utils import timezone

from formations.models import SessionModule, QRToken
from formations.session_views import (
    AUTO_CLOSE_DELAY_MINUTES,
    _invalidate_session_qr_cache,
    _session_fin_prevue_local,
    _should_auto_close_session,
)


DEFAUT_DELAI_MINUTES = AUTO_CLOSE_DELAY_MINUTES


class Command(BaseCommand):
    help = (
        "Clôt automatiquement les SessionModule dont heure_fin_prevue est dépassée "
        "d'au moins --delai minutes (par défaut 30)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help="Affiche les séances concernées sans les modifier.",
        )
        parser.add_argument(
            '--delai',
            type=int,
            default=DEFAUT_DELAI_MINUTES,
            help=f"Délai (en minutes) après heure_fin_prevue avant clôture. "
                 f"Défaut : {DEFAUT_DELAI_MINUTES}.",
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        delai_minutes = options['delai']
        if delai_minutes < 0:
            self.stderr.write("--delai doit être positif ou nul.")
            return

        now = timezone.now()
        local_now = timezone.localtime(now)
        sessions = (
            SessionModule.objects.filter(
                demarree_le__isnull=False,
                terminee_le__isnull=True,
                heure_fin_prevue__isnull=False,
            )
            .select_related('module')
        )

        cloturees = 0
        ignorees = 0
        for sess in sessions:
            if not _should_auto_close_session(sess, local_now, delai_minutes=delai_minutes):
                ignorees += 1
                continue

            fin_prevue_dt_local = _session_fin_prevue_local(sess)
            # ``terminee_le`` borné à la fin prévue (UTC).
            terminee_le_utc = fin_prevue_dt_local.astimezone(dt_timezone.utc)

            label = f"#{sess.pk} {sess.module.intitule} — {sess.date_journee} {sess.heure_fin_prevue}"
            if dry_run:
                self.stdout.write(f"[dry-run] clôturerait {label}")
                cloturees += 1
                continue

            sess.terminee_le = terminee_le_utc
            sess.save(update_fields=['terminee_le'])
            _invalidate_session_qr_cache(sess)
            QRToken.objects.filter(session=sess, actif=True).update(actif=False)
            self.stdout.write(self.style.SUCCESS(f"Clôturée : {label}"))
            cloturees += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"\nTerminé. Clôturées : {cloturees} | Ignorées (délai non atteint) : {ignorees}"
            )
        )
