from django.core.management.base import BaseCommand

from authentication.role_groups import ensure_role_groups, sync_all_users_role_groups


class Command(BaseCommand):
    help = (
        "Crée les groupes de rôles manquants et resynchronise l'appartenance des utilisateurs. "
        "Par défaut, les permissions des groupes existants ne sont PAS modifiées "
        "(les changements effectués dans l'admin Django sont préservés). "
        "Utilisez --reset pour rétablir les permissions définies dans ROLE_POLICY."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            default=False,
            help=(
                "Réinitialise les permissions de TOUS les groupes à partir de ROLE_POLICY, "
                "écrasant les modifications manuelles effectuées dans l'admin Django."
            ),
        )

    def handle(self, *args, **options):
        force_reset = options['reset']

        ensure_role_groups(force_reset=force_reset)
        sync_all_users_role_groups()

        if force_reset:
            self.stdout.write(
                self.style.WARNING(
                    "Groupes réinitialisés depuis ROLE_POLICY (les permissions manuelles ont été écrasées)."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    "Groupes manquants créés. Permissions des groupes existants inchangées."
                )
            )
