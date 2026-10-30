"""Vérifie le canevas horaire réel contre le canevas officiel de l'INJS.

Le canevas est la donnée la plus structurante de l'emploi du temps : il décide
de la durée des séances, donc du nombre de séances, donc de la charge des
étudiants. Un canevas qui dérive du référentiel ne se voit pas — il produit des
plannings plausibles et faux.

Trois écarts sont distingués, parce qu'ils appellent des corrections
différentes :

* **manquants** — créneaux officiels absents : des plages de cours ne sont pas
  planifiables, la capacité de l'établissement est sous-utilisée ;
* **non prévus** — créneaux en base qui ne figurent pas au référentiel : ils
  seront réellement utilisés par le moteur, donc un horaire non validé entrera
  dans les plannings ;
* **chevauchements** — deux créneaux du même jour se recouvrent : les contrôles
  C1/C2/C3 ne peuvent plus être garantis sur l'intervalle commun.

Rien n'est modifié sans `--creer-manquants`, rien n'est supprimé jamais : un
créneau en base peut déjà porter des séances réelles.

Exemples
--------
    python manage.py verifier_canevas
    python manage.py verifier_canevas --json rapport.json
    python manage.py verifier_canevas --creer-manquants
"""

import json

from django.core.management.base import BaseCommand

from edts.moteur import canevas_officiel as O
from edts.models import CreneauTemplate


class Command(BaseCommand):
    help = (
        'Compare les créneaux types en base au canevas officiel INJS '
        '(6 jours × 4 plages = 24 créneaux) et signale manquants, non prévus '
        'et chevauchements.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--creer-manquants', dest='creer', action='store_true',
            help='Crée les créneaux officiels absents. Ne modifie ni ne supprime '
                 'aucun créneau existant.',
        )
        parser.add_argument(
            '--json', dest='fichier_json', default='',
            help='Écrit le rapport de conformité dans ce fichier JSON.',
        )

    def _creneaux_reels(self):
        return [
            (c.jour, c.heure_debut, c.heure_fin)
            for c in CreneauTemplate.objects.order_by('jour', 'heure_debut')
        ]

    def handle(self, *args, **options):
        rapport = O.comparer_canevas(self._creneaux_reels())

        self.stdout.write(f'Référentiel : {rapport["source"]}')
        self.stdout.write(
            f'Grille officielle : {rapport["attendus"]} créneaux '
            f'({len(O.JOURS_OFFICIELS)} jours × {len(O.PLAGES_OFFICIELLES)} plages de 2 h)')
        self.stdout.write(f'Créneaux en base : {rapport["presents"]}')

        if rapport['manquants']:
            self.stdout.write(self.style.WARNING(
                f'Manquants ({len(rapport["manquants"])}) :'))
            for libelle in rapport['manquants']:
                self.stdout.write(f'  - {libelle}')
        if rapport['non_prevus']:
            self.stdout.write(self.style.WARNING(
                f'Non prévus au référentiel ({len(rapport["non_prevus"])}) :'))
            for libelle in rapport['non_prevus']:
                self.stdout.write(f'  - {libelle}')
        if rapport['chevauchements']:
            self.stdout.write(self.style.ERROR(
                f'Chevauchements ({len(rapport["chevauchements"])}) — '
                'C1/C2/C3 ne sont pas garantis sur ces intervalles :'))
            for gauche, droite in rapport['chevauchements']:
                self.stdout.write(f'  - {gauche}  ⨯  {droite}')

        if options['creer'] and rapport['manquants']:
            crees = 0
            for jour, debut, fin in O.grille_officielle():
                _, cree = CreneauTemplate.objects.get_or_create(
                    jour=jour, heure_debut=debut, heure_fin=fin,
                )
                crees += int(cree)
            self.stdout.write(self.style.SUCCESS(
                f'{crees} créneau(x) officiel(s) créé(s).'))
            rapport = O.comparer_canevas(self._creneaux_reels())
            rapport['crees'] = crees

        if options['fichier_json']:
            with open(options['fichier_json'], 'w', encoding='utf-8') as flux:
                json.dump(rapport, flux, ensure_ascii=False, indent=2)
            self.stdout.write(f'Rapport écrit dans {options["fichier_json"]}')

        if rapport['conforme'] and not rapport['chevauchements']:
            self.stdout.write(self.style.SUCCESS(
                'Canevas CONFORME au référentiel officiel.'))
            return
        self.stdout.write(self.style.ERROR(
            'Canevas NON conforme : les écarts ci-dessus doivent être corrigés '
            'dans Scolarité › Créneaux types (aucune correction automatique '
            'n’est appliquée sans --creer-manquants).'))
