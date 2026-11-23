"""Contrôle d'un référentiel pédagogique INJS-LMD — moteur d'import (A-5.4).

Cette commande **ne sait pas importer**. Elle valide, trace et prévisualise.
L'écriture en base n'est volontairement pas implémentée : elle appartient à un
lot ultérieur, après validation humaine du rapport de contrôle.

    python manage.py import_referentiel_pedagogique --help
    python manage.py import_referentiel_pedagogique --input fichier.csv --dry-run
    python manage.py import_referentiel_pedagogique --input fichier.csv --dry-run --strict

Garanties :

* ``--dry-run`` est **implicite et obligatoire** : cette commande n'écrit rien ;
* une seule condition A→K manquante rend la ligne NON IMPORTABLE ;
* une valeur absente reste ``None`` — jamais 0, jamais une estimation ;
* un code n'est jamais généré ;
* une source P3/P4 ne peut pas devenir une donnée officielle.
"""

import csv
from collections import Counter
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from scolarite.pedagogie_validateur import valider_fichier


class Command(BaseCommand):
    help = (
        "Controle un referentiel pedagogique INJS-LMD (CSV) et emet un rapport de "
        "validation. N'ecrit jamais en base de donnees."
    )

    def add_arguments(self, parser):
        parser.add_argument('--input', '-i', metavar='CHEMIN',
                            help='Fichier CSV a controler.')
        parser.add_argument('--format', '-f', default='csv', choices=['csv', 'xlsx'],
                            help="Format d'entree (A-5.4 : seul csv est operationnel).")
        parser.add_argument('--delimiter', default=';',
                            help='Delimiteur CSV (defaut « ; »).')
        parser.add_argument('--dry-run', action='store_true', default=True,
                            help='Mode simulation — seule valeur acceptee en A-5.4.')
        parser.add_argument('--apply', action='store_true', default=False,
                            help='RESERVE — non implemente en A-5.4.')
        parser.add_argument('--strict', action='store_true', default=False,
                            help='Echoue des la premiere anomalie bloquante.')
        parser.add_argument('--rapport-erreurs', metavar='CHEMIN',
                            help='Fichier CSV de sortie pour les anomalies.')
        parser.add_argument('--rapport-resume', metavar='CHEMIN',
                            help='Fichier CSV de sortie pour le resume.')
        parser.add_argument('--previsualisation', action='store_true', default=False,
                            help="Affiche l'apercu de chaque ligne evaluee.")
        parser.add_argument('--plan', action='store_true', default=False,
                            help='Simule le plan d\'import (A-6) — jamais d\'ecriture.')
        parser.add_argument('--rapport-plan', metavar='CHEMIN',
                            help='Fichier CSV du plan d\'import simule.')

    def handle(self, *args, **options):
        if options['apply']:
            raise CommandError(
                "--apply n'est PAS implemente en A-5.4. Cette commande controle et "
                "previsualise uniquement. Aucune ecriture en base n'est possible.")
        if options['format'] != 'csv':
            raise CommandError(
                f"Format {options['format']} non operationnel en A-5.4 : "
                "utilisez --format csv.")
        if not options['input']:
            raise CommandError('Indiquer --input CHEMIN.')
        chemin = Path(options['input'])
        if not chemin.exists():
            raise CommandError(f'Fichier introuvable : {chemin}')

        resultat = valider_fichier(chemin, delimiter=options['delimiter'])
        lignes = resultat['lignes']
        anomalies = list(resultat['anomalies'])
        for lv in lignes:
            anomalies.extend(lv.anomalies)

        bloquantes = [a for a in anomalies if a.niveau == 'ERREUR_BLOQUANTE']
        avert = [a for a in anomalies if a.niveau == 'AVERTISSEMENT']
        importables = [lv for lv in lignes if lv.importable]
        # Une ligne est invalide si au moins une anomalie bloquante la concerne
        # (les anomalies globales d'ECTS / doublons n'ont pas de n° de ligne).
        lignes_invalides = {a.ligne for a in bloquantes if a.ligne}
        invalides = len(lignes_invalides)

        self.stdout.write('')
        self.stdout.write('=' * 72)
        self.stdout.write('CONTROLE DU REFERENTIEL PEDAGOGIQUE INJS-LMD (dry-run)')
        self.stdout.write('=' * 72)
        self.stdout.write(f"Fichier            : {resultat['fichier']}")
        self.stdout.write(f"SHA-256 source     : {resultat['sha256']}")
        self.stdout.write(f"Lignes lues        : {len(lignes)}")
        self.stdout.write(f"Lignes valides     : {len(lignes) - invalides}")
        self.stdout.write(f"Lignes invalides   : {invalides}")
        self.stdout.write(f"Lignes importables : {len(importables)}")
        self.stdout.write(f"Lignes NON import. : {len(lignes) - len(importables)}")
        self.stdout.write(f"Erreurs bloquantes : {len(bloquantes)}")
        self.stdout.write(f"Avertissements     : {len(avert)}")
        self.stdout.write('')
        self.stdout.write('Repartition par code :')
        for code, n in sorted(Counter(a.code for a in anomalies).items(),
                              key=lambda x: -x[1]):
            self.stdout.write(f'   {code:<34} {n}')
        self.stdout.write('')
        self.stdout.write(f"ANOMALIES ECTS     : {len([a for a in anomalies if a.code.startswith('G_ECTS')])}")
        self.stdout.write(f"ANOMALIES CODES     : {len([a for a in anomalies if 'CODE' in a.code])}")
        self.stdout.write(f"ANOMALIES COEFF     : {len([a for a in anomalies if 'COEFFICIENT' in a.code])}")
        self.stdout.write(f"ANOMALIES CM        : {len([a for a in anomalies if a.code.startswith('I_')])}")
        self.stdout.write(f"ANOMALIES TD        : {len([a for a in anomalies if a.code.startswith('J_')])}")
        self.stdout.write(f"ANOMALIES TP        : {len([a for a in anomalies if a.code.startswith('K_')])}")
        self.stdout.write(f"DOUBLONS            : {len([a for a in anomalies if 'DOUBLON' in a.code])}")
        self.stdout.write(f"CONTRADICTIONS      : {len([a for a in anomalies if 'CONTRAD' in a.code])}")

        if options['previsualisation']:
            self.stdout.write('')
            self.stdout.write('PREVISUALISATION :')
            self.stdout.write(f"{'L':>4} {'FIL':<5} {'NIV':<4} {'SEM':<5} {'CODE_UE':<9} "
                              f"{'CODE_ECUE':<10} {'CECT':<6} {'COEF':<6} {'CM':<5} "
                              f"{'TD':<5} {'TP':<5} {'IMP':<4}")
            for lv in lignes:
                a = lv.apercu()
                self.stdout.write(
                    f"{a['ligne']:>4} {a['filiere'][:5]:<5} {a['niveau'][:4]:<4} "
                    f"{a['semestre'][:5]:<5} {a['code_ue'][:9]:<9} {a['code_ecue'][:10]:<10} "
                    f"{a['cect'][:6]:<6} {a['coefficient'][:6]:<6} {a['cm'][:5]:<5} "
                    f"{a['td'][:5]:<5} {a['tp'][:5]:<5} {a['importable']:<4}")

        if options['rapport_erreurs']:
            self._ecrire_erreurs(options['rapport_erreurs'], anomalies,
                                 resultat['fichier'])
            self.stdout.write(f"\nRapport d'anomalies ecrit : {options['rapport_erreurs']}")
        if options['rapport_resume']:
            self._ecrire_resume(options['rapport_resume'], resultat, lignes,
                                bloquantes, avert, invalides, importables)
            self.stdout.write(f"Resume ecrit : {options['rapport_resume']}")

        if options['plan']:
            self._simuler_plan(resultat, options)

        self.stdout.write('')
        if bloquantes:
            self.stdout.write(self.style.ERROR(
                f"ECHEC : {len(bloquantes)} anomalie(s) bloquante(s). "
                "Aucune ecriture en base."))
            if options['strict']:
                raise CommandError(
                    f"--strict : {len(bloquantes)} anomalie(s) bloquante(s). "
                    "Controle interrompu, aucune ecriture.")
        else:
            self.stdout.write(self.style.SUCCESS(
                'Aucune anomalie bloquante. Referentiel techniquement importable '
                '— validation humaine remainante.'))

    def _simuler_plan(self, resultat, options):
        """Simule le plan d'import. N'exécute AUCUNE écriture (A-6)."""
        from scolarite.models import AnneeAcademique
        from scolarite.pedagogie_raccordement import construire_plan

        lignes = [lv for lv in resultat['lignes'] if not any(
            a.niveau == 'ERREUR_BLOQUANTE' for a in lv.anomalies)]
        self.stdout.write('')
        self.stdout.write('=' * 72)
        self.stdout.write('SIMULATION DU PLAN D\'IMPORT (aucune ecriture)')
        self.stdout.write('=' * 72)
        self.stdout.write(f"Lignes eligible au plan : {len(lignes)} "
                          f"(sur {len(resultat['lignes'])} lues)")

        if not lignes:
            self.stdout.write(self.style.ERROR(
                'Aucune ligne ne franchit la grille A->K : aucun plan construit.'))
            return

        annee = AnneeAcademique.objects.order_by('id').first()
        plan = construire_plan(lignes, resultat['fichier'], resultat['sha256'], annee)
        resume = plan.resume()
        for k, v in resume.items():
            self.stdout.write(f"{k:<20} {v}")

        self.stdout.write('')
        self.stdout.write('PREVISUALISATION DU PLAN :')
        self.stdout.write(f"{'OBJET':<9}{'ID':<11}{'ACTION':<11}{'STATUT':<20}MOTIF")
        for a in plan.actions[:50]:
            self.stdout.write(f"{a.objet:<9}{str(a.identifiant)[:10]:<11}"
                              f"{a.action:<11}{a.statut:<20}{a.motif[:44]}")
        if len(plan.actions) > 50:
            self.stdout.write(f'... {len(plan.actions) - 50} actions supplementaires')

        if options['rapport_plan']:
            with open(options['rapport_plan'], 'w', encoding='utf-8', newline='') as fh:
                w = csv.writer(fh, delimiter=';')
                w.writerow(['objet', 'source', 'identifiant', 'libelle', 'action_future',
                            'statut', 'raison', 'filiere', 'niveau', 'semestre',
                            'source_id', 'source_hash', 'ligne'])
                for a in plan.actions:
                    w.writerow([a.objet, plan.source, a.identifiant, a.libelle,
                                a.action, a.statut, a.motif, a.filiere, a.niveau,
                                a.semestre, a.source_id, a.source_hash, a.ligne])
            self.stdout.write(f"\nPlan simule ecrit : {options['rapport_plan']}")

        self.stdout.write('')
        self.stdout.write(self.style.WARNING(
            'SIMULATION UNIQUEMENT — PRETE_A_IMPORTER ne declenche AUCUNE ecriture.'))

    def _ecrire_erreurs(self, chemin, anomalies, fichier):
        with open(chemin, 'w', encoding='utf-8', newline='') as fh:
            w = csv.DictWriter(fh, fieldnames=[
                'fichier', 'ligne', 'niveau', 'code', 'critere', 'filiere',
                'niveau_etude', 'semestre', 'ue', 'ecue', 'champ', 'valeur', 'motif'],
                delimiter=';')
            w.writeheader()
            for a in anomalies:
                d = a.ligne_csv()
                d['fichier'] = fichier
                w.writerow(d)

    def _ecrire_resume(self, chemin, resultat, lignes, bloquantes, avert,
                       invalides, importables):
        with open(chemin, 'w', encoding='utf-8', newline='') as fh:
            w = csv.writer(fh, delimiter=';')
            w.writerow(['fichier', 'sha256', 'lignes_lues', 'lignes_valides',
                        'lignes_invalides', 'lignes_importables', 'lignes_non_importables',
                        'erreurs_bloquantes', 'avertissements', 'doublons',
                        'contradictions', 'anomalies_ects', 'anomalies_codes',
                        'anomalies_coefficients', 'anomalies_cm', 'anomalies_td',
                        'anomalies_tp'])
            w.writerow([
                resultat['fichier'], resultat['sha256'], len(lignes),
                len(lignes) - invalides, invalides, len(importables),
                len(lignes) - len(importables), len(bloquantes), len(avert),
                len([a for a in bloquantes if 'DOUBLON' in a.code]),
                len([a for a in bloquantes if 'CONTRAD' in a.code]),
                len([a for a in bloquantes if a.code.startswith('G_ECTS')]),
                len([a for a in bloquantes if 'CODE' in a.code]),
                len([a for a in bloquantes if 'COEFFICIENT' in a.code]),
                len([a for a in bloquantes if a.code.startswith('I_')]),
                len([a for a in bloquantes if a.code.startswith('J_')]),
                len([a for a in bloquantes if a.code.startswith('K_')]),
            ])
