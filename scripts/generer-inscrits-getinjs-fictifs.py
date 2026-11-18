#!/usr/bin/env python3
"""Générer 3 500 inscriptions fictives GET-INJS ; aucune écriture en base.

Catalogue : 8 filières × cycles Licence/Master observés dans la base locale.
Toujours analyser le fichier sur l'instance cible avant toute importation.
"""

import argparse
import csv
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

FILIERES = (
    ('F01', 'ÉDUCATION ET MOTRICITÉ'),
    ('F02', 'ACTIVITÉS PHYSIQUES ADAPTÉES'),
    ('F03', 'ENTRAÎNEMENT SPORTIF'),
    ('F04', 'MANAGEMENT DU SPORT'),
    ('F05', 'ANDRAGOGIE'),
    ('F06', 'LOISIR'),
    ('F07', 'ENTREPRENEURIAT JEUNESSE ET CONDUITE DE PROJETS'),
    ('F08', 'GÉRONTOLOGIE'),
)
NOMS = ('Kouassi', 'Koné', 'Traoré', 'Yao', 'Kouamé', 'N’Guessan',
        'Bamba', 'Ouattara', 'Touré', 'Koffi', 'N’Dri', 'Yapi', 'Soro',
        'Kouadio', 'Diabaté', 'Aké')
PRENOMS_F = ('Aya', 'Aïssata', 'Awa', 'Aminata', 'Mariame', 'Adjoua',
             'Affoué', 'Fatoumata', 'Mariam', 'Nadia', 'Akissi', 'Kady')
PRENOMS_M = ('Kouamé', 'Koffi', 'Yao', 'Moussa', 'Ibrahim', 'Bakary',
             'Adama', 'Ismaël', 'Désiré', 'Siaka', 'Serge', 'Souleymane')
VAGUES = ('PREMIERE VAGUE', 'DEUXIEME VAGUE', 'TROISIEME VAGUE')
ENTETES = ('matricule', 'nom', 'prenoms', 'sexe', 'date_naissance',
           'formation', 'filiere', 'filiere_code', 'niveau', 'semestre',
           'groupe', 'vague', 'statut')
NOMBRE = 3500
CAPACITE_CIBLE = 35

# Combinaisons cohérentes : 3 niveaux Licence × 2 semestres + 2 niveaux
# Master × 2 semestres = 10 par filière, 80 sur les huit filières.
COHORTES = tuple(
    (code, filiere, cycle, niveau, semestre)
    for code, filiere in FILIERES
    for cycle, niveaux in (('LICENCE', ('L1', 'L2', 'L3')),
                           ('MASTER', ('M1', 'M2')))
    for niveau in niveaux
    for semestre in (2 * int(niveau[1]) - 1 + (6 if cycle == 'MASTER' else 0),
                     2 * int(niveau[1]) + (6 if cycle == 'MASTER' else 0))
)


def generer(chemin):
    """Écrit un CSV UTF-8 BOM reproductible, groupes distincts par semestre."""
    compteurs = Counter()
    chemin.parent.mkdir(parents=True, exist_ok=True)
    with chemin.open('w', encoding='utf-8-sig', newline='') as fichier:
        writer = csv.writer(fichier, delimiter=';', lineterminator='\n')
        writer.writerow(ENTETES)
        for numero in range(1, NOMBRE + 1):
            code, filiere, cycle, niveau, semestre = COHORTES[(numero - 1) % len(COHORTES)]
            cle = (code, niveau, semestre)
            rang = compteurs[cle]
            compteurs[cle] += 1
            indice_groupe = rang // CAPACITE_CIBLE + 1
            groupe = f'GETDEMO-{code}-{niveau}-S{semestre}-G{indice_groupe:02d}'
            vague = VAGUES[(semestre + indice_groupe) % len(VAGUES)]
            feminin = numero % 2 == 1
            prenoms = PRENOMS_F if feminin else PRENOMS_M
            naissance = date(1998, 1, 1) + timedelta(days=(numero * 37) % 4000)
            writer.writerow((
                f'FICTGET-{numero:05d}', NOMS[(numero * 7) % len(NOMS)],
                prenoms[(numero * 11) % len(prenoms)],
                'Féminin' if feminin else 'Masculin', naissance.isoformat(),
                f'{filiere} — {cycle}', filiere, code, niveau, f'S{semestre}',
                groupe, vague, 'INSCRIT',
            ))
    assert sum(compteurs.values()) == NOMBRE
    return compteurs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('chemin', type=Path, help='CSV à produire')
    args = parser.parse_args()
    comptes = generer(args.chemin)
    print(f'{args.chemin}: {sum(comptes.values())} lignes, '
          f'{len(comptes)} cohortes formation/niveau/semestre')


if __name__ == '__main__':
    main()
