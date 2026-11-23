"""U3 (livrable L4) — génère le document imprimable de la matrice.

Produit ``docs/CURP_INJS_MATRICE.md``, destiné aux ateliers de validation
ligne à ligne (jalon J2) avec l'expert fonctionnel et les référents de
domaine : le tableau rôle × module (niveaux N0–N4), les rôles sensibles,
les incompatibilités, les permissions critiques et la correspondance avec
les douze rôles existants. La commande est régénérable à volonté.
"""
from datetime import date
from pathlib import Path

from django.core.management.base import BaseCommand

from habilitations.referentiel.catalogue_modules import (
    MODULES,
    PERMISSIONS_CRITIQUES,
)
from habilitations.referentiel.catalogue_roles import ROLES
from habilitations.referentiel.catalogue_matrice import (
    CORRESPONDANCE_LEGACY,
    INCOMPATIBILITES,
    MODULES_A2,
)
from habilitations.referentiel.chargement import niveaux_du_role

# Modules absents des colonnes d'A2 : cases provisoires à valider en J2.
MODULES_EXTRA = (
    'administrations', 'finances_form', 'exports', 'parametres',
    'referentiels',
)

CHEMIN_DEFAUT = Path(__file__).resolve().parents[4] / 'docs' / 'CURP_INJS_MATRICE.md'


def _libelle_module(module):
    return MODULES[module][0] if module in MODULES else module


def _tableau_niveaux():
    colonnes = list(MODULES_A2) + list(MODULES_EXTRA)
    entetes = ['Rôle'] + colonnes
    lignes = ['| ' + ' | '.join(entetes) + ' |',
              '|' + '|'.join(['---'] * len(entetes)) + '|']
    for ligne in ROLES:
        code, _lib, domaine = ligne[0], ligne[1], ligne[2]
        niveaux, origine = niveaux_du_role(code, domaine)
        cellules = [code]
        for module in colonnes:
            valeur = niveaux.get(module)
            if not valeur:
                cellules.append('—')
            elif origine.get(module) == 'J2':
                cellules.append(f'{valeur}*')
            else:
                cellules.append(valeur)
        lignes.append('| ' + ' | '.join(cellules) + ' |')
    return '\n'.join(lignes)


def _tableau_roles():
    lignes = [
        '| Code | Libellé | Domaine | Niv. | Périmètre | Module requis | Sensible | Canal |',
        '|---|---|---|---|---|---|---|---|',
    ]
    for (code, libelle, domaine, niveau, perimetre, module,
         sensible, canal, _ordre, _desc) in ROLES:
        lignes.append(
            f'| `{code}` | {libelle} | {domaine} | {niveau} | {perimetre} '
            f'| {module or "—"} | {"oui" if sensible else "non"} '
            f'| {canal or "web/mobile"} |'
        )
    return '\n'.join(lignes)


def _correspondance():
    lignes = ['| Rôle existant | Rôles métier CURP |', '|---|---|']
    for legacy, cibles in CORRESPONDANCE_LEGACY.items():
        lignes.append(f'| `{legacy}` | ' + ', '.join(f'`{c}`' for c in cibles) + ' |')
    return '\n'.join(lignes)


def generer_contenu():
    return f"""# CURP-INJS — Matrice des rôles et permissions (document de travail J2)

> Généré par `python manage.py generer_matrice_habilitations` le {date.today().isoformat()}.
> **Statut : PROVISOIRE, en attente de la validation ligne à ligne de l'expert
> fonctionnel (jalon J2).** Les cases suivies d'une astérisque (`*`) portent sur
> des modules absents de l'annexe A2 ; elles sont proposées par l'équipe de
> réalisation et doivent être confirmées en atelier.
>
> Lecture du tableau des niveaux : **N0** consultation très limitée ·
> **N1** consultation · **N2** saisie et traitement · **N3** validation ·
> **N4** administration et décision. Un tiret signifie aucun accès. Les
> limitations « à ses ECUE » ou « à son propre dossier » sont portées par le
> périmètre du rôle, pas par le niveau.

## 1. Matrice rôle × module (annexe A2 + cases provisoires)

{_tableau_niveaux()}

## 2. Référentiel des rôles (annexe A1)

{_tableau_roles()}

Le recueil titre « 33 rôles » ; le tableau A1 comporte 35 lignes, dont trois
destinataires du service (`ETUDIANT`, `CANDIDAT`, `CONSULTATION`). Les 35
lignes sont chargées par sécurité additive.

## 3. Incompatibilités de séparation des tâches (J5)

""" + '\n'.join(
        f'- `{a}` est incompatible avec `{b}` (et réciproquement).'
        for a, b in INCOMPATIBILITES
    ) + f"""

## 4. Permissions critiques (motif obligatoire, double validation, journalisation renforcée)

""" + '\n'.join(f'- `{code}`' for code in sorted(PERMISSIONS_CRITIQUES)) + f"""

## 5. Correspondance avec les 12 rôles existants (annexe A6, appliquée en U8)

{_correspondance()}

## 6. Modules du catalogue (annexe A3) et activation conditionnelle

""" + '\n'.join(
        f'- `{cle}` — {libelle} (application Django : `{app or "interne"}`'
        f'{", conditionnel MOA" if conditionnel else ""}).'
        for cle, (libelle, app, conditionnel) in MODULES.items()
    ) + "\n"


class Command(BaseCommand):
    help = "Génère le document imprimable de la matrice d'habilitation (J2)."

    def add_arguments(self, parser):
        parser.add_argument('--sortie', default=None,
                            help="Chemin du fichier markdown à écrire.")

    def handle(self, *args, **options):
        cible = Path(options['sortie']) if options['sortie'] else CHEMIN_DEFAUT
        cible.parent.mkdir(parents=True, exist_ok=True)
        cible.write_text(generer_contenu(), encoding='utf-8')
        self.stdout.write(self.style.SUCCESS(
            f"Matrice écrite : {cible}"
        ))
