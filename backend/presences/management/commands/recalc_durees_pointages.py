"""
Commande : python manage.py recalc_durees_pointages

Recalcule ``duree_presence_minutes`` de tous les pointages terminés avec la
règle canonique SYGEP (presences.duree) : durée clampée au créneau planifié
de la séance, jamais négative.

À lancer une fois après l'unification des calculs de durée, pour corriger les
durées historiques stockées en brut (sorties auto, forçages, heartbeats…).

Options :
  --dry-run : affiche les écarts sans modifier la base.
"""

from django.core.management.base import BaseCommand

from presences.duree import pointage_minutes_clampees
from presences.models import Pointage


class Command(BaseCommand):
    help = (
        "Recalcule les durées de présence stockées avec la règle canonique "
        "(clamp au créneau planifié de la séance)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help="Affiche les pointages dont la durée changerait, sans modifier la base.",
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        qs = (
            Pointage.objects
            .filter(timestamp_entree__isnull=False, timestamp_sortie__isnull=False)
            .select_related('session')
            .only(
                'duree_presence_minutes', 'timestamp_entree', 'timestamp_sortie',
                'session__heure_debut_prevue', 'session__heure_fin_prevue',
            )
        )

        total = 0
        modifies = 0
        a_sauver = []
        for pt in qs.iterator(chunk_size=500):
            total += 1
            nouvelle = pointage_minutes_clampees(pt)
            ancienne = float(pt.duree_presence_minutes) if pt.duree_presence_minutes is not None else None
            if ancienne is not None and abs(ancienne - nouvelle) < 0.01:
                continue
            modifies += 1
            if dry_run:
                self.stdout.write(
                    f"[DRY-RUN] Pointage #{pt.pk} : {ancienne} → {nouvelle} min"
                )
                continue
            pt.duree_presence_minutes = nouvelle
            a_sauver.append(pt)
            if len(a_sauver) >= 500:
                Pointage.objects.bulk_update(a_sauver, ['duree_presence_minutes'])
                a_sauver = []

        if a_sauver:
            Pointage.objects.bulk_update(a_sauver, ['duree_presence_minutes'])

        verbe = "seraient corrigés" if dry_run else "corrigés"
        self.stdout.write(self.style.SUCCESS(
            f"{modifies} pointage(s) {verbe} sur {total} pointage(s) terminé(s)."
        ))
