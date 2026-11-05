# H5 — Expertise des sauvegardes disponibles avant toute décision de récupération

**Date** : 2026-11-05
**Objet** : déterminer ce que contiennent réellement les quatre sauvegardes identifiées, sans rien restaurer.
**Nature** : audit **lecture seule**. Aucune restauration, aucune écriture, aucun redémarrage.

---

## 0. Statut d'exécution

Le VPS n'est pas joignable depuis l'environnement de travail : `kex_exchange_identification: read: Connection reset by peer` (sixième vérification, résultat constant). **Aucune des quatre sauvegardes n'a donc été ouverte.**

| Étape du cahier des charges | État |
|---|---|
| 1. Disponibilité des outils | ❌ **non exécutée sur le VPS** — le kit la mesure en tête de journal |
| 2. Expertise de l'archive custom du 26 octobre | ❌ **non exécutée** |
| 3. Expertise du fichier gzip | ❌ **non exécutée** |
| 4. Comparaison des deux SQL du 23 octobre | ❌ **non exécutée** |
| 5. Recherche des indices de conformité INJS | ❌ **non exécutée** — aucun indice n'est « trouvé », tous restent « attendus » |
| 6. Rapport final comparatif | ⚠️ **produit sous forme de cadre** : statuts à remplir par la mesure |

**Livré à la place** : `docs/audits/vps/h5_expertise_sauvegardes.sh`, un kit **réellement testé** (§4), qui exécute les étapes 1 à 5 en lecture seule et imprime un bloc `SYNTHESE_H5_BEGIN … SYNTHESE_H5_END` suffisant pour remplir le tableau §2.

---

## 1. Ce que le kit mesure, étape par étape

| Étape | Mesures effectuées | Ce que cela tranche |
|---|---|---|
| 1 | `pg_restore --version`, `psql --version` **dans le conteneur** ; présence de `gzip`, `awk`, `grep`, `sha256sum`, `sort`, `comm` sur l'hôte | compatibilité binaire/archive : un `pg_restore` plus ancien que l'archive refuse de la lire |
| 2 | `cat dump \| docker exec -i injs-db pg_restore --list` (sommaire seul, **jamais** de restauration) : format, version, nombre d'objets, répartition par type, schémas, tables, séquences, index, contraintes, présence des objets Django / utilisateurs / habilitations | **structure** de l'archive et son époque technologique |
| 3 | `gzip -t` puis analyse en tube (`gzip -dc`) : nombre de `CREATE DATABASE`, `\connect`, `CREATE SCHEMA/TABLE/SEQUENCE`, `COPY`, `INSERT`, `GRANT`, en-têtes `pg_dump`, lignes de `django_migrations`, `authentication_user`, erreurs visibles | **volumes et nature** du dump, sans extraction disque |
| 4 | pour chaque SQL : tables, sections `COPY`, `INSERT`, lignes de migrations, lignes `authentication_user`, `GRANT/REVOKE` ; puis `comm` : tables communes / propres à A / propres à B | **différence de structure** entre les deux états du 23 octobre |
| 5 | matrice de présence des objets structurants INJS 2026 dans les quatre sources ; comptage des indices de valeurs (`ENSEP`, `S1..S10`, `ECTS`) sur les dumps **texte** uniquement | **conformité fonctionnelle**, distincte de l'intégrité technique |

**Limite explicite du kit** : une archive *custom* n'est pas lue par ce script au-delà de son sommaire — PostgreSQL n'expose pas les valeurs sans restauration. Les indices de valeurs (§5.2) ne sont donc calculés que sur les dumps texte. C'est une limite assumée, pas un oubli : inspecter les valeurs d'une archive custom exigerait une restauration, ce que ce lot interdit.

---

## 2. Tableau comparatif demandé

Les statuts possibles étant : *NON EXPERTISÉE · STRUCTURE IDENTIFIÉE · INTÉGRITÉ CONFIRMÉE · DONNÉES IDENTIFIÉES · CONFORMITÉ INJS À CONFIRMER · POTENTIELLEMENT EXPLOITABLE*.

| Sauvegarde | Intégrité | Structure | Données | Conformité INJS 2026 | Observations |
|---|---|---|---|---|---|
| `/home/almalinux/injs-db-backups/injs_lmd_20261026-133624.dump` (custom, 26/10) | **NON EXPERTISÉE** | **NON EXPERTISÉE** | **NON EXPERTISÉE** | **À CONFIRMER** | État final **NON EXPERTISÉE**. Fichier le plus récent et le seul nommé « injs_lmd » — indice de nom, pas une preuve |
| `/home/almalinux/injs-predeploy-20261026-124700/postgres-all.sql.gz` (26/10) | **NON EXPERTISÉE** | **NON EXPERTISÉE** | **NON EXPERTISÉE** | **À CONFIRMER** | État final **NON EXPERTISÉE**. Dossier « predeploy » : capture prise **avant** le déploiement du 26/10 — hypothèse, non vérifiée |
| `/home/almalinux/backups/injs-lmd/postgres-20261023-025115.sql` (23/10) | **NON EXPERTISÉE** | **NON EXPERTISÉE** | **NON EXPERTISÉE** | **À CONFIRMER** | État final **NON EXPERTISÉE**. Chemin contenant `injs-lmd` : indice de nom uniquement |
| `/home/almalinux/backup_injs_production_20261023_170117.sql` (23/10) | **NON EXPERTISÉE** | **NON EXPERTISÉE** | **NON EXPERTISÉE** | **À CONFIRMER** | État final **NON EXPERTISÉE**. Nom « production » : déclaratif, aucune preuve |

**Aucune sauvegarde ne peut recevoir aujourd'hui le statut POTENTIELLEMENT EXPLOITABLE.** Ce statut exige d'avoir constaté : intégrité vérifiée **et** structure identifiée **et** données présentes **et** indices de conformité relevés.

---

## 3. Les trois questions posées

| Question | Réponse actuelle | Ce qui la tranchera |
|---|---|---|
| **1. Quelle sauvegarde contient réellement des données ?** | **Indéterminé.** Un fichier de 26 Mo ou de 118 Mo peut être vide de données métier (structure seule) ou plein ; seule la mesure le dit | étape 3 (`.gz`) et étape 4 (SQL) : comptage des sections `COPY` **et** des lignes par table ; étape 2 pour le custom (objets `TABLE DATA`) |
| **2. Quelle sauvegarde a une structure compatible avec `backend-injs2026` actuel ?** | **Indéterminé.** On sait par le code que la cible attend **222 tables** (202 modèles + 19 tables de liaison + `django_migrations`) ; aucune sauvegarde n'a encore été confrontée à ce référentiel | étape 2 (nb de tables du custom) et étape 4 (liste des tables) confrontés à `docs/audits/tables_cibles_attendues.txt` |
| **3. Quelle sauvegarde contient des données métier authentiquement exploitables pour l'INJS ?** | **Indéterminé.** Aucun indice n'a été *trouvé* ; les 15 objets attendus sont listés à l'étape 5 et restent à 0/1 par source | étape 5, matrice de présence + arbitrage métier sur les référentiels (8 filières, S1–S10, UE/ECUE, jurys) |

**Distinction maintenue** : une archive lisible par `pg_restore` prouve une **intégrité technique**, rien de plus. Elle ne prouve ni la présence de données, ni la conformité au référentiel INJS 2026.

---

## 4. Tests réellement exécutés sur le kit

Les tests ne portent pas sur les fichiers du VPS (inaccessibles) mais sur des artefacts **équivalents, générés localement** avec `pg_dump`/`pg_restore` 16.2 : une archive custom, un dump texte, un dump texte partiel et un `.gz`. Cela valide la mécanique de lecture, pas le contenu de vos sauvegardes. Les jeux d'essai sont désormais fabriqués par le harnais lui-même, ce qui rend la vérification reproductible chez vous sans dépendre de mes fichiers temporaires.

| # | Test | Nature | Résultat |
|---|---|---|---|
| T1 | Validation syntaxique `sh -n` | **réel** | PASS |
| T2 | Archive **custom réelle** (26 385 o, générée par `pg_dump -Fc`) | **réel** — `pg_restore --list` | PASS : en-tête lu (`Format: CUSTOM`, `Dump Version: 1.15-0`), 84 objets, **12 tables**, 36 séquences, 12 contraintes, 12 `DEFAULT`, 0 index, 0 FK (conforme au jeu d'essai) |
| T3 | **Dump gzip réel** (`postgres-all.sql.gz`) | **réel** — `gzip -t` + analyse en tube | PASS : intégrité OK, 19 516 o décompressés, 12 `CREATE TABLE`, 12 `COPY`, 0 `INSERT`, en-têtes `pg_dump` détectés |
| T4 | **Comparaison de deux dumps SQL réels** | **réel** — `comm` | PASS : 5 tables communes, 7 seulement dans A, 0 dans B (écart conforme au jeu d'essai) |
| T5 | **Matrice de conformité** sur les quatre sources | **réel** | PASS : les objets LMD sont détectés (1) dans les trois sources complètes, absents (0) dans le dump partiel |
| T6 | Fichiers **absents** | **réel** | PASS : 4 messages `FICHIER ABSENT`, synthèse `non_lue`, code de retour 0 |
| T7 | Archive **tronquée** | **réel** | PASS : erreur `pg_restore: could not read from input file`, pas d'arrêt brutal |
| T8 | gzip **corrompu** | **réel** | PASS après correction : `gzip -t` échoue, analyse ignorée, synthèse `s2_gzip=corrompue` |
| T9 | **non-régression** : aucune analyse partielle du gzip corrompu | **réel** — comptage des accès au fichier | PASS : 0 décompression, 0 marqueur, colonne gzip vide, statut `corrompue` conservé |

**Trois défauts trouvés par ces tests, et corrigés** :
1. les sections 2.5 à 2.7 lisaient le sommaire avec un décalage de colonnes (type en `$4`, et non `$3`) — toutes les valeurs sortaient à 0 ; corrigé par une normalisation unique du sommaire ;
2. un gzip corrompu laissait fuiter son message d'erreur dans le bloc de synthèse et faisait passer l'archive pour « lue » ; corrigé par un indicateur d'intégrité qui conditionne l'analyse ;
3. **un gzip corrompu restait réanalysé après l'échec de `gzip -t`** : la constitution de la liste de tables de l'étape 5 et les indices de valeurs de §5.2 relisaient l'archive, et la taille décompressée était publiée comme une mesure valide alors qu'elle ne portait que sur un fragment. Cinq relectures partielles mesurées sur la version antérieure, zéro après correction.

### 4 bis. Test de non-régression du défaut n° 3

Le harnais `docs/audits/vps/tests/h5_tests.sh` rejoue l'ensemble et ajoute **T9**, qui ne se contente pas de relire le code : il **compte les accès réels au fichier** au moyen d'un relais `gzip` placé en tête de `PATH`, et place dans la partie encore décompressable de l'archive un marqueur de table (`zzz_marqueur_analyse_partielle`) qu'une analyse partielle ne manquerait pas de faire apparaître.

Journal des garanties vérifiées :

| Assertion | Contrôle |
|---|---|
| T9.0 | le jeu d'essai échoue bien à `gzip -t` (sinon le test serait vacant) |
| T9.1 | le marqueur est bien présent dans la partie lisible (sinon l'absence de marqueur ne prouverait rien) |
| T9.2 | **0 décompression** de l'archive corrompue — 5 sur la version antérieure |
| T9.3 | exactement 1 contrôle d'intégrité |
| T9.4 | le marqueur n'apparaît nulle part dans le journal |
| T9.5 | colonne « gzip » de la matrice de conformité entièrement à 0 |
| T9.6 | section 3 : « ANALYSE IGNORÉE » affichée |
| T9.7 | taille décompressée annoncée « NON MESURABLE » |
| T9.8 | §5.2 : archive illisible explicitement non analysée |
| T9.9 | statut `s2_gzip=corrompue` conservé |
| T9.10 | code de retour 0 malgré l'archive corrompue |
| T9.11 | contrôle de non-vacuité : le compteur détecte bien les lectures sur un gzip sain |

Exécution : `sh docs/audits/vps/tests/h5_tests.sh docs/audits/vps/h5_expertise_sauvegardes.sh`
(ajouter `H5_DUMP_FIXTURE=/chemin/archive.dump` pour activer T2 et T7 ; sans ce paramètre ils sont marqués SKIP, jamais PASS).

Résultat sur la version corrigée : **35 PASS, 0 FAIL, 0 SKIP**. Résultat sur la version antérieure : **31 PASS, 4 FAIL** — le défaut est donc bien détecté, et le comportement nominal est inchangé (journaux identiques hors horodatage).

**Ce que ces tests ne prouvent pas** : que vos quatre fichiers sont lisibles. Un dump PostgreSQL 15 lu par un `pg_restore` 15 le sera ; une archive produite par une version **plus récente** que le binaire échouera avec un message explicite, que le kit affiche.

---

## 5. Recommandation

**Aucune sauvegarde ne sera restaurée, ni totalement ni partiellement, à ce stade.** Conformément à votre consigne, et parce que l'état réel de la base en production n'est toujours pas mesuré (LOT H2 non exécuté).

**Sauvegardes à conserver comme candidates** — les quatre, sans exception, pour trois raisons :
1. aucune n'est encore expertisée : éliminer sur la foi d'un nom de fichier serait une faute ;
2. elles couvrent trois moments différents (23/10, 26/10 avant déploiement, 26/10 après) — cette chronologie est précisément ce qui permettra de dater une éventuelle perte ;
3. elles sont peu volumineuses au regard du risque : les conserver ne coûte rien, en supprimer une coûte potentiellement tout.

**Ordre d'expertise recommandé** (le plus informatif d'abord) :
1. `injs_lmd_20261026-133624.dump` — la plus récente, et la seule au format custom (sommaire lisible sans restauration) ;
2. `postgres-all.sql.gz` — capture « predeploy » du même jour : la comparaison 1↔2 datera exactement ce que le déploiement a changé ;
3. les deux SQL du 23/10 — utiles surtout pour établir la différence entre les deux emplacements de sauvegarde.

**Garde-fous avant toute récupération ultérieure** (hors de ce lot) :
- ne jamais restaurer par-dessus la base en production ;
- restaurer d'abord dans une base **jetable** et y exécuter le pack `20_empreinte_modules.sql` ;
- vérifier la conformité métier (8 filières, S1–S10, 30/60 ECTS, inscriptions, jurys) **avant** d'envisager la production ;
- conserver les originaux en lecture seule, avec leurs empreintes SHA-256 relevées par le kit.

---

## 6. Exécution sur le VPS (quand vous l'autoriserez)

```sh
scp docs/audits/vps/h5_expertise_sauvegardes.sh almalinux@152.228.233.123:~/
ssh almalinux@152.228.233.123 \
  'sh ~/h5_expertise_sauvegardes.sh 2>&1 | tee ~/h5-expertise-$(date -u +%Y%m%dT%H%M%SZ).log'
scp almalinux@152.228.233.123:~/h5-expertise-*.log ./
```

Mode par défaut : `MODE=docker`, conteneur `injs-db`. Les chemins des quatre fichiers sont ceux de votre message et peuvent être surchargés par variables (`S1_DUMP`, `S2_GZ`, `S3_SQL_A`, `S3_SQL_B`).

Le script n'exécute **jamais** `pg_restore` autrement qu'avec `--list`, ne crée aucune base, ne modifie aucun fichier, et n'affiche aucune donnée nominative, aucun mot de passe, aucun hash.

---

**Aucune restauration effectuée — aucune sauvegarde modifiée — aucun conteneur touché — lecture seule.**
