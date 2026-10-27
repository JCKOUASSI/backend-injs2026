#!/usr/bin/env python3

# Script manuel HORS RUNTIME Django (P00-05) : CLI opérateur d'import/reprise.
# Sorties print() de console volontaires ; exclu du garde-fou check_repo_hygiene.
"""
Vérifie un fichier Excel d'import Cours avant import en base.

Usage :
  python scripts/verify_import_file.py "chemin/vers/fichier.xlsx"
  python manage.py import_excel fichier.xlsx --dry-run   # variante avec écriture simulée
"""
import os
import sys

# backend/ comme racine Django
BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from openpyxl import load_workbook
from formations.management.commands.import_excel import Command
from formations.import_coherence import check_workbook


def main():
    if len(sys.argv) < 2:
        print('Usage: python scripts/verify_import_file.py <fichier.xlsx>')
        sys.exit(1)

    path = sys.argv[1]
    if not os.path.isfile(path):
        print(f'❌ Fichier introuvable : {path}')
        sys.exit(1)

    print('=' * 60)
    print('VÉRIFICATION IMPORT COURS')
    print('=' * 60)
    print(f'Fichier : {path}')
    print(f'Taille  : {os.path.getsize(path):,} octets')

    wb = load_workbook(path, read_only=True)
    print(f'Feuilles: {wb.sheetnames}')

    sheet_name = 'Formations' if 'Formations' in wb.sheetnames else wb.sheetnames[0]
    ws = wb[sheet_name]
    rows = list(ws.iter_rows(values_only=True))
    print(f'\nFeuille utilisée : « {sheet_name} » ({max(0, len(rows) - 1)} lignes données)')

    if rows:
        print(f'En-têtes : {list(rows[0])}')
        print('\nAperçu (3 premières lignes) :')
        for i, r in enumerate(rows[1:4], 2):
            print(f'  L{i}: {r}')
        if len(rows) > 5:
            print('  …')
            for i, r in enumerate(rows[-3:], len(rows) - 2):
                print(f'  L{i}: {r}')

    wb_coherence = load_workbook(path, read_only=True)
    report = check_workbook(wb_coherence)
    wb_coherence.close()

    print('\n--- Colonnes / cohérence ---')
    print('Stats :', report.stats)
    if report.errors:
        print(f'❌ {len(report.errors)} erreur(s) structurelle(s) :')
        for e in report.errors:
            print(f'   • {e}')
    else:
        print('✅ Structure OK')

    if report.warnings:
        print(f'⚠️  {len(report.warnings)} avertissement(s) :')
        for w in report.warnings[:10]:
            print(f'   • {w}')

    cmd = Command()

    class _Stdout:
        def write(self, msg):
            pass

    cmd.stdout = _Stdout()
    errors = []
    ws = wb[sheet_name]
    created, updated = cmd._import_formations(ws, errors)

    print('\n--- Simulation import (sans écriture) ---')
    print(f'Créés     : {created}')
    print(f'Mis à jour: {updated}')
    print(f'Erreurs   : {len(errors)}')

    if errors:
        print('\n❌ Détail des erreurs :')
        for e in errors:
            print(f'   • {e}')
        if rows:
            headers = list(rows[0])
            print('\n--- Cellules des lignes en erreur ---')
            for e in errors:
                try:
                    ln = int(e.split('ligne ')[1].split(':')[0].split(' ')[0])
                except (IndexError, ValueError):
                    continue
                if 1 <= ln <= len(rows):
                    r = rows[ln - 1]
                    d = {str(h): v for h, v in zip(headers, r) if h}
                    print(f'  L{ln}: {d}')
    else:
        print('\n✅ Fichier prêt pour import (aucune erreur détectée).')

    wb.close()
    print('=' * 60)
    sys.exit(1 if errors or report.errors else 0)


if __name__ == '__main__':
    main()
