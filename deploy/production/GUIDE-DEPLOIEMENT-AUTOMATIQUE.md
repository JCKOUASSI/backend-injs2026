# Guide du déploiement automatisé INJS-LMD (GitHub Actions → VPS)

Ce guide complète le [RUNBOOK.md](RUNBOOK.md) (procédure serveur) et décrit la
chaîne automatisée mise en place par `.github/workflows/deploy-injs-lmd.yml`.

Périmètre : **INJS Abidjan uniquement** — images `jckouassi/injs-be` et
`jckouassi/injs-fe`, VPS AlmaLinux, domaine <https://injs.badge-qr-code.pro>.

---

## 1. Architecture retenue

```
GitHub (branche main)
   │
   ├─ .github/workflows/publish-injs-lmd.yml      ← INCHANGÉ par cette mission
   │     construit et publie sur Docker Hub :
   │       jckouassi/injs-be:<SHA Git complet>  + :stable
   │       jckouassi/injs-fe:<SHA Git complet>  + :stable
   │
   └─ .github/workflows/deploy-injs-lmd.yml       ← CE WORKFLOW
         │  déclenché par workflow_run (fin de la publication) ou à la main
         │
         ├─ job « résolution »   (aucun accès au VPS)
         │     1. garde d'entrée : publication = le bon workflow,
         │        conclusion `success`, branche de tête `main`
         │     2. cible = workflow_run.head_sha (le commit réellement publié)
         │     3. re-contrôle de la réussite de publication par l'API GitHub
         │     4. validation du tag (immuable ; `latest`/`stable` refusés)
         │     5. résolution des DIGESTS exacts sur le registre Docker Hub
         │        (API v2 : manifeste du tag + manifeste linux/amd64)
         │
         ├─ job « VPS »          (environnement GitHub `production`)
         │     6. secrets SSH vérifiés, clé + known_hosts installés
         │     7. connexion SSH (StrictHostKeyChecking=yes, BatchMode)
         │     8. pré-contrôles du VPS en LECTURE SEULE : système, espace
         │        disque, PostgreSQL `injs-db`, `.env` serveur (valeurs
         │        sensibles masquées), conteneurs historiques
         │     9. état du domaine public AVANT intervention
         │    10. instantané de protection AVANT (conteneurs + volumes + réseaux)
         │    11. tirage des images PAR DIGEST puis par tag, comparaison des
         │        identifiants : l'image déployée = l'image publiée
         │        (plateforme linux/amd64, entrypoint, contenu, LABEL version)
         │    12. transfert de deploy/production et docker/ (SANS le .env)
         │    13. exécution de deploy/production/deploy.sh <mode>
         │        (sauvegarde vérifiée, plan de migrations analysé, up)
         │    14. contrôles post-exécution : compose ps, santé des conteneurs,
         │        tests HTTP sur le port de validation
         │    15. instantané APRÈS + comparaison bloquante (protection)
         │    16. tests HTTP du domaine public + détection de régression
         │    17. rédaction du rapport, récupération des journaux du VPS
         │
         └─ job « rapport final » (toujours exécuté)
               18. consolidation, résumé lisible, annotations d'échec
```

**Indépendance** : ce workflow ne construit aucune image et ne modifie pas
`publish-injs-lmd.yml`. Il ne fait que déployer ce qui a été publié.

**Ce qui reste manuel, volontairement** : la bascule du domaine dans Nginx
Proxy Manager (RUNBOOK.md §7). La nouvelle stack est exposée sur un port de
validation ; l'ancienne stack continue de servir le public tant que la
bascule n'a pas été faite et vérifiée par un humain.

---

## 2. Secrets et variables GitHub à configurer

Emplacement : dépôt GitHub → **Settings → Secrets and variables → Actions**.

### 2.1 Secrets (onglet *Secrets*)

| Secret | Requis | Contenu | Comment l'obtenir |
|---|---|---|---|
| `SSH_HOST` | **oui** | Hôte du VPS (IP ou nom) | Adresse du serveur de production |
| `SSH_USER` | **oui** | Utilisateur SSH de déploiement | `almalinux` (utilisateur du RUNBOOK) — doit pouvoir exécuter `docker` |
| `SSH_PRIVATE_KEY` | **oui** | Clé privée **ED25519**, PEM complet, **sans phrase de passe** | Voir §2.2 |
| `VPS_KNOWN_HOSTS` | **oui** | Lignes `known_hosts` du VPS (empreintes vérifiées) | Voir §2.3 |
| `SSH_PORT` | non | Port SSH si différent de 22 | Laisser vide ⇒ port 22 |
| `DOCKERHUB_USERNAME` | non ici | Compte Docker Hub (`jckouassi`) | Déjà requis par la publication |
| `DOCKERHUB_TOKEN` | non ici | Jeton d'accès Docker Hub | Déjà requis par la publication |

`DOCKERHUB_USERNAME` / `DOCKERHUB_TOKEN` servent dans ce workflow à deux
choses **facultatives** : résoudre les digests d'un dépôt privé, et authentifier
le VPS si les images sont privées (tirage refusé en anonyme). Si les images
sont publiques, ces secrets ne sont pas nécessaires au déploiement — mais ils
existent déjà pour la publication. Le jeton est transmis au VPS **uniquement
par stdin**, jamais en argument de commande (il serait visible dans la table
des processus du serveur), et jamais affiché dans les journaux.

> Aucun secret applicatif (mot de passe PostgreSQL, `DJANGO_SECRET_KEY`) ne
> transite par GitHub Actions. Ils vivent exclusivement dans
> `/opt/injs/injs-lmd/deploy/production/.env` **sur le VPS**, créé une seule
> fois depuis `.env.example` (RUNBOOK.md §4). Ce fichier n'est jamais
> transféré, jamais écrasé, jamais lu valeur par valeur dans les journaux.

### 2.2 Générer la clé SSH de déploiement

À faire depuis un poste d'administration, **pas** depuis le VPS :

```bash
ssh-keygen -t ed25519 -C "github-actions-injs-lmd" -f injs_deploy_ed25519 -N ""
# → injs_deploy_ed25519 (privée) et injs_deploy_ed25519.pub (publique)

# Installer la clé PUBLIQUE sur le VPS, pour l'utilisateur de déploiement :
ssh almalinux@<HÔTE> 'umask 077; mkdir -p ~/.ssh; cat >> ~/.ssh/authorized_keys' \
    < injs_deploy_ed25519.pub

# Vérifier l'accès, puis détruire la copie locale de la clé privée :
ssh -i injs_deploy_ed25519 almalinux@<HÔTE> 'docker ps --format "{{.Names}}"'
```

Coller le **contenu intégral** de `injs_deploy_ed25519` (y compris les lignes
`-----BEGIN/END OPENSSH PRIVATE KEY-----`) dans le secret `SSH_PRIVATE_KEY`.
Cette clé ne doit servir qu'à ce workflow : ne pas la réutiliser ailleurs, et
la retirer de `authorized_keys` si elle est compromise.

L'utilisateur de déploiement doit pouvoir exécuter `docker` sans `sudo`
(groupe `docker` sur AlmaLinux) : `sudo usermod -aG docker almalinux`.

### 2.3 Générer `VPS_KNOWN_HOSTS` (empreinte vérifiée)

```bash
ssh-keyscan -p 22 -t ed25519,ecdsa,rsa <HÔTE> > vps_known_hosts
ssh-keygen -lf vps-known_hosts          # afficher les empreintes
```

Comparer l'empreinte ED25519 obtenue à celle publiée par l'hébergeur du VPS
(console d'administration). **Ne coller le contenu dans le secret qu'après
cette comparaison.** Le workflow utilise `StrictHostKeyChecking=yes` : toute
empreinte différente interrompt la connexion, ce qui protège d'une
interposition. Les secrets GitHub acceptent le multi-lignes : coller le
fichier entier.

### 2.4 Variables de dépôt (onglet *Variables*)

| Variable | Valeur | Effet |
|---|---|---|
| `INJS_DEPLOIEMENT_AUTO` | `deployer` | Arme le déploiement réel en mode automatique |
| `INJS_CONFIRMATION_AUTO` | `DEPLOYER` | Seconde confirmation, obligatoire avec la précédente |

**Par défaut (variables absentes) : le déclenchement automatique exécute le
mode `preflight`, intégralement en lecture seule.** Rien n'est écrit sur le
VPS, aucun conteneur n'est touché : le workflow vérifie la publication, les
digests, l'état du serveur, l'état du domaine et produit un rapport.

Le déploiement automatique réel exige les **deux** variables (double opt-in
auditable). Toute autre valeur de `INJS_DEPLOIEMENT_AUTO` ramène au mode
`preflight`.

### 2.5 Environnement GitHub `production` (approbation humaine)

Le job « VPS » est rattaché à l'environnement `production`. Pour imposer une
validation humaine avant **toute** exécution (manuelle comme automatique) :

**Settings → Environments → production → Required reviewers** : ajouter au
moins un relecteur. Optionnel mais recommandé :
*Deployment branches* = `main`, et un *Wait timer* de quelques minutes.

Tant qu'aucun relecteur n'est exigé, le déclenchement suffit à exécuter le
job : **configurer au moins un relecteur avant d'armer le mode `deployer`**.

---

## 3. Procédure d'exécution manuelle

Onglet **Actions** → workflow **« Déploiement VPS INJS-LMD »** →
**Run workflow** → choisir la branche `main` → renseigner les entrées.

| Entrée | Valeurs | Rôle |
|---|---|---|
| `mode` | `preflight` (défaut), `inventaire`, `sauvegarde`, `plan`, `deployer`, `rollback` | Opération exécutée sur le VPS |
| `tag_images` | SHA Git complet publié | Tag immuable à déployer. Vide ⇒ déduit de la dernière publication réussie sur main (uniquement `preflight`/`plan`, **jamais** `deployer`) |
| `confirmation` | `DEPLOYER` | Obligatoire pour `deployer` |
| `autoriser_examen_migrations` | booléen | Lève le blocage des migrations « à examiner » (altérations, index, migrations de données) **après lecture du plan** |
| `autoriser_migrations_destructives` | booléen | Lève le blocage des migrations **bloquantes** (suppression/renommage) : rend l'ancienne application incompatible — à n'utiliser qu'en connaissance de cause |

### 3.1 Séquence recommandée pour une première mise en service

1. **`preflight`** (tag vide) — lecture seule : vérifie les secrets, la
   connexion SSH, PostgreSQL, le `.env` serveur, l'espace disque, les digests
   des images publiées, l'état du domaine. Aucune écriture sur le VPS.
2. **`inventaire`** — état des lieux détaillé du VPS (conteneurs, volumes,
   réseaux, disque, mémoire).
3. **`sauvegarde`** — dump PostgreSQL horodaté, vérifié (`pg_restore --list`
   dont tout échec est fatal) et contrôlé par SHA-256 entre source et copie,
   plus les comptages de référence.
4. **`plan`** — `migrate --plan` analysé et contre-vérifié par
   `showmigrations --plan`. **Lire le rapport** : opérations sûres, à
   examiner, bloquantes.
5. **`deployer`** avec `tag_images` = SHA publié et `confirmation` =
   `DEPLOYER` — sauvegarde → plan → migrations validées → démarrage sur le
   port de validation → contrôles de santé, HTTP et comptages.
6. **Recette humaine** sur `http://<HÔTE>:<port de validation>` (RUNBOOK §6),
   puis **bascule manuelle** Nginx Proxy Manager (RUNBOOK §7).

Le `tag_images` doit être le SHA Git complet publié par le workflow de
publication ; il est affiché dans le résumé de l'exécution de publication et
peut être retrouvé avec :

```bash
gh run list --workflow publish-injs-lmd.yml --limit 5 --json headSha,conclusion,displayTitle
```

### 3.2 Ce que fait chaque mode

| Mode | Écrit sur le VPS ? | Action |
|---|---|---|
| `preflight` | **non** | Vérifications complètes en lecture seule + rapport |
| `inventaire` | **non** | État des lieux Docker/système |
| `sauvegarde` | oui (dump + journaux) | Dump PostgreSQL vérifié, comptages de référence |
| `plan` | oui (tirage d'images + journaux) | Plan de migrations analysé, aucune application |
| `deployer` | oui | Chaîne complète RUNBOOK §2 → §6, sur le port de validation |
| `rollback` | oui | Retour à la configuration précédente (voir §4) |

Aucun mode ne supprime PostgreSQL, un volume, un réseau, ni un conteneur
historique (`injs-be`, `injs-fe`, `injs-worker`, `injs-cron`, Redis,
RabbitMQ, Nginx Proxy Manager).

---

## 4. Déploiement automatique (après publication)

### 4.1 Conditions — toutes doivent être réunies

1. Le workflow **« Publication images INJS-LMD »** s'est terminé ;
2. sa conclusion est **`success`** ;
3. sa branche de tête est **`main`** ;
4. son `head_sha` permet de résoudre les deux images sur Docker Hub.

Sinon le job de résolution est **ignoré** (`skipped`) et le rapport final
l'explique : aucune intervention n'a lieu. Une publication déclenchée par un
tag Git `deploy-*` (branche de tête ≠ `main`) n'entraîne donc **pas** de
déploiement automatique — elle reste déployable à la main avec son SHA.

### 4.2 Limite GitHub à connaître (importante)

Un workflow déclenché par `workflow_run` s'exécute toujours dans la version
présente sur la **branche par défaut**. Conséquences :

* le déclenchement automatique n'est actif **qu'après fusion de
  `deploy-injs-lmd.yml` sur `main`** ; tant que le fichier n'existe que sur
  une branche de travail, seule l'exécution manuelle est possible ;
* une modification du workflow de déploiement sur `main` prend effet
  immédiatement pour les publications suivantes ;
* si la publication est déclenchée depuis une *pull request* d'un fork, GitHub
  ne transmet pas les secrets au workflow `workflow_run`. La publication
  INJS-LMD n'est pas déclenchée par pull request : ce cas ne se présente pas.

### 4.3 Comportement par défaut

Automatique non armé ⇒ **mode `preflight`** : le workflow vérifie tout et ne
modifie rien. C'est l'état livré par cette mission. Pour passer au
déploiement réel automatique : configurer les deux variables du §2.4 **et** un
relecteur obligatoire (§2.5), puis relancer une publication.

---

## 5. Procédure de retour arrière

Deux niveaux, à distinguer absolument.

### 5.1 Niveau 1 — le domaine (immédiat, sans perte de données)

La bascule étant manuelle, tant qu'elle n'a pas été faite le domaine sert
toujours l'ancienne stack : **il n'y a rien à annuler**. Si la bascule a été
faite et qu'un problème apparaît :

1. Nginx Proxy Manager → proxy host `injs.badge-qr-code.pro` → repointer vers
   la cible **relevée avant la bascule** (RUNBOOK §7.1).
2. Vérifier <https://injs.badge-qr-code.pro> (page de connexion, API).
3. Conserver la nouvelle stack démarrée pour analyse : aucune donnée n'a été
   touchée par ce retour.

### 5.2 Niveau 2 — la stack candidate : `rollback`

Workflow → **Run workflow** → `mode` = **`rollback`** (aucun tag requis), ou
sur le VPS :

```bash
cd /opt/injs/injs-lmd/deploy/production && ./deploy.sh rollback
```

Ce que fait `rollback`, dans cet ordre :

1. retrouve le dernier `.env.bak-*` (créé au début du déploiement concerné) ;
2. **valide intégralement** cette configuration avant tout arrêt : tags
   immuables, `POSTGRES_DB`/`POSTGRES_USER`, secrets non provisoires, port
   numérique, fichier compose présent ;
3. arrête la stack candidate (jamais de suppression de volumes) ;
4. sauvegarde l'état courant (`.env.avant-rollback-*`) puis restaure la
   configuration précédente ;
5. retire les images de la version restaurée et relance les services ;
6. **vérifie la disponibilité HTTP** de la version restaurée ; échoue
   explicitement si elle ne répond pas.

Le workflow ajoute, autour de cet appel : instantanés avant/après avec
sanction en cas de modification d'un conteneur protégé, d'un volume ou d'un
réseau ; tests HTTP du port de validation ; test du domaine public avec
détection de régression (un domaine qui répondait 200 avant et ne répond plus
après fait échouer l'exécution) ; rapport archivé.

### 5.3 Limites fondamentales du retour arrière

* `rollback` est **applicatif et de configuration** : il ne restaure ni un
  schéma PostgreSQL déjà migré, ni des données transformées par la nouvelle
  version, ni les médias.
* Si des migrations appliquées ont rendu l'ancienne application incompatible
  (renommage/suppression de colonne, migration de données), revenir en
  arrière exige une **décision humaine distincte** : migration inverse écrite
  et testée, ou restauration de sauvegarde explicitement autorisée. C'est
  précisément pourquoi la porte d'analyse du plan bloque suppressions et
  renommages (RUNBOOK §5).
* La restauration du dump PostgreSQL est une procédure **distincte, jamais
  automatique** : uniquement en cas de corruption ou de perte de données
  constatée et documentée, jamais pour un bug applicatif (RUNBOOK §8.3).
* Worker et Cron historiques ne sont jamais remplacés par cette chaîne : ils
  ne sont pas définis dans `deploy/production/compose.yml`, et leur état est
  comparé avant/après. Toute modification constatée bloque le déploiement.

---

## 6. Contrôles effectués par le workflow

| Exigence | Où |
|---|---|
| Publication terminée avec succès | Garde d'entrée du job de résolution + re-contrôle par l'API GitHub |
| Tags et digests exacts | Résolution registre (manifeste du tag + manifeste `linux/amd64`), jamais `latest` |
| Connexion SSH sécurisée | Clé ED25519, `StrictHostKeyChecking=yes`, `BatchMode`, `known_hosts` par secret |
| Récupération des images | Tirage **par digest** sur le VPS avant toute intervention |
| Vérification des images | Identité tag/digest, plateforme `linux/amd64`, entrypoint, ports exposés, `LABEL version`, contenu réel (`manage.py`, `staticfiles`, `index.html`, `nginx.conf`) |
| Déploiement conforme à la configuration réelle | `deploy/production/compose.yml` + `deploy/production/deploy.sh` inchangés, `.env` du serveur préservé |
| État des conteneurs | `compose ps`, `.State.Status`, `.State.Health.Status`, `.RestartCount`, identifiants d'image |
| Tests HTTP | `/api/health/`, `/`, `/admin/login/` sur le port de validation ; `/api/health/` et `/` sur le domaine public (avec TLS) |
| Rapport de déploiement | Résumé de l'exécution, artefact de preuves (90 jours), exemplaire déposé sur le VPS |
| Échecs signalés | Annotations `::error::` / `::warning::` / `::notice::`, job rouge, rapport final toujours produit |
| Permissions minimales | `contents: read`, `actions: read` — rien d'autre |
| Déploiements simultanés | `concurrency: deploiement-production-injs`, `cancel-in-progress: false` |
| Secrets jamais affichés | Aucune valeur sensible imprimée ; aucune expression GitHub interpolée dans un script (tout passe par `env:`) ; jeton Docker Hub transmis par stdin |

### 6.1 Contrôles normalisés du préflight (PASS / WARN / FAIL)

Depuis le mode `preflight`, chaque contrôle produit une ligne normalisée
`CONTROLE|id|STATUT|OBLIGATOIRE|RESULTAT|OBSERVATION` et le rapport présente
le tableau **Contrôle / Statut / Obligatoire / Résultat / Observation** suivi
d'un bilan chiffré. La logique de verdict est centralisée dans
`deploy/production/normaliser-controles.sh` (source unique, testée) :

| Situation | Verdict | Workflow |
|---|---|---|
| Aucun `FAIL`, aucun `NON_EXECUTE`, aucun `WARN` | **PRÉFLIGHT VALIDÉ** | vert |
| Aucun `FAIL`, aucun `NON_EXECUTE`, mais au moins un `WARN` | **PRÉFLIGHT VALIDÉ AVEC RÉSERVES** | vert + `::warning::` |
| Au moins un contrôle obligatoire en `FAIL` | **PRÉFLIGHT REFUSÉ** | rouge + `::error::` |
| Au moins un contrôle obligatoire en `NON_EXECUTE` | **PRÉFLIGHT REFUSÉ** | rouge + `::error::` |

**Un contrôle non exécuté n'est jamais converti en `PASS`** : un statut
inconnu, une ligne mal formée ou un fichier de contrôles absent produisent un
`NON_EXECUTE` et donc un refus (analyse à échec fermé).

### 6.2 Contrôle des sauvegardes — seuils explicites

Répertoire contrôlé : `/opt/injs/backups` (même chemin que `BACKUP_DIR` de
`deploy.sh`, constante `DOSSIER_BACKUPS` du workflow).

| Paramètre | Valeur | Signification |
|---|---|---|
| `SEUIL_DUMP_RECENT_JOURS` | **7** | en deçà : sauvegarde considérée fraîche → `PASS` |
| `SEUIL_DUMP_ANCIEN_JOURS` | **30** | au-delà : sauvegarde `WARN` (ancienne), à rafraîchir |
| `TAILLE_MIN_DUMP_OCTETS` | **1 048 576** (1 Mio) | plancher de vraisemblance d'un dump |

**Méthode d'identification** : un dump PostgreSQL au format custom commence
par la signature binaire `PGDMP`, lue avec `head -c 5`. C'est une **lecture**
— il n'y a **ni `pg_restore`, ni restauration, même à blanc**.

| Constat | Statut |
|---|---|
| Répertoire absent | `FAIL` (obligatoire) |
| Répertoire illisible | `FAIL` (obligatoire) |
| Aucun dump | `FAIL` (obligatoire) |
| Dump `PGDMP` récent et au-dessus du plancher | `PASS` — présence et signature seulement |
| Dump ancien (> 7 j) | `WARN` |
| Signature incorrecte ou taille sous le plancher | `WARN` (archive non vérifiable) |
| Aucune sauvegarde fraîche mais des dumps valides anciens | `FAIL` de disponibilité |

> **Limite assumée et affichée dans le rapport** : la signature `PGDMP` et la
> taille ne démontrent **ni l'intégrité complète ni la restaurabilité** du
> dump. La vérification forte (`pg_restore --list`, empreinte SHA-256
> bout-en-bout) n'est faite que par `deploy.sh sauvegarde`, au moment de
> produire une sauvegarde — jamais sur une sauvegarde existante, car cela
> exigerait d'ouvrir une base ou un outil de restauration.

Le contrôle est **strictement en lecture seule** : il n'utilise que `test`,
`stat`, `head`, `date` et écrit uniquement sur la sortie standard du runner.
Aucun fichier n'est créé, déplacé, renommé ou modifié ; aucune permission
n'est changée ; PostgreSQL et les conteneurs ne sont pas sollicités.

---

## 7. Dépannage

| Symptôme | Cause probable | Action |
|---|---|---|
| `Secrets GitHub absents ou vides : …` | Secrets du §2.1 non créés | Les créer, relancer |
| `Permission denied (publickey)` | Clé non autorisée, mauvais utilisateur, mauvais port | Vérifier `authorized_keys`, `SSH_USER`, `SSH_PORT` |
| `Host key verification failed` | `VPS_KNOWN_HOSTS` incomplet ou empreinte changée | Régénérer (§2.3) **après** vérification auprès de l'hébergeur |
| `Aucune exécution de « Publication images INJS-LMD » pour le commit …` | Tag non publié | Relancer la publication, puis le déploiement avec le bon SHA |
| `Image introuvable sur le registre` | Tag erroné, ou dépôt privé sans identifiants | Vérifier le SHA ; renseigner `DOCKERHUB_USERNAME`/`DOCKERHUB_TOKEN` |
| `.env absent sur le VPS` | Première installation non faite | RUNBOOK §4 : créer le `.env` **sur le VPS** depuis `.env.example` |
| `Secret applicatif … encore à sa valeur d'exemple` | `.env` serveur non renseigné | Renseigner `POSTGRES_PASSWORD` et `DJANGO_SECRET_KEY` sur le VPS |
| `PostgreSQL (injs-db) ne répond pas` | Base arrêtée | `docker ps`, `docker logs injs-db` ; ne rien relancer avant diagnostic |
| `Opérations à examiner présentes` | Plan de migrations non trivial | Lire le plan dans l'artefact, puis relancer avec `autoriser_examen_migrations` |
| `Migrations bloquantes refusées` | Suppression/renommage de modèle ou de champ | **Stop** : décision humaine (RUNBOOK §5). L'ancienne application partage la même base |
| `VOLUME SUPPRIMÉ` / `CONTENEUR PROTÉGÉ SUPPRIMÉ` | Intervention tierce sur le VPS pendant le déploiement | Ne pas basculer le proxy ; analyser les instantanés archivés |
| `RÉGRESSION du domaine public` | Le domaine ne répond plus après intervention | Bascule interdite ; vérifier NPM et l'ancienne stack |

Les preuves complètes (pré-contrôles, instantanés avant/après, vérification
des images, contrôles HTTP, journaux `deploy.sh`) sont archivées dans
l'artefact `deploiement-<mode>-<tag>-<run_id>` de l'exécution.

---

## 8. Validation locale de la chaîne

Aucun déploiement n'est nécessaire pour valider la chaîne :

```bash
python3 -m venv .venv-ci && .venv-ci/bin/pip install pyyaml yamllint
PYTHON=.venv-ci/bin/python ./scripts/valider-deploiement-injs.sh
```

Le script contrôle la syntaxe YAML, la syntaxe bash de **chaque** bloc `run:`
et de **chaque** script distant embarqué, le chaînage entre les deux
workflows, les permissions, l'absence de toute commande destructive, le refus
de `latest`/`stable`, la configuration SSH, l'épinglage des actions par SHA,
l'anti-injection (aucune expression GitHub dans un script) et la cohérence
avec les fichiers réels du dépôt (compose, Dockerfile, `.env.example`,
`urls.py`, `deploy.sh`). Il n'écrit rien et ne contacte aucun serveur.

Voir aussi [RAPPORT-VALIDATION-DEPLOIEMENT-AUTOMATIQUE.md](RAPPORT-VALIDATION-DEPLOIEMENT-AUTOMATIQUE.md)
pour le relevé des validations effectivement exécutées.

---

## 9. Limites connues et assumées

* **Analyse statique du garde-fou** : comme dans `deploy.sh`, la détection de
  commandes destructrices est textuelle. Elle ne détecterait pas une commande
  assemblée dynamiquement. C'est une défense en profondeur, pas une garantie
  absolue (RUNBOOK §10).
* **Comparaison des comptages** : une hausse reflète l'activité de l'ancienne
  application encore en service, une baisse bloque. Une suppression et une
  insertion simultanées peuvent se compenser et rester invisibles : la preuve
  d'intégrité demeure le dump vérifié par SHA-256 (RUNBOOK §3).
* **Bascule du domaine manuelle** : le workflow constate si le domaine sert
  déjà la nouvelle version (comparaison d'empreinte de la page d'accueil), il
  ne modifie jamais Nginx Proxy Manager.
* **`workflow_run` et branche par défaut** : voir §4.2.
* **Images privées** : si les dépôts Docker Hub sont privés, un `docker login`
  est effectué sur le VPS (jeton par stdin) et les identifiants sont alors
  stockés dans la configuration Docker de l'utilisateur de déploiement. Si les
  images sont publiques, aucune authentification n'est faite sur le VPS.
