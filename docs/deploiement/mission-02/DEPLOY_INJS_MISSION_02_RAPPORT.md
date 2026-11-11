# MISSION 02 — LEVÉE DES BLOCAGES PRÉ-DÉPLOIEMENT

**Projet** : INJS Abidjan — `JCKOUASSI/backend-injs2026`
**Date** : 6 novembre 2026 · **Cible** : VPS AlmaLinux · **Domaine** : `injs.badge-qr-code.pro`

---

## 0. CADRE ET CONTRAINTES

### 0.1 Branche

La mission demandait une branche dédiée `deploy-injs-2026/mission-02`.
**L'environnement de travail impose une branche unique par session** : il n'est
possible ni de créer ni de pousser une autre branche. Tout le travail a donc été
réalisé sur la branche de livraison **`arena/4524a57c-backend-injs2026`**, qui
est la branche suivie par la session et par la PR #5. Aucune autre branche n'a
été créée, renommée ou supprimée.

### 0.2 Point de restauration

| Élément | Valeur |
|---|---|
| Commit de référence avant mission | `08e2f4e` |
| Tag local de restauration | `mission-02-point-restauration` |
| Commande de retour arrière | `git reset --hard mission-02-point-restauration` |

Aucune modification préexistante de l'utilisateur n'a été écrasée : le dépôt
était propre (`git status` vide) au démarrage, et tous les apports de la mission
sont des commits distincts et réversibles.

### 0.3 Interdictions respectées

| Interdiction | Respect |
|---|---|
| Publier les images Docker | ✅ aucun workflow de publication exécuté, aucun tag `deploy-*` créé |
| Déployer sur le VPS | ✅ aucune connexion au serveur |
| Modifier PostgreSQL en production / exécuter des migrations en production | ✅ la base `injs_lmd_prod_20261026` n'a jamais été contactée |
| Basculer Nginx Proxy Manager | ✅ configuration candidate livrée, **non appliquée** |
| Modifier les comptes RBAC / exécuter `rbac_initialisation --apply` | ✅ jamais |
| Modifier les 81 rôles et les 1 157 permissions | ✅ aucun fichier du référentiel touché |
| Force push / suppression de branche ou de tag | ✅ aucun |
| Écraser une configuration sans sauvegarde | ✅ toutes les versions restent dans l'historique Git |
| Réintroduire SYGEP/CPFAE ou `dossier_trvx` | ✅ aucun |
| Modifier les règles métier LMD | ✅ aucun fichier métier modifié (B5 a été corrigé **dans le test**) |

---

## 1. B2 — SÉCURISATION DU DÉMARRAGE DJANGO

### 1.1 Mécanisme identifié

La chaîne qui déclenchait `manage.py migrate` :

```
deploy/production/compose.yml  (service backend)
   └── aucun `env_file`, SKIP_DB_SETUP absent du bloc `environment:`
          └── la variable n'atteint jamais le conteneur
                 └── backend/entrypoint.sh : `if [ "${SKIP_DB_SETUP:-}" = "true" ]`
                        └── faux → attend PostgreSQL, `migrate`, `collectstatic`, superuser
```

Le modèle `deploy/production/.env.example` documentait pourtant
`SKIP_DB_SETUP=true` : la variable était **documentée mais non transmise**, donc
sans effet. Le démarrage en production aurait appliqué les migrations
implicitement.

### 1.2 Corrections

| Fichier | Apport |
|---|---|
| `backend/config/demarrage.py` *(créé)* | Fonction pure `analyser_environnement()` + `main()` : **sans dépendance Django**, testable sans base |
| `backend/entrypoint.sh` *(modifié)* | Délègue la décision au module (`python3 -m config.demarrage`) et gère les trois codes de sortie ; message explicite si démarrage en root sans `gosu` |
| `deploy/production/compose.yml` *(modifié)* | **Transmission effective** : `SKIP_DB_SETUP: "${SKIP_DB_SETUP:-true}"`, plus `REDIS_URL`, `BADGE_BASE_URL`, `PUBLIC_APP_URL` |
| `backend/compose.yml` *(modifié)* | Pile de développement : `SKIP_DB_SETUP=false` **explicite** (comportement antérieur préservé) |

### 1.3 Comportement obtenu

| Situation | Décision | Code |
|---|---|---|
| `SKIP_DB_SETUP=true` | aucune migration, aucune écriture | 0 |
| **variable absente** | **défaut sûr** : aucune migration, avertissement explicite | 0 |
| valeur **invalide** | **arrêt du conteneur**, aucune action implicite | 2 |
| `SKIP_DB_SETUP=false` | migrations + collectstatic **explicites** | 10 |

Les migrations restent exécutables séparément et sous contrôle :
`docker compose -f deploy/production/compose.yml exec backend python manage.py migrate --noinput`.

### 1.4 Preuve de transmission (exigence de la mission)

La transmission n'est pas seulement documentée, elle est **vérifiée par les
tests** de deux manières indépendantes :

1. **Analyse du YAML du compose** : le test lit `deploy/production/compose.yml`,
   résout la substitution `${SKIP_DB_SETUP:-true}` et vérifie que la clé figure
   bien dans `environment:` du service `backend`.
2. **Exécution en sous-processus** : le test exécute la commande réellement
   appelée par l'entrypoint (`python3 -m config.demarrage`) avec l'environnement
   que le conteneur recevrait, et contrôle le code de sortie.

`manage.py test config.tests.test_demarrage` → **23 tests, OK**.

---

## 2. B3 — RÉCONCILIATION DES WORKFLOWS

| Workflow | Avant | Après |
|---|---|---|
| `ci.yml` | identique à `main` | réconcilié + **déclenchement corrigé** (voir §3) |
| `publish-injs-lmd.yml` | **absent** | ✅ repris depuis `origin/main` |
| `deploy-injs-lmd.yml` | **absent** | ✅ repris depuis `origin/main` |

Vérification préalable : `git diff origin/main -- .github/workflows/ci.yml`
était **vide** → le rapport des deux workflows n'écrase aucune modification
récente de la branche.

**Garde-fou de publication** : `publish-injs-lmd.yml` ne peut plus se déclencher
par mégarde — les jobs de construction exigent
`inputs.confirmation == 'PUBLIER-IMAGES'` en déclenchement manuel, et le
déclenchement automatique reste limité aux tags `deploy-*`.
**Aucun workflow de publication n'a été exécuté pendant cette mission.**

---

## 3. B4 — VALIDATION CI

### 3.1 Cause racine de l'absence d'exécution

`ci.yml` ne se déclenchait que sur `push: branches: [main]` et `pull_request`.
Un push sur la branche de livraison **ne déclenchait donc jamais rien**, et la
PR #5 étant en conflit avec `main`, aucun contrôle n'était remonté. La branche
de livraison n'était validée **nulle part**.

**Correction** (commit `cd293ab`) : ajout du motif `'arena/**'` aux branches de
push, sans retirer `pull_request` ni `workflow_dispatch`.

### 3.2 Exécutions réelles obtenues

| Run | Déclenchement | Résultat |
|---|---|---|
| `43067954548` | push | ❌ **échec** à l'étape « Hygiène du dépôt » : 2 `print()` dans `config/demarrage.py` (garde-fou P00-05) |
| `43068984612` | push (après correction `99491c3`) | ✅ **Frontend vert** (2 min 25 s) · **Backend** : voir `DEPLOY_INJS_MISSION_02_CI_CD.md` §5 |

Le premier échec est une **preuve de fonctionnement** : la CI a bloqué le code
ajouté par la mission 02. Correctif apporté (`sys.stdout`/`sys.stderr` au lieu
de `print()`), contrôle `check_repo_hygiene` repassé en local : **CONFORME**
(2 261 fichiers suivis vérifiés).

---

## 4. B5 — CORRECTION DU TEST EDT

Fichier modifié : **`backend/edts/tests/test_seed_edt_demo.py` uniquement**.
Aucun fichier métier touché — vérifiable par `git show --stat 3e5aad2`.

Le tableau de bord est désormais évalué **dans le même contexte temporel** que
les données semées (date de référence déterministe). Le test vérifie les
**6 séances** et le taux **41,7** attendus, sans dépendre de la date de la
machine.

| Exécution | Résultat |
|---|---|
| Test isolé | `Ran 1 test — OK` |
| Groupe EDT | `Ran 591 tests — RÉUSSI` |
| Suite complète | `3 066 tests — 9 groupes — 0 échec` |

---

## 5. DOCKER — `.dockerignore`

Deux fichiers créés : `backend/.dockerignore`, `frontend/.dockerignore`.

| Contexte | Avant | Après | Réduction |
|---|---:|---:|---:|
| `backend/` | **181,6 Mio** (12 526 fichiers) | **8,8 Mio** (1 164 fichiers) | **−95,2 %** |
| `frontend/` | **229,7 Mio** (19 712 fichiers) | **5,9 Mio** (400 fichiers) | **−97,4 %** |

Exclus notamment : `.git`, `.venv`, `venv`, `node_modules`, `__pycache__`,
`*.pyc`, `db.sqlite3`, sauvegardes, journaux, rapports de couverture, `.env*`,
clés et secrets.

**Aucun fichier nécessaire exclu** (vérifié un par un) : `entrypoint.sh`,
`scripts/gunicorn-autoscale.sh`, `manage.py`, `requirements.txt`,
`config/demarrage.py`, `scolarite/data/complement_referentiel_lmd_pdf.json`,
`habilitations/referentiel/catalogue_roles.py`, `package*.json`, `index.html`,
`vite.config.js`, `nginx.conf`, `src/`.

---

## 6. NGINX — CONFIGURATION CANDIDATE (non appliquée)

`docker/nginx/default.conf` durci : relais de `X-Forwarded-Proto` (aucun
écrasement par `$scheme`), `/admin/` fermée par défaut (`deny all`, liste
d'autorisation à compléter), `client_max_body_size 25 Mio` justifié par les
limites applicatives (10 Mio par pièce + 5 Mio par preuve). **13 tests** dédiés.
Détail et procédure d'application : `DEPLOY_INJS_MISSION_02_NGINX.md`.

---

## 7. PYTHON 3.12

| Environnement | Version | Statut |
|---|---|---|
| Image Docker backend | `python:3.12-slim` | ✅ inchangé |
| CI GitHub Actions | **3.12** | ✅ aligné |
| Référence déclarée | `backend/.python-version` = 3.12 | ✅ |
| Bac à sable d'audit | 3.11.2 | ⚠️ **impossible à aligner** |

**Preuve de l'impossibilité locale** (deux méthodes indépendantes) :

```
$ uv python install 3.12
  cause: invalid peer certificate: UnknownIssuer   (github.com/astral-sh/...)

$ curl -sL <cpython-3.12.16 standalone>
curl: (35) OpenSSL SSL_connect: SSL_ERROR_SYSCALL in connection to
release-assets.githubusercontent.com:443
```

Les hôtes de téléchargement (`objects.githubusercontent.com`,
`release-assets.githubusercontent.com`) sont hors de la liste autorisée.
**La validation 3.12 est donc apportée par la CI**, qui est aussi
l'environnement de référence pour la livraison.
Aucune version de Django ou de dépendance n'a été modifiée (`pip check` : OK,
30 paquets toujours épinglés).

---

## 8. AUTONOMIE

| Contrôle | Résultat |
|---|---|
| `dossier_trvx` nécessaire à l'exécution ? | **NON** ✅ — aucune migration ni chargement runtime |
| Référentiels indispensables présents dans le dépôt ? | ✅ (JSON commité pour `completer_referentiel_lmd`) |
| Contextes Docker exempts d'archives de travail ? | ✅ 8,8 Mio et 5,9 Mio ; `dossier_trvx` hors contexte **et** exclu |
| Réintroduction SYGEP/CPFAE ? | **AUCUNE** ✅ |
| Paramètres de production dépendants de fichiers locaux ? | **NON** ✅ — tout passe par l'environnement |

---

## 9. FICHIERS

### Créés (12)

`backend/.dockerignore` · `backend/.python-version` · `backend/config/demarrage.py` ·
`backend/config/tests/test_demarrage.py` · `backend/config/tests/test_nginx_gateway.py` ·
`frontend/.dockerignore` · `.github/workflows/publish-injs-lmd.yml` ·
`.github/workflows/deploy-injs-lmd.yml` ·
`docs/deploiement/mission-02/DEPLOY_INJS_MISSION_02_{CI_CD,DOCKER,NGINX,GO_NO_GO,TESTS,RAPPORT}.md`

### Modifiés (6)

`.github/workflows/ci.yml` · `backend/compose.yml` · `backend/entrypoint.sh` ·
`backend/edts/tests/test_seed_edt_demo.py` · `deploy/production/compose.yml` ·
`docker/nginx/default.conf`

### Supprimés

**Aucun.**

---

## 10. COMMITS

| SHA | Objet |
|---|---|
| `3e5aad2` | Mission 02 : B2 (démarrage maîtrisé), B3 (workflows), B5 (test EDT), `.dockerignore`, Nginx, Python 3.12, 4 livrables |
| `cd293ab` | CI : déclenchement sur les branches de livraison `arena/**` (cause racine de B4) |
| `99491c3` | Correction `print()` → `sys.stdout/stderr` dans `config/demarrage.py` (garde-fou P00-05) |
| *(ce commit)* | Livrables `TESTS` et `RAPPORT`, résultat CI consolidé |

---

## 11. ÉTAT DE LA BRANCHE ET DE LA CI

| Élément | État |
|---|---|
| Branche | `arena/4524a57c-backend-injs2026` |
| Tête | voir `git log --oneline -1` |
| Avance / retard sur `main` | **15 commits d'avance · 93 de retard** |
| Dépôt | propre (0 modification non commitée) |
| PR #5 | **OPEN — `CONFLICTING` (DIRTY)** : 9 fichiers en conflit |
| CI de la branche | exécutions réelles : `43067954548` (échec corrigé), `43068984612` (voir CI_CD §5) |

### ⚠️ Anomalie : conflit de la PR #5

La fusion de `main` dans la branche produit **9 conflits**, dont des fichiers
**métier** :

```
.github/workflows/deploy-injs-lmd.yml
.github/workflows/publish-injs-lmd.yml
backend/dashboard/services.py
backend/dashboard/tests.py
backend/formations/serializers.py
frontend/src/pages/DashboardEngineView.jsx
frontend/src/pages/EvaluationsModule.jsx
frontend/src/pages/scolarite/ChargesEnseignants.jsx
frontend/src/styles/evaluations.css
```

Arbitrer ces conflits revient à choisir entre deux versions **fonctionnelles** du
métier (tableau de bord, serializers de formations, pages d'évaluation), ce qui
sort du périmètre de la mission 02 (« ne pas modifier les règles métier LMD »,
« ne jamais écraser les modifications préexistantes »). **La fusion a donc été
annulée** (`git merge --abort`) et la branche laissée intacte : cette décision
appartient au responsable fonctionnel.

---

## 12. ANOMALIES RESTANTES

| # | Anomalie | Gravité | Traitement |
|---|---|---|---|
| A1 | **PR #5 en conflit** (9 fichiers, dont 4 métier) | majeure | arbitrage fonctionnel puis fusion |
| A2 | Python 3.12 non installable dans l'environnement d'audit | mineure | la CI valide 3.12 ; aligner le poste de référence |
| A3 | `nginx -t` et validation HTTPS/CSRF/cookies non exécutés | mineure | mission 03, sur le VPS, après application de la configuration candidate |
| A4 | Bundle frontend 1 446,63 kB (> 500 kB) | mineure | découpage `manualChunks` recommandé |
| A5 | 1 117 avertissements `check --deploy` | informative | OpenAPI (1 116) + `SECURE_SSL_REDIRECT` volontaire — justifiés dans l'en-tête de `ci.yml` |
| A6 | Résidus de nomenclature SYGEP/CPFAE (comptes témoins, documentation) | cosmétique | renommage à décider (imposerait une migration de données) |
| A7 | **B1 — base de production** | hors périmètre | mission VPS distincte : la base `injs_lmd_prod_20261026` n'a jamais été contactée |
