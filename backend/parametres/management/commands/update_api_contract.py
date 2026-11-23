"""P00-08 — renouvellement EXPLICITE du snapshot de contrat d'API.

Contrairement à ``export_api_contract`` (génération initiale), cette commande
exige une justification qui est consignée dans
``docs/api/CHANGELOG_CONTRAT.md`` avec le récapitulatif des ajouts (autorisés)
et des retraits/renommages (ruptures de contrat à justifier).

Usage :
    python manage.py update_api_contract --justification "P0x-yy : ajout du champ X"
"""

import json
import os
from datetime import datetime, timezone

from django.core.management.base import BaseCommand, CommandError

from config.api_contract import (
    build_contract,
    changelog_path,
    diff_contract,
    snapshot_path,
)

CHANGELOG_ENTETE = (
    "# Changelog du contrat d’API (P00-08)\n\n"
    "Ce fichier est alimenté **exclusivement** par la commande :\n\n"
    "```\n"
    "python manage.py update_api_contract --justification \"…\"\n"
    "```\n\n"
    "Les **ajouts** de routes/clés sont des extensions non cassantes ; les "
    "**retraits ou renommages** sont des ruptures de contrat qui doivent être "
    "explicitement justifiés (et coordonnés avec les clients de l’API).\n\n"
)


class Command(BaseCommand):
    help = "Régénère le snapshot de contrat d’API avec justification tracée."

    def add_arguments(self, parser):
        parser.add_argument(
            '--justification',
            required=True,
            help='Motif du renouvellement (obligatoire, consigné au changelog).',
        )

    def handle(self, *args, **options):
        justification = (options['justification'] or '').strip()
        if not justification:
            raise CommandError('Une justification non vide est obligatoire (--justification).')

        contrat = build_contract()
        target = snapshot_path()
        changelog = changelog_path()

        # Comparaison avec le snapshot précédent (s'il existe).
        try:
            with open(target, encoding='utf-8') as fh:
                precedent = json.load(fh)
        except FileNotFoundError:
            precedent = {'routes': {}}

        retraits = diff_contract(contrat, precedent)
        ajouts = diff_contract(precedent, contrat)
        premiere_fois = not precedent.get('routes')

        # Écriture du snapshot (tri des clés pour des diffs stables).
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, 'w', encoding='utf-8') as fh:
            json.dump(contrat, fh, indent=2, ensure_ascii=False, sort_keys=True)
            fh.write('\n')

        horodatage = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
        lignes = [f'## {horodatage}', '']
        if premiere_fois:
            lignes += [
                '**Génération initiale du contrat.**',
                '',
                f'- Justification : {justification}',
                f"- Routes figées : {len(contrat['routes'])}",
                '',
            ]
        else:
            lignes += [
                f'- **Justification :** {justification}',
                f"- Routes dans le contrat : {len(contrat['routes'])}",
                f"- **Ruptures (retraits/renommages) : {len(retraits)}**",
            ]
            lignes += [f'  - {item}' for item in retraits] or ['  - _aucune_']
            lignes += [f'- Ajouts (extensions non cassantes) : {len(ajouts)}']
            lignes += [f'  - {item}' for item in ajouts] or ['  - _aucun_']
            lignes.append('')
        bloc = '\n'.join(lignes) + '\n'

        try:
            with open(changelog, encoding='utf-8') as fh:
                contenu = fh.read()
        except FileNotFoundError:
            contenu = CHANGELOG_ENTETE
        if not contenu.strip():
            contenu = CHANGELOG_ENTETE
        # La nouvelle entrée est insérée juste après l'entête, en tête d'historique.
        if contenu == CHANGELOG_ENTETE:
            nouveau_contenu = CHANGELOG_ENTETE + '\n' + bloc
        else:
            nouveau_contenu = contenu.rstrip() + '\n\n' + bloc
        os.makedirs(os.path.dirname(changelog), exist_ok=True)
        with open(changelog, 'w', encoding='utf-8') as fh:
            fh.write(nouveau_contenu)

        self.stdout.write(self.style.SUCCESS(
          f'Contrat régénéré : {target} ({len(contrat["routes"])} routes).'
        ))
        self.stdout.write(self.style.SUCCESS(f'Changelog tenu : {changelog}.'))
        if retraits:
            self.stdout.write(self.style.WARNING(
                f'  → {len(retraits)} rupture(s) de contrat enregistrée(s) (vérifiez la justification).'
            ))
