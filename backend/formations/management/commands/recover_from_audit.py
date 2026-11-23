"""Reconstitue séances et badgeages depuis le journal d'audit (sans dump)."""

from django.core.management.base import BaseCommand

from formations.audit_recovery import recover_pointages_from_audit, recover_sessions_from_audit
from presences.models import AuditLog


class Command(BaseCommand):
    help = (
        'Reconstitue demarree_le/terminee_le et les pointages orphelins '
        'à partir du journal d\'audit (après migration 0076). '
        'Toujours lancer avec --dry-run d\'abord.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simule sans écrire en base.',
        )
        parser.add_argument(
            '--since',
            type=str,
            default='2026-06-01',
            help='Date ISO min. pour l\'audit (défaut : 2026-06-01).',
        )
        parser.add_argument(
            '--intitule',
            type=str,
            help='Limiter à un intitulé de module (ex: DEONTOLOGIE).',
        )
        parser.add_argument(
            '--sessions-only',
            action='store_true',
            help='Ne reconstituer que les séances (pas les badgeages).',
        )
        parser.add_argument(
            '--pointages-only',
            action='store_true',
            help='Ne reconstituer que les badgeages (séances déjà récupérées).',
        )

        parser.add_argument(
            '--mapping',
            type=str,
            help=(
                'Appariement manuel supprimé:survivant, ex: '
                '"321:327,312:372,330:336,357:363" (prioritaire, stable).'
            ),
        )

        parser.add_argument(
            '--relink-pointages-only',
            action='store_true',
            help='Rattache les pointages existants aux séances du mapping (sans recréer).',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        since = options['since']
        intitule = (options.get('intitule') or '').strip()
        from formations.audit_recovery import _parse_explicit_mapping
        explicit_mapping = _parse_explicit_mapping(options.get('mapping') or '')

        audit_qs = AuditLog.objects.filter(
            action__in=(
                AuditLog.Action.SEANCE_START,
                AuditLog.Action.SEANCE_STOP,
                AuditLog.Action.SCAN_SECURE_ENTREE,
                AuditLog.Action.SCAN_SECURE_SORTIE,
                AuditLog.Action.FORCE_ENTREE,
                AuditLog.Action.FORCE_SORTIE,
            ),
        ).order_by('timestamp')
        if since:
            audit_qs = audit_qs.filter(timestamp__date__gte=since)

        prefix = '[dry-run] ' if dry_run else ''
        self.stdout.write(self.style.HTTP_INFO(f'\n{prefix}Reconstitution depuis l\'audit\n'))

        run_sessions = not options['pointages_only'] and not options['relink_pointages_only']
        run_pointages = not options['sessions_only'] or options['relink_pointages_only']

        module_mapping = {}
        deleted_by_module = {}

        if run_sessions:
            session_audit = audit_qs.filter(action__in=(
                AuditLog.Action.SEANCE_START,
                AuditLog.Action.SEANCE_STOP,
            ))
            if intitule:
                session_audit = session_audit.filter(
                    extra__module_intitule__iexact=intitule,
                )

            results, totals, mapping = recover_sessions_from_audit(
                session_audit, dry_run=dry_run, explicit_mapping=explicit_mapping or None,
            )
            module_mapping = mapping
            from formations.audit_recovery import collect_orphan_session_events
            from formations.models import Module, SessionModule
            existing_session_ids = set(SessionModule.objects.values_list('id', flat=True))
            existing_module_ids = set(Module.objects.values_list('id', flat=True))
            deleted_by_module, _ = collect_orphan_session_events(
                session_audit, existing_session_ids, existing_module_ids,
            )

            self.stdout.write(self.style.HTTP_INFO('--- Séances ---'))
            for row in results:
                mid = row['deleted_module_id']
                surv = row['survivor']
                if not surv:
                    meta = row.get('meta') or {}
                    self.stdout.write(self.style.WARNING(
                        f'  module supprimé #{mid} '
                        f'(formation_id={meta.get("formation_id")}) : '
                        f'aucun survivant apparié'
                    ))
                    continue
                st = row['stats']
                meta = row.get('meta') or {}
                inferred = meta.get('inferred_groupe') or '?'
                score = meta.get('match_score', '?')
                edt_cov = meta.get('edt_coverage', '?')
                method = meta.get('match_method', '?')
                warning = meta.get('match_warning') or meta.get('match_error') or ''
                warn_suffix = f' ⚠ {warning}' if warning else ''
                self.stdout.write(
                    f'  #{mid} → module #{surv.id} '
                    f'({surv.intitule} / {surv.groupe}, {method}, score={score}, EDT={edt_cov})'
                    f'{warn_suffix} '
                    f'[formation_id={meta.get("formation_id")}] : '
                    f'{st["updated"]} mise(s) à jour, '
                    f'{st.get("edt_created", 0)} créneau(x) EDT créé(s), '
                    f'{st["missing"]} EDT manquant(s), '
                    f'{st.get("already_complete", 0)} déjà complète(s)'
                )

            self.stdout.write(
                f'\n{prefix}Modules appariés : {totals["modules"]}, '
                f'séances mises à jour : {totals["sessions_updated"]}, '
                f'créneaux EDT créés : {totals.get("edt_created", 0)}, '
                f'non appariés : {totals["unmapped"]}'
            )

        if run_pointages:
            pt_audit = audit_qs.filter(action__in=(
                AuditLog.Action.SCAN_SECURE_ENTREE,
                AuditLog.Action.SCAN_SECURE_SORTIE,
                AuditLog.Action.FORCE_ENTREE,
                AuditLog.Action.FORCE_SORTIE,
            ))
            if intitule:
                from formations.models import Module
                formation_ids = Module.objects.filter(
                    intitule__iexact=intitule,
                ).values_list('formation_id', flat=True).distinct()
                pt_audit = pt_audit.filter(formation_id__in=formation_ids)

            if options['pointages_only'] and not module_mapping:
                from formations.audit_recovery import (
                    collect_orphan_session_events,
                    match_deleted_modules_to_survivors,
                )
                from formations.models import Module, SessionModule
                session_audit = audit_qs.filter(action__in=(
                    AuditLog.Action.SEANCE_START,
                    AuditLog.Action.SEANCE_STOP,
                ))
                if intitule:
                    session_audit = session_audit.filter(
                        extra__module_intitule__iexact=intitule,
                    )
                existing_session_ids = set(SessionModule.objects.values_list('id', flat=True))
                existing_module_ids = set(Module.objects.values_list('id', flat=True))
                deleted_by_module, meta_by_module = collect_orphan_session_events(
                    session_audit, existing_session_ids, existing_module_ids,
                )
                module_mapping = match_deleted_modules_to_survivors(
                    deleted_by_module, meta_by_module,
                    explicit_mapping=explicit_mapping or None,
                )

            if options['relink_pointages_only']:
                from formations.audit_recovery import (
                    collect_orphan_session_events,
                    relink_recovered_pointages,
                )
                from formations.models import Module, SessionModule
                if not module_mapping and explicit_mapping:
                    module_mapping = {
                        deleted: Module.objects.get(pk=survivor_id)
                        for deleted, survivor_id in explicit_mapping.items()
                    }
                if not deleted_by_module:
                    session_audit = audit_qs.filter(action__in=(
                        AuditLog.Action.SEANCE_START,
                        AuditLog.Action.SEANCE_STOP,
                    ))
                    if intitule:
                        session_audit = session_audit.filter(
                            extra__module_intitule__iexact=intitule,
                        )
                    existing_session_ids = set(SessionModule.objects.values_list('id', flat=True))
                    existing_module_ids = set(Module.objects.values_list('id', flat=True))
                    deleted_by_module, _ = collect_orphan_session_events(
                        session_audit, existing_session_ids, existing_module_ids,
                    )
                pt_stats = relink_recovered_pointages(
                    pt_audit, module_mapping, deleted_by_module, dry_run=dry_run,
                )
            else:
                pt_stats = recover_pointages_from_audit(
                    pt_audit, dry_run=dry_run, intitule_hint=intitule,
                    module_mapping=module_mapping or None,
                    deleted_by_module=deleted_by_module or None,
                )
            self.stdout.write(self.style.HTTP_INFO('\n--- Badgeages ---'))
            if options['relink_pointages_only']:
                self.stdout.write(
                    f'{prefix}Rattachés : {pt_stats.get("relinked", 0)}, '
                    f'déjà corrects : {pt_stats.get("unchanged", 0)}, '
                    f'sans cible : {pt_stats.get("no_target", 0)}, '
                    f'sans pointage : {pt_stats.get("no_pointage", 0)}'
                )
            else:
                self.stdout.write(
                    f'{prefix}Créés : {pt_stats["created"]}, '
                    f'rattachés : {pt_stats.get("relinked", 0)}, '
                    f'ignorés (déjà là) : {pt_stats["skipped"]}, '
                    f'sans module : {pt_stats["no_module"]}, '
                    f'sans séance : {pt_stats["no_session"]}'
                )

        if dry_run:
            self.stdout.write(self.style.WARNING(
                '\nRelancez sans --dry-run pour appliquer.'
            ))
