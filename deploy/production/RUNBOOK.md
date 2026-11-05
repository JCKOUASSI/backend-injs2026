# Runbook — Déploiement INJS-LMD en production (injs.badge-qr-code.pro)

Procédure d'exécution **sur le serveur** (152.228.233.123, AlmaLinux,
utilisateur `almalinux`). Elle suppose les images publiées par
`.github/workflows/publish-injs-lmd.yml` (tags = SHA Git complet).

**Règles absolues (préservation des données)** : ne jamais supprimer la
base PostgreSQL existante, jamais `flush`, jamais `docker compose down -v`,
jamais supprimer de volume, jamais restaurer un dump pour un simple
problème applicatif. La nouvelle stack **ne crée pas** de PostgreSQL :
elle consomme le conteneur existant via le réseau Docker externe.

---

## 0. Prérequis (côté GitHub, avant de toucher au serveur)

1. Secrets du dépôt créés (Settings → Secrets and variables → Actions) :
   `DOCKERHUB_USERNAME` (= `jckouassi`) et `DOCKERHUB_TOKEN`
   (jeton d'accès Docker Hub, pas le mot de passe du compte).
2. Workflow « Publication images INJS-LMD » relancé et **vert** :
   il publie `jckouassi/injs-be:<SHA>` et `jckouassi/injs-fe:<SHA>`.
3. Noter le SHA complet publié : c'est `DEPLOY_SHA` ci-dessous.

## 1. Inventaire (lecture seule)

```bash
ssh almalinux@152.228.233.123
cat /etc/almalinux-release; docker --version; docker compose version
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Ports}}'
docker volume ls; docker network ls
docker logs --tail 50 injs-db 2>&1 | tail -5     # conteneur PostgreSQL actuel
df -h; free -h
```

Identifier : le conteneur PostgreSQL (`injs-db`), son réseau Docker
(ex. `injs-net`), le répertoire de l'installation actuelle
(ex. `/opt/injs`), le port public actuel derrière Nginx Proxy Manager.

## 2. Sauvegarde complète et vérifiée (AVANT toute modification)

```bash
mkdir -p /opt/injs/backups && cd /opt/injs/backups
STAMP=$(date +%Y%m%d-%H%M%S)

# 2.1 Dump PostgreSQL de la base réellement utilisée (adapter DB/USER)
docker exec injs-db pg_dump -U injs -d injs -Fc -f /tmp/injs-$STAMP.dump
docker cp injs-db:/tmp/injs-$STAMP.dump ./injs-$STAMP.dump
# Vérification d'exploitabilité (liste le contenu, ne restaure rien)
pg_restore --list injs-$STAMP.dump | head -20

# 2.2 Médias et documents existants
tar czf media-$STAMP.tgz -C /opt/injs/injs-be/data media

# 2.3 Configurations actuelles (compose, .env, reverse proxy)
tar czf config-$STAMP.tgz -C /opt/injs .env* docker-compose*.yml 2>/dev/null || true
# Nginx Proxy Manager : recopier la configuration du proxy host
# injs.badge-qr-code.pro (hôte/port cible actuels) dans un fichier texte.

chmod 600 injs-$STAMP.dump media-$STAMP.tgz config-$STAMP.tgz
```

## 3. Comptages de référence (avant déploiement)

```sql
-- À exécuter : docker exec -it injs-db psql -U injs -d injs
SELECT (SELECT count(*) FROM authentication_user)        AS utilisateurs,
       (SELECT count(*) FROM scolarite_dossieretudiant)  AS etudiants,
       (SELECT count(*) FROM scolarite_inscriptionadministrative) AS inscriptions,
       (SELECT count(*) FROM formations_refformation)    AS formations,
       (SELECT count(*) FROM edts_emploidutemps)          AS emplois_du_temps;
```
(Ajuster les noms de tables si `psql \dt` montre des préfixes différents.)
Conserver ces chiffres pour la comparaison finale, avec la portée
exacte suivante : cette requête unique produit un instantané cohérent
des cinq tables ; le dump de l'étape 2 possède **son propre**
instantané interne (garanti par `pg_dump`, pas par ces chiffres).
Après déploiement : une **baisse** d'un compteur est un signal de
perte possible (ne pas basculer, analyser) ; une **hausse** reflète en
général l'activité normale des utilisateurs sur l'ancienne application
encore en service (vérifier métier par métier avant de basculer). Des
chiffres identiques ne prouvent pas à eux seuls l'absence de perte
(une suppression et une insertion peuvent se compenser) : la preuve
d'intégrité reste le dump vérifié par SHA-256.

## 4. Préparation de la nouvelle stack (sans arrêter l'existante)

Le répertoire de référence sur le VPS est `/opt/injs/injs-lmd`
(c'est celui qu'alimente le workflow de déploiement et qu'attend le
chemin relatif `../../docker/nginx/default.conf` du compose) :

```bash
mkdir -p /opt/injs/injs-lmd
# Y déposer deploy/production/ et docker/ du dépôt (transfert rsync du
# workflow, ou copie manuelle) — jamais le .env d'un autre poste.
cp /opt/injs/injs-lmd/deploy/production/.env.example \
   /opt/injs/injs-lmd/deploy/production/.env   # une seule fois, sur le VPS
```

Renseigner `deploy/production/.env` :
- `INJS_BACKEND_TAG=<DEPLOY_SHA>`, `INJS_FRONTEND_TAG=<DEPLOY_SHA>`
- `POSTGRES_HOST=` nom/IP du conteneur `injs-db` **sur le réseau Docker**
  (jamais 127.0.0.1), `POSTGRES_DB/USER/PASSWORD` = ceux de l'installation
  actuelle (reprendre son `.env` actuel, ne pas en inventer).
- `DJANGO_SECRET_KEY=` **reprendre celle de l'application actuelle** si elle
  est récupérable (préserve les sessions) ; sinon en générer une nouvelle
  (les utilisateurs devront se reconnecter — à noter dans le rapport).
- `INJS_NETWORK_NAME=` réseau Docker du conteneur PostgreSQL, `INJS_NETWORK_EXTERNAL=true`
- `INJS_PUBLIC_PORT=8080` (validation sur un port libre, **sans toucher**
  au service actuel)
- `INJS_HOST_MEDIA_DIR=/opt/injs/injs-be/data/media` (continuité des médias)

## 5. Migrations : revue AVANT application

La référence automatisée est `deploy.sh plan`. Elle analyse l'image
désignée par les tags **actuellement présents dans le `.env` serveur**
(le journal les affiche : pour analyser une cible, renseigner d'abord
`INJS_BACKEND_TAG`/`INJS_FRONTEND_TAG`), calcule le plan au **format
réel de Django** (`Planned operations:` puis opérations indentées sans
tiret), le classe, et le contre-vérifie par `showmigrations --plan`
(toute incohérence entre les deux arrête la chaîne) :

```bash
cd /opt/injs/injs-lmd/deploy/production
./deploy.sh plan
```

- Opérations sûres (`Create model`, `Add field`) → poursuivre.
- Opérations **bloquantes** (`Delete model`, `Remove field`,
  `Rename field`, `Rename model`) → **STOP** : l'ancienne application
  partage la même base et deviendrait incompatible. Elles ne peuvent
  être autorisées que par la variable
  `DEPLOY_AUTORISER_MIGRATIONS_DESTRUCTIVES=oui-explicite`.
- Altérations, index, contraintes, migrations de données
  (`Raw Python operation`, `Raw SQL operation`), opérations
  personnalisées et **toute opération non reconnue** → classées
  « à examiner » : la chaîne s'arrête et exige l'inspection humaine,
  confirmable par `DEPLOY_AUTORISER_EXAMEN_MIGRATIONS=oui-explicite`.
  Une opération inconnue n'est jamais présumée inoffensive.
- Un plan vide, tronqué ou de format inattendu **arrête** la chaîne :
  une erreur d'analyse ne vaut jamais autorisation.
- Ne jamais modifier `django_migrations` à la main, jamais `--fake` sans
  analyse écrite.

## 6. Démarrage parallèle et vérification

```bash
cd /opt/injs/injs-lmd/deploy/production
./deploy.sh deployer --tag <SHA publié>   # sauvegarde → plan → migrations → up → santé
curl -sf http://127.0.0.1:8080/api/health/ && echo " API OK"
curl -sf http://127.0.0.1:8080/ -o /dev/null -w "Frontend HTTP %{http_code}\n"
```

**Comportement réel de l'entrypoint** : le compose transmet
`SKIP_DB_SETUP=true` par défaut — l'entrypoint exécute alors
directement la commande (Gunicorn) **sans appliquer aucune migration,
sans attente PostgreSQL et sans créer de superuser**. Les migrations
sont appliquées explicitement par `deploy.sh` après le plan validé
(§5), les fichiers statiques sont collectés à la construction de
l'image puis rafraîchis par `deploy.sh`, et les comptes existants sont
préservés tels quels. Ne passer `SKIP_DB_SETUP` à `false` que si l'on
assume délibérément la migration automatique au démarrage.
Vérifier les logs :
`docker compose -f deploy/production/compose.yml logs --tail 100 backend`.

Recette sur `http://152.228.233.123:8080` : page de connexion, authentification
avec un compte existant, référentiels, scolarité, GET-INJS. Refaire les
comptages de l'étape 3 : toute **baisse** impose l'arrêt et l'analyse ;
une **hausse** doit être expliquée par l'activité métier avant bascule
(voir §3 pour la portée exacte de cette comparaison).

## 7. Bascule du domaine (Nginx Proxy Manager)

1. Dans NPM, proxy host `injs.badge-qr-code.pro` : relever la cible actuelle
   (rollback) puis pointer vers la nouvelle passerelle
   (`<hôte>:8080` ou le conteneur `gateway` selon le réseau NPM).
2. Vérifier : `https://injs.badge-qr-code.pro` (certificat valide, page de
   connexion nouvelle version, aucun appel vers localhost).
3. Conserver l'ancienne stack **démarrée et intacte** pendant la période
   d'observation (retour arrière = repointer NPM, cf. §8).

## 8. Rollback (si problème majeur)

1. NPM : repointer `injs.badge-qr-code.pro` vers l'ancienne cible relevée
   au §7.1. Aucune donnée n'a été touchée par ce retour.
2. Si la nouvelle stack pose problème : `deploy.sh rollback` — valide
   **intégralement** la configuration précédente (tags, variables,
   secrets — mêmes contrôles qu'au chargement normal —, port, fichier
   compose) **avant le moindre arrêt**, puis arrête la stack
   (**sans `-v`**), **restaure les tags d'images précédents** depuis le
   dernier `.env.bak-*` (créé au début du déploiement concerné),
   relance les services restaurés et **vérifie leur disponibilité
   HTTP** ; le rollback échoue explicitement si la version restaurée
   ne répond pas, sans jamais restaurer la base automatiquement.
3. Ne restaurer le dump PostgreSQL **que** si une corruption/perte de
   données est constatée et documentée — jamais pour un bug applicatif.

**Limite fondamentale du rollback applicatif** : il ne restaure ni un
schéma PostgreSQL déjà migré, ni des données transformées par la
nouvelle version. Si les migrations appliquées ont rendu l'ancienne
application incompatible (renommage/suppression de colonne, migration
de données), revenir en arrière exige une décision humaine distincte
(migration inverse écrite et testée, ou restauration de sauvegarde
explicitement autorisée). C'est pour cela que la porte d'analyse du
plan (§5) bloque suppressions et renommages.

**Test de restauration isolée (à exécuter avant le premier vrai
déploiement, jamais sur la base de production)** : démarrer un
conteneur PostgreSQL 15 jetable et indépendant, y restaurer le dump de
sauvegarde, y relancer les comptages de référence, puis détruire le
conteneur et son volume temporaire. Ce test prouve que le dump est
restaurable sans jamais toucher à la base réelle.

## 9. Nettoyage (après validation seulement)

Conserver : le dump et les tarballs du §2, l'ancienne stack et ses images
jusqu'à validation métier. Ne supprimer ni volumes ni anciennes images
avant cette validation.

## 10. Chaîne automatisée (GitHub Actions + deploy.sh)

Les étapes §1 à §8 peuvent être exécutées par la chaîne automatisée,
sans jamais court-circuiter les contrôles :

- `.github/workflows/deploy-injs-lmd.yml` — déclenchement **manuel**
  uniquement, environnement GitHub `production`, cinq secrets SSH
  (`SSH_HOST`, `SSH_USER`, `SSH_PORT`, `SSH_PRIVATE_KEY`,
  `VPS_KNOWN_HOSTS`), `StrictHostKeyChecking=yes`, tag d'image
  explicite et immuable (`stable`/`latest` refusés), confirmation
  `DEPLOYER` tapée pour le mode `deployer`.
- `deploy/production/deploy.sh` — exécuté sur le VPS ; modes
  `inventaire` (lecture seule), `sauvegarde` (§2–3 ci-dessus :
  comptages en une seule instruction, dump à instantané propre,
  `pg_restore --list` dont **tout échec est fatal**, empreinte SHA-256
  comparée entre source et copie, copie rejetée renommée `.INVALIDE`),
  `plan` (§5 : analyse au format réel de Django, blocage des
  suppressions/renommages et arrêt sur opérations à examiner sauf
  autorisations explicites par variables), `deployer` (§2→§6
  enchaînés), `rollback` (§8, applicatif uniquement, configuration
  restaurée validée intégralement avant tout arrêt).
- Garde-fou anti-commandes destructrices : le script et les fichiers
  compose sont analysés sur texte normalisé (formes `-v`/`--volumes`,
  espacements). Limite assumée : une analyse statique ne détecte pas
  une commande assemblée dynamiquement (variables, interpolation) —
  c'est une défense en profondeur contre les erreurs, pas une
  garantie absolue.
- L'entrypoint ne migre plus tout seul : le compose transmet
  `SKIP_DB_SETUP=true` (défaut), seul `deploy.sh` lance `migrate`
  après la porte de contrôle du plan.
- Le `.env` du serveur n'est jamais transféré par le workflow
  (exclusion explicite) : il est créé une fois sur le VPS depuis
  `.env.example`.
- La bascule Nginx Proxy Manager (§7) reste **manuelle**, même via
  la chaîne automatisée.
- Premier usage recommandé : mode `inventaire`, puis `sauvegarde`
  seule, puis `plan`, avant tout `deployer`.

**Approbation humaine (environnement GitHub `production`)** : le
workflow est rattaché à l'environnement `production`, mais la règle
d'approbation se configure côté GitHub (Settings → Environments →
production → *Required reviewers*). Tant qu'aucun relecteur n'y est
exigé, un déclenchement manuel suffit à exécuter le job : configurer
au moins un relecteur avant le premier usage en mode `deployer`.
Le mode `inventaire` du workflow est intégralement en lecture seule :
aucun transfert, aucune création de fichier ou de répertoire sur le
VPS, journaux uniquement dans le journal du job GitHub.

Le script historique `scripts/backup_injs_lmd.sh` (base
`injs_lmd_current` en local hôte) n'est pas la référence sur le VPS :
la sauvegarde de référence est `deploy.sh sauvegarde`, qui identifie
explicitement le conteneur PostgreSQL et la base réellement utilisés.
