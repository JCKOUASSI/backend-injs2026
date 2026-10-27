"""Diagnostic de pertes de données après migration 0076 (sans sauvegarde)."""

from django.core.management.base import BaseCommand

from formations.models import Module, SessionModule
from presences.models import AuditLog


class Command(BaseCommand):
    help = (
        'Sans dump PostgreSQL : liste ce qui peut encore être reconstitué '
        'via le journal d\'audit (séances / badgeages référencés mais absents en base).'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--formation-id',
            type=int,
            help='Limiter à une formation.',
        )
        parser.add_argument(
            '--since',
            type=str,
            help='Date ISO (YYYY-MM-DD) : ignorer les entrées d\'audit antérieures.',
        )

    def handle(self, *args, **options):
        formation_id = options.get('formation_id')
        since = options.get('since')

        audit_qs = AuditLog.objects.filter(
            action__in=(
                AuditLog.Action.SEANCE_START,
                AuditLog.Action.SEANCE_STOP,
                AuditLog.Action.SCAN_SECURE_ENTREE,
                AuditLog.Action.SCAN_SECURE_SORTIE,
                AuditLog.Action.FORCE_ENTREE,
                AuditLog.Action.FORCE_SORTIE,
            ),
        ).order_by('-timestamp')
        if formation_id:
            audit_qs = audit_qs.filter(formation_id=formation_id)
        if since:
            audit_qs = audit_qs.filter(timestamp__date__gte=since)

        session_ids = set(
            SessionModule.objects.values_list('id', flat=True)
        )
        module_ids = set(
            Module.objects.values_list('id', flat=True)
        )

        missing_sessions = []
        seen_session_keys = set()
        for log in audit_qs.filter(action__in=(
            AuditLog.Action.SEANCE_START,
            AuditLog.Action.SEANCE_STOP,
        )):
            extra = log.extra or {}
            sid = extra.get('session_id')
            if not sid or sid in session_ids:
                continue
            key = (sid, log.action)
            if key in seen_session_keys:
                continue
            seen_session_keys.add(key)
            missing_sessions.append({
                'session_id': sid,
                'action': log.action,
                'timestamp': log.timestamp,
                'formation': log.formation_titre or (log.formation.formation if log.formation_id else '—'),
                'module_id': extra.get('module_id'),
                'module_intitule': extra.get('module_intitule', ''),
                'date_journee': extra.get('date_journee', ''),
                'module_exists': extra.get('module_id') in module_ids,
            })

        scan_actions = (
            AuditLog.Action.SCAN_SECURE_ENTREE,
            AuditLog.Action.SCAN_SECURE_SORTIE,
            AuditLog.Action.FORCE_ENTREE,
            AuditLog.Action.FORCE_SORTIE,
        )
        scans_with_dead_pointage = audit_qs.filter(
            action__in=scan_actions,
            pointage__isnull=True,
        ).exclude(
            cible_numero='',
        ).count()

        empty_modules = Module.objects.filter(
            statut='PLANIFIEE',
        ).exclude(
            sessions__demarree_le__isnull=False,
        ).distinct()

        self.stdout.write(self.style.HTTP_INFO('\n=== Diagnostic sans dump ===\n'))

        self.stdout.write(
            f'Séances référencées dans l\'audit mais absentes en base : '
            f'{len(missing_sessions)}'
        )
        for row in missing_sessions[:30]:
            mod_status = 'module OK' if row['module_exists'] else 'module SUPPRIMÉ'
            self.stdout.write(
                f"  • séance #{row['session_id']} ({row['action']}) "
                f"{row['date_journee']} — {row['module_intitule']} "
                f"[{mod_status}] @ {row['timestamp']:%Y-%m-%d %H:%M}"
            )
        if len(missing_sessions) > 30:
            self.stdout.write(f'  … et {len(missing_sessions) - 30} autre(s)')

        self.stdout.write(
            f'\nBadgeages tracés dans l\'audit sans pointage lié : '
            f'{scans_with_dead_pointage} entrée(s)/sortie(s) potentiellement reconstituables'
        )

        self.stdout.write(
            f'\nModules « planifiés » sans aucune séance démarrée : '
            f'{empty_modules.count()}'
        )
        for m in empty_modules[:15]:
            self.stdout.write(
                f'  • #{m.id} {m.intitule} ({m.grade}/{m.groupe}/{m.vague})'
            )

        self.stdout.write(self.style.HTTP_INFO('\n--- Pistes ---'))
        if missing_sessions:
            self.stdout.write(
                '• Des démarrages de séance sont encore tracés : on peut '
                'reposer demarree_le sur les séances EDT existantes (reconstitution partielle).'
            )
        if scans_with_dead_pointage:
            self.stdout.write(
                '• Des badgeages sont tracés dans l\'audit : reconstitution manuelle '
                'ou script (matricule + date + formation).'
            )
        if not missing_sessions and not scans_with_dead_pointage:
            self.stdout.write(
                '• Peu de traces audit exploitables : reprise opérationnelle '
                '(redémarrer les séances, refaire les badgeages si nécessaire).'
            )
        self.stdout.write(
            '\nReconstitution : python manage.py recover_from_audit --dry-run --intitule DEONTOLOGIE'
        )
        self.stdout.write(
            '\nMettre en place des dumps quotidiens : '
            'pg_dump -Fc qr_badge > /backups/qr_badge_$(date +%F).dump'
        )
