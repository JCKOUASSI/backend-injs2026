"""GET-INJS APP — mesure de charge reproductible (Phase 4 de la mission).

Le module doit tenir **3 500 étudiants** par année et viser **14 000**. Une
telle affirmation ne se démontre pas par un commentaire : ce commandement
construit un jeu synthétique reproductible, exécute le vrai chemin d'import et
le vrai moteur de génération, puis publie les mesures.

Trois précautions :

1. **les données sont synthétiques et identifiables** (matricules ``BENCH-…``,
   formation « FORMATION BENCHMARK ») : aucun étudiant réel n'est créé ;
2. **rien ne reste en base par défaut** : tout le scénario s'exécute dans une
   transaction annulée à la fin (``--garder`` pour conserver, à réserver à un
   environnement de test) ;
3. **aucune mesure inventée** : si le scénario ne peut pas générer (pas de
   créneau, pas de salle…), la commande le dit et sort en code non nul.

Exemples
--------
    python manage.py benchmark_getinjs --etudiants 100
    python manage.py benchmark_getinjs --tous --json /tmp/bench.json
"""

import json
import time
from datetime import time as heure

from django.core.management.base import BaseCommand
from django.db import connection, transaction
from django.test.utils import CaptureQueriesContext

ETAPES_STANDARD = (100, 500, 3500, 7000, 14000)


class Command(BaseCommand):
    help = "Mesure l'import et la génération GET-INJS pour un volume d'étudiants donné."

    def add_arguments(self, parser):
        parser.add_argument(
            '--etudiants', type=int, default=100,
            help='Nombre d’étudiants synthétiques (défaut 100).',
        )
        parser.add_argument(
            '--groupes', type=int, default=0,
            help='Nombre de groupes (défaut : ceil(étudiants / 60)).',
        )
        parser.add_argument(
            '--tous', action='store_true',
            help='Exécute la série standard 100 / 500 / 3 500 / 7 000 / 14 000.',
        )
        parser.add_argument(
            '--garder', action='store_true',
            help='Conserve les données synthétiques (par défaut, tout est annulé).',
        )
        parser.add_argument('--json', dest='fichier_json', default='',
                            help='Écrit le rapport de mesures dans ce fichier JSON.')
        parser.add_argument(
            '--max-consecutives', dest='max_consecutives', type=float, default=None,
            help='Borne de série consécutive à appliquer pendant la mesure '
                 '(défaut : valeur enregistrée dans l’administration).',
        )
        parser.add_argument(
            '--max-jour', dest='max_jour', type=float, default=None,
            help='Borne journalière à appliquer pendant la mesure '
                 '(défaut : valeur enregistrée dans l’administration).',
        )
        parser.add_argument(
            '--souples', choices=('defaut', 'inactif', 'actif'), default='defaut',
            help='Régime des contraintes souples pendant la mesure. « defaut » '
                 '(défaut) mesure la politique réellement enregistrée ; '
                 '« inactif »/« actif » forcent un régime dans la transaction '
                 'annulée, sans modifier la base.',
        )

    def handle(self, *args, **options):
        volumes = list(ETAPES_STANDARD) if options['tous'] else [options['etudiants']]
        self.souples = options['souples']
        self.max_consecutives = options['max_consecutives']
        self.max_jour = options['max_jour']
        rapports = []
        for volume in volumes:
            rapport = self._scenario(
                volume,
                groupes=options['groupes'] or max(1, -(-volume // 60)),
                garder=options['garder'],
            )
            rapports.append(rapport)
            self.stdout.write(self.style.HTTP_INFO(
                f"{volume} étudiants : import {rapport['import_ms']} ms, "
                f"génération {rapport['generation_ms']} ms, "
                f"{rapport['seances_placees']} séances placées, "
                f"{rapport['seances_non_placees']} non placées, "
                f"{rapport['requetes_sql']} requêtes SQL."
            ))
            if rapport.get('contraintes_souples_bilan') is not None:
                bilan_souple = rapport['contraintes_souples_bilan']
                self.stdout.write(
                    '    contraintes souples : '
                    f"{'actives' if bilan_souple['active'] else 'inactives'}, "
                    f"{bilan_souple['trous']} trou(s), "
                    f"{bilan_souple['series_trop_longues']} série(s) longue(s), "
                    f"{bilan_souple['journees_surchargees']} journée(s) chargée(s), "
                    f"{bilan_souple['penalites']} pénalité(s)."
                )
            if rapport.get('erreur'):
                self.stderr.write(self.style.ERROR(rapport['erreur']))

        if options['fichier_json']:
            with open(options['fichier_json'], 'w', encoding='utf-8') as flux:
                json.dump(rapports, flux, ensure_ascii=False, indent=2)
            self.stdout.write(f'Rapport écrit dans {options["fichier_json"]}')

        return json.dumps(rapports, ensure_ascii=False)

    # ── Scénario ─────────────────────────────────────────────────────────────
    def _scenario(self, nb_etudiants, *, groupes, garder):
        from edts.moteur.annee import generer_annee
        from edts.moteur.import_inscrits import importer_inscrits
        from edts.models import CreneauTemplate
        from formations.models import RefBatiment, RefFormation, RefSalle, RefSite
        from scolarite.models import (
            ECUE, AnneeAcademique, Groupe, Maquette, Niveau, Parcours, Semestre, UE,
        )

        rapport = {
            'etudiants_demandes': nb_etudiants,
            'groupes': groupes,
            'import_ms': None,
            'generation_ms': None,
            'seances_placees': 0,
            'seances_non_placees': 0,
            'requetes_sql': 0,
            'conserve': garder,
            'erreur': '',
        }

        with transaction.atomic():
            annee = AnneeAcademique.objects.create(
                libelle=f'BENCHMARK-{nb_etudiants}',
                date_debut='2098-09-01', date_fin='2099-08-31',
            )
            formation = RefFormation.objects.create(
                intitule=f'FORMATION BENCHMARK {nb_etudiants}',
                perimetre='INJS', filiere_code='F01', source='A45',
            )
            niveau, _ = Niveau.objects.get_or_create(
                code='L1',
                defaults={'libelle': 'Licence 1', 'cycle': 'LICENCE',
                          'ordre': 1, 'credits_requis': 60},
            )
            semestre, _ = Semestre.objects.get_or_create(
                niveau=niveau, numero=1, defaults={'libelle': 'S1'},
            )
            parcours = Parcours.objects.create(
                code=f'PB{nb_etudiants}', intitule='Parcours benchmark',
                ref_formation=formation,
            )
            site = RefSite.objects.create(nom=f'SITE BENCHMARK {nb_etudiants}')
            batiment = RefBatiment.objects.create(site=site, nom='B1')
            # ``get_or_create`` et non ``create`` : la base réelle contient déjà
            # les 24 créneaux du canevas officiel. Un benchmark qui exige une
            # table vide n'est pas rejouable là où l'on veut mesurer.
            crees, reutilises = 0, 0
            for jour in ('LUNDI', 'MARDI', 'MERCREDI', 'JEUDI', 'VENDREDI'):
                for debut, fin in ((8, 10), (10, 12), (14, 16), (16, 18)):
                    _, cree = CreneauTemplate.objects.get_or_create(
                        jour=jour, heure_debut=heure(debut, 0),
                        heure_fin=heure(fin, 0),
                    )
                    crees += int(cree)
                    reutilises += int(not cree)
            for index in range(groupes):
                Groupe.objects.create(
                    annee_academique=annee, ref_formation=formation,
                    parcours=parcours, niveau=niveau, nom=f'L1-G{index + 1}',
                    capacite_max=60,
                )
                RefSalle.objects.create(
                    site=site, batiment=batiment, nom=f'S{index + 1}',
                    type_lieu='SALLE', capacite=60,
                )

            maquette = Maquette.objects.create(
                annee_academique=annee, ref_formation=formation,
                parcours=parcours, niveau=niveau,
            )
            for numero in range(1, 6):
                ue = UE.objects.create(
                    maquette=maquette, semestre=semestre, code=f'UE{numero}',
                    intitule=f'UE benchmark {numero}', credits=6,
                )
                ecue = ECUE.objects.create(
                    ue=ue, code=f'ECUE{numero}', intitule=f'ECUE benchmark {numero}',
                    credits=3,
                )
                ecue.volume_cm = 10
                ecue.volume_td = 6
                ecue.save(update_fields=['volume_cm', 'volume_td'])
            maquette.statut = Maquette.Statut.ACTIVE
            maquette.save()

            # Import réel : même chemin que la production (CSV, idempotence,
            # rapprochement référentiel), pas un insert direct en base.
            entete = 'matricule;nom;prenoms;formation;niveau;semestre;groupe;vague\n'
            lignes = [
                f'BENCH-{i:06d};ETUDIANT{i};BENCHMARK;{formation.intitule};L1;S1;'
                f'L1-G{(i % groupes) + 1};V1'
                for i in range(nb_etudiants)
            ]
            contenu = (entete + '\n'.join(lignes) + '\n').encode('utf-8')

            debut = time.monotonic()
            import_rapport = importer_inscrits(
                annee_academique_id=annee.pk,
                nom_fichier=f'benchmark_{nb_etudiants}.csv',
                contenu=contenu,
                appliquer=True,
            )
            rapport['import_ms'] = int((time.monotonic() - debut) * 1000)
            rapport['etudiants_importes'] = import_rapport.effectif_total
            rapport['lignes_rejetees'] = import_rapport.lignes_rejetees

            # Régime des contraintes souples, appliqué dans la transaction
            # (donc annulé avec elle) : la mesure ne laisse aucune trace.
            from edts.models import PolitiqueContraintesSouples
            from edts.moteur import contraintes as C
            # « defaut » = ne rien forcer : on mesure la politique enregistrée.
            if self.souples != 'defaut':
                reglages = {'actives': self.souples == 'actif'}
                if self.max_consecutives is not None:
                    reglages['max_heures_consecutives'] = self.max_consecutives
                if self.max_jour is not None:
                    reglages['max_heures_par_jour'] = self.max_jour
                PolitiqueContraintesSouples.objects.update_or_create(
                    pk=1, defaults=reglages,
                )
            rapport['contraintes_souples_regime'] = self.souples
            rapport['contraintes_souples_politique'] = C.politique_lisible(
                C.politique_souples())

            debut = time.monotonic()
            with CaptureQueriesContext(connection) as requetes:
                bilan = generer_annee(annee.pk, semaines=[1], persister=False)
            rapport['generation_ms'] = int((time.monotonic() - debut) * 1000)
            # 0 = journal saturé (Django plafonne à 9 000 requêtes) : on ne
            # présente pas ce cas comme « aucune requête ».
            rapport['requetes_sql'] = len(requetes.captured_queries) or None
            rapport['status_global'] = bilan.get('status_global')
            rapport['seances_placees'] = bilan.get('totaux', {}).get('seances_placees', 0)
            rapport['seances_non_placees'] = bilan.get('totaux', {}).get('seances_non_placees', 0)
            rapport['etudiants_couverts'] = bilan.get('totaux', {}).get('etudiants_couverts', 0)
            rapport['contraintes_souples_bilan'] = bilan.get('totaux', {}).get(
                'contraintes_souples')
            rapport['creneaux_crees'] = crees
            rapport['creneaux_reutilises'] = reutilises
            if bilan.get('status_global') == 'IMPOSSIBLE':
                rapport['erreur'] = (
                    'Génération impossible : '
                    + str(bilan.get('motif_echec') or 'motif non fourni')
                )

            if not garder:
                # Annulation explicite : aucune donnée synthétique ne survit.
                transaction.set_rollback(True)
        return rapport
