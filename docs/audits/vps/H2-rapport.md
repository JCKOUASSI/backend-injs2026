# H2 — Cartographie technique et identification des données de production

**Projet** : INJS Abidjan — `backend-injs2026`
**Date** : 2026-11-05
**Nature** : audit **lecture seule** — aucune bascule, aucune modification
**Statut global** : ⛔ **non exécuté sur le VPS** — accès impossible depuis l'environnement d'audit

---

## 0. Statut réel de ce lot (à lire avant les sections A à I)

Le VPS n'est pas joignable depuis cet environnement : le proxy de sortie accepte le TCP puis réinitialise le protocole SSH **avant tout échange de clés**.

```
$ ssh -o BatchMode=yes -o ConnectTimeout=10 almalinux@152.228.233.123 'echo OK'
kex_exchange_identification: read: Connection reset by peer
Connection reset by 152.228.233.123 port 22
```

Cinquième vérification, résultat identique aux précédentes. **Aucune commande n'a donc pu être exécutée sur le VPS** : ni `docker`, ni `psql`, ni lecture de fichiers.

En conséquence, dans tout ce rapport :

| Statut | Signification |
|---|---|
| **CONFIRMÉ** | établi par une source vérifiable — ici, le plus souvent **le diagnostic H1** (rapporté par vous), jamais re-vérifié par mes soins |
| **NON CONFIRMÉ** | hypothèse plausible, cohérente avec les indices disponibles, **à prouver** |
| **IMPOSSIBLE À VÉRIFIER** | aucune mesure possible depuis cet environnement |

**Aucune valeur estimée n'est présentée comme mesurée.** Les sections B à F sont donc des **cadres de mesure** : ils décrivent ce qu'il faut relever, pourquoi, et ce que chaque relevé tranchera — avec le moyen de le relever (§J).

---

## A. Architecture réelle du VPS

| Élément | Contenu | Statut |
|---|---|---|
| `injs-db` | PostgreSQL 15 | **CONFIRMÉ (source H1)** |
| `injs-be` | ancienne image `ophirdesire/injs-be:channel1-latest-amd64` | **CONFIRMÉ (source H1)** |
| `injs-be-candidate` | `jckouassi/injs-be:prod-20261026-fix2` | **CONFIRMÉ (source H1)** |
| `injs-fe` | `jckouassi/injs-fe:prod-20261023` | **CONFIRMÉ (source H1)** |
| `npm-app-1` | Nginx Proxy Manager (routage public) | **CONFIRMÉ (source H1)** |
| `injs-redis`, `injs-rabbitmq`, `injs-worker`, `injs-cron` | services annexes | **CONFIRMÉ (source H1)** |
| Coexistence ancien environnement / candidat | deux backends en parallèle | **CONFIRMÉ (source H1)** |
| Réseaux Docker, alias DNS, ports internes, volumes | non relevés | **IMPOSSIBLE À VÉRIFIER** |
| Le candidat est-il joint au réseau de NPM ? | non relevé | **NON CONFIRMÉ** |

**Lecture** : la coexistence de deux backends sur un même hôte est la source principale de risque de ce lot. Tout dépend de trois mesures : la base visée par chacun, l'alias réseau sous lequel chacun se présente, et la cible `proxy_pass` de NPM (§B, §C, §D).

---

## B. Inventaire des bases PostgreSQL

### B.1 Ce qui doit être relevé (LOT 1 du kit)

| Donnée | Pourquoi elle est décisive |
|---|---|
| `pg_database` + `pg_database_size` | identifier les bases réellement présentes et leur poids |
| **Nombre de tables** par base | discriminateur immédiat : base héritée ≈ 73 tables ; base cible ≈ 222 (cf. plus bas) |
| Nombre de tables non vides (estimation `reltuples`, + volume inconnu) | distinguer « vide », « alimentée », « jamais analysée » |
| Schémas présents | confirmer `public` unique, ou présence de schémas de travail |
| `SHOW data_directory` + volumes montés | localiser les données persistantes (§E) |
| Rôles PostgreSQL (nom, superutilisateur, connexion autorisée) | cartographier les accès **sans jamais afficher de mot de passe** |

### B.2 Éléments déjà établis, non re-vérifiés

| Fait | Statut |
|---|---|
| `injs-db` : 73 tables, 327 migrations, données métier nombreuses | **CONFIRMÉ (votre inventaire antérieur)** |
| `injs_lmd_prod_20261026` : 203 tables annoncées, applications métier quasi vides | **CONFIRMÉ (votre inventaire antérieur)** |
| La base cible attend **222 tables physiques** d'après le code `main@767dabf` (202 modèles + 19 tables de liaison + `django_migrations`) | **CONFIRMÉ (introspection du code, vérifiable localement)** |
| Écart 203 vs 222 = probablement les 19 tables de liaison M2M non comptées | **NON CONFIRMÉ** — l'écart se tranche exactement au LOT 1 (comptage des tables par base) |

### B.3 Le point qui décide de tout

Une base « récente et vide » et une base « ancienne et remplie » ne sont **pas** deux états du même système. La base héritée est organisée en `academics`, `students`, `admissions`, `exams`, `faculty`, `accounts`, `finance`, `library` ; la cible est organisée en `scolarite`, `referentiels`, `edts`, `presences`, `evaluations`, `jurys`, `habilitations`. Les deux vocabulaires ne se recouvrent pas — c'est démontré dans `docs/audits/2026-11-05-identite-fonctionnelle-modules.md`. Le LOT 1 fournit la preuve chiffrée de cette asymétrie.

---

## C. Correspondance backend / base de données

### C.1 Ce qui doit être relevé (LOT 2)

Pour `injs-be` et `injs-be-candidate` : image, date de création, réseaux et **alias**, volumes, ports exposés, **noms** des variables d'environnement (valeurs masquées), puis **uniquement** `POSTGRES_DB`, `POSTGRES_HOST`, `POSTGRES_PORT`.

La comparaison se conclut en une ligne :
- `POSTGRES_DB` identiques → les deux backends écrivent dans **la même base** (situation à haut risque de corruption croisée) ;
- `POSTGRES_DB` différents → deux sources de vérité coexistent (à documenter avant toute bascule).

### C.2 Hypothèses actuelles

| Hypothèse | Indice | Statut |
|---|---|---|
| `injs-be-candidate` vise `injs_lmd_prod_20261026` | le nom d'image contient `prod-20261026`, comme le nom de la base cible | **NON CONFIRMÉ** |
| `injs-be` vise `injs-db` | c'est l'ancien environnement, et `injs-db` est la base historique | **NON CONFIRMÉ** |
| `injs-worker` / `injs-cron` (Celery) pointent encore l'ancienne base | votre constat H1 | **NON CONFIRMÉ** (à relever au LOT 2, §2.10 du kit) |

**Piège à ne pas manquer** : si les deux backends partagent le même alias réseau (`injs-be`), NPM peut router vers l'un ou l'autre selon l'ordre de résolution Docker. C'est précisément pourquoi le LOT 3 relève les alias **et** les adresses, pas seulement les noms.

---

## D. Routage du domaine public

### D.1 Ce qui doit être relevé (LOT 3)

- Fichiers `/data/nginx/proxy_host/*.conf` du conteneur NPM : `server_name` et `proxy_pass` (aucune modification, simple lecture).
- Fichiers de redirection éventuels.
- Table réseau → conteneurs et adresses, pour résoudre la cible de chaque `proxy_pass`.
- Recherche ciblée du domaine `injs.badge-qr-code.pro` dans `/data/nginx/`.

### D.2 Ce que la réponse tranchera

| Résultat attendu | Interprétation |
|---|---|
| `proxy_pass http://injs-be:8000` | le domaine public sert l'**ancien** backend → le candidat n'est pas exposé |
| `proxy_pass http://injs-be-candidate:8000` | le domaine public sert déjà le **candidat** → situation inverse, à vérifier d'urgence |
| Résolution ambiguë (alias partagé) | route indéterminée → **risque critique** avant toute bascule |

Statut actuel : **IMPOSSIBLE À VÉRIFIER**. Le rapport H1 ne tranche pas ce point, et c'est, de votre propre analyse, l'une des trois inconnues majeures.

---

## E. Inventaire des volumes et sauvegardes

### E.1 Ce qui doit être relevé (LOT 4)

| Donnée | Enjeu |
|---|---|
| Volumes Docker (nom → point de montage) | localiser les données persistantes réelles |
| `Mounts` des conteneurs `injs-db`, backends, worker | distinguer volume nommé / bind mount |
| `docker system df -v` | mesurer l'espace occupé |
| Dumps `*.sql`, `*.sql.gz`, `*.dump`, `*.backup`, archives | **prouver l'existence d'une sauvegarde avant toute opération** |
| Dates et tailles, en particulier **avant et après le 2026-10-26** | dater la dernière sauvegarde exploitable |
| Tâches planifiées de sauvegarde (`cron`, `pg_dump`) | savoir si les sauvegardes sont automatiques ou manuelles |

### E.2 Règle de sécurité à conserver

Aucune restauration n'est autorisée dans ce cadre, et **aucune opération de migration ne doit être engagée avant qu'une sauvegarde n'ait été vérifiée par un test de restauration sur environnement isolé**. Ce test n'a pas été fait et ne peut pas l'être depuis ici : statut **IMPOSSIBLE À VÉRIFIER**.

---

## F. Localisation du pack d'audit

### F.1 Ce que le LOT 5 recherche sur le VPS

`20_empreinte_modules.sql`, `19_empreinte_modules.sql`, `run_audit.sh`, `consolider.py`, et tout répertoire `docs/audits/sql` sous `/home`, `/opt`, `/srv`, `/root`, `/data`.

### F.2 Ce qui est établi hors VPS

| Fichier | Présence | Statut |
|---|---|---|
| `docs/audits/sql/20_empreinte_modules.sql` | présent dans le dépôt (commit `c716c00`) | **CONFIRMÉ** |
| `docs/audits/sql/00_profil_schema.sql`, `10_anomalies.sql` | présents dans le dépôt | **CONFIRMÉ** |
| `docs/audits/sql/run_audit.sh`, `consolider.py` | présents dans le dépôt | **CONFIRMÉ** |
| `19_empreinte_modules.sql` | **n'existe pas** : le numéro retenu est `20_` (le `19_` n'a jamais été créé) | **CONFIRMÉ** |
| Présence d'une copie **sur le VPS** | non vérifiable | **IMPOSSIBLE À VÉRIFIER** |

Conséquence pratique : le pack devra être **transféré** sur le VPS (ou exécuté depuis le Mac) ; il n'y a aucune raison de supposer qu'il y est déjà.

---

## G. Risques identifiés

| # | Risque | Gravité | Pourquoi |
|---|---|---|---|
| 1 | **Alias réseau partagé** entre `injs-be` et `injs-be-candidate` | **critique** | le routage NPM devient indéterminé ; une bascule « invisible » peut déjà avoir eu lieu |
| 2 | **Deux sources de vérité** si les backends visent des bases différentes | **critique** | écritures divergentes, réconciliation impossible sans arbitrage |
| 3 | **Celery sur l'ancienne base** pendant que le web change de base | élevé | tâches exécutées sur des données que le web ne voit plus |
| 4 | **Absence de sauvegarde vérifiée** avant toute opération | **critique** | perte de données irréversible ; prérequis absolu |
| 5 | **Base candidate non initialisée** (référentiels, maquettes, comptes) | élevé | le module « fonctionne » mais ne peut rien produire : faux sentiment de disponibilité |
| 6 | **Non-conformité des données historiques** au référentiel INJS 2026 | élevé | une reprise en bloc contaminerait la base neuve |
| 7 | **Écart de schéma 203 vs 222** non tranché | moyen | des tables manquantes feraient échouer des fonctionnalités après bascule |
| 8 | **NPM comme point unique** de vérité du routage | moyen | une modification manuelle non tracée change la production |

---

## H. Informations manquantes

| # | Information | Lot qui la fournit |
|---|---|---|
| 1 | Liste réelle des bases + tailles + nombre de tables de chacune | LOT 1 |
| 2 | Tables non vides et volumes inconnus par base | LOT 1 |
| 3 | Base visée par `injs-be` et par `injs-be-candidate` | LOT 2 |
| 4 | Base visée par `injs-worker` et `injs-cron` | LOT 2 |
| 5 | Alias réseau et adresses des deux backends | LOT 2 / LOT 3 |
| 6 | Cible `proxy_pass` du domaine `injs.badge-qr-code.pro` | LOT 3 |
| 7 | Inventaire des volumes et emplacement de `PGDATA` | LOT 4 |
| 8 | Existence, date et taille de sauvegardes avant/après le 2026-10-26 | LOT 4 |
| 9 | Présence éventuelle du pack d'audit sur le VPS | LOT 5 |
| 10 | Écart exact entre 222 tables attendues et tables réelles en cible | LOT 1 + `consolider.py` |

---

## I. Recommandations pour le prochain lot

1. **Exécuter le kit H2** (§J) et conserver le journal intégral — c'est la seule action nécessaire pour lever les dix inconnues ci-dessus.
2. **Ne rien changer à NPM** avant d'avoir la réponse du LOT 3. Le routage public est la ligne de vie de la production.
3. **Produire et vérifier une sauvegarde** de `injs-db` **avant** toute manipulation ultérieure, avec un test de restauration sur environnement isolé (hors périmètre de cet audit).
4. **Trancher l'identité de la base par la fonction, pas par le volume** : les mesures du LOT 1 (nombre de tables, présence des `edts_*` / `presences_*` / `gi_*`) suffisent à désigner la base applicative ; le pack `20_empreinte_modules.sql` en donne la preuve chiffrée.
5. **Ne pas basculer sur `injs-be-candidate`** tant que les points 1 à 4 ne sont pas établis — avis que je partage sans réserve.
6. **Enchaîner ensuite un H3 « compatibilité »** : exécuter `00`, `10` et `20` sur les deux bases, puis `consolider.py`, avant toute décision de reprise de données.

### Réponse aux trois inconnues de votre recommandation

| Inconnue | État | Ce qui la lève |
|---|---|---|
| Le candidat utilise-t-il la bonne base PostgreSQL ? | **NON CONFIRMÉ** | LOT 2, section 2.9 du kit (comparaison `POSTGRES_DB`) |
| Les données historiques sont-elles récupérables et conformes ? | **NON** — ni la récupérabilité ni la conformité ne sont établies | LOT 1 (volumes) puis pack `00`/`10`/`20` + arbitrage métier |
| Le domaine public pointe-t-il toujours l'ancien backend ? | **NON CONFIRMÉ** | LOT 3, section 3.4 du kit |

---

## J. Exécution du kit (5 minutes, lecture seule)

Le script `docs/audits/vps/h2_collecte_lecture_seule.sh` couvre les cinq lots.

```sh
# 1. transférer le script sur le VPS
scp docs/audits/vps/h2_collecte_lecture_seule.sh almalinux@152.228.233.123:~/

# 2. l'exécuter (aucune modification, journal horodaté conservé)
ssh almalinux@152.228.233.123 \
  'sh ~/h2_collecte_lecture_seule.sh 2>&1 | tee ~/h2-collecte-$(date -u +%Y%m%dT%H%M%SZ).log'

# 3. rapatrier le journal
scp almalinux@152.228.233.123:~/h2-collecte-*.log ./
```

**Garanties vérifiées du script** :
- aucune commande de cycle de vie Docker (`restart`, `stop`, `start`, `rm`, `pull`) ;
- `docker exec` limité à `psql` en `BEGIN TRANSACTION READ ONLY` + `ROLLBACK`, et à `grep`/`cat` ;
- variables d'environnement listées **par nom**, valeurs remplacées par `<masque>` ; seuls `POSTGRES_DB`, `POSTGRES_HOST`, `POSTGRES_PORT` sont lus en clair ;
- aucune écriture de fichier hors du journal ;
- testé sur un Docker simulé contenant de faux secrets : **0 fuite constatée**, 15 masquages corrects ;
- les requêtes SQL ont été exécutées sur un PostgreSQL réel : syntaxe et résultats validés ;
- un défaut a été trouvé et corrigé au passage : `reltuples = -1` (table jamais analysée) n'est plus compté comme « non vide » — il apparaît désormais dans une colonne `volume_inconnu`.

Le bloc `SYNTHESE_H2_BEGIN … SYNTHESE_H2_END` en fin de journal contient les cinq valeurs qui suffisent à rédiger le rapport final : image et volume de PostgreSQL, image et base de chaque backend, égalité ou non des bases.

---

**Aucune opération corrective effectuée. Aucun fichier du VPS lu, aucune commande Docker exécutée, aucune base interrogée, aucune configuration NPM touchée, aucun commit ni push Git (conformément aux consignes du lot).**

`AUCUNE DONNÉE MODIFIÉE — AUCUNE BASCULE EFFECTUÉE — AUDIT EN LECTURE SEULE`

---

## K. Traçabilité des tests (ajout du 2026-11-05)

Les tests ci-dessous ont été **réellement exécutés** dans l'environnement de travail de l'agent,
et le journal complet est conservé : `docs/audits/vps/tests/H2-tests-<horodatage>.log`.

| # | Test | Nature | Résultat |
|---|---|---|---|
| T1 | Validation syntaxique POSIX sh (`sh -n`) | **réel** | PASS (code 0) |
| T2 | Exécution complète du script | **simulée** (Docker factice) | PASS — code de retour 0, 194 lignes, 6 sections + synthèse présentes |
| T3 | Masquage des secrets (faux secrets injectés dans le simulateur) | **simulée** | PASS — **0 fuite**, 15 masquages `<masque>` |
| T4 | Exécution des 5 requêtes SQL | **réelle**, sur une instance PostgreSQL 16.2 locale éphémère | PASS — 5/5 acceptées, 0 erreur de syntaxe |
| T5 | Erreurs de connexion (conteneurs inexistants) | **simulée** | PASS — code 0, messages `IMPOSSIBLE` émis, synthèse produite avec `INDETERMINE` |
| T6 | Absence de commandes de modification (hors commentaires) | **réelle** (analyse du script) | PASS — aucun `restart/stop/start/rm/pull`, aucun `DROP/TRUNCATE/DELETE/INSERT/UPDATE`, aucune migration |
| T7 | Absence de données nominatives dans le journal | **réelle** (analyse de la sortie) | PASS — 0 occurrence |
| T8 | Intégrité du script avant/après tests | **réelle** (sha256) | PASS — empreinte identique |

**Ce qui n'a PAS été testé, et ne le sera pas sans votre autorisation** : l'exécution sur le VPS.
Aucun conteneur réel n'a été interrogé, aucune base de production n'a été lue, aucun diagnostic
distant n'a été lancé.
