"""Inventaire et rapprochement non destructif des volumes CM/TD/TP.

Exemple sur la base effectivement configurée (AUCUNE écriture en DB) :
    python manage.py audit_volumes_ecue --annee 2026-2027 > audit.json
    python manage.py audit_volumes_ecue --annee 2026-2027 --format csv > audit.csv
"""
import csv
import json

from django.core.management.base import BaseCommand, CommandError

from scolarite.volumes_audit import rapprocher


class Command(BaseCommand):
    help = 'Audit lecture seule des volumes ECUE, toutes années/maquettes ; aucune importation.'

    def add_arguments(self, parser):
        parser.add_argument('--annee', required=True, help='Année cible, ex. 2026-2027')
        parser.add_argument('--format', choices=('json', 'csv'), default='json')

    def handle(self, *args, **options):
        try:
            rapport = rapprocher(options['annee'])
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        if options['format'] == 'json':
            self.stdout.write(json.dumps(rapport, ensure_ascii=False, indent=2))
            return
        champs = ('statut', 'annee', 'formation_id', 'formation', 'filiere',
                  'parcours_id', 'parcours', 'niveau_id', 'niveau', 'semestre',
                  'maquette_id', 'maquette_version', 'maquette_statut', 'ue_id',
                  'ue_code', 'ecue_id', 'ecue_code', 'ecue_intitule',
                  'ref_module_id', 'cm', 'td', 'tp', 'sources_exactes',
                  'references_module_indicatives')
        # self.stdout est un TextIO wrapper portable pour manage.py et tests.
        writer = csv.DictWriter(self.stdout, fieldnames=champs, lineterminator='\n')
        writer.writeheader()
        for ligne in rapport['ecues_cible']:
            writer.writerow({k: json.dumps(ligne[k], ensure_ascii=False)
                             if k in ('sources_exactes', 'references_module_indicatives')
                             else ligne[k] for k in champs})
