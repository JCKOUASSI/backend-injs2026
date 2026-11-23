#!/usr/bin/env python3
"""Générateur HORS BASE de charge fictive : 5k/10k/15k étudiants.

Sortie CSV volontairement non importable en production : identités et
formations fictives, format de banc d'essai, aucune valeur institutionnelle.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def generer(nb_etudiants: int, sortie: Path, *, capacite: int = 60) -> dict:
    if not (1 <= nb_etudiants <= 15000) or not (1 <= capacite <= 500):
        raise ValueError('Volume ou capacité hors bornes du jeu de test.')
    sortie = sortie.resolve()
    sortie.mkdir(parents=True, exist_ok=True)
    if any(sortie.iterdir()):
        raise ValueError('Le dossier de sortie doit être vide (aucun écrasement).')

    def ouvrir(nom, champs):
        fichier = (sortie / nom).open('w', encoding='utf-8', newline='')
        writer = csv.DictWriter(fichier, fieldnames=champs, delimiter=';')
        writer.writeheader()
        return fichier, writer

    nb_groupes = (nb_etudiants + capacite - 1) // capacite
    f, w = ouvrir('groupes_BENCH_NON_IMPORTABLE.csv', ['groupe_test', 'formation_test', 'capacite_test'])
    with f:
        for numero in range(1, nb_groupes + 1):
            w.writerow({'groupe_test': f'BENCH-G{numero:04d}',
                        'formation_test': 'FORMATION-FICTIVE-BENCH', 'capacite_test': capacite})
    f, w = ouvrir('etudiants_BENCH_NON_IMPORTABLE.csv', ['matricule_fictif', 'groupe_test'])
    with f:
        for numero in range(1, nb_etudiants + 1):
            w.writerow({'matricule_fictif': f'BENCH-ETU-{numero:06d}',
                        'groupe_test': f'BENCH-G{(numero - 1) // capacite + 1:04d}'})
    f, w = ouvrir('besoins_BENCH_NON_IMPORTABLE.csv',
                  ['groupe_test', 'ecue_fictif', 'type_seance', 'duree_minutes_test', 'occurrences_test'])
    with f:
        for numero in range(1, nb_groupes + 1):
            for ecue in range(1, 5):
                w.writerow({'groupe_test': f'BENCH-G{numero:04d}',
                            'ecue_fictif': f'BENCH-ECUE-{ecue}', 'type_seance': 'CM',
                            'duree_minutes_test': 120, 'occurrences_test': 12})
    f, w = ouvrir('calendrier_a_confirmer_NON_ACTIF.csv',
                  ['annee_fictive', 'type', 'date_debut', 'date_fin', 'statut_validation', 'source_document'])
    with f:
        w.writerow({'annee_fictive': 'BENCH-2098-2099', 'type': 'FERIE', 'date_debut': '',
                    'date_fin': '', 'statut_validation': 'A_CONFIRMER', 'source_document': ''})
    manifeste = {'nature': 'DONNEES_SYNTHETIQUES_NON_IMPORTABLES', 'etudiants': nb_etudiants,
                 'groupes': nb_groupes, 'capacite_test': capacite,
                 'besoins_fictifs': nb_groupes * 4,
                 'periode_mobile': 'A_CONFIRMER_SANS_DATE',
                 'note': 'Volumes uniquement fictifs pour mesure de charge, non officiels.'}
    (sortie / 'manifest.json').write_text(json.dumps(manifeste, ensure_ascii=False, indent=2) + '\n')
    return manifeste


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--etudiants', type=int, choices=(5000, 10000, 15000), required=True)
    parser.add_argument('--sortie', type=Path, required=True,
                        help='Dossier de test vide, hors du dépôt. Aucune base utilisée.')
    args = parser.parse_args()
    print(json.dumps(generer(args.etudiants, args.sortie), ensure_ascii=False))
