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
       (SELECT count(*) FROM edts_emploisdutemps)        AS emplois_du_temps;
```
(Ajuster les noms de tables si `psql \dt` montre des préfixes différents.)
Conserver ces chiffres : ils devront être **identiques après** déploiement.

## 4. Préparation de la nouvelle stack (sans arrêter l'existante)

```bash
cd /opt/injs
git clone https://github.com/JCKOUASSI/backend-injs2026.git injs-lmd-src 2>/dev/null \
  || (cd injs-lmd-src && git fetch --tags && git checkout deploy-20261105)
cp injs-lmd-src/deploy/production/.env.example injs-lmd-src/deploy/production/.env
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

```bash
cd /opt/injs/injs-lmd-src
docker compose -f deploy/production/compose.yml --env-file deploy/production/.env \
  run --rm backend python manage.py migrate --plan
```

- Plan uniquement additif (nouvelles tables/colonnes/index) → poursuivre.
- Toute opération destructive (`RemoveField`, `DeleteModel`, `AlterField`
  réducteur) → **STOP** : ne pas appliquer, remonter l'analyse.
- Ne jamais modifier `django_migrations` à la main, jamais `--fake` sans
  analyse écrite.

## 6. Démarrage parallèle et vérification

```bash
docker compose -f deploy/production/compose.yml --env-file deploy/production/.env up -d
docker compose -f deploy/production/compose.yml ps
curl -sf http://127.0.0.1:8080/api/health/ && echo " API OK"
curl -sf http://127.0.0.1:8080/ -o /dev/null -w "Frontend HTTP %{http_code}\n"
```

L'entrypoint backend applique `migrate --noinput` au démarrage (déjà
revu à l'étape 5) puis `collectstatic`. Vérifier les logs :
`docker compose -f deploy/production/compose.yml logs --tail 100 backend`.

Recette sur `http://152.228.233.123:8080` : page de connexion, authentification
avec un compte existant, référentiels, scolarité, GET-INJS. Refaire les
comptages de l'étape 3 : **ils doivent être inchangés**.

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
2. Si la nouvelle stack pose problème : `docker compose ... down`
   (**sans `-v`**) dans `injs-lmd-src` uniquement.
3. Ne restaurer le dump PostgreSQL **que** si une corruption/perte de
   données est constatée et documentée — jamais pour un bug applicatif.

## 9. Nettoyage (après validation seulement)

Conserver : le dump et les tarballs du §2, l'ancienne stack et ses images
jusqu'à validation métier. Ne supprimer ni volumes ni anciennes images
avant cette validation.
