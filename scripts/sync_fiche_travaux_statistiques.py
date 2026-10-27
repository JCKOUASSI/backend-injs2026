#!/usr/bin/env python3
"""
Met à jour « Fiche de travaux App - Statistiques.txt ».

Usage:
  python scripts/sync_fiche_travaux_statistiques.py
      → Met à jour la date « Dernière mise à jour »

  python scripts/sync_fiche_travaux_statistiques.py --add "Description de la tâche"
      → Ajoute une entrée datée dans TÂCHES RÉALISÉES

  python scripts/sync_fiche_travaux_statistiques.py --add "..." --statut "EN COURS"
      → Met aussi à jour le statut global
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FICHE = ROOT / 'Fiche de travaux App - Statistiques.txt'
MARKER_REALISEES = ' TÂCHES RÉALISÉES'
MARKER_ATTENTE = ' TÂCHES EN ATTENTE / BACKLOG'


def _now_fr() -> str:
    return datetime.now().strftime('%d/%m/%Y %H:%M')


def _today_fr() -> str:
    return datetime.now().strftime('%d/%m/%Y')


def update_timestamp(content: str) -> str:
    return re.sub(
        r'(Dernière mise à jour\s*:\s*).+',
        rf'\g<1>{_now_fr()}',
        content,
        count=1,
    )


def update_statut(content: str, statut: str) -> str:
    return re.sub(
        r'(Statut global\s*:\s*).+',
        rf'\g<1>{statut}',
        content,
        count=1,
    )


def append_task(content: str, description: str) -> str:
    """Insère une nouvelle tâche juste après l'en-tête TÂCHES RÉALISÉES."""
    block = (
        f'\n[{_today_fr()}] {description.strip()}\n'
        f'  · Enregistré automatiquement le {_now_fr()}\n'
    )
    idx = content.find(MARKER_REALISEES)
    if idx == -1:
        return content + block

    # Insérer après la ligne de séparation suivant le titre section
    line_end = content.find('\n', idx)
    sep_end = content.find('\n\n', line_end)
    if sep_end == -1:
        sep_end = line_end
    insert_at = sep_end + 2 if sep_end != -1 else len(content)
    return content[:insert_at] + block + content[insert_at:]


def main():
    parser = argparse.ArgumentParser(description='Sync Fiche de travaux Statistiques')
    parser.add_argument('--add', metavar='TEXTE', help='Ajouter une tâche réalisée')
    parser.add_argument('--statut', metavar='STATUT', help='Mettre à jour le statut global')
    parser.add_argument('--check', action='store_true', help='Vérifier que le fichier existe')
    args = parser.parse_args()

    if args.check:
        if not FICHE.exists():
            print('fiche manquante', file=sys.stderr)
            sys.exit(1)
        print('ok')
        sys.exit(0)

    if not FICHE.exists():
        print(f'Erreur : {FICHE} introuvable', file=sys.stderr)
        sys.exit(1)

    content = FICHE.read_text(encoding='utf-8')
    content = update_timestamp(content)

    if args.statut:
        content = update_statut(content, args.statut)

    if args.add:
        content = append_task(content, args.add)

    FICHE.write_text(content, encoding='utf-8')
    print(f'✓ Fiche mise à jour : {FICHE.relative_to(ROOT)}')


if __name__ == '__main__':
    main()
