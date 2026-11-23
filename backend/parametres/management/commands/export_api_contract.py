"""P00-08 — fige le contrat courant de l'API dans docs/api/contract.snapshot.json.

Le snapshot ne contient QUE la forme publique (routes, paramètres, clés de
requête/réponse), jamais de valeurs. La non-régression est vérifiée par le
test ``config.tests.test_api_contract`` : toute route/clé supprimée ou renommée
fait échouer la CI ; les ajouts sont autorisés.

Usage :
    python manage.py export_api_contract                 # écrit le snapshot
    python manage.py export_api_contract --check         # compare, sans écrire
    python manage.py export_api_contract --output x.json # autre destination
"""

import json
import os

from django.core.management.base import BaseCommand, CommandError

from config.api_contract import build_contract, diff_contract, snapshot_path


class Command(BaseCommand):
    help = "Génère (ou vérifie avec --check) le snapshot de contrat d'API."

    def add_arguments(self, parser):
        parser.add_argument('--check', action='store_true', help='Compare au snapshot sans réécrire.')
        parser.add_argument('--output', default=None, help='Chemin de sortie (défaut : docs/api/contract.snapshot.json).')

    def handle(self, *args, **options):
        target = options['output'] or snapshot_path()
        contrat = build_contract()

        if options['check']:
            try:
                with open(target, encoding='utf-8') as fh:
                    snapshot = json.load(fh)
            except FileNotFoundError:
                raise CommandError(
                    f"Snapshot introuvable : {target}. Exécutez d'abord "
                    f"'python manage.py export_api_contract' (génération initiale)."
                )
            ruptures = diff_contract(contrat, snapshot)
            if ruptures:
                self.stdout.write(self.style.ERROR(
                    f"Contrat d'API en rupture ({len(ruptures)} écart(s)) :"
                ))
                for ligne in ruptures:
                    self.stdout.write(self.style.ERROR(f'  - {ligne}'))
                self.stdout.write(self.style.WARNING(
                    "Si ce changement est volontaire, renouvelez le contrat avec :\n"
                    "  python manage.py update_api_contract --justification \"...\""
                ))
                raise CommandError('Contrat d’API non conforme au snapshot.')
            self.stdout.write(self.style.SUCCESS('Contrat d’API conforme au snapshot.'))
            return

        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, 'w', encoding='utf-8') as fh:
            json.dump(contrat, fh, indent=2, ensure_ascii=False, sort_keys=True)
            fh.write('\n')
        nb_routes = len(contrat['routes'])
        self.stdout.write(self.style.SUCCESS(
            f'Snapshot de contrat écrit : {target} ({nb_routes} routes).'
        ))
