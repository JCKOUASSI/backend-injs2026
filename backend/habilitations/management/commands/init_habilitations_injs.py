"""Initialisation minimale et idempotente du dispositif CURP (unité U1).

Crée la politique de sécurité singleton avec ses valeurs par défaut. Le
chargement des rôles et du catalogue de permissions (annexes A1/A3, 35
lignes du tableau A1 — le recueil en titre 33) est explicitement réalisé
par la migration de données de l'unité **U3** ; U1 ne fournit que la
structure et ne peuple aucun droit. La commande ne touche à aucune donnée
des applications existantes.
"""
from django.core.management.base import BaseCommand

from habilitations.models import PolitiqueSecurite
from habilitations.services.journalisation import journaliser


class Command(BaseCommand):
    help = "Initialise la politique de sécurité CURP (idempotent, sans droit)."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help="Affiche ce qui serait fait sans rien écrire.",
        )

    def handle(self, *args, **options):
        sec = options['dry_run']
        existe = PolitiqueSecurite.objects.filter(pk=1).exists()
        if existe:
            self.stdout.write(self.style.SUCCESS(
                "Politique de sécurité déjà présente — aucune création."
            ))
            return
        if sec:
            self.stdout.write("[simulation] La politique de sécurité singleton serait créée.")
            return
        politique = PolitiqueSecurite.objet()
        journaliser(
            'POLITIQUE_MODIFIEE',
            cible=politique,
            nouvelle_valeur={'initialisation': True},
            motif="Initialisation de la politique par défaut (U1).",
        )
        self.stdout.write(self.style.SUCCESS(
            "Politique de sécurité initialisée avec les valeurs par défaut."
        ))
