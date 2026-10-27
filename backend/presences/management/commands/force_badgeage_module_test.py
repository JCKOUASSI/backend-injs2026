"""
Forçage de test : badge 80–95 % des absents (auditeurs, formateurs, encadrants) par séance.

Usage :
  python manage.py force_badgeage_module_test --module-id 1
  python manage.py force_badgeage_module_test --app-wide
  python manage.py force_badgeage_module_test --app-wide --dry-run
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from formations.models import Module, SessionModule
from presences.bulk_force_auditeurs import (
    _ActeurRequest,
    absent_auditeurs_for_seance,
    absents_encadrants_for_seance,
    absents_formateurs_for_seance,
    find_module_for_test,
    run_bulk_force_application,
)

User = get_user_model()

DEFAULT_MOTIF = 'Test présences — forçage 80-95 % auditeurs, formateurs, encadrants'


class Command(BaseCommand):
    help = (
        'Force le badgeage entrée (80–95 % aléatoire par séance) pour les auditeurs, '
        'formateurs et encadrants attendus. Option --app-wide : toute l\'application.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--app-wide',
            action='store_true',
            help='Toutes les séances de tous les modules',
        )
        parser.add_argument(
            '--intitule',
            default='',
            help='Recherche du module par intitulé (icontains), si pas --app-wide',
        )
        parser.add_argument('--module-id', type=int, help='ID du module')
        parser.add_argument('--date', help='Limiter à une date (AAAA-MM-JJ) — module uniquement')
        parser.add_argument('--motif', default=DEFAULT_MOTIF, help='Motif audit')
        parser.add_argument('--username', default='admin', help='Utilisateur acteur audit')
        parser.add_argument('--dry-run', action='store_true', help='Aperçu sans créer de pointages')

    def handle(self, *args, **options):
        module_ids = None
        if not options['app_wide']:
            module = find_module_for_test(
                module_id=options.get('module_id'),
                intitule_contains=options.get('intitule') or None,
            )
            if not module:
                hint = Module.objects.order_by('-id').values_list('id', 'intitule')[:8]
                lines = '\n'.join(f'  - {mid}: {title}' for mid, title in hint)
                raise CommandError(f'Aucun module trouvé.\nModules récents :\n{lines}')
            module_ids = [module.id]
            self.stdout.write(f'Module #{module.id} — {module.intitule}')
        else:
            self.stdout.write('Périmètre : toutes les séances de l\'application')

        seances_qs = SessionModule.objects.all()
        if module_ids:
            seances_qs = seances_qs.filter(module_id__in=module_ids)
        if options.get('date'):
            from datetime import datetime
            d = datetime.strptime(options['date'], '%Y-%m-%d').date()
            seances_qs = seances_qs.filter(date_journee=d)

        seance_count = seances_qs.count()
        self.stdout.write(f'  Séances concernées : {seance_count}')

        if options['dry_run']:
            for seance in seances_qs.select_related('module').order_by('date_journee', 'numero')[:30]:
                na = len(absent_auditeurs_for_seance(seance, ignore_constraints=True))
                nf = len(absents_formateurs_for_seance(seance, ignore_constraints=True))
                ne = len(absents_encadrants_for_seance(seance, ignore_constraints=True))
                self.stdout.write(
                    f'  · #{seance.id} mod.{seance.module_id} {seance.date_journee} '
                    f'— absents: {na} aud., {nf} form., {ne} enc.'
                )
            if seance_count > 30:
                self.stdout.write(f'  … et {seance_count - 30} autres séances')
            self.stdout.write(self.style.WARNING('Dry-run : aucun pointage créé.'))
            return

        try:
            acteur = User.objects.get(username=options['username'])
        except User.DoesNotExist:
            raise CommandError(f'Utilisateur "{options["username"]}" introuvable.')

        req = _ActeurRequest(acteur)
        result, status_hint = run_bulk_force_application(
            motif=options['motif'],
            request=req,
            ignore_constraints=True,
            module_ids=module_ids,
        )

        totals = result.get('totals', {})
        self.stdout.write(
            f'  Auditeurs : {totals.get("auditeurs", 0)} | '
            f'Formateurs : {totals.get("formateurs", 0)} | '
            f'Encadrants : {totals.get("encadrants", 0)}'
        )
        for s in result.get('sessions', [])[:15]:
            self.stdout.write(
                f'  · séance {s["session_id"]} ({s.get("session_date", "")}) : '
                f'{s.get("auditeurs", 0)} aud. · {s.get("formateurs", 0)} form. · {s.get("encadrants", 0)} enc.'
            )

        if status_hint == 201:
            self.stdout.write(self.style.SUCCESS(result['detail']))
        else:
            self.stdout.write(self.style.ERROR(result['detail']))
