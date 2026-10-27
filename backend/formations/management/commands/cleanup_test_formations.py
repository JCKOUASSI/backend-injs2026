"""
Supprime les formations / entrées référentiel créées par les tests ou le debug local.

Usage :
    python manage.py cleanup_test_formations --dry-run
    python manage.py cleanup_test_formations
    python manage.py cleanup_test_formations --label "Mon libellé test"
"""

from django.core.management.base import BaseCommand
from django.db.models import Q

from formations.models import Formation, Module, RefFormation, SessionModule

DEFAULT_TEST_LABELS = (
    'Test DEONTO',
    'TEST_AUDIT_RECOVERY',
)

DEFAULT_TEST_PREFIXES = (
    'TEST_',
)


def _label_query(field_name, *, extra_labels=(), extra_prefixes=(), include_test_prefix=False):
    q = Q()
    for label in (*DEFAULT_TEST_LABELS, *extra_labels):
        stripped = (label or '').strip()
        if stripped:
            q |= Q(**{f'{field_name}__iexact': stripped})
    for prefix in (*DEFAULT_TEST_PREFIXES, *extra_prefixes):
        stripped = (prefix or '').strip()
        if stripped:
            q |= Q(**{f'{field_name}__istartswith': stripped})
    if include_test_prefix:
        q |= Q(**{f'{field_name}__istartswith': 'Test '})
    return q


def formations_test_queryset(*, extra_labels=(), extra_prefixes=(), include_test_prefix=False):
    q = _label_query(
        'formation',
        extra_labels=extra_labels,
        extra_prefixes=extra_prefixes,
        include_test_prefix=include_test_prefix,
    )
    if not q:
        return Formation.objects.none()
    return Formation.objects.filter(q).order_by('id')


def ref_formations_test_queryset(*, extra_labels=(), extra_prefixes=(), include_test_prefix=False):
    q = _label_query(
        'intitule',
        extra_labels=extra_labels,
        extra_prefixes=extra_prefixes,
        include_test_prefix=include_test_prefix,
    )
    if not q:
        return RefFormation.objects.none()
    return RefFormation.objects.filter(q).order_by('id')


class Command(BaseCommand):
    help = (
        'Supprime les formations de test (Test DEONTO, TEST_*, etc.) '
        'et les entrées RefFormation correspondantes.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Affiche ce qui serait supprimé sans modifier la base.',
        )
        parser.add_argument(
            '--label',
            action='append',
            default=[],
            help='Libellé additionnel à traiter (répétable).',
        )
        parser.add_argument(
            '--prefix',
            action='append',
            default=[],
            help='Préfixe additionnel istartswith (répétable).',
        )
        parser.add_argument(
            '--include-test-prefix',
            action='store_true',
            help='Inclure aussi les libellés commençant par « Test » (espace inclus).',
        )
        parser.add_argument(
            '--skip-ref-formations',
            action='store_true',
            help='Ne pas supprimer les RefFormation correspondantes.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        extra_labels = options['label']
        extra_prefixes = options['prefix']
        include_test_prefix = options['include_test_prefix']
        skip_refs = options['skip_ref_formations']

        formations = formations_test_queryset(
            extra_labels=extra_labels,
            extra_prefixes=extra_prefixes,
            include_test_prefix=include_test_prefix,
        )
        refs = (
            RefFormation.objects.none()
            if skip_refs
            else ref_formations_test_queryset(
                extra_labels=extra_labels,
                extra_prefixes=extra_prefixes,
                include_test_prefix=include_test_prefix,
            )
        )

        if not formations.exists() and not refs.exists():
            self.stdout.write(self.style.WARNING('Aucune formation / référentiel de test trouvé.'))
            return

        for formation in formations:
            modules = Module.objects.filter(formation=formation)
            sessions = SessionModule.objects.filter(module__formation=formation)
            self.stdout.write(
                f"Formation #{formation.pk} « {formation.formation} » — "
                f"{modules.count()} module(s), {sessions.count()} séance(s)"
            )

        for ref in refs:
            prix = ref.prix_heure_realisee
            prix_label = f'{prix} FCFA/h' if prix is not None else 'Non défini'
            self.stdout.write(
                f"RefFormation #{ref.pk} « {ref.intitule} » — {prix_label}"
            )

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f'[dry-run] {formations.count()} formation(s), '
                    f'{refs.count()} RefFormation(s) — aucune suppression.'
                )
            )
            return

        ref_count = refs.count()
        if not skip_refs and ref_count:
            refs.delete()

        formation_count = formations.count()
        deleted_total, deleted_detail = formations.delete()

        self.stdout.write(
            self.style.SUCCESS(
                f'Supprimé : {formation_count} formation(s) '
                f'({deleted_total} objet(s) en cascade), '
                f'{ref_count} RefFormation(s).'
            )
        )
        if deleted_detail:
            for model_label, count in sorted(deleted_detail.items()):
                if count:
                    self.stdout.write(f'  - {model_label}: {count}')
