"""
Corrige le lien ref_module des modules opérationnels lorsque l'intitulé
ne correspond pas au référentiel attendu (ex. SIGFAE ET TELETRAVAIL → SIGFAE).

Usage :
  python manage.py fix_ref_module_links --dry-run
  python manage.py fix_ref_module_links --intitule "SIGFAE ET TELETRAVAIL"
  python manage.py fix_ref_module_links --groupe "GROUPE 1" --sync-duree
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from formations.duree_prevue_resolve import ensure_module_duree_prevue
from formations.models import Module, RefModule


class Command(BaseCommand):
    help = (
        'Rattache chaque module opérationnel au RefModule dont l\'intitulé '
        'correspond exactement (après normalisation).'
    )

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--module-id', type=int, default=None)
        parser.add_argument('--intitule', type=str, default=None, help='Filtre intitulé (contient).')
        parser.add_argument('--groupe', type=str, default=None)
        parser.add_argument('--formation', type=str, default=None)
        parser.add_argument(
            '--sync-duree',
            action='store_true',
            help='Recalcule duree_prevue_heures depuis le référentiel après correction.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        prefix = '[dry-run] ' if dry_run else ''

        qs = Module.objects.select_related('ref_module', 'formation').order_by('id')
        if options['module_id']:
            qs = qs.filter(pk=options['module_id'])
        if options['intitule']:
            qs = qs.filter(intitule__icontains=options['intitule'])
        if options['groupe']:
            qs = qs.filter(groupe__iexact=options['groupe'])
        if options['formation']:
            qs = qs.filter(formation__formation__icontains=options['formation'])

        to_fix = []
        for module in qs.iterator():
            expected = RefModule.resolve_for_intitule(module.intitule)
            if expected is None:
                continue
            if module.ref_module_id == expected.id:
                continue
            current_label = module.ref_module.intitule if module.ref_module_id else None
            to_fix.append({
                'module': module,
                'expected': expected,
                'current_label': current_label,
            })

        if not to_fix:
            self.stdout.write(self.style.SUCCESS('Aucun lien référentiel à corriger.'))
            return

        self.stdout.write(self.style.HTTP_INFO(
            f'\n{prefix}{len(to_fix)} module(s) à corriger :\n'
        ))

        linked = 0
        synced = 0

        with transaction.atomic():
            for item in to_fix:
                module = item['module']
                expected = item['expected']
                old = item['current_label'] or '—'
                self.stdout.write(
                    f'  #{module.id} {module.intitule} ({module.groupe}) : '
                    f'{old} → {expected.intitule} (id {expected.id})'
                )
                if not dry_run:
                    module.ref_module_id = expected.id
                    module.save(update_fields=['ref_module_id'])
                    linked += 1
                    if options['sync_duree']:
                        heures, source = ensure_module_duree_prevue(module)
                        if source:
                            synced += 1
                            self.stdout.write(
                                f'      duree_prevue_heures → {heures}h ({source})'
                            )

            if dry_run:
                transaction.set_rollback(True)

        self.stdout.write(self.style.SUCCESS(
            f'\n{prefix}Liens corrigés : {linked}  |  Durées synchronisées : {synced}'
        ))
        if dry_run:
            self.stdout.write(self.style.WARNING(
                'Relancez sans --dry-run pour appliquer les modifications.'
            ))
