# Mise à jour de production INJS — paquet de la session Arena

**État : paquet prêt, production NON mise à jour.** Aucun accès au Terminal du Mac, à Docker Desktop du Mac, ni au VPS `152.228.233.123` n'a été exécuté depuis cette session. Ne pas interpréter ce document comme une preuve de bascule.

- Source : commit `7c128c3da2a450f93ab9cde6599f1f5d3bb89eab` de la branche `arena/a8060ecf-backend-injs2026` (includes correctifs du contrôle des dossiers, dépôt/remplacement des pièces, formats de documents usuels et précédents changements de cette branche).
- Archive **de code uniquement** : `injs-source-7c128c3da2a450f93ab9cde6599f1f5d3bb89eab.tar.gz`, avec le fichier `.sha256` correspondant. SHA-256 : `7e39607d2d685f16514cb4b9dc9dffdc98b6e45a674800ca8354128737844550`.
- L'archive contient `backend/`, `frontend/`, `docker/`, `deploy/` et `scripts/` au même commit. Elle **ne contient pas** la base SQLite locale, les médias, les secrets ou un dump de production. Sa vérification et le test du mode de transfert local ont réussi dans une copie isolée ; aucune image Docker réelle n'a été construite ici.
- Chemin de déploiement retenu : **Arena → Terminal macOS → VPS**, images INJS construites sur le Mac et transférées par `scp`, sans publication Docker Hub ni GitHub Actions. Un commit GitHub n'est pas un déploiement.

## Commandes de départ sur le Mac

Enregistrer depuis Arena les **deux** fichiers dans `~/Downloads`. Sur le Mac (pas dans Arena) :

```sh
SHA=7c128c3da2a450f93ab9cde6599f1f5d3bb89eab
cd "$HOME/Downloads" || exit 1
shasum -a 256 -c "injs-source-$SHA.tar.gz.sha256" || exit 1
SOURCE="$HOME/injs-source-$SHA"
mkdir -p "$SOURCE" || exit 1
tar -xzf "injs-source-$SHA.tar.gz" -C "$SOURCE" || exit 1
bash "$SOURCE/scripts/tester-deploiement-local.sh" || exit 1
# Vérifier la clé hôte SSH par un canal indépendant avant cette commande :
sh "$SOURCE/deploy/production/preflight-macos.sh" || exit 1
```

**STOP à ce point tant que l'inventaire VPS, la base et les médias réels, l'espace disque, les accès SSH et le port parallèle ne sont pas confirmés.** Ne jamais saisir de mot de passe, de `.env`, ni de clé privée dans Arena. Suivre ensuite **pas à pas** `"$SOURCE/deploy/production/DEPLOIEMENT-DIRECT-MACOS.md"` (sections 2 à 6) depuis le Mac. Ce guide inclut les commandes Buildx, le transfert direct, l'inventaire du VPS, la sauvegarde PostgreSQL, le plan de migration, la recette parallèle et le rollback NPM. Ne pas substituer une sauvegarde de la démo SQLite à celle de la base réellement servie.

## Portes obligatoires avant bascule

1. Vérifier l'identité de l'hôte, les chemins/configurations réels, la cible actuelle Nginx Proxy Manager, les comptes de démonstration éventuellement encore actifs et l'espace disque.
2. Faire **et vérifier une restauration isolée** d'un dump PostgreSQL de la base servie ; sauvegarder aussi les médias depuis leur vrai emplacement et conserver les configurations/proxy actuels. Le script `deploy.sh sauvegarde` **ne sauvegarde pas les médias**.
3. Examiner sur le VPS le `migrate --plan` : cette branche apporte notamment des ajouts de champs et index dans `edts`, `formations`, `referentiels` et `scolarite`. Le plan dépend des migrations **déjà appliquées sur la base servie** : ne pas déduire sa sûreté de la seule lecture du dépôt. Une migration de production peut ne pas être rétrocompatible avec l'ancienne stack ; préparer le retour arrière avant application.
4. Démarrer la nouvelle stack **sur un port parallèle**, conserver l'ancienne en ligne. Tester authentification, droits, ouvertures de dossiers, dépôt/remplacement de formats autorisés, validation/refus, téléchargements, inscriptions, comptages, médias, exports/imports et QR physiques, avec des comptes/échantillons de recette contrôlés. Un simple `GET /api/health/` ne suffit pas.
5. Seulement après validation : basculer la cible NPM réelle ; vérifier le domaine public, puis conserver l'ancienne stack et les sauvegardes. En cas d'anomalie, remettre immédiatement la cible NPM précédente. `deploy.sh rollback` ne restaure **ni données ni migrations**.

**Aucune opération VPS ou bascule n'a été confirmée au moment de la rédaction de ce dossier.**
