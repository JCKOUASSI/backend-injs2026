"""Prévisualisation de l'initialisation RBAC — **aucune écriture possible**.

Cette commande est le livrable de prévisualisation demandé avant toute
mise en service : elle produit le rapport complet (comptes à créer,
correspondance Django ↔ CURP, matrice rôles / périmètres, propositions
sensibles, anomalies) sans jamais ouvrir de transaction d'écriture.

Usage :

    python manage.py previsualiser_initialisation_rbac
    python manage.py previsualiser_initialisation_rbac --json /tmp/rapport.json
    python manage.py previsualiser_initialisation_rbac --inclure-superutilisateurs

Le code de sortie est 0 même en présence d'anomalies : le but est de les
rendre visibles, pas de bloquer un pipeline.
"""
from __future__ import annotations

import json

from django.core.management.base import BaseCommand

from habilitations.services.initialisation_rbac import construire_plan


class Command(BaseCommand):
    help = ("Rapport d'initialisation RBAC (lecture seule, n'écrit jamais).")

    def add_arguments(self, parser):
        parser.add_argument(
            '--json', dest='json_path', default='',
            help='Écrit aussi le rapport au format JSON à ce chemin.',
        )
        parser.add_argument(
            '--inclure-superutilisateurs', action='store_true',
            help='Inclut les superutilisateurs dans le rapport (aucune attribution).',
        )
        parser.add_argument(
            '--username', default='',
            help="Limite le rapport à un nom d'utilisateur donné.",
        )

    def handle(self, *args, **options):
        plan = construire_plan(
            inclure_superutilisateurs=options['inclure_superutilisateurs'],
            filtre_username=options['username'],
        )
        self._ecrire(plan)
        chemin = options['json_path']
        if chemin:
            with open(chemin, 'w', encoding='utf-8') as fp:
                json.dump(plan.vers_dict(), fp, ensure_ascii=False, indent=2)
            self.stdout.write(self.style.SUCCESS(f'Rapport JSON : {chemin}'))

    # ------------------------------------------------------------------
    def _ecrire(self, plan) -> None:
        ecrire = self.stdout.write
        ecrire(self.style.MIGRATE_HEADING('PRÉVISUALISATION — INITIALISATION RBAC'))
        ecrire(f'  Horodatage            : {plan.horodatage}')
        for cle, etat in plan.drapeaux.items():
            statut = ('ouvert' if etat['actif']
                      else ('absent de la base' if not etat['present'] else 'fermé'))
            ecrire(f'  Drapeau               : {cle} → {statut}')
        ecrire(f'  Écriture autorisée    : {plan.ecriture_autorisee}')
        for motif in plan.motifs_ecriture:
            ecrire(f'    · {motif}')

        if plan.anomalies_globales:
            ecrire(self.style.WARNING('  ANOMALIES TRANSVERSES :'))
            for anomalie in plan.anomalies_globales:
                ecrire(f'    · {anomalie}')

        ecrire('')
        ecrire(self.style.MIGRATE_HEADING(
            f'  COMPTES À TRAITER ({len(plan.lignes)}) — '
            f'{plan.comptes_a_creer} profil(s) à créer, '
            f'{plan.attributions_prevues} attribution(s), '
            f'{plan.propositions_prevues} proposition(s) sensible(s), '
            f'{plan.roles_bloques} rôle(s) bloqué(s) par un périmètre local'
        ))
        for ligne in plan.lignes:
            marque = 'SUPERUSER' if ligne.est_superutilisateur else ligne.role_legacy
            ecrire(f'  · {ligne.username} [{marque}]')
            for prevu in ligne.roles:
                cible = ('PROPOSÉ (sensible)' if prevu.sensible and prevu.perimetre_posable
                         else ('ACTIF' if prevu.perimetre_posable else 'BLOQUÉ'))
                ecrire(
                    f'      - {prevu.code} · {cible} · périmètre « {prevu.perimetre_defaut} »'
                    f' · plafonds {", ".join(prevu.plafonds_permissions) or "—"}'
                )
                for anomalie in prevu.anomalies:
                    ecrire(f'        ! {anomalie}')
            for anomalie in ligne.anomalies:
                ecrire(f'      ! {anomalie}')
        ecrire('')
        ecrire(self.style.SUCCESS(
            'Prévisualisation terminée (aucune écriture). '
            'Passer par « initialiser_rbac --appliquer » après validation.'
        ))
