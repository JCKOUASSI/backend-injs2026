"""Initialisation idempotente du socle RBAC — **désactivée par défaut**.

Sans ``--appliquer`` la commande se comporte comme la prévisualisation
(aucune écriture). Avec ``--appliquer`` elle exige que les deux drapeaux
soient ouverts :

* ``flag.lot01_socle_referentiels_rbac`` (catalogue rôles / permissions) ;
* ``flag.curp_module_utilisateurs`` (module Utilisateurs gouverné).

Le contournement (``--ignorer-drapeaux``) existe pour la recette et le bac à
sable ; il est tracé dans le rapport et dans le journal.

Garanties :

* idempotente : un second passage ne crée rien et ne modifie rien ;
* aucune attribution automatique d'un rôle sensible (→ ``PROPOSEE``) ;
* aucun périmètre élargi : les rôles à périmètre local ne sont pas posés ;
* les superutilisateurs ne reçoivent aucune attribution ;
* aucune suppression, révocation ou modification d'objet existant ;
* ``authentication.User`` n'est jamais modifié.

Usage :

    python manage.py initialiser_rbac                      # rapport seul
    python manage.py initialiser_rbac --appliquer          # écrit (si drapeaux ouverts)
    python manage.py initialiser_rbac --appliquer --username agent1
    python manage.py initialiser_rbac --appliquer --ignorer-drapeaux   # recette
"""
from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from habilitations.services.initialisation_rbac import (
    appliquer_plan,
    construire_plan,
    ecriture_autorisee,
)


class Command(BaseCommand):
    help = ("Initialise les comptes RBAC manquants (idempotent, inactif par défaut).")

    def add_arguments(self, parser):
        parser.add_argument(
            '--appliquer', action='store_true',
            help='Écrit réellement (défaut : simulation).',
        )
        parser.add_argument(
            '--ignorer-drapeaux', action='store_true',
            help="Écrit même si les drapeaux ne sont pas ouverts (recette).",
        )
        parser.add_argument(
            '--inclure-superutilisateurs', action='store_true',
            help='Crée le profil des superutilisateurs, sans aucune attribution.',
        )
        parser.add_argument(
            '--username', default='',
            help="Limite l'initialisation à un nom d'utilisateur donné.",
        )
        parser.add_argument(
            '--json', dest='json_path', default='',
            help='Écrit aussi le rapport au format JSON à ce chemin.',
        )

    def handle(self, *args, **options):
        appliquer = options['appliquer']
        ignorer = options['ignorer_drapeaux']

        if appliquer:
            autorise, motifs = ecriture_autorisee(ignorer_drapeaux=ignorer)
            if not autorise:
                raise CommandError(
                    'Écriture refusée — drapeaux non réunis :\n  - '
                    + '\n  - '.join(motifs)
                    + "\nOuvrir les deux drapeaux, ou --ignorer-drapeaux en recette."
                )

        plan = construire_plan(
            inclure_superutilisateurs=options['inclure_superutilisateurs'],
            filtre_username=options['username'],
            ignorer_drapeaux=ignorer,
        )

        if appliquer:
            appliquer_plan(plan, acteur=None)
            entete = 'INITIALISATION APPLIQUÉE'
        else:
            entete = 'SIMULATION — aucune écriture'

        self._ecrire(entete, plan)
        chemin = options['json_path']
        if chemin:
            with open(chemin, 'w', encoding='utf-8') as fp:
                json.dump(plan.vers_dict(), fp, ensure_ascii=False, indent=2)
            self.stdout.write(self.style.SUCCESS(f'Rapport JSON : {chemin}'))

    # ------------------------------------------------------------------
    def _ecrire(self, entete: str, plan) -> None:
        ecrire = self.stdout.write
        style = self.style.SUCCESS if 'APPLIQUÉE' in entete else self.style.WARNING
        ecrire(style(f'{entete} — {len(plan.lignes)} compte(s) analysé(s)'))
        ecrire(
            f'  profils créés : {sum(1 for l in plan.lignes if l.applique and l.a_creer_compte)}'
            f' · attributions : {plan.attributions_prevues}'
            f' · propositions sensibles : {plan.propositions_prevues}'
            f' · rôles bloqués (périmètre local) : {plan.roles_bloques}'
        )
        for ligne in plan.lignes:
            marque = 'ÉCRIT' if ligne.applique else '—'
            ecrire(f'  [{marque}] {ligne.username} ({ligne.role_legacy}) : {ligne.detail}')
            for anomalie in ligne.anomalies:
                ecrire(f'        ! {anomalie}')
        for anomalie in plan.anomalies_globales:
            ecrire(self.style.WARNING(f'  ! {anomalie}'))
