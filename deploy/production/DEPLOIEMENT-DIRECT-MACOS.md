# Déploiement direct depuis le Mac — sans GitHub Actions ni Docker Hub pour les images INJS

**Source** : archive de la session Arena (`injs-source-<SHA>.tar.gz`) et son fichier `.sha256` fournis avec ce guide. Elle contient les répertoires `backend/`, `frontend/`, `docker/`, `deploy/` et le test local. Le SHA du nom est celui de la source ; ce n'est **pas** une preuve que la version tourne sur le VPS. Ne pas remplacer l'archive par une ancienne version du dépôt GitHub. Le Mac doit disposer de Docker Desktop avec Buildx, de `ssh`, `scp` et `rsync`. Docker peut télécharger ses **images de base** (Python, Node, nginx) depuis un registre ; les images INJS sont construites sur le Mac et transférées directement au VPS, sans publication sur GitHub/Docker Hub.

**Stop avant production** : contrôle local et revue du code, préflight VPS, identité SSH vérifiée hors bande, vraie base et médias identifiés, sauvegarde/restauration isolée, plan de migrations lu, recette sur port parallèle, rollback NPM documenté. Le site public actuel présente des comptes de démonstration : vérifier leur révocation/rotation par un administrateur avant bascule. Ne jamais envoyer le mot de passe SSH ou le `.env` dans Arena.

## 1. Mac — source et contrôle

Télécharger l'archive et son `.sha256` depuis Arena dans `~/Downloads`. Remplacer `SHA_A_REPRENDRE_DU_NOM_DE_L_ARCHIVE` ci-dessous par **le SHA complet inscrit dans les noms téléchargés**.

```sh
SHA=SHA_A_REPRENDRE_DU_NOM_DE_L_ARCHIVE
case "$SHA" in *[!0-9a-f]*|'') echo 'SHA invalide'; exit 1;; esac
[ "${#SHA}" -eq 40 ] || { echo 'SHA incomplet'; exit 1; }
cd "$HOME/Downloads"
shasum -a 256 -c "injs-source-$SHA.tar.gz.sha256" || exit 1
SOURCE="$HOME/injs-source-$SHA"
mkdir -p "$SOURCE"
tar -xzf "injs-source-$SHA.tar.gz" -C "$SOURCE"
[ -f "$SOURCE/deploy/production/deploy.sh" ] || exit 1
bash "$SOURCE/scripts/tester-deploiement-local.sh" || exit 1
sh "$SOURCE/deploy/production/preflight-macos.sh" || exit 1
```

Le préflight est **en lecture seule**. La clé hôte du VPS doit avoir été vérifiée par un autre canal avant de lancer SSH avec `StrictHostKeyChecking=yes` ; aucun `sshpass` ni désactivation de la vérification de clé.

## 2. Mac — construire des images linux/amd64 locales

```sh
docker info >/dev/null || exit 1
cd "$SOURCE"
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
docker save -o "$BUNDLE" "jckouassi/injs-be:$SHA" "jckouassi/injs-fe:$SHA" nginx:1.27-alpine || exit 1
BUNDLE_SHA="$(shasum -a 256 "$BUNDLE" | awk '{print $1}')"
printf 'Archive images : %s\nSHA-256 : %s\n' "$BUNDLE" "$BUNDLE_SHA"
```

Vérifier que l'espace disque est suffisant sur le Mac **et** sur le VPS (archive, images chargées, sauvegarde et stack parallèle). Aucun `docker system prune`.

## 3. Mac → VPS — transférer code et images, sans secrets

Ne poursuivre que si l'inventaire a confirmé l'utilisateur `almalinux`, le réseau/base réellement servis, les chemins des médias et l'accès en écriture au **seul** répertoire candidat. Si `/opt/injs/injs-lmd` n'est pas inscriptible par `almalinux`, arrêter et faire préparer ce dossier par l'administrateur ; ne pas changer les droits de `/opt/injs` en bloc.

```sh
ssh -o StrictHostKeyChecking=yes almalinux@152.228.233.123 \
  'mkdir -p /opt/injs/injs-lmd && df -h /opt/injs'
# --relative garde deploy/production et docker/ ; pas de --delete ni de .env.
rsync -av --relative --exclude '.env' --exclude 'logs/' \
  "$SOURCE/./deploy/production/" "$SOURCE/./docker/" \
  almalinux@152.228.233.123:/opt/injs/injs-lmd/
scp -o StrictHostKeyChecking=yes "$BUNDLE" \
  "almalinux@152.228.233.123:/opt/injs/injs-lmd/images-$SHA.tar"
# Le SHA-256 de l'archive doit être identique AVANT docker load.
ssh -o StrictHostKeyChecking=yes almalinux@152.228.233.123 \
  "printf '%s  %s\n' '$BUNDLE_SHA' '/opt/injs/injs-lmd/images-$SHA.tar' | sha256sum -c - && docker load -i '/opt/injs/injs-lmd/images-$SHA.tar'"
```

Pas de `--delete`, de `docker compose down`, de restauration de dump ni d'envoi de `.env`. Ne jamais révéler l'archive si elle contient des données non destinées au serveur (ce paquet source ne contient pas de base SQLite ni de secrets runtime).

## 4. VPS — configuration, sauvegarde et plan, sans bascule

Ouvrir une session depuis le Mac (saisie du mot de passe **dans le Mac seulement**, si nécessaire) :

```sh
ssh -o StrictHostKeyChecking=yes almalinux@152.228.233.123
```

Dans **cette session VPS**, exécuter les commandes suivantes une par une ; **vérifier les sorties avant de poursuivre** :

```sh
cd /opt/injs/injs-lmd/deploy/production
./deploy.sh inventaire
# Si .env est absent, une seule fois :
umask 077
[ -f .env ] || cp .env.example .env
chmod 600 .env
vi .env
```

Dans l'éditeur sur le VPS, renseigner les deux `INJS_*_TAG` au SHA du paquet, le mot de passe PostgreSQL de la base **réellement servie**, sa DB/USER/HOST, la clé Django, le réseau Docker externe, `INJS_HOST_MEDIA_DIR` existant et un port libre (8080 seulement s'il est libre). Les placeholders sont refusés par `deploy.sh`. Ne pas copier un fichier `.env` du Mac ou d'un autre environnement. Confirmer la cible actuelle Nginx Proxy Manager et documenter le rollback **avant** de démarrer.

```sh
# Toujours dans /opt/injs/injs-lmd/deploy/production sur le VPS :
DEPLOY_IMAGES_LOCALES=oui ./deploy.sh sauvegarde
# STOP : vérifier le dump, son empreinte, les médias et une RESTAURATION
# sur une base isolée, jamais sur la base servie.
DEPLOY_IMAGES_LOCALES=oui ./deploy.sh plan
# STOP : examiner les migrations et leur compatibilité avec l'ancienne stack.
```

Le script sauvegarde PostgreSQL, mais **ne sauvegarde pas les médias** : les sauvegarder séparément depuis le **chemin réel confirmé** (`RUNBOOK.md` §2), et vérifier leur archive. Un plan « à examiner » ou destructif bloque ; ne pas forcer une autorisation de migration sans analyse écrite.

## 5. VPS — démarrage parallèle seulement après validation des portes

```sh
# SHA = SHA complet du paquet, saisir à nouveau DANS LA SESSION VPS :
SHA=SHA_A_REPRENDRE_DU_NOM_DE_L_ARCHIVE
case "$SHA" in *[!0-9a-f]*|'') echo 'SHA invalide'; exit 1;; esac
[ "${#SHA}" -eq 40 ] || { echo 'SHA incomplet'; exit 1; }
cd /opt/injs/injs-lmd/deploy/production
DEPLOY_IMAGES_LOCALES=oui ./deploy.sh deployer --tag "$SHA"
curl -fsS http://127.0.0.1:8080/api/health/
curl -sS -o /dev/null -w 'Frontend HTTP %{http_code}\n' http://127.0.0.1:8080/
```

**Attention** : si le port du `.env` diffère de 8080, utiliser le vrai port. `deploy.sh deployer` refait un dump, contrôle les migrations et démarre une stack **parallèle** sans toucher au proxy. Contrôler les effectifs, médias et les parcours authentifiés sur ce port ; faire tester les QR sur les appareils réels. Aucun HTTP 200 ne remplace cette recette.

## 6. Bascule / retour arrière

Sur Nginx Proxy Manager, enregistrer **la cible actuelle réelle** du host `injs.badge-qr-code.pro`, puis le pointer manuellement sur la passerelle du port parallèle validé (routage accessible depuis NPM à confirmer). Ce dépôt n'a pas l'ID/configuration NPM : **ne pas inventer une commande API**. Garder l'ancienne stack en ligne.

Après la modification, depuis le Mac :

```sh
curl -fsS --max-time 20 https://injs.badge-qr-code.pro/api/health/
curl -sS --max-time 20 -o /dev/null \
  -w 'Racine HTTP %{http_code}; TLS %{ssl_verify_result}\n' \
  https://injs.badge-qr-code.pro/
```

Si anomalie : **replacer immédiatement la cible NPM précédente**. Le rollback applicatif `DEPLOY_IMAGES_LOCALES=oui ./deploy.sh rollback` ne restaure PAS les migrations ou données PostgreSQL ; ne l'utiliser qu'après décision humaine et preuve de disponibilité des anciennes images. Ne jamais supprimer la base, les volumes ou l'ancienne stack pour « réparer » un test de santé.
