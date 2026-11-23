"""
Commande : python manage.py backfill_duree_prevue

Pour chaque Module dont ``duree_prevue_heures`` vaut 0 (ou NULL), tente de
récupérer la valeur via 3 sources, dans cet ordre :

  1. Jumeau (même intitulé) dans le même secrétariat avec ``duree > 0``.
  2. Jumeau (même intitulé) dans n'importe quel secrétariat avec ``duree > 0``.
  3. Capacité planifiée : somme des fenêtres ``heure_fin_prevue
     - heure_debut_prevue`` des sessions du module concerné.

Ne supprime rien. N'affecte que les modules à 0.

Usage :
  python manage.py backfill_duree_prevue --dry-run
  python manage.py backfill_duree_prevue
  python manage.py backfill_duree_prevue --secretariat "FAB B"
  python manage.py backfill_duree_prevue --no-capa-fallback  # désactive l'étape 3
"""

from collections import defaultdict
from decimal import Decimal

from django.core.management.base import BaseCommand

from formations.models import Module, SessionModule


def _norm(s):
    return ' '.join((s or '').strip().split()).lower()


def _capa_planifiee_heures(module):
    """Σ (heure_fin_prevue - heure_debut_prevue) en heures, sur les sessions du module."""
    minutes = 0.0
    for s in SessionModule.objects.filter(
        module=module,
        heure_debut_prevue__isnull=False,
        heure_fin_prevue__isnull=False,
    ).only('heure_debut_prevue', 'heure_fin_prevue'):
        delta = (
            (s.heure_fin_prevue.hour * 60 + s.heure_fin_prevue.minute)
            - (s.heure_debut_prevue.hour * 60 + s.heure_debut_prevue.minute)
        )
        if delta > 0:
            minutes += delta
    return minutes / 60.0


class Command(BaseCommand):
    help = (
        "Recopie duree_prevue_heures depuis un module 'jumeau' (même secrétariat "
        "+ même intitulé) lorsque la valeur courante est 0."
    )

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument(
            '--secretariat',
            type=str,
            default=None,
            help="Filtrer par libellé du type de secrétariat (ex. 'FAB B').",
        )
        parser.add_argument(
            '--no-capa-fallback',
            action='store_true',
            help="Désactive le fallback sur la capacité planifiée des sessions.",
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        secretariat = options['secretariat']
        use_capa_fallback = not options['no_capa_fallback']

        modules_qs = Module.objects.select_related('secretariat__type').all()
        if secretariat:
            modules_qs = modules_qs.filter(
                secretariat__type__libelle__iexact=secretariat
            )

        # Index global jumeaux : on construit deux indexes à partir de TOUS les
        # modules (pas seulement ceux filtrés), pour permettre le fallback
        # cross-secretariat.
        all_modules = Module.objects.all().only(
            'id', 'intitule', 'secretariat_id', 'duree_prevue_heures'
        )
        index_meme_sec: dict[tuple, float] = defaultdict(float)
        index_global: dict[str, float] = defaultdict(float)
        for m in all_modules:
            d = float(m.duree_prevue_heures or 0)
            if d <= 0:
                continue
            nom = _norm(m.intitule)
            cle = (m.secretariat_id, nom)
            if d > index_meme_sec[cle]:
                index_meme_sec[cle] = d
            if d > index_global[nom]:
                index_global[nom] = d

        rectifies_jumeau_sec = 0
        rectifies_jumeau_global = 0
        rectifies_capa = 0
        sans_source = 0
        ignores = 0

        for m in modules_qs:
            d = float(m.duree_prevue_heures or 0)
            if d > 0:
                ignores += 1
                continue

            nom = _norm(m.intitule)
            source = None
            nouvelle = 0.0

            # 1) Même secrétariat
            v = index_meme_sec.get((m.secretariat_id, nom), 0.0)
            if v > 0:
                nouvelle, source = v, "jumeau-meme-sec"

            # 2) Cross-secretariat
            if not source:
                v = index_global.get(nom, 0.0)
                if v > 0:
                    nouvelle, source = v, "jumeau-global"

            # 3) Capacité planifiée
            if not source and use_capa_fallback:
                v = _capa_planifiee_heures(m)
                if v > 0:
                    nouvelle, source = v, "capa-planifiee"

            if not source:
                sans_source += 1
                continue

            sec_lib = ''
            try:
                sec_lib = m.secretariat.type.libelle if m.secretariat and m.secretariat.type else ''
            except AttributeError:
                pass

            label = (
                f"#{m.pk} {m.intitule!r} (sec={sec_lib}, grade={m.grade!r}) "
                f"0h -> {nouvelle:.1f}h [{source}]"
            )
            if dry_run:
                self.stdout.write(f"[dry-run] {label}")
            else:
                m.duree_prevue_heures = Decimal(str(round(nouvelle, 2)))
                m.save(update_fields=['duree_prevue_heures'])
                self.stdout.write(self.style.SUCCESS(label))

            if source == "jumeau-meme-sec":
                rectifies_jumeau_sec += 1
            elif source == "jumeau-global":
                rectifies_jumeau_global += 1
            else:
                rectifies_capa += 1

        suffixe = " (dry-run)" if dry_run else ""
        total_rect = rectifies_jumeau_sec + rectifies_jumeau_global + rectifies_capa
        self.stdout.write(
            self.style.SUCCESS(
                f"\nTerminé{suffixe}. Rectifiés : {total_rect} "
                f"(meme-sec={rectifies_jumeau_sec}, "
                f"global={rectifies_jumeau_global}, "
                f"capa={rectifies_capa}) | "
                f"Sans source : {sans_source} | "
                f"Déjà OK : {ignores}"
            )
        )
