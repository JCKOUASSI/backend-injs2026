"""
Commande : python manage.py backfill_categorie_ref

Normalise le champ ``Participant.categorie`` vers le libellé canonique du
référentiel ``RefCategorie`` (ex. FAB A → A).

Usage :
  python manage.py backfill_categorie_ref --dry-run
  python manage.py backfill_categorie_ref
  python manage.py backfill_categorie_ref --matricule FNCE001
"""

from collections import Counter

from django.core.management.base import BaseCommand
from django.db import transaction

from formations.categorie_referentiel import (
    libelles_ref_actifs,
    reset_ref_categorie_index,
    resolve_categorie_participant,
)
from formations.models import Participant


class Command(BaseCommand):
    help = (
        "Normalise les catégories auditeur vers le référentiel RefCategorie "
        "(FAB A, FABA… → libellé canonique)."
    )

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument(
            '--matricule',
            type=str,
            default=None,
            help='Traiter un seul auditeur (matricule exact).',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Nombre maximum de mises à jour (hors dry-run).',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        matricule = (options['matricule'] or '').strip()
        limit = options['limit']

        reset_ref_categorie_index()
        ref_libelles = libelles_ref_actifs()
        if not ref_libelles:
            self.stderr.write(
                self.style.ERROR(
                    'Aucune RefCategorie active. Créez les libellés (A, B, C, D…) '
                    'dans le référentiel avant de lancer cette commande.'
                )
            )
            return

        self.stdout.write(f"Référentiel actif : {', '.join(ref_libelles)}")

        qs = Participant.objects.all().only(
            'id', 'matricule', 'nom', 'prenom', 'categorie', 'grade',
        )
        if matricule:
            qs = qs.filter(matricule=matricule)

        updated = 0
        already_ok = 0
        empty = 0
        unmappable = Counter()
        pending_updates = []

        for participant in qs.iterator(chunk_size=500):
            raw = (participant.categorie or '').strip()
            if not raw:
                empty += 1
                continue

            resolved = resolve_categorie_participant(raw, grade=participant.grade)
            if not resolved:
                unmappable[raw] += 1
                continue

            if raw == resolved:
                already_ok += 1
                continue

            label = (
                f"{participant.matricule or f'#{participant.pk}'} "
                f"{participant.nom} {participant.prenom}: {raw!r} → {resolved!r}"
            )
            if dry_run:
                self.stdout.write(f"[dry-run] {label}")
                updated += 1
                continue

            pending_updates.append((participant.pk, resolved, label))
            if limit is not None and len(pending_updates) >= limit:
                break

        if not dry_run and pending_updates:
            with transaction.atomic():
                for pk, resolved, label in pending_updates:
                    Participant.objects.filter(pk=pk).update(categorie=resolved)
                    self.stdout.write(self.style.SUCCESS(label))
            updated = len(pending_updates)

        suffixe = ' (dry-run)' if dry_run else ''
        self.stdout.write(
            self.style.SUCCESS(
                f"\nTerminé{suffixe}. "
                f"Normalisés : {updated} | "
                f"Déjà conformes : {already_ok} | "
                f"Vides : {empty} | "
                f"Non mappables : {sum(unmappable.values())}"
            )
        )
        if unmappable:
            self.stdout.write('Valeurs non mappables :')
            for value, count in unmappable.most_common(20):
                self.stdout.write(f"  - {value!r} ({count})")
