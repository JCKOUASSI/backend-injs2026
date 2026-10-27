"""Fusionne les modules dupliqués en conservant celui qui a le plus d'activité."""

from django.core.management.base import BaseCommand

from formations.module_merge import (
    find_duplicate_module_groups,
    merge_module_into,
    module_activity_score,
    pick_keeper_module,
)
from formations.models import Module


class Command(BaseCommand):
    help = (
        'Repère les modules en double (formation + intitulé + grade + groupe + vague) '
        'et fusionne les doublons vers le module le plus actif (séances démarrées, '
        'pointages). À lancer avant/après déploiement si des doublons subsistent.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Liste les fusions sans modifier la base.',
        )
        parser.add_argument(
            '--module-id',
            type=int,
            help='Fusionner uniquement les doublons du groupe contenant ce module.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        module_id = options.get('module_id')

        groups = find_duplicate_module_groups()
        if module_id:
            try:
                anchor = Module.objects.get(pk=module_id)
            except Module.DoesNotExist:
                self.stderr.write(self.style.ERROR(f'Module #{module_id} introuvable.'))
                return
            groups = [
                g for g in groups
                if any(
                    m.formation_id == anchor.formation_id
                    and m.intitule == anchor.intitule
                    and m.grade == anchor.grade
                    and m.groupe == anchor.groupe
                    and m.vague == anchor.vague
                    for m in g
                )
            ]

        if not groups:
            self.stdout.write(self.style.SUCCESS('Aucun module dupliqué trouvé.'))
            return

        merged = 0
        for modules in groups:
            keeper = pick_keeper_module(modules)
            sources = [m for m in modules if m.pk != keeper.pk]
            sample = modules[0]
            label = (
                f'"{sample.intitule}" '
                f'({sample.grade}/{sample.groupe}/{sample.vague}) '
                f'— {sample.formation.formation}'
            )
            self.stdout.write(self.style.HTTP_INFO(f'\n{label}'))
            self.stdout.write(
                f'  → conservé #{keeper.pk} (score={module_activity_score(keeper)})'
            )
            for src in sources:
                self.stdout.write(
                    f'  → fusion #{src.pk} (score={module_activity_score(src)})'
                )
                if dry_run:
                    continue
                result = merge_module_into(keeper, src)
                self.stdout.write(
                    f'     séances: {result["sessions"]}, '
                    f'participants +{result["participants_merged"]}, '
                    f'formateurs +{result["formateurs_merged"]}'
                )
                merged += 1

        if dry_run:
            self.stdout.write(self.style.WARNING(
                f'\n[dry-run] {sum(len(g) - 1 for g in groups)} fusion(s) seraient effectuée(s).'
            ))
        elif merged:
            self.stdout.write(self.style.SUCCESS(f'\n{merged} doublon(s) fusionné(s).'))
        else:
            self.stdout.write('Aucune fusion effectuée.')
