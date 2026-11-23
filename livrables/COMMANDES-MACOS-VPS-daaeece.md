# Commandes Terminal macOS → VPS INJS (paquet exact daaeece)

**Exécution par l'administrateur sur SON Mac. Aucune commande de cette fiche n'a été exécutée sur le Mac ni sur le VPS depuis Arena.** Ne jamais saisir un mot de passe ou une clé privée dans Arena. Mot de passe SSH : uniquement dans l'invite du Terminal macOS. Les sections marquées STOP doivent être validées avant de continuer. Source = `arena/a8060ecf-backend-injs2026` au commit `daaeece25b88b88ba7000c670b75b81165e45c85`. Destination = `https://injs.badge-qr-code.pro/`, VPS `152.228.233.123` (`almalinux`). Le déploiement est **direct Mac → VPS**, sans publication des images INJS via GitHub ou Docker Hub.

## A. Mac — réception et contrôle du paquet (aucun contact VPS)

Télécharger depuis Arena dans `~/Downloads` les fichiers `injs-source-daaeece25b88b88ba7000c670b75b81165e45c85.tar.gz` et `.tar.gz.sha256` de même préfixe.

```sh
SHA=daaeece25b88b88ba7000c670b75b81165e45c85
cd "$HOME/Downloads" || exit 1
shasum -a 256 -c "injs-source-$SHA.tar.gz.sha256" || exit 1
SOURCE="$HOME/injs-source-$SHA"
[ ! -e "$SOURCE" ] || { echo "STOP : $SOURCE existe déjà"; exit 1; }
mkdir -p "$SOURCE" || exit 1
tar -xzf "injs-source-$SHA.tar.gz" -C "$SOURCE" || exit 1
grep -Fx "Commit: $SHA" "$SOURCE/REVISION.txt" || exit 1
bash "$SOURCE/scripts/tester-deploiement-local.sh" || exit 1
```

Ce répertoire est distinct de `/Users/jckouassi/injs-arena-source` : ne pas écraser la démo locale et **ne jamais** lancer ses seeds contre la production.

## B. Mac — préflight en lecture seule

**STOP : vérifier l'empreinte de la clé hôte du VPS par un canal indépendant et l'inscrire dans `~/.ssh/known_hosts` avant SSH.** Ne pas contourner `StrictHostKeyChecking=yes`.

```sh
sh "$SOURCE/deploy/production/preflight-macos.sh" || exit 1
```

Lire la sortie : conteneur PostgreSQL effectivement servi, base et réseau, volumes, chemin réel des médias, espace disque, ancienne stack, port libre pour la recette, cible Nginx Proxy Manager actuelle. **STOP si ces éléments ne sont pas établis.** Préserver l'état du site actuel ; faire révoquer les identifiants démo encore actifs par un administrateur.

## C. Mac — construire les images linux/amd64 depuis l'archive Arena

N'exécuter qu'après préflight concluant, avec Docker Desktop + Buildx opérationnels et assez de place sur le Mac ET le VPS (images, archive et sauvegardes).

```sh
cd "$SOURCE" || exit 1
docker info >/dev/null || exit 1
docker buildx build --platform linux/amd64 --load \
  -t "jckouassi/injs-be:$SHA" -f backend/Dockerfile backend || exit 1
docker buildx build --platform linux/amd64 --load \
  --build-arg VITE_API_URL=https://injs.badge-qr-code.pro/api \
  --build-arg VITE_BADGE_BASE_URL=https://injs.badge-qr-code.pro \
  --build-arg "VERSION=$SHA" \
  -t "jckouassi/injs-fe:$SHA" -f frontend/Dockerfile frontend || exit 1
docker pull --platform linux/amd64 nginx:1.27-alpine || exit 1
for image in "jckouassi/injs-be:$SHA" "jckouassi/injs-fe:$SHA" nginx:1.27-alpine; do
  [ "$(docker image inspect --format '{{.Os}}/{{.Architecture}}' "$image")" = linux/amd64 ] || exit 1
done
BUNDLE="$HOME/Downloads/injs-images-$SHA.tar"
[ ! -e "$BUNDLE" ] || { echo 'STOP : archive images déjà présente'; exit 1; }
docker save -o "$BUNDLE" "jckouassi/injs-be:$SHA" "jckouassi/injs-fe:$SHA" nginx:1.27-alpine || exit 1
BUNDLE_SHA=$(shasum -a 256 "$BUNDLE" | awk '{print $1}')
printf 'Archive : %s\nSHA-256 : %s\n' "$BUNDLE" "$BUNDLE_SHA"
```

## D. Mac — transfert direct vers le dossier candidat VPS (pas de bascule)

**STOP** si `/opt/injs/injs-lmd` n'est pas identifié et inscriptible par `almalinux`. Ne pas toucher aux permissions de `/opt/injs` en bloc, ne pas utiliser `--delete` ni transférer `.env` ou une base SQLite locale.

```sh
ssh -o StrictHostKeyChecking=yes almalinux@152.228.233.123 \
  'test -d /opt/injs/injs-lmd && test -w /opt/injs/injs-lmd && df -h /opt/injs' || exit 1
ssh -o StrictHostKeyChecking=yes almalinux@152.228.233.123 \
  "test ! -e '/opt/injs/injs-lmd/images-$SHA.tar'" || { echo 'STOP : archive déjà présente sur VPS'; exit 1; }
rsync -av --relative -e 'ssh -o StrictHostKeyChecking=yes' --exclude '.env' --exclude '.env.bak-*' --exclude 'logs/' \
  "$SOURCE/./deploy/production/" "$SOURCE/./docker/" \
  almalinux@152.228.233.123:/opt/injs/injs-lmd/ || exit 1
scp -o StrictHostKeyChecking=yes "$BUNDLE" "almalinux@152.228.233.123:/opt/injs/injs-lmd/images-$SHA.tar" || exit 1
ssh -o StrictHostKeyChecking=yes almalinux@152.228.233.123 \
  "printf '%s  %s\n' '$BUNDLE_SHA' '/opt/injs/injs-lmd/images-$SHA.tar' | sha256sum -c - && docker load -i '/opt/injs/injs-lmd/images-$SHA.tar'" || exit 1
```

## E. VPS — configuration et sauvegardes (dans la session SSH ouverte depuis le Mac)

```sh
ssh -o StrictHostKeyChecking=yes almalinux@152.228.233.123
```

**Les commandes ci-dessous s'exécutent sur le VPS, pas sur le Mac.** Vérifier le chemin de la base et des médias d'après l'inventaire. `deploy.sh` refuse les secrets placeholders. Ne jamais afficher ni copier `.env` dans Arena.

```sh
cd /opt/injs/injs-lmd/deploy/production || exit 1
./deploy.sh inventaire || exit 1
umask 077
[ -f .env ] && cp -p .env ".env.avant-$(date -u +%Y%m%d-%H%M%S)"
[ -f .env ] || cp .env.example .env
chmod 600 .env
vi .env
```

Dans `vi`, renseigner **sur le VPS** : `INJS_BACKEND_TAG` et `INJS_FRONTEND_TAG` = `daaeece25b88b88ba7000c670b75b81165e45c85`, `POSTGRES_*` de la base réellement servie, `DJANGO_SECRET_KEY`, `INJS_NETWORK_*`, `INJS_HOST_MEDIA_DIR` réel et `INJS_PUBLIC_PORT` **libre** (8080 seulement s'il est libre). Ne jamais remplacer l'ancien `.env` d'une installation différente. Noter sur un support sûr la cible NPM actuelle et le plan de retour arrière.

```sh
SHA=daaeece25b88b88ba7000c670b75b81165e45c85
DEPLOY_IMAGES_LOCALES=oui ./deploy.sh sauvegarde || exit 1
```

**STOP : le dump vérifié par ce script n'inclut PAS les médias.** Sauvegarder les médias depuis le chemin réellement confirmé ; remplacer la valeur illustrative ci-dessous par le chemin EXISTANT constaté, sans supprimer quoi que ce soit :

```sh
MEDIA_DIR=/CHEMIN/REEL/DES/MEDIAS
BACKUP_DIR=/opt/injs/backups
[ -d "$MEDIA_DIR" ] && [ -r "$MEDIA_DIR" ] && [ -w "$BACKUP_DIR" ] || { echo 'STOP : chemins/permissions à confirmer'; exit 1; }
STAMP=$(date -u +%Y%m%d-%H%M%S)
tar -C "$(dirname "$MEDIA_DIR")" -czf "$BACKUP_DIR/media-$STAMP.tar.gz" "$(basename "$MEDIA_DIR")" || exit 1
chmod 600 "$BACKUP_DIR/media-$STAMP.tar.gz"
tar -tzf "$BACKUP_DIR/media-$STAMP.tar.gz" >/dev/null || exit 1
sha256sum "$BACKUP_DIR/media-$STAMP.tar.gz" > "$BACKUP_DIR/media-$STAMP.tar.gz.sha256"
```

**STOP : `pg_restore --list` et SHA-256 ne démontrent pas qu'une restauration fonctionne.** Si la base courante utilise l'image officielle `postgres:*`, que le dump sélectionné est le dernier dump **validé** et que l'espace disque suffit pour une seconde copie/restauration intégrale, utiliser le contrôle **isolé et sans réseau** suivant. Sinon arrêter et faire établir une procédure de restauration isolée par l'administrateur (ne pas tester sur la base servie). Remplacer le chemin du dump par le nom réel renvoyé par `deploy.sh sauvegarde` ; ce chemin ne doit pas finir par `.INVALIDE`.

```sh
PG_IMAGE=$(docker inspect --format '{{.Config.Image}}' injs-db) || exit 1
case "$PG_IMAGE" in postgres:*|docker.io/library/postgres:*) ;; *) echo 'STOP : image PostgreSQL non officielle, procédure à adapter'; exit 1;; esac
DUMP=/opt/injs/backups/injs-NOM-REEL.dump
[ -s "$DUMP" ] && [ -f "$DUMP.sha256" ] || { echo 'STOP : dump non vérifié'; exit 1; }
(cd "$(dirname "$DUMP")" && sha256sum -c "$(basename "$DUMP").sha256") || exit 1
df -h /opt/injs /var/lib/docker
RESTORE_NAME="injs-restore-$(date -u +%Y%m%d%H%M%S)"
docker run --rm -d --name "$RESTORE_NAME" --network none \
  -e POSTGRES_HOST_AUTH_METHOD=trust "$PG_IMAGE" || exit 1
# Attendre la disponibilité ; si échec, diagnostiquer sans toucher à injs-db :
docker exec "$RESTORE_NAME" pg_isready -U postgres || exit 1
docker exec -i "$RESTORE_NAME" pg_restore --exit-on-error --no-owner --no-acl \
  --create -U postgres -d postgres < "$DUMP" || exit 1
# Adapter le nom DB à celui contenu dans le dump s'il diffère de la base servie :
docker exec "$RESTORE_NAME" psql -U postgres -d injs -Atc \
  'SELECT count(*) FROM authentication_user;' || exit 1
# Uniquement après preuve conservée de restauration et vérification :
docker stop "$RESTORE_NAME" || exit 1
```

Le conteneur temporaire utilise une copie privée, sans volume de production ni accès réseau. Il consomme néanmoins de l'espace sur le disque Docker ; **ne pas le lancer si la capacité est incertaine**. Si `pg_isready` échoue immédiatement après le démarrage, consulter les logs du conteneur isolé et retenter seulement ce contrôle, sans reprendre les étapes suivantes. Vérifier aussi la lecture de l'archive médias. Ne pas passer à `plan` sans preuve de restauration concluante.

## F. VPS — plan, déploiement parallèle et recette

Après validation documentée des sauvegardes, tester le plan. Il peut nécessiter une revue manuelle (notamment pour `AlterField`) : **ne pas définir `DEPLOY_AUTORISER_EXAMEN_MIGRATIONS` ou `DEPLOY_AUTORISER_MIGRATIONS_DESTRUCTIVES` sans analyse formelle.**

```sh
cd /opt/injs/injs-lmd/deploy/production || exit 1
DEPLOY_IMAGES_LOCALES=oui ./deploy.sh plan || exit 1
```

**STOP si le script bloque ou si le plan est incompatible avec l'ancienne stack ou les données présentes.** Les migrations utilisent la base de production partagée : la recette sur port parallèle n'isole pas les changements de schéma. Après revue et accord de l'administrateur sur la compatibilité, démarrer sans changer le proxy :

```sh
DEPLOY_IMAGES_LOCALES=oui ./deploy.sh deployer --tag "$SHA" || exit 1
# Remplacer 8080 si INJS_PUBLIC_PORT diffère ; contrôles HTTP locaux sur le VPS :
curl -fsS --max-time 20 http://127.0.0.1:8080/api/health/ || exit 1
curl -fsS --max-time 20 http://127.0.0.1:8080/ >/dev/null || exit 1
```

**STOP** : tester sur ce port parallèle avec des comptes habilités et des données de recette contrôlées : connexion, contrôle des dossiers, dépôt et remplacement de pièces, validation/refus, téléchargement, listes étudiants, imports/exports, autres étapes Scolarité, médias et QR physiques. Comparer les comptages avant/après, vérifier les logs et les droits. Un HTTP 200 ne suffit pas. Ne pas créer de faux pointages en production.

## G. Bascule Nginx Proxy Manager (manuelle) et vérification depuis le Mac

**Uniquement après recette validée et cible historique NPM notée** : dans NPM, modifier le *proxy host* `injs.badge-qr-code.pro` pour pointer vers la passerelle parallèle sur son hôte/port **réellement accessibles depuis NPM**. Ne pas inventer une cible à partir de `127.0.0.1:8080` (localhost dépend du conteneur). Garder l'ancienne stack en ligne. Depuis le Mac :

```sh
curl -fsS --max-time 20 https://injs.badge-qr-code.pro/api/health/ || exit 1
curl -sS --max-time 20 -o /dev/null \
  -w 'Racine HTTP %{http_code}; TLS %{ssl_verify_result}\n' \
  https://injs.badge-qr-code.pro/ || exit 1
```

Tester à nouveau les parcours métier authentifiés. En cas d'anomalie, **remettre immédiatement l'ancienne cible NPM**. Le retour arrière du proxy n'annule pas les migrations ; ne pas exécuter `deploy.sh rollback`, restaurer la base ou arrêter l'ancienne stack sans décision humaine distincte. Ne jamais faire `docker compose down -v`, `flush`, `dropdb` ou `docker system prune`.
