"""Scan des événements métier → file de provisionnement (U5, L2).

Lit les cinq sondes dont le drapeau dédié ET le drapeau maître sont
ouverts, et dépose les propositions en file de validation humaine. La
commande est sans effet quand tout est éteint (comportement par défaut).

Planification de production (quotidienne) :

    python manage.py provisionnement_scanner
    python manage.py provisionnement_scanner --declencheur ADMISSION
"""
from django.core.management.base import BaseCommand

from parametres.flags import is_enabled

from habilitations.services.drapeaux import MAITRE_PROVISIONNEMENT
from habilitations.services.provisionnement.file import scanner


class Command(BaseCommand):
    help = "Détecte les événements métier et alimente la file de provisionnement."

    def add_arguments(self, parser):
        parser.add_argument(
            '--declencheur', action='append', default=None,
            choices=['ADMISSION', 'INSCRIPTION', 'RECRUTEMENT',
                     'AFFECTATION_ENSEIGNANT', 'FIN_RELATION', 'JURY'],
            help="Limite le scan à un ou plusieurs déclencheurs.",
        )

    def handle(self, *args, **options):
        if not is_enabled(MAITRE_PROVISIONNEMENT):
            self.stdout.write(self.style.WARNING(
                "Drapeau maître " + MAITRE_PROVISIONNEMENT
                + " fermé : aucun scan (no-op total)."
            ))
            return
        declencheurs = options['declencheur']
        bilan = scanner(declencheurs=declencheurs)
        if not bilan:
            self.stdout.write("Aucun déclencheur actif : rien à faire.")
            return
        for code, nombre in sorted(bilan.items()):
            self.stdout.write(f"  {code:<24} {nombre} nouvelle(s) proposition(s)")
        total = sum(bilan.values())
        self.stdout.write(self.style.SUCCESS(
            f"Scan terminé : {total} proposition(s) en file de validation humaine."
        ))
