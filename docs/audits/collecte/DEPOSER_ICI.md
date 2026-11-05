# Dépôt des résultats de collecte

Ce dossier reçoit les fichiers produits par `run_audit.sh` sur le VPS.

## Convention de nommage (automatique)

`run_audit.sh` produit déjà les bons noms ; il suffit de copier les fichiers tels quels :

```
injs-db__20_empreinte_modules__<horodatage>.txt
injs-db__00_profil_schema__<horodatage>.txt
injs-db__10_anomalies__<horodatage>.txt
injs_lmd_prod_20261026__00_profil_schema__<horodatage>.txt
injs_lmd_prod_20261026__10_anomalies__<horodatage>.txt
```

## Consolidation

Dès que les fichiers sont ici :

```sh
python3 ../sql/consolider.py . -o ../2026-11-05-consolidation.md
```

Le script lit uniquement ces fichiers texte, n'ouvre aucune connexion, et produit les
tableaux comparatifs : contexte des deux bases, volumes exacts, contraintes, anomalies
quantifiées (orphelins, doublons, vides, dates, statuts, algorithmes de hachage) et
écart entre les 222 tables attendues et les tables réellement présentes.

Toute rubrique absente d'un fichier est marquée « non fourni » : aucune valeur n'est
estimée.

## Contrôle avant dépôt

Aucun fichier de ce dossier ne doit contenir de donnée nominative. Les scripts
n'affichent que des compteurs, des noms de tables/colonnes/contraintes et des codes
de statut. En cas de doute, vérifier par :

```sh
grep -iE "@|nom|prenom|telephone|email" *.txt | head
```
