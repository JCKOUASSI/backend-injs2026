"""Lot B — rattache les sessions de formation (``Formation``) à leur cycle du
référentiel (``RefFormation``) : double représentation D3 résolue par un lien,
pas par une fusion.

Règles :
- rapprochement par intitulé normalisé (insensible à la casse/espaces) ;
- ne touche jamais une ``Formation`` déjà reliée (idempotent, rejouable) ;
- ``--dry-run`` produit le rapport sans écrire.

Aucune donnée n'est déplacée ni supprimée : l'intitulé texte reste la valeur
affichée tant qu'un utilisateur ne valide pas le rattachement.
"""
import re

from django.core.management.base import BaseCommand
from django.db import transaction

from formations.models import Formation, RefFormation


def normaliser(valeur):
    return ' '.join((valeur or '').split()).casefold()


def variantes(intitule):
    """Clés de rapprochement, de la plus stricte à la plus permissive : intitulé
    complet, puis segment avant tiret long/tiret (les sessions ajoutent souvent
    un suffixe « — Vague n » que le cycle du référentiel ne porte pas)."""
    cle = normaliser(intitule)
    rendus = [cle]
    for separateur in ('—', ' – ', ' - ', ' -', '— '):
        if separateur in cle:
            base = normaliser(cle.split(separateur)[0])
            if base and base not in rendus:
                rendus.append(base)
            break
    sans_par = re.sub(r'\s*\([^)]*\)\s*$', '', rendus[-1]).strip()
    if sans_par and sans_par not in rendus:
        rendus.append(sans_par)
    return rendus


class Command(BaseCommand):
    help = 'Rattache les Formations aux cycles RefFormation (lien D3), idempotent.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Affiche le rapport sans écrire.')
        parser.add_argument('--creer-cycles-manquants', action='store_true',
                            help='Pour toute base d’intitulé de session sans cycle '
                                 'correspondant, crée le cycle du référentiel '
                                 '(intitulé nettoyé, actif) puis rattache les sessions.')

    def handle(self, *args, **options):
        dry = options['dry_run']
        cycles = {}
        ambigues = set()
        for cycle in RefFormation.objects.all():
            for index, cle in enumerate(variantes(cycle.intitule)):
                if index == 0:
                    cycles.setdefault(cle, cycle)
        for cycle in RefFormation.objects.all():
            base = variantes(cycle.intitule)
            if len(base) > 1:
                # une base partagée par deux cycles devient non fiable
                if base[1] in cycles and normaliser(cycles[base[1]].intitule) != base[0]:
                    ambigues.add(base[1])

        relatees = 0
        deja = 0
        orphelines = []
        cycles_crees = 0
        qs = Formation.objects.select_related('ref_formation').filter(ref_formation__isnull=True)

        if options['creer_cycles_manquants'] and not dry:
            bases = {}
            for formation in qs:
                cle = variantes(formation.formation)[-1]
                if cle and cle not in cycles:
                    bases.setdefault(cle, formation.formation)
            for cle, intitule_brut in sorted(bases.items()):
                intitule_net = ' '.join(intitule_brut.split())
                for separateur in ('—', ' – ', ' - '):
                    if separateur in intitule_net:
                        intitule_net = intitule_net.split(separateur)[0].strip()
                        break
                cycle, cree = RefFormation.objects.get_or_create(
                    intitule=intitule_net, defaults={'actif': True})
                if cree:
                    cycles_crees += 1
                for index, cle_cycle in enumerate(variantes(cycle.intitule)):
                    if index == 0:
                        cycles.setdefault(cle_cycle, cycle)

        with transaction.atomic():
            for formation in qs:
                cycle = None
                for cle in variantes(formation.formation):
                    if cle in cycles and cle not in ambigues:
                        cycle = cycles[cle]
                        break
                if cycle is None:
                    orphelines.append(formation.formation)
                    continue
                if not dry:
                    formation.ref_formation = cycle
                    formation.save(update_fields=['ref_formation', 'updated_at'])
                relatees += 1
            deja = Formation.objects.filter(ref_formation__isnull=False).count()

        statut = '(SIMULATION — aucune écriture)' if dry else ''
        self.stdout.write(self.style.SUCCESS(
            f'Reconciliation cycles↔formations {statut} : '
            f'{relatees} rattachée(s), {deja} déjà reliée(s), '
            f'{len(orphelines)} sans cycle correspondant'
            + (f', {cycles_crees} cycle(s) créé(s)' if cycles_crees else '') + '.'))
        if orphelines:
            apercu = sorted(set(orphelines))[:15]
            self.stdout.write('Intitulés sans cycle : ' + '; '.join(apercu)
                              + ('…' if len(orphelines) > 15 else ''))
