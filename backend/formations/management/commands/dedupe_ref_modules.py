"""Fusionne les entrées RefModule en double (intitulés proches ou identiques)."""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models.functions import Lower

from formations.models import Module, RefModule


class Command(BaseCommand):
    help = (
        'Repère les RefModule en double (même intitulé normalisé) et fusionne '
        'les entrées redondantes vers la plus ancienne.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Affiche les fusions sans modifier la base.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        # Étape 1 : normaliser tous les intitulés existants (majuscules + espaces)
        normalized = 0
        for ref in RefModule.objects.all():
            normalized_val = RefModule.normalize_intitule(ref.intitule)
            if ref.intitule != normalized_val:
                self.stdout.write(f'  Normalisation : « {ref.intitule} » → « {normalized_val} »')
                if not dry_run:
                    ref.intitule = normalized_val
                    ref.save(update_fields=['intitule'])
                normalized += 1
        if normalized:
            self.stdout.write(self.style.WARNING(
                f'{"[dry-run] " if dry_run else ""}{normalized} intitulé(s) normalisé(s).'
            ))

        seen = {}
        merged = 0

        for ref in RefModule.objects.annotate(
            intitule_norm=Lower('intitule'),
        ).order_by('id'):
            key = RefModule.normalize_intitule(ref.intitule)
            if not key:
                continue
            if key not in seen:
                seen[key] = ref
                continue

            keeper = seen[key]
            self.stdout.write(
                f'  Fusion : #{ref.id} « {ref.intitule} » → #{keeper.id} « {keeper.intitule} »'
            )
            if dry_run:
                merged += 1
                continue

            with transaction.atomic():
                Module.objects.filter(ref_module=ref).update(ref_module=keeper)
                if not keeper.volume_horaire and ref.volume_horaire:
                    keeper.volume_horaire = ref.volume_horaire
                    keeper.save(update_fields=['volume_horaire'])
                keeper.formations.add(*ref.formations.all())
                ref.delete()
            merged += 1

        if merged:
            self.stdout.write(self.style.SUCCESS(
                f'{"[dry-run] " if dry_run else ""}{merged} entrée(s) fusionnée(s).'
            ))
        else:
            self.stdout.write('Aucun doublon exact trouvé.')
