"""Worker supervisable pour une seule campagne expérimentale BENCHMARK.

Usage de test isolé : python manage.py traiter_campagne_v2 --execution-id N
Ne PAS l'exécuter en production : un garde DEBUG + flag + année BENCHMARK
refuse tout placement hors des essais. Sans worker lancé, aucune tâche ne part.
"""
from django.core.management.base import BaseCommand

from edts.moteur.campagnes_v2 import executer_campagne_v2


class Command(BaseCommand):
    help = 'Traite une exécution v2 BENCHMARK uniquement (phase 3 non publiée).'

    def add_arguments(self, parser):
        parser.add_argument('--execution-id', type=int, required=True)
        parser.add_argument('--revision', type=int, required=True)
        parser.add_argument('--graine', type=int, default=0)

    def handle(self, *args, **options):
        resultat = executer_campagne_v2(options['execution_id'],
            revision=options['revision'], graine=options['graine'])
        self.stdout.write(f"État: {resultat['etat']} ; groupes: {resultat['groupes_traites']}")
