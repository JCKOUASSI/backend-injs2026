"""Paramètre la notation INJS sans l'activer.

Le classeur officiel publie trois valeurs — poids du contrôle continu (0,4),
poids de l'examen (0,6) et seuil de validation d'une UE (10/20) — en les
présentant lui-même comme **à confirmer par le règlement des études**.

Cette commande les enregistre donc dans le référentiel ``parametres.Parametre``
au statut **PROVISOIRE** :

* elles sont visibles, datées, tracées et modifiables par l'administration ;
* elles ne sont **jamais** renvoyées par ``Parametre.valeur_institutionnelle``,
  donc aucun calcul ne les applique ;
* ``--valider`` les promeut au statut VALIDÉ, ce qui est une **décision
  institutionnelle** et non une opération technique : l'historique
  ``ParametreHistorique`` en conserve la trace.

La commande est idempotente et non destructive : une valeur déjà saisie par
l'établissement n'est jamais écrasée sans ``--force``.
"""

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from parametres.models import CLES_NOTATION, Parametre, ParametreHistorique

#: Jeu de données produit par le script d'extraction.
DONNEES = (
    Path(__file__).resolve().parents[3]
    / 'scolarite' / 'data' / 'referentiel_offre_formation.json'
)

#: Clé du jeu de données → clé du paramètre.
CORRESPONDANCE = {
    'poids_controle_continu': 'notation.poids_controle_continu',
    'poids_examen': 'notation.poids_examen',
    'seuil_validation_ue': 'notation.seuil_validation_ue',
}

TYPES = {
    'notation.poids_controle_continu': 'decimal',
    'notation.poids_examen': 'decimal',
    'notation.seuil_validation_ue': 'decimal',
}


class Command(BaseCommand):
    help = (
        'Enregistre les paramètres de notation du référentiel INJS au statut '
        'PROVISOIRE (jamais appliqués) ; --valider les promeut en règle '
        'institutionnelle.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--fichier', default=str(DONNEES))
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument(
            '--valider', action='store_true',
            help='Promeut les paramètres au statut VALIDÉ (décision institutionnelle).',
        )
        parser.add_argument(
            '--force', action='store_true',
            help='Écrase une valeur déjà saisie par l’établissement.',
        )

    def handle(self, *args, **options):
        simuler = options['dry_run']
        chemin = Path(options['fichier'])
        if not chemin.is_file():
            raise CommandError(
                f'Jeu de données introuvable : {chemin}\n'
                'Générez-le avec : python scripts/extraire_referentiel_offre_formation.py'
            )
        donnees = json.loads(chemin.read_text(encoding='utf-8'))
        notation = donnees.get('notation_provisoire') or {}
        valeurs = notation.get('valeurs') or {}

        if not valeurs:
            raise CommandError(
                'Le jeu de données ne contient aucune valeur de notation : '
                'aucun paramètre créé.'
            )

        self.stdout.write(f'Source   : {notation.get("source", "?")}')
        self.stdout.write(f'Statut   : {notation.get("statut", "?")}')
        self.stdout.write(
            f'Mode     : {"SIMULATION" if simuler else "ÉCRITURE"} '
            f'— cible : {"VALIDÉ" if options["valider"] else "PROVISOIRE"}'
        )
        self.stdout.write('')

        creees = maj = inchangees = ignorees = 0
        with transaction.atomic():
            for cle_source, cle in CORRESPONDANCE.items():
                valeur = valeurs.get(cle_source)
                if valeur in (None, ''):
                    self.stdout.write(self.style.WARNING(
                        f'  ABSENT   {cle} — valeur non publiée par la source.'
                    ))
                    ignorees += 1
                    continue

                statut = (
                    Parametre.StatutValidation.VALIDE if options['valider']
                    else Parametre.StatutValidation.PROVISOIRE
                )
                existant = Parametre.objects.filter(cle=cle).first()
                if existant is None:
                    creees += 1
                    self.stdout.write(
                        f'  CRÉÉ     {cle} = {valeur} ({statut})'
                    )
                    if not simuler:
                        Parametre.objects.create(
                            cle=cle,
                            libelle=CLES_NOTATION[cle],
                            description=(
                                'Valeur publiée par le référentiel officiel INJS et '
                                'marquée « à confirmer » par ce même document. '
                                f'Provenance : {notation.get("source", "")}. '
                                + notation.get('avertissement_source', '')
                            ).strip(),
                            categorie='scolarite',
                            type=TYPES[cle],
                            valeur=str(valeur),
                            valeur_defaut=str(valeur),
                            statut_validation=statut,
                            ordre=10,
                        )
                    continue

                deja_saisi = existant.valeur not in ('', None, existant.valeur_defaut)
                if deja_saisi and not options['force']:
                    ignorees += 1
                    self.stdout.write(self.style.WARNING(
                        f'  PRÉSERVÉ {cle} = {existant.valeur} (valeur de '
                        'l’établissement ; utiliser --force pour l’écraser).'
                    ))
                    continue

                changement = (
                    str(existant.valeur) != str(valeur)
                    or existant.statut_validation != statut
                )
                if not changement:
                    inchangees += 1
                    continue

                maj += 1
                self.stdout.write(
                    f'  MIS À JOUR {cle} : {existant.valeur} → {valeur} ({statut})'
                )
                if not simuler:
                    ancienne = existant.valeur
                    existant.valeur = str(valeur)
                    existant.statut_validation = statut
                    existant.save(update_fields=[
                        'valeur', 'statut_validation', 'modifie_le',
                    ])
                    if ancienne != str(valeur):
                        ParametreHistorique.objects.create(
                            parametre=existant,
                            ancienne_valeur=ancienne,
                            nouvelle_valeur=str(valeur),
                            motif_modification=(
                                'Alignement sur le référentiel officiel INJS.'
                            ),
                        )

            if simuler:
                transaction.set_rollback(True)

        self.stdout.write('')
        self.stdout.write(
            f'Bilan : {creees} créé(s), {maj} mis à jour, {inchangees} inchangé(s), '
            f'{ignorees} ignoré(s).'
        )
        if not options['valider']:
            self.stdout.write(self.style.WARNING(
                'Statut PROVISOIRE : ces valeurs ne sont appliquées par aucun '
                'calcul (Parametre.valeur_institutionnelle renvoie None). '
                'Utiliser --valider après décision du conseil.'
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                'Statut VALIDÉ : les valeurs sont désormais institutionnelles.'
            ))
