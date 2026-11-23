"""Vérification de l'intégrité du journal chaîné des habilitations.

Recalcule toutes les empreintes et contrôle la continuité de la séquence et
les liens de chaînage. Sort en code 1 dès qu'une anomalie est détectée (une
altération, un trou ou une rupture). Prémices du contrôle périodique d'U7.
"""
import sys

from django.core.management.base import BaseCommand

from habilitations.models import JournalHabilitation
from habilitations.services.journalisation import verifier_chaine


class Command(BaseCommand):
    help = "Vérifie le chaînage et l'immutabilité du journal des habilitations."

    def add_arguments(self, parser):
        parser.add_argument(
            '--silencieux', action='store_true',
            help="N'affiche que le résultat (utile en supervision).",
        )

    def handle(self, *args, **options):
        nombre = JournalHabilitation.objects.count()
        anomalies = verifier_chaine()
        if not options['silencieux']:
            self.stdout.write(f"{nombre} événement(s) vérifié(s).")
        if anomalies:
            self.stdout.write(self.style.ERROR(
                f"ANOMALIE — {len(anomalies)} problème(s) détecté(s) :"
            ))
            for ligne in anomalies:
                self.stdout.write(self.style.ERROR(f"  - {ligne}"))
            sys.exit(1)
        self.stdout.write(self.style.SUCCESS(
            "Chaînage du journal des habilitations intègre."
        ))
