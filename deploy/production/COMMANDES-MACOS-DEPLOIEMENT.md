# Terminal macOS — procédure conditionnelle de déploiement VPS

**Cible** : `injs.badge-qr-code.pro`, VPS `152.228.233.123`, compte `almalinux`. Cette fiche donne les commandes à lancer **sur votre Mac**, pas dans le sandbox de l'agent. Elle ne constitue pas une autorisation de passer outre un contrôle en échec. Lire aussi `RUNBOOK.md` et `GUIDE-DEPLOIEMENT-AUTOMATIQUE.md`.

**État au moment de la rédaction** : PR #12 ouverte, backend PostgreSQL encore en cours, aucune image réussie du SHA de la PR, déclenchement GitHub Actions refusé à l'intégration de l'agent (403). **Ne pas lancer les étapes de publication/déploiement/bascule avant leur résolution.** Le site actuel affiche des comptes de démonstration : vérifier et révoquer/faire tourner les identifiants concernés par canal administrateur sécurisé avant la bascule. Ne jamais tester un de ces mots de passe depuis cette procédure.

## 0. Préparation sur le Mac (sans écrire sur le VPS)

Installer/ouvrir une copie du dépôt et `gh` sur macOS ; se connecter à GitHub dans le terminal Mac avec un compte habilité. Ne communiquer aucun secret, mot de passe ni clé privée dans la conversation. Vérifier **hors bande** l'empreinte de la clé hôte SSH du serveur auprès de l'administrateur avant de l'inscrire dans `~/.ssh/known_hosts` ; ne pas accepter aveuglément une empreinte issue d'un seul `ssh-keyscan`.

```sh
cd /chemin/vers/backend-injs2026
git status --short --branch
gh auth status
gh pr view 12 --json state,headRefOid,baseRefName
gh pr checks 12
sh deploy/production/preflight-macos.sh
```

Le préflight SSH n'est qu'un inventaire : un nom de dump et sa taille ne prouvent **pas** sa restaurabilité. SSH peut demander un mot de passe dans le terminal du Mac ; ne jamais le passer en argument ou le publier. `StrictHostKeyChecking=yes` refuse un hôte non vérifié. Si `gh` retourne 403 ou si SSH refuse la connexion, **STOP** : habiliter le compte GitHub et l'accès SSH par clé du workflow, sans contourner la protection. La connexion SSH du Mac par mot de passe ne répare pas les secrets SSH du workflow GitHub.

## 1. Qualification du code et publication des images (Mac, compte GitHub habilité)

**Porte** : tous les checks de la PR doivent être verts (y compris Django/PostgreSQL), la revue et les données métier nécessaires approuvées. Ne fusionner que dans ce cas. Ne jamais publier le SHA d'une ancienne image « verte » à la place du code à déployer.

```sh
gh pr checks 12 --watch
# SEULEMENT SI tous les checks sont verts et la revue approuve la PR :
gh pr merge 12 --merge
# S'assurer que le commit fusionné est effectivement sur main :
git fetch origin main
SHA="$(git rev-parse origin/main)"
printf 'Cible main : %s\n' "$SHA"
# Confirmer que le SHA affiché contient les changements attendus avant publication :
git log -1 --format='%H %s' origin/main
```

**STOP** si la PR ne peut pas être fusionnée, si `origin/main` ne contient pas les changements, ou si un autre changement a été ajouté sans revue. Dans GitHub, vérifier que les secrets Docker Hub nécessaires sont configurés. Depuis le Mac avec les droits Actions `workflow_dispatch` :

```sh
gh workflow run publish-injs-lmd.yml --ref main
gh run list --workflow publish-injs-lmd.yml --branch main --limit 10
# Avec l'identifiant RÉEL de l'exécution qui vient d'être créée :
gh run watch IDENTIFIANT_REEL
# Vérifier que les deux images correspondent exactement au SHA retenu :
gh run list --workflow publish-injs-lmd.yml --branch main --limit 10 \
  --json headSha,status,conclusion,databaseId \
  --jq '.[] | {id:.databaseId,sha:.headSha,status:.status,conclusion:.conclusion}'
```

**Porte** : les deux images backend/frontend sont publiées avec leurs digests pour **exactement** `$SHA`, et la publication se conclut par `success`. Les tags `stable`/`latest` ne sont jamais une cible de déploiement.

## 2. Préflight, sauvegarde et plan (Mac → workflow VPS)

Avant la première exécution : un administrateur doit configurer sur GitHub l'environnement `production`, les secrets SSH par clé et l'approbation humaine ; le dossier serveur `/opt/injs/injs-lmd`, le `.env` VPS **non transféré par GitHub**, le réseau PostgreSQL, la cible proxy actuelle et la destination média doivent être inspectés et configurés selon `RUNBOOK.md`. Ne **jamais** recopier un `.env` dans ce dépôt ou dans le chat. Dans `production`, le nom exact de la base réellement servie doit être prouvé, ainsi que la possibilité de restauration d'un dump dans une base **isolée**.

```sh
# SHA reste celui de l'image publiée, jamais un tag mutable :
case "$SHA" in
  *[!0-9a-f]*|'') echo 'SHA invalide'; exit 1 ;;
esac
[ "${#SHA}" -eq 40 ] || { echo 'SHA incomplet'; exit 1; }
gh workflow run deploy-injs-lmd.yml --ref main -f mode=preflight -f tag_images="$SHA"
gh run list --workflow deploy-injs-lmd.yml --limit 10
# Avec l'identifiant RÉEL du preflight :
gh run watch IDENTIFIANT_REEL
```

**STOP** tant que le préflight n'est pas vert, que la cible proxy historique n'est pas relevée ou que le plan de sauvegarde/restauration n'est pas validé. Ensuite, séparément, inspecter **chaque** rapport avant de déclencher le suivant :

```sh
gh workflow run deploy-injs-lmd.yml --ref main -f mode=sauvegarde -f tag_images="$SHA"
# Relever l'ID réel puis : gh run watch IDENTIFIANT_REEL ; vérifier dump + empreinte + restauration isolée.
gh workflow run deploy-injs-lmd.yml --ref main -f mode=plan -f tag_images="$SHA"
# Relever l'ID réel puis : gh run watch IDENTIFIANT_REEL ; lire et approuver le plan de migrations.
```

**STOP** si le plan contient des opérations bloquantes ou à examiner sans décision documentée, si la restauration isolée échoue, si les médias ne sont pas conservés ou si le VPS ne dispose pas de l'installation/configuration attendue. Ne pas ajouter d'option de contournement des migrations pour « faire passer » le workflow.

## 3. Démarrage parallèle (sans changer le domaine)

Après réussite documentée de toutes les portes précédentes, déclencher :

```sh
gh workflow run deploy-injs-lmd.yml --ref main \
  -f mode=deployer -f tag_images="$SHA" -f confirmation=DEPLOYER
gh run list --workflow deploy-injs-lmd.yml --limit 10
# Avec l'identifiant RÉEL du déploiement :
gh run watch IDENTIFIANT_REEL
```

Le workflow protège les conteneurs historiques et démarre la nouvelle stack sur le port de validation (habituellement 8080, **à confirmer**). Pour contrôler ce port sans l'exposer publiquement, après vérification de l'empreinte hôte SSH :

```sh
ssh -o StrictHostKeyChecking=yes almalinux@152.228.233.123 \
  'curl -fsS --max-time 15 http://127.0.0.1:8080/api/health/ && printf "\n"; curl -sS -o /dev/null -w "Frontend HTTP %{http_code}\n" --max-time 15 http://127.0.0.1:8080/'
```

Faire ensuite la recette métier authentifiée, des QR **sur les terminaux réels**, des médias et les comptages de données avant/après. Aucune création de pointages factices en production. Un HTTP 200 seul n'est **pas** une recette.

## 4. Bascule manuelle Nginx Proxy Manager et retour arrière

**Seulement après la recette concluante** : dans Nginx Proxy Manager, relever et conserver l'ancien *proxy host* `injs.badge-qr-code.pro` (cible/port, TLS et options) ; pointer le même host sur la nouvelle passerelle **vérifiée** (hôte:port ou conteneur selon le réseau NPM). Ce dépôt ne connaît pas la configuration NPM effective et ne fournit pas de commande API inventée pour la modifier. Garder l'ancienne stack intacte.

Depuis le Mac, vérifier le site après la modification :

```sh
curl -fsS --max-time 20 https://injs.badge-qr-code.pro/api/health/
curl -sS --max-time 20 -o /dev/null -w 'Racine HTTP %{http_code}; TLS %{ssl_verify_result}\n' \
  https://injs.badge-qr-code.pro/
```

Comparer la version affichée et les parcours authentifiés à la recette parallèle, contrôler les journaux et les médias. **Si anomalie : repointer immédiatement NPM vers l'ancienne cible enregistrée.** Ce retour arrière du proxy ne restaure pas un schéma de base migré : suivre `RUNBOOK.md` pour arbitrer séparément toute migration incompatible. Ne jamais lancer `docker compose down -v`, `flush`, `dropdb` ni restaurer un dump sur la production pour un simple incident applicatif.
