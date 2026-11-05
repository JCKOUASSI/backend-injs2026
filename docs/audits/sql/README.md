# Pack de collecte — audit comparatif des bases INJS

Ce dossier contient **uniquement des scripts de lecture**. Il sert à obtenir les
mesures qui manquent au rapport d'audit (`../2026-11-05-audit-comparatif-bases-injs.md`)
parce que les bases du VPS ne sont pas joignables depuis l'environnement d'audit.

## Garanties de sécurité

- Chaque script ouvre `BEGIN TRANSACTION READ ONLY` et se termine par `ROLLBACK`.
  PostgreSQL refuse toute écriture dans une transaction en lecture seule : même une
  erreur de script ne peut pas modifier la base.
- `SET default_transaction_read_only = on;` en tête de chaque script.
- Aucune requête n'affiche de donnée nominative : uniquement des compteurs,
  des noms de tables, de colonnes et de contraintes.
- Aucun mot de passe n'est présent dans ces fichiers. L'authentification utilise
  `~/.pgpass` (mode hôte) ou l'utilisateur du conteneur (mode `docker`).
- Aucun `pg_dump`, aucune copie, aucune création de table temporaire.

## Exécution

Sur le VPS (recommandé : la base n'est alors pas exposée au réseau) :

```sh
cd /chemin/vers/backend-injs2026/docs/audits/sql
MODE=docker PG_CONTAINER=<nom_du_conteneur_postgres> sh run_audit.sh
```

ou, si `psql` est installé sur le Mac et que le port 5432 est joignable :

```sh
PGUSER=<utilisateur> PGHOST=<hote> sh run_audit.sh
```

Les résultats sont écrits dans `./collecte/`.

## Ce que produit chaque script

| Script | Contenu |
|---|---|
| `00_profil_schema.sql` | contexte, volumes par schéma, liste et comptage exact des tables, colonnes, clés primaires/étrangères, contraintes `CHECK`, index, historique `django_migrations`, tables sans clé primaire, séquences |
| `10_anomalies.sql` | intégrité des FK (`convalidated`), références orphelines, colonnes texte NOT NULL vides, dates incohérentes, doublons sur clés naturelles (`matricule`, `code`, `numero`), orphelins métier de la base cible |

## Validation effectuée

Les deux scripts ont été exécutés sur deux schémas témoins PostgreSQL 16 créés
pour l'occasion (un schéma de type historique, un schéma de type cible) :
**0 erreur**, et les anomalies volontairement introduites ont toutes été détectées
(clé étrangère orpheline, chaîne vide, doublon de matricule, participant hors
inscription pédagogique, UE sans semestre, ECUE sans UE).

Le VPS étant en PostgreSQL 15, ces scripts n'utilisent que des fonctions
disponibles depuis la version 12 (`to_regclass`, `pg_sequences`, `\gexec`).

Dès que les fichiers de `collecte/` sont disponibles, la consolidation est automatique :

```sh
python3 consolider.py collecte -o ../2026-11-05-consolidation.md
```

`consolider.py` ne se connecte à aucune base : il lit les fichiers texte, produit les
tableaux comparatifs et signale « non fourni » pour toute rubrique absente. Il a été
testé sur les sorties des deux schémas témoins utilisés pour valider les scripts SQL.

## Ce qu'il faut me renvoyer

Les fichiers de `collecte/` (ou le simple copier-coller de leur contenu).
Ils ne contiennent aucune donnée personnelle. Avec ces sorties, les audits A, B
et D pourront être chiffrés exactement, sans nouvelle intervention sur le VPS.
