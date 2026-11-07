# Rapport des validations — déploiement automatisé INJS-LMD

**Mission** : automatiser le déploiement VPS de GET-INJS (INJS Abidjan).
**Date des validations** : 7 novembre 2026.
**Branche** : `arena/4b0b3737-backend-injs2026` — pull request
[#6](https://github.com/JCKOUASSI/backend-injs2026/pull/6), base `main`.
**Commit de départ** : `767dabf0faf317c333d280248ebf93fe4ad66ea6`.

> **Aucun déploiement réel n'a été effectué.** Conformément à la mission, la
> phase de développement et de validation n'a touché ni le VPS, ni Docker Hub
> en écriture, ni le domaine public en modification. Le mode automatique
> livré est `preflight` (lecture seule) et le déploiement réel reste
> désarmé.

---

## 1. Environnement de validation

| Élément | Valeur |
|---|---|
| Système | Linux (sandbox Arena), bash 5.2.15 |
| Python | 3.11.2 en local ; 3.12 sur le runner GitHub Actions |
| PyYAML | 6.0.3 |
| yamllint | installé (environnement virtuel local ; `pip` direct sur le runner) |
| jq | 1.6 |
| Accès réseau | `github.com`, `api.github.com`, `pypi.org` uniquement |

Conséquence de cet accès réseau restreint : **Docker Hub
(`hub.docker.com`, `registry-1.docker.io`, `auth.docker.io`) et le VPS
n'étaient pas joignables depuis l'environnement de développement.** Les
appels au registre et la connexion SSH n'ont donc pas pu être exercés ; ils
sont listés en §5.

---

## 2. Validations exécutées et résultats

### 2.1 Contrôles statiques — `scripts/valider-deploiement-injs.sh`

Commande :

```bash
PYTHON=.venv-ci/bin/python ./scripts/valider-deploiement-injs.sh
```

**Résultat : 57 OK, 0 ÉCHEC, 0 IGNORE — code de retour 0.**

| Groupe | Contenu | Résultat |
|---|---|---|
| A. YAML et scripts embarqués | chargeabilité des 4 workflows, `yamllint` strict, `bash -n` sur les **21 blocs `run:`** et sur les **5 scripts distants embarqués** (heredocs), absence de tabulation | 11 OK |
| B. Déclenchement et dépendance | `workflow_run` pointé sur le **nom exact** de `publish-injs-lmd.yml`, `types: [completed]`, `workflow_dispatch`, garde `conclusion == 'success'`, garde `head_branch == 'main'`, cible issue de `head_sha`, `github.sha` jamais utilisé comme tag | 7 OK |
| C. Protection et sécurité | concurrence partagée sans annulation, permissions ⊆ {`contents: read`, `actions: read`}, **16 motifs destructifs** absents, `latest`/`stable` refusés, SSH strict + `known_hosts` par secret, environnement `production`, **3 actions épinglées par SHA 40 caractères**, **aucune expression GitHub dans un script** (anti-injection), `.env` exclu du transfert, `rsync` sans `--delete`, `SKIP_DB_SETUP`, compose sans `container_name` ni PostgreSQL, instantanés avant/après sanctionnés | 20 OK |
| D. Cohérence avec le dépôt | images identiques entre workflow de déploiement, workflow de publication et compose ; `PROJET_COMPOSE` = `name:` du compose ; `/api/health/` présent dans `backend/config/urls.py` ; `docker/nginx/default.conf` présent et arborescence de transfert correcte ; modes du workflow ⊆ modes de `deploy.sh` ; variables du compose documentées dans `.env.example` ; entrypoint vérifié = `backend/Dockerfile` ; `LABEL version` = `frontend/Dockerfile` ; worker/cron protégés et absents du compose ; secrets documentés dans le guide | 13 OK |
| E. Vérifications et rapport | archivage des preuves, récupération par le job de rapport, résumé publié, **31 annotations `::error::`**, tests HTTP services + domaine, état des conteneurs contrôlé, workflow de validation en lecture seule | 8 OK |

### 2.2 Tests fonctionnels — `scripts/tester-deploiement-injs.sh`

Commande :

```bash
PYTHON=.venv-ci/bin/python ./scripts/tester-deploiement-injs.sh
```

**Résultat : 85 tests passés, 0 échoué — code de retour 0.**

Ces tests n'imitent pas le workflow : ils **extraient les blocs `run:` et les
scripts distants du fichier YAML réel** et les exécutent dans un environnement
simulé (`GITHUB_OUTPUT`, `GITHUB_STEP_SUMMARY`, `RUNNER_TEMP` réels ;
`vps-ssh` simulé). Ils exécutent aussi `deploy/production/deploy.sh` pour de
vrai sur ses modes qui n'exigent ni Docker ni PostgreSQL.

| Groupe | Ce qui est réellement exécuté | Tests |
|---|---|---|
| T0 | fidélité de l'environnement de test au workflow (constantes comparées au fichier) | 3 |
| T1 | détermination du mode et de la cible : `workflow_dispatch` (4 scénarios dont 2 refus) et `workflow_run` (5 scénarios d'opt-in) | 9 |
| T2 | validation du tag : `latest`, `stable`, vide, SHA complet, `v1.2.3`, `1.2.3-rc1`, tag arbitraire, SHA tronqué | 9 |
| T3 | **comparaison des instantanés de protection** : identiques, apparition de la stack candidate, disparition de `injs-worker`, `injs-db` recréé en `postgres:16`, volume supprimé, réseau `injs-net` supprimé, retrait légitime du réseau candidat en `rollback`, activité tierce en `preflight`, preuve d'absence d'écriture | 9 |
| T4 | lecture du `.env` (fonction `lire()` du workflow **et** `lire_var_env()` de `deploy.sh`) : commentaires en ligne, guillemets, `#` intérieur, ligne commentée | 10 |
| T5 | filtre jq de sélection du digest `linux/amd64` sur un index OCI réel, un manifeste unique, un index sans amd64 | 4 |
| T6 | extraction des résultats depuis les fichiers de preuves (`awk`, regex d'état de santé, conteneur sans healthcheck) | 8 |
| T7 | génération de `rapport.md` : contenu, tableau markdown, **absence de toute valeur de secret applicatif** | 11 |
| T8 | **garde-fou de `deploy.sh`** : compose du dépôt franchi, puis refus sur `down -v`, `system prune -af`, `volume prune`, et sur un espacement multiple normalisé | 5 |
| T9 | **`deploy.sh deployer`** : refus de `latest`, `stable`, tag arbitraire, absence de tag ; acceptation du SHA puis exigence du `.env` serveur | 5 |
| T10 | **porte d'analyse des migrations de `deploy.sh`** sur 9 plans au format réel de Django : vide, aucune opération, sûres, à examiner (+ autorisation), bloquantes (+ autorisation), format inattendu, opération inconnue, opération irréversible, plan contradictoire, opération `Undo` | 12 |

### 2.3 Exécution réelle sur GitHub Actions

Le workflow `valider-chaine-deploiement.yml` a été déclenché par la pull
request #6 et a exécuté les deux scripts **sur un runner `ubuntu-latest`
réel** :

* Exécution : <https://github.com/JCKOUASSI/backend-injs2026/actions/runs/42414292292>
* Job « Contrôles statiques et tests fonctionnels » : **success** (14 s)
* Étapes en succès : `Installer PyYAML et yamllint`, `Contrôles statiques de
  la chaîne`, `Tests fonctionnels (sans VPS, sans Docker Hub, sans
  déploiement)`, `Synthèse`.

C'est la preuve que les deux scripts passent dans l'environnement cible, et
pas seulement dans le sandbox de développement.

### 2.4 `yamllint` en configuration stricte

```bash
yamllint -d '{extends: default, rules: {line-length: {max: 200}, truthy: {check-keys: false}, document-start: disable}}' .github/workflows/*.yml
```

**Aucune anomalie** sur les quatre workflows (`ci.yml`,
`deploy-injs-lmd.yml`, `publish-injs-lmd.yml`,
`valider-chaine-deploiement.yml`).

### 2.5 Vérification du format réel de `migrate --plan`

Le classement des migrations par `deploy.sh` dépend du format exact de sortie
de Django. Ce format a été vérifié **dans les sources**, et non supposé :
`Django==5.1.4` (version épinglée dans `backend/requirements.txt`) a été
téléchargé depuis PyPI et `django/core/management/commands/migrate.py`
inspecté :

```python
self.stdout.write("Planned operations:", self.style.MIGRATE_LABEL)
if not plan:
    self.stdout.write("  No planned migration operations.")
else:
    for migration, backwards in plan:
        self.stdout.write(str(migration), self.style.MIGRATE_HEADING)   # colonne 0
        for operation in migration.operations:
            ...
            self.stdout.write("    " + message, style)                  # 4 espaces
```

Conclusion : en-tête de migration **en colonne 0**, opérations **indentées de
4 espaces**, message « aucune opération » indenté de 2 espaces. C'est bien ce
que `deploy.sh` analyse, et les plans de test T10 sont construits sur ce
format. Les libellés d'opérations (`Create model`, `Add field`, `Delete
model`, `Rename field`, `Alter field`, `Raw Python operation`, `IRREVERSIBLE`,
préfixe `Undo`) proviennent de `describe_operation()` du même fichier.

### 2.6 Contrôle de la publication existante (API GitHub)

Vérification que la publication de référence existe bien, telle que décrite
dans la mission :

| Champ | Valeur lue par l'API |
|---|---|
| Exécution | [42407161982](https://github.com/JCKOUASSI/backend-injs2026/actions/runs/42407161982) |
| Workflow | Publication images INJS-LMD |
| Événement | `workflow_dispatch` |
| Branche de tête | `main` |
| SHA de tête | `767dabf0faf317c333d280248ebf93fe4ad66ea6` |
| Conclusion | `success` |
| Jobs | backend `success`, frontend `success`, résumé `success` |

Cette exécution satisfait **exactement** les trois conditions de la garde
d'entrée du déploiement automatique : une publication identique déclencherait
le mode `preflight` (et `deployer` si l'opt-in double est positionné).

---

## 3. Exigences de la mission → preuve de couverture

| # | Exigence | Comment elle est satisfaite | Preuve |
|---|---|---|---|
| 1 | Vérifier la réussite de la publication | Garde d'entrée `workflow_run` + re-contrôle par l'API GitHub (`actions/runs?head_sha=`) | §2.1 B4, §2.6 |
| 2 | Identifier tags **et digests** exacts | Résolution registre (en-tête `Docker-Content-Digest` + manifeste enfant `linux/amd64`) | T5.1–T5.3 |
| 3 | Connexion SSH sécurisée | Clé ED25519, `StrictHostKeyChecking=yes`, `BatchMode`, `IdentitiesOnly`, `known_hosts` par secret | §2.1 C5 |
| 4 | Récupérer les images depuis Docker Hub | `docker pull repo@sha256:…` puis `repo:tag`, avant tout transfert | §2.1 C4, T9 |
| 5 | Vérifier les images avant déploiement | Identité tag/digest par `.Id`, plateforme, entrypoint, ports exposés, `LABEL version`, contenu réel (`manage.py`, `staticfiles`, `index.html`, `nginx.conf`) | §2.1 D7 |
| 6 | Déployer selon la configuration Docker réelle | `deploy/production/compose.yml` et `deploy.sh` **inchangés** et seuls exécutés | §2.1 C10, D1–D6 |
| 7 | Vérifier l'état des conteneurs | `compose ps`, `.State.Status`, `.State.Health.Status`, `.RestartCount`, identifiants d'image | §2.1 E5, T6.6–T6.7 |
| 8 | Tests HTTP sur les services | `/api/health/`, `/`, `/admin/login/` sur le port de validation ; `/api/health/` et `/` sur le domaine (code, TLS, empreinte) | §2.1 E4, §2.1 D3 |
| 9 | Rapport de déploiement | Résumé d'exécution + artefact 90 jours + exemplaire déposé sur le VPS | T7.1–T7.4, §2.1 E1–E2 |
| 10 | Signaler clairement les échecs | 31 annotations `::error::`, job rouge, rapport final toujours produit | §2.1 E3 |
| — | Secrets GitHub, jamais affichés | 4 secrets SSH requis + 2 Docker Hub optionnels ; aucune valeur imprimée ; aucune expression GitHub dans un script ; jeton transmis par stdin | §2.1 C8, T7.4 |
| — | Permissions minimales | `contents: read`, `actions: read` | §2.1 C2 |
| — | Protection contre déploiements simultanés | `concurrency: deploiement-production-injs`, `cancel-in-progress: false` | §2.1 C1 |
| — | Jamais `down -v`, `prune`, `flush`, `dropdb` | 16 motifs absents du workflow + garde-fou `deploy.sh` testé en exécution réelle | §2.1 C3, T8.1–T8.5 |
| — | Jamais supprimer volumes / PostgreSQL | Instantanés avant/après sanctionnés | T3.3–T3.6 |
| — | Ne pas supprimer les anciens conteneurs avant validation | Conteneurs protégés comparés nom + image + date de création | T3.3, T3.4 |
| — | Préserver configurations et variables d'environnement | `.env` exclu du transfert, jamais écrasé, `deploy.sh` en fait une sauvegarde `.env.bak-*` | §2.1 C9, T4.8 |
| — | Retour arrière possible | Mode `rollback` (workflow + `deploy.sh`) + bascule NPM ; limites documentées | §2.1 D5, T9, guide §5 |
| — | Ne pas remplacer Worker/Cron sans vérification | Absents du compose ; état comparé avant/après | §2.1 D8, T3.3 |
| — | Migrations Django | `SKIP_DB_SETUP=true` + porte `migrate --plan` analysée et contre-vérifiée | §2.1 C10, T10.1–T10.12 |

---

## 4. Défauts détectés puis corrigés pendant la validation

Ces défauts ont été trouvés **par les tests**, ce qui montre qu'ils ne sont
pas décoratifs :

1. **`lire_var_env` (`deploy.sh`) ne retirait pas les commentaires en ligne.**
   `.env.example` contient `INJS_BACKEND_TAG=  # requis : ex. …`. Un
   `.env.bak-*` issu de ce modèle aurait fait échouer `valider_tag` et
   **bloqué un retour arrière**, alors que la valeur réellement restaurée est
   correcte. Corrigé, couvert par T4.8 et T4.9.
2. **Même défaut dans la fonction `lire()` du script distant de
   pré-contrôles** : port de validation illisible, secrets faussement
   signalés comme provisoires. Corrigé, couvert par T4.1–T4.7.
3. **Régression du domaine jamais détectable** : la comparaison avant/après
   lisait une variable posée dans un fichier de preuves au lieu de la sortie
   d'étape ; elle valait donc toujours `000`. Corrigé (passage par
   `steps.domaine-avant.outputs.code`).
4. **Tri des instantanés dépendant de la locale** : `comm` et `sort`
   pouvaient diverger et produire une comparaison fausse. Corrigé
   (`LC_ALL=C` des deux côtés).
5. **Interpolation d'entrées utilisateur dans les scripts** (présente dans la
   version antérieure du workflow : `if [ "${{ inputs.mode }}" = … ]`), vecteur
   d'injection de commandes. Corrigé : **aucune** expression GitHub
   n'apparaît plus dans un bloc `run:` ; tout passe par `env:`. Contrôlé en
   continu par le test C8.
6. **`rsync` non vérifié côté serveur** : son absence produisait un échec
   obscur. Ajout d'un contrôle explicite avec message actionnable.
7. **Harnais de test lui-même corrigé** (3 itérations) : verdict lu sur la
   sortie standard au lieu de `GITHUB_OUTPUT`, conteneurs de test ajoutés hors
   de la section `## conteneurs`, libellé de message attendu obsolète. Ces
   corrections portent sur le harnais, pas sur le workflow.

---

## 5. Ce qui n'a PAS été testé

Aucune de ces validations n'a été exécutée ; elles ne doivent pas être
considérées comme acquises.

| Non testé | Raison | Comment le valider ensuite |
|---|---|---|
| Connexion SSH réelle au VPS | Aucun accès au VPS depuis l'environnement de développement ; mission interdisant tout déploiement réel | Exécution manuelle en mode `preflight` après création des secrets |
| Commandes `docker` / `docker compose` sur le VPS | idem | idem (le mode `preflight` les exécute en lecture seule) |
| Appels au registre Docker Hub (jeton, en-tête `Docker-Content-Digest`, manifestes) | `hub.docker.com`, `auth.docker.io`, `registry-1.docker.io` hors liste d'accès | Mode `preflight` avec un SHA publié : la résolution des digests y est bloquante |
| Requête HTTP réelle vers `injs.badge-qr-code.pro` | Sortie réseau restreinte | Mode `preflight` (état du domaine avant/après) |
| Exécution complète de `deploy.sh deployer` (dump PostgreSQL, `migrate`, `compose up`) | Exige le VPS et la base de production | Mode `sauvegarde`, puis `plan`, puis `deployer` — dans cet ordre |
| Déclenchement `workflow_run` effectif | Un workflow `workflow_run` s'exécute dans la version de la **branche par défaut** : il n'est actif qu'après fusion sur `main` | Après fusion : relancer `publish-injs-lmd.yml` et observer l'exécution `preflight` déclenchée |
| Approbation de l'environnement `production` | Configuration côté GitHub, hors dépôt | Settings → Environments → production → Required reviewers |
| `actionlint` | Binaire téléchargeable uniquement depuis `release-assets.githubusercontent.com`, hôte non joignable | Compensé par `yamllint` strict + `bash -n` sur chaque bloc + exécution réelle des étapes sur runner |
| CI backend Django de la PR | Suite longue, encore en cours à la rédaction de ce rapport ; **aucun fichier backend n'est modifié par cette PR** | Vérification `ci.yml` sur la PR #6 |

**Limitation connue à signaler explicitement** : le nom du workflow enregistré
côté GitHub est encore « Déploiement VPS INJS-LMD (manuel) », car GitHub
enregistre les workflows depuis la branche par défaut. Il deviendra
« Déploiement VPS INJS-LMD » après fusion. Sans incidence fonctionnelle.

---

## 6. Reproduction des validations

```bash
# Environnement (sans toucher à l'interprète système)
python3 -m venv .venv-ci
.venv-ci/bin/pip install pyyaml yamllint

# Contrôles statiques (57 contrôles)
PYTHON=.venv-ci/bin/python ./scripts/valider-deploiement-injs.sh

# Tests fonctionnels (85 tests)
PYTHON=.venv-ci/bin/python ./scripts/tester-deploiement-injs.sh
```

Les deux scripts sont également exécutés automatiquement par
`.github/workflows/valider-chaine-deploiement.yml` sur toute pull request
modifiant la chaîne de déploiement (workflows, `deploy/production/**`,
`docker/**`, `Dockerfile`, `entrypoint.sh`, `backend/config/urls.py`).

Ils ne contactent ni le VPS, ni Docker Hub, ni aucun service externe : ils
sont sans risque et rejouables à tout moment.

---

## 7. Blocages et prérequis avant mise en service

Aucun blocage technique. Les prérequis sont **de configuration**, côté
GitHub et côté VPS :

1. **Secrets GitHub** à créer : `SSH_HOST`, `SSH_USER`, `SSH_PRIVATE_KEY`,
   `VPS_KNOWN_HOSTS` (+ `SSH_PORT` si ≠ 22). Procédure :
   [GUIDE-DEPLOIEMENT-AUTOMATIQUE.md §2](GUIDE-DEPLOIEMENT-AUTOMATIQUE.md).
   Sans eux, le job échoue immédiatement avec la liste exacte des secrets
   manquants, avant toute connexion.
2. **Environnement `production`** : configurer au moins un *Required
   reviewer* avant d'armer le mode `deployer`.
3. **`.env` serveur** présent sur le VPS dans
   `/opt/injs/injs-lmd/deploy/production/.env`, avec `POSTGRES_PASSWORD` et
   `DJANGO_SECRET_KEY` renseignés (valeurs non provisoires), `POSTGRES_HOST`
   joignable sur le réseau Docker, `INJS_NETWORK_NAME`/`INJS_NETWORK_EXTERNAL`
   alignés sur le réseau de `injs-db`. Procédure : RUNBOOK.md §4.
4. **Utilisateur SSH** membre du groupe `docker` (exécution de `docker` sans
   `sudo`) et `rsync` installé sur le VPS.
5. **Fusion sur `main`** pour activer le déclenchement automatique (§5).
6. **Première exécution recommandée** : mode `preflight` en manuel. Elle
   valide secrets, SSH, PostgreSQL, `.env`, espace disque, digests des images
   publiées et état du domaine — **sans rien écrire sur le VPS**.

Tant que les variables `INJS_DEPLOIEMENT_AUTO=deployer` et
`INJS_CONFIRMATION_AUTO=DEPLOYER` ne sont pas positionnées, une publication
réussie sur `main` ne déclenche qu'une vérification en lecture seule :
**la livraison est désarmée par défaut.**
