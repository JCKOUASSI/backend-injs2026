"""Reconstruit le référentiel RefModule à partir des modules opérationnels."""

from collections import Counter, defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction

from formations.categorie_referentiel import resolve_categorie_participant
from formations.models import Module, RefCategorie, RefFormation, RefModule, RefModuleVolumeHoraire


def _mode(values):
    if not values:
        return None
    return Counter(values).most_common(1)[0][0]


class Command(BaseCommand):
    help = (
        'Reconstruit RefModule (et volumes formation × catégorie) '
        'à partir des modules opérationnels existants.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Affiche le plan sans modifier la base.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        prefix = '[dry-run] ' if dry_run else ''

        ref_formations_by_label = {
            rf.intitule.strip().upper(): rf
            for rf in RefFormation.objects.all()
        }
        ref_categories_by_label = {
            c.libelle.strip().upper(): c
            for c in RefCategorie.objects.filter(actif=True)
        }

        # intitule_norm → {formation_label, categorie_id} → [durees]
        volume_buckets = defaultdict(list)
        # intitule_norm → set(formation_label)
        formation_labels = defaultdict(set)
        # intitule_norm → raw intitule counter (pour choisir l'orthographe canonique)
        intitule_variants = defaultdict(Counter)

        for mod in Module.objects.select_related('formation').exclude(intitule='').iterator():
            norm = RefModule.normalize_intitule(mod.intitule)
            if not norm:
                continue
            intitule_variants[norm][mod.intitule.strip()] += 1

            cycle = (mod.formation.formation or '').strip()
            if cycle:
                formation_labels[norm].add(cycle)

            duree = mod.duree_prevue_heures
            if duree is None or float(duree) <= 0:
                continue

            cat_label = resolve_categorie_participant(grade=mod.grade)
            if not cat_label:
                continue
            cat = ref_categories_by_label.get(cat_label.strip().upper())
            if not cat or not cycle:
                continue

            volume_buckets[(norm, cycle.upper(), cat.id)].append(float(duree))

        if not intitule_variants:
            self.stdout.write(self.style.WARNING('Aucun module opérationnel trouvé.'))
            return

        created_modules = 0
        updated_links = 0
        created_volumes = 0

        with transaction.atomic():
            for norm, variant_counter in sorted(intitule_variants.items()):
                canonical = RefModule.normalize_intitule(variant_counter.most_common(1)[0][0])
                ref = RefModule.objects.filter(intitule__iexact=canonical).first()
                if not ref:
                    self.stdout.write(f'{prefix}Création RefModule « {canonical} »')
                    if not dry_run:
                        ref = RefModule.objects.create(intitule=canonical, actif=True)
                    created_modules += 1

                rf_ids = []
                for label in formation_labels.get(norm, set()):
                    rf = ref_formations_by_label.get(label.strip().upper())
                    if rf:
                        rf_ids.append(rf.id)
                if rf_ids:
                    labels = ', '.join(sorted(formation_labels.get(norm, set())))
                    self.stdout.write(f'  formations : {labels}')
                if rf_ids and not dry_run and ref:
                    ref.formations.set(rf_ids)

                for (v_norm, cycle_upper, cat_id), durees in volume_buckets.items():
                    if v_norm != norm:
                        continue
                    rf = ref_formations_by_label.get(cycle_upper)
                    if not rf:
                        continue
                    vh = _mode(durees)
                    if vh is None:
                        continue
                    created_volumes += 1
                    self.stdout.write(
                        f'  volume {rf.intitule} × cat#{cat_id} = {vh}h'
                    )
                    if not dry_run and ref:
                        RefModuleVolumeHoraire.objects.update_or_create(
                            module=ref,
                            formation_id=rf.id,
                            categorie_id=cat_id,
                            defaults={'volume_horaire': vh},
                        )

                if not dry_run and ref:
                    linked = 0
                    for mod in Module.objects.exclude(intitule='').iterator():
                        if RefModule.normalize_intitule(mod.intitule) == norm:
                            if mod.ref_module_id != ref.id:
                                mod.ref_module_id = ref.id
                                mod.save(update_fields=['ref_module_id'])
                                linked += 1
                    updated_links += linked

            if dry_run:
                transaction.set_rollback(True)

        self.stdout.write(self.style.SUCCESS(
            f'{prefix}{created_modules} RefModule(s), '
            f'{created_volumes} volume(s), {updated_links} lien(s) module opérationnel.'
        ))
