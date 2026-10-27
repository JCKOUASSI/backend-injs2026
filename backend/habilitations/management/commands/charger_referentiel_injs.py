"""U3 — charge (ou simule avec ``--dry-run``) le référentiel des rôles et la
matrice de permissions issus des annexes A1, A2, A3, A4, A6.

Idempotent : la commande peut être relancée après une correction de ligne,
elle remet le catalogue à sa référence sans toucher aux attributions de
comptes.
"""
from django.core.management.base import BaseCommand

from habilitations.referentiel.chargement import charger_referentiel


class Command(BaseCommand):
    help = "Charge le référentiel INJS des rôles et permissions (annexes A1 à A6)."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help="Simule le chargement sans rien écrire en base.",
        )

    def handle(self, *args, **options):
        rapport = charger_referentiel(dry_run=options['dry_run'])
        prefixe = '[simulation] ' if options['dry_run'] else ''
        self.stdout.write(self.style.SUCCESS(
            f"{prefixe}Référentiel chargé : {rapport.roles} rôles, "
            f"{rapport.permissions} permissions atomiques, "
            f"{rapport.liaisons_matrice} liaisons de matrice, "
            f"{rapport.couples_incompatibilite} couples d'incompatibilité."
        ))
        if rapport.roles_indisponibles:
            self.stdout.write(self.style.WARNING(
                "Rôles indisponibles (module requis absent, sans erreur) : "
                + ', '.join(rapport.roles_indisponibles)
            ))
        else:
            self.stdout.write(
                "Tous les rôles sont disponibles (modules conditionnels présents)."
            )
        if rapport.permissions_orphelines:
            self.stdout.write(self.style.ERROR(
                f"{len(rapport.permissions_orphelines)} permissions orphelines "
                "(aucun rôle ne les détient)."
            ))
        if rapport.roles_sans_permission:
            self.stdout.write(self.style.ERROR(
                "Rôles sans aucune permission : "
                + ', '.join(rapport.roles_sans_permission)
            ))
        if (
            not rapport.permissions_orphelines
            and not rapport.roles_sans_permission
        ):
            self.stdout.write(self.style.SUCCESS(
                "Cohérence : aucune permission orpheline, aucun rôle vide."
            ))
