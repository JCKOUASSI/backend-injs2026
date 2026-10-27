"""Détection des comptes inactifs (U5, C3 point 2).

Préavis notifié à l'agent et à son responsable, puis proposition de
suspension déposée dans la file de validation HUMAINE : la commande ne
suspend jamais rien elle-même (jamais de suspension silencieuse). No-op
tant que ``flag.curp_suspension_inactivite`` est fermé (défaut).

Planification de production (quotidienne) :

    python manage.py detecter_inactivite
"""
from django.core.management.base import BaseCommand

from habilitations.services.drapeaux import inactivite_active
from habilitations.services.expirations import detecter_inactivite


class Command(BaseCommand):
    help = "Préavis d'inactivité et propositions de suspension en file."

    def handle(self, *args, **options):
        if not inactivite_active():
            self.stdout.write(self.style.WARNING(
                "flag.curp_suspension_inactivite fermé : aucun contrôle (no-op)."
            ))
            return
        bilan = detecter_inactivite()
        self.stdout.write(
            f"Inactivité : {bilan['preavis']} préavis émis, "
            f"{bilan['propositions']} proposition(s) de suspension en file."
        )
