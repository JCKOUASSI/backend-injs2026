# Transfert direct Mac → VPS — source exacte `daaeece`

**État : non déployé.** Ce dossier accompagne l'archive source du commit `daaeece25b88b88ba7000c670b75b81165e45c85` sur `arena/a8060ecf-backend-injs2026`. Il ne prouve aucune connexion au Mac/VPS. Le site cible est `https://injs.badge-qr-code.pro/`, VPS `152.228.233.123` (utilisateur `almalinux`). Le mot de passe SSH, s'il est demandé, se saisit uniquement dans le Terminal macOS ; **ne jamais le communiquer dans Arena**.

## 1. Sur votre Mac : récupérer et vérifier la source

Télécharger depuis cette session Arena dans `~/Downloads` les deux fichiers :

- `injs-source-daaeece25b88b88ba7000c670b75b81165e45c85.tar.gz`
- `injs-source-daaeece25b88b88ba7000c670b75b81165e45c85.tar.gz.sha256`

```sh
SHA=daaeece25b88b88ba7000c670b75b81165e45c85
cd "$HOME/Downloads" || exit 1
shasum -a 256 -c "injs-source-$SHA.tar.gz.sha256" || exit 1
SOURCE="$HOME/injs-source-$SHA"
[ ! -e "$SOURCE" ] || { echo "STOP : $SOURCE existe déjà ; ne rien écraser"; exit 1; }
mkdir -p "$SOURCE" || exit 1
tar -xzf "injs-source-$SHA.tar.gz" -C "$SOURCE" || exit 1
cat "$SOURCE/REVISION.txt"
grep -Fx "Commit: $SHA" "$SOURCE/REVISION.txt" || exit 1
bash "$SOURCE/scripts/tester-deploiement-local.sh" || exit 1
```

Le paquet contient le code et les scripts, **pas** la base ni les médias de production. Il ne modifie pas `/Users/jckouassi/injs-arena-source` (qui peut contenir une démo locale). Ne pas y lancer les seeds de démonstration pour préparer la production.

## 2. Préflight VPS : lecture seule

Vérifier **hors bande** l'empreinte SSH du VPS avant connexion et l'inscrire dans `~/.ssh/known_hosts` sur le Mac. Ne jamais désactiver `StrictHostKeyChecking`.

```sh
sh "$SOURCE/deploy/production/preflight-macos.sh"
```

**STOP** : examiner la sortie (conteneurs actuels, base, réseau, médias et espace libre) avant tout transfert. Ne pas coller de secrets dans Arena. Si vous souhaitez une revue guidée, communiquer uniquement les informations non sensibles de l'inventaire.

## 3. Suite contrôlée

Sur le Mac, suivre les **sections 2 à 6** du guide livré dans l'archive :

```sh
open "$SOURCE/deploy/production/DEPLOIEMENT-DIRECT-MACOS.md"
```

Construire les images `linux/amd64` sur le Mac, les transférer directement avec le code et vérifier les SHA-256 sur le VPS. Depuis le VPS, sauvegarder la **base réellement servie** et les **médias réels**, vérifier une restauration isolée, lire le plan de migrations, puis démarrer une stack sur un port parallèle. Recetter les fonctionnalités et les QR physiques avant toute bascule de la cible réelle Nginx Proxy Manager. Conserver l'ancienne stack ; noter sa cible pour le retour arrière. **Aucune bascule n'est automatisée par ce document.**

Le guide historique `livrables/MISE-A-JOUR-PRODUCTION-2026-11-18.md` dans l'archive décrit un paquet de code au commit précédent ; **pour ce déploiement, utiliser exclusivement le SHA et les fichiers ci-dessus**. Ne pas remplacer l'archive par le précédent paquet `7c128c3`.
