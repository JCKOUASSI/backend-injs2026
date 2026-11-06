# AUDIT PRÉ-DÉPLOIEMENT INJS — 6 novembre 2026

**Dépôt** : `JCKOUASSI/backend-injs2026`
**Branche auditée** : `arena/4524a57c-backend-injs2026` · **Commit** : `7c9d56a`
**Objet** : préparer la livraison en production (INJS Abidjan) — audit, **pas un déploiement**.
**Périmètre exclu** : `dossier_trvx` (hors livraison).

> **Aucune opération de publication, de migration ou d'écriture en production n'a
> été exécutée.** Aucune image n'a été construite ni poussée. `rbac_initialisation
> --apply` n'a pas été lancé. Aucun fichier du dépôt n'a été modifié au cours de
> l'audit (vérifié : `git status` vide, aucun commit produit par les vérifications).

---

## Synthèse

| Domaine | Verdict |
|---|---|
| **A. Git** | ✅ **PRÊT SOUS RÉSERVE** — branche propre et synchronisée, mais jamais validée par la CI |
| **B. Backend** | ⚠️ **PRÊT SOUS RÉSERVE** — 3 030 tests, 1 échec (test dépendant de la date) ; migrations cohérentes ; sécurité conforme |
| **C. Frontend** | ✅ **PRÊT** — 2 167 tests verts, lint 0 erreur, build OK |
| **D. Docker** | ⚠️ **PRÊT SOUS RÉSERVE** — chaîne d'images éprouvée, mais 5 correctifs à apporter |
| **E. Autonomie** | ✅ **PRÊT** — aucun référentiel chargé depuis `dossier_trvx` à l'exécution |
| **F. Production (VPS)** | ⛔ **BLOQUANT** — 5 points à traiter avant déploiement |

**Recommandation** : ne pas déployer en l'état. Les 5 blocages sont tous
levables en moins d'une demi-journée ; un seul (l'accès à la base de production)
dépend d'une habilitation externe. Voir §7 (plan de déploiement).

---

## A. GIT

| Contrôle | Résultat |
|---|---|
| Branche courante | `arena/4524a57c-backend-injs2026` |
| Commit de référence | `7c9d56a` |
| État du dépôt | **propre** — 0 modification, 0 fichier non suivi |
| Cohérence distante | **synchronisée** — 0 commit de retard, 0 d'avance |
| Exécutions CI sur cette branche | **aucune** (`gh run list --branch …` vide) |
| Workflows présents sur la branche | `ci.yml` **uniquement** |
| Workflows présents sur `origin/main` | `ci.yml`, `publish-injs-lmd.yml`, `deploy-injs-lmd.yml` |

**Constats**

1. Le fichier `deploy/production/compose.yml` déclare que les images sont
   publiées par `.github/workflows/publish-injs-lmd.yml` — **ce workflow n'existe
   pas sur la branche livrée** (il est sur `main`). Publier depuis cette branche
   est impossible sans fusion préalable. → **BLOQUANT B3**
2. La branche n'a **jamais été validée par la CI GitHub** (seules les branches
   `main` et `arena/86930808-…` ont des exécutions). La suite a donc été
   rejouée intégralement dans cet environnement (§B).
3. `origin/main` a fusionné la PR #4 hier (CI verte, `42079925844`) — la branche
   auditée en est **à 6 commits** (`2e51af0…7c9d56a`).

---

## B. BACKEND

### B.1 Tests — exécutés intégralement

`./arena/tests_par_groupe.sh` (9 groupes, base de test isolée) :

| Groupe | Tests | Résultat | Durée |
|---|---:|---|---|
| scolarite | 515 | ✅ | 153 s |
| formations | 289 | ✅ | 106 s |
| auth | 242 | ✅ | 153 s |
| habilitations | 520 | ✅ | 283 s |
| **edt** | **591** | **⛔ 1 échec** | 182 s |
| evaluations | 237 | ✅ | 119 s |
| pilotage | 209 | ✅ | 71 s |
| socle | 275 | ✅ | 137 s |
| divers | 152 | ✅ | 75 s |
| **Total** | **3 030** | **1 échec** | ~21 min |

L'unique échec : `edts.tests.test_seed_edt_demo.SeedEdtDemoTests.test_seances_aujourdhui_et_kpi_reellement_mesures`.
**Cause prouvée par la mesure** (voir `DEPLOY_INJS_TESTS_20261106.md` §3) : le
test fige la date du jeu de démonstration au **2026-11-03** mais interroge le
tableau de bord à la **date réelle** (2026-11-06). Mesures relevées :

| Appel | `taux_assiduite_moyen` | séances mesurées |
|---|---:|---:|
| date réelle (2026-11-06) | `None` | 0 |
| date figée (2026-11-03) | `41.7` | 6 |

Il s'agit d'un **défaut de conception du test** (patch incomplet), pas d'un défaut
de production : renvoyer `None` lorsqu'aucune assiduité n'est mesurée est le
comportement **voulu et documenté** du service (`dashboard/services.py` : « un
taux sans dénominateur vaut `None` »). Le test échouera **tous les jours à partir
du 4 novembre 2026** tant qu'il n'est pas corrigé. → **BLOQUANT B5** (validation CI).

### B.2 Migrations

- `manage.py makemigrations --check --dry-run` → **« No changes detected »** (code 0) :
  les modèles sont en phase avec les migrations.
- 22 applications, **251 migrations** au total ; `formations` en compte **101**
  (la plus lourde — durée de `migrate` à anticiper sur le VPS).
- ⚠️ **L'état des migrations appliquées en production n'a pas pu être vérifié** :
  la base `injs_lmd_prod_20261026` n'est pas joignable depuis cet environnement
  (cf. mission RBAC-PROD-01). → **BLOQUANT B4**

### B.3 Dépendances

`backend/requirements.txt` : **30 paquets, tous épinglés** (`==`). `pip check` →
**« No broken requirements found »**. Détail : `DEPLOY_INJS_DEPENDANCES_20261106.md`.
⚠️ Aucun fichier de hachage / `pip-audit` exécutable ici : la revue CVE des
dépendances reste à faire sur le VPS.

### B.4 Paramètres et sécurité de production

| Réglage | État |
|---|---|
| `DEBUG` | faux par défaut ; `DJANGO_DEBUG`/`DEBUG` lus depuis l'environnement ✅ |
| `SECRET_KEY` | **exigée** si `DEBUG=False` (sinon `ImproperlyConfigured`) ✅ |
| `ALLOWED_HOSTS` | depuis l'env ; le joker `*` est **retiré** en production ✅ |
| `CSRF_TRUSTED_ORIGINS` / `CORS_ALLOWED_ORIGINS` | depuis l'env ✅ |
| Cookies | `SESSION_COOKIE_SECURE` / `CSRF_COOKIE_SECURE` = `True` hors DEBUG ✅ |
| HSTS | 1 an, sous-domaines, préchargement ✅ |
| Proxy TLS | `SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')` ✅ |
| `SECURE_SSL_REDIRECT` | **faux, volontairement** (TLS terminé par Nginx Proxy Manager) — seul avertissement `security.W008` ✅ |
| `POSTGRES_DB` | défaut **`qr_badge`** — piège si la variable est absente ⚠️ |
| Cache | Redis si `REDIS_URL`, sinon fichier local ✅ |

`manage.py check --deploy` (DEBUG=0, clé longue) : **1 117 avertissements** =
610 `drf_spectacular.W001` + 506 `drf_spectacular.W002` + 1 `security.W008`.
Les deux premières familles concernent **uniquement la génération du schéma
OpenAPI** (infos de type non résolues, serializers non inférables) : **aucun
impact à l'exécution**. Aucune erreur bloquante.

---

## C. FRONTEND

| Contrôle | Commande | Résultat |
|---|---|---|
| Installation selon le lockfile | `npm ci` | ✅ **518 paquets** en 5 s, 0 erreur |
| Cohérence du lockfile | `package-lock.json` v3, 568 entrées | ✅ cohérent avec `package.json` |
| Tests | `npm run test:run` | ✅ **131 fichiers / 2 167 tests**, 0 échec (142 s) |
| Lint | `npm run lint` | ✅ **0 erreur**, 6 avertissements (variables inutilisées) |
| Build | `npm run build` | ✅ **8,96 s**, 0 erreur |
| Variables d'environnement | `VITE_API_URL`, `VITE_BADGE_BASE_URL` | ✅ transmises en `--build-arg` par le workflow de publication |

**Réserves** : le bundle principal pèse **1 446,63 kB** (349,32 kB gzip) — un
avertissement de taille de chunk est émis (> 500 kB) ; un découpage
(`manualChunks`) est recommandé mais **non bloquant**. `package.json` ne déclare
pas de champ `engines` : Node 20 est utilisé en CI et dans l'image, 22 dans cet
environnement de test (build vérifié sur les deux).

---

## D. DOCKER

### D.1 Dockerfiles

| | Backend | Frontend |
|---|---|---|
| Image de base | `python:3.12-slim` | `node:20-alpine` → `nginx:1.27-alpine` |
| Contexte (CI) | `./backend` | `./frontend` |
| Utilisateur | `appuser` (non-root) ✅ | nginx (non-root) ✅ |
| Port exposé | 8000 | 80 |
| Particularité | `entrypoint.sh` : attend PostgreSQL, `migrate`, `collectstatic`, superuser idempotent, gunicorn | build args `VITE_API_URL`, `VITE_BADGE_BASE_URL`, `VERSION` |

### D.2 Images

- Dernière publication **réussie** : exécution GitHub `41985711224` (5 novembre,
  branche `deploy-20261105-r2`) → `jckouassi/injs-be` en 1 min 18 s,
  `jckouassi/injs-fe` en 1 min 16 s. La chaîne fonctionne.
- ⚠️ L'existence actuelle des tags sur Docker Hub **n'a pas pu être vérifiée**
  depuis cet environnement (sortie réseau limitée à github.com / pypi.org).

### D.3 Compose de production (`deploy/production/compose.yml`)

- 3 services : `backend`, `frontend`, `gateway` (nginx). Pas de `container_name`
  (évite les collisions avec la production actuelle) ✅
- **Healthcheck backend** sur `GET /api/health/` — endpoint **existant**
  (`config/urls.py:23`) ✅ ; `gateway` attend `service_healthy` ✅
- **Pas de healthcheck sur le frontend** (dépendance `service_started` seulement) ⚠️
- Réseau `injs-prod` (externe possible pour rejoindre le réseau PostgreSQL),
  volumes `media` / `staticfiles`, port public `8080` configurable ✅
- `depends_on`, `restart: unless-stopped`, montage nginx en lecture seule ✅

### D.4 Points faibles (détail et correctifs : `DEPLOY_INJS_BLOCAGES_20261106.md`)

1. **Aucun `.dockerignore`** (ni racine, ni `backend/`, ni `frontend/`) — en CI le
   checkout est propre (donc sans impact), mais un build local embarquerait
   `.venv` (139 Mo), `db.sqlite3` (15 Mo, **empreintes de mots de passe**),
   `node_modules` (253 Mo).
2. **`SKIP_DB_SETUP` n'est pas transmis au conteneur** (absent du bloc
   `environment:` du compose, aucun `env_file`) alors que `.env.example` le
   documente à `true` → l'entrypoint exécutera `migrate` **en production au
   démarrage**. → **BLOQUANT B2**
3. Variables documentées mais non transmises : `REDIS_URL`, `BADGE_BASE_URL`,
   `PUBLIC_APP_URL`, `DJANGO_SUPERUSER_*` (celui-là sans conséquence : pas de
   création automatique de superutilisateur).
4. `proxy_set_header X-Forwarded-Proto $scheme;` dans le gateway **écrase**
   l'en-tête `https` envoyé par Nginx Proxy Manager → Django voit `http`
   (sans boucle de redirection puisque `SECURE_SSL_REDIRECT=False`, mais
   `request.is_secure()` est faux).
5. `gosu` est appelé par `entrypoint.sh` en cas de démarrage en **root** mais
   n'est **installé par aucune instruction** du Dockerfile. En configuration
   nominale (`USER appuser`) la branche n'est pas exécutée → **robustesse**, pas
   un blocage.
6. Pas de `client_max_body_size` dans le gateway : limite nginx par défaut à
   **1 Mo** pour les téléversements (photos, justificatifs, imports).
7. Le gateway proxifie **`/admin/` vers le backend** : l'administration Django
   serait joignable publiquement sur `https://injs.badge-qr-code.pro/admin/`
   — à restreindre au niveau de Nginx Proxy Manager (le front Vite, lui, bloque
   déjà `/admin` sur le port 3000).
8. `external: ${INJS_NETWORK_EXTERNAL:-false}` : substitution de chaîne à valider
   par `docker compose config` avant déploiement.
9. Permissions du montage `/opt/injs/injs-be/data/media` : l'`appuser` du
   conteneur (uid 1000) doit pouvoir écrire dans le répertoire hôte.
10. Pile de **développement** (`backend/compose.yml`) : noms de conteneurs
    `qr-badge-*`, image `qr-badge-app:local`, port `8001` alors que l'image
    expose 8000 — héritage à nettoyer (hors périmètre production).

---

## E. AUTONOMIE DU PROJET

| Contrôle | Résultat |
|---|---|
| `dossier_trvx` présent ? | **Oui** (4,5 Mo) — mais **non embarqué** par les contextes de build CI (`./backend`, `./frontend`) |
| Référentiel chargé depuis ce dossier à l'exécution ? | **NON** ✅ |
| Migration dépendante de ce dossier ? | **NON** ✅ |
| Référence SYGEP/CPFAE fonctionnelle ? | **NON** ✅ (résidus cosmétiques) |

**Détail `dossier_trvx`** — 3 natures de références, toutes hors exécution :

1. `backend/scripts/extraire_referentiel_offre_formation.py` (ligne 510) :
   outil d'extraction **ponctuel**, `--source` permet de pointer ailleurs ;
   non appelé par une migration, ni au démarrage, ni par l'API.
2. `backend/scolarite/management/commands/completer_referentiel_lmd.py` : la
   docstring cite le PDF source, mais la commande lit le **JSON commité**
   `scolarite/data/complement_referentiel_lmd_pdf.json` ✅ (aucune lecture du dossier).
3. Documents (`.gitignore`, `ANNEXE-MAQUETTES-INJS.md`, rapports de mission).

**Détail SYGEP/CPFAE** — aucune référence fonctionnelle. Résidus :
identifiants de comptes témoins `temoin_cpfae_admin` / `temoin_chef_cpfae_admin`
(`creer_comptes_temoins.py`, `fumee_authentification.py`), migrations
historiques `0008`/`0009` (**à ne jamais réécrire**), deux scripts d'analyse
(`analyse_dossier.py`, `analyze_edt.py`) et le `README`.
→ Cosmétique ; un renommage imposerait une migration de données. **PRÊT SOUS RÉSERVE.**

---

## F. COMPATIBILITÉ AVEC L'ENVIRONNEMENT CIBLE

| Composant | Compatibilité | Points de vigilance |
|---|---|---|
| **AlmaLinux** | ✅ aucune dépendance à l'OS hôte (tout tourne en conteneur) | SELinux : appliquer `chcon -Rt container_file_t` (ou `:z`) sur les montages `/opt/injs/...` ; ouvrir le pare-feu pour `8080` ; Docker Engine + **plugin Compose v2** requis (clé `name:` en tête de fichier) |
| **Docker Server** | ✅ | `docker compose config` à exécuter avant `up` |
| **PostgreSQL** | ✅ `psycopg2-binary==2.9.10`, variables `POSTGRES_*`, base **non créée** par le compose | `POSTGRES_HOST` doit être l'**IP/nom du conteneur** sur le réseau Docker (pas `127.0.0.1`) ; défaut `qr_badge` si `POSTGRES_DB` manque ; version serveur non vérifiable ici |
| **Redis** | ✅ optionnel (`REDIS_URL`), `redis==5.2.1` | non câblé dans le compose : **à ajouter** si un cache partagé entre workers est souhaité |
| **RabbitMQ** | ✅ **aucune dépendance** — pas de Celery dans `requirements.txt` ni dans `settings.py` | si un worker Celery d'une ancienne pile tourne sur le VPS, il est étranger à cette application |
| **Nginx Proxy Manager** | ✅ TLS terminé en amont, `SECURE_SSL_REDIRECT=False` cohérent, HSTS et cookies sécurisés actifs | conserver/relayer `X-Forwarded-Proto` ; restreindre `/admin/` ; augmenter `client_max_body_size` |
| **`injs.badge-qr-code.pro`** | ✅ domaine déclaré dans `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `CORS_ALLOWED_ORIGINS`, `PUBLIC_APP_URL`, `BADGE_BASE_URL`, `VITE_API_URL` | résolution DNS et certificat à valider côté NPM |

---

## 6. CLASSIFICATION

### ✅ PRÊT POUR DÉPLOIEMENT

1. **Code applicatif** : 3 030 tests backend (1 échec non fonctionnel) + 2 167
   tests frontend, lint propre, build reproductible.
2. **Migrations** : modèles et migrations en phase, aucune migration manquante.
3. **Sécurité applicative** : `SECRET_KEY` imposée, cookies sécurisés, HSTS,
   en-têtes de proxy, `ALLOWED_HOSTS` stricte, utilisateur non-root dans l'image.
4. **Autonomie** : aucun référentiel chargé depuis `dossier_trvx` à l'exécution ;
   aucune dépendance fonctionnelle à SYGEP/CPFAE.
5. **Chaîne d'images** : éprouvée (publication réussie le 5 novembre), images
   taguées par SHA, multi-étapes avec utilisateur non-root.
6. **Cohérence du dépôt** : propre, synchronisé, sans secret commité.

### ⚠️ PRÊT SOUS RÉSERVE

1. Bundle frontend > 500 kB (découpage recommandé).
2. Pas de healthcheck sur le service frontend.
3. Aucun `.dockerignore` (risque si build hors CI).
4. `X-Forwarded-Proto` écrasé par le gateway ; `client_max_body_size` absent.
5. `gosu` manquant pour un démarrage en root ; uid `appuser` vs montage média.
6. Résidus de nomenclature SYGEP/CPFAE (comptes témoins, documentation).
7. Python **3.11 en CI** contre **3.12 dans l'image** de production — la suite
   n'est jamais exécutée sur la version réellement déployée.
8. `POSTGRES_DB` par défaut `qr_badge` (mauvaise base silencieuse si oubli).

### ⛔ BLOQUANT

| Id | Blocage | Référence |
|---|---|---|
| **B1** | Base de production non joignable / non identifiée → état des migrations en production inconnu | RBAC-PROD-01 |
| **B2** | `SKIP_DB_SETUP` non transmis → migrations exécutées automatiquement au démarrage en production | §D.4.2 |
| **B3** | Workflow de publication `publish-injs-lmd.yml` absent de la branche livrée | §A.1 |
| **B4** | Aucune exécution CI sur la branche livrée | §A.2 |
| **B5** | Test `edt` en échec (dépendant de la date) → suite non verte, impossible à valider | §B.1 |

Détail, preuves et correctifs : `DEPLOY_INJS_BLOCAGES_20261106.md`.

---

## 7. RECOMMANDATION ET PLAN DE DÉPLOIEMENT

**Recommandation : ne pas déployer en l'état.** Le code est sain, mais trois
blocages (B2, B3, B5) se corrigent en quelques dizaines de minutes et un quatrième
(B1) conditionne **toute** décision d'écriture en base. Déployer maintenant
reviendrait à appliquer des migrations de production **sans les avoir décidées**,
sur une base dont on ne connaît pas l'état.

### Plan en 9 étapes (à valider avant exécution)

**Étape 0 — Prérequis d'accès et sauvegarde** *(bloque tout le reste)*
- Obtenir un accès au VPS et à la base `injs_lmd_prod_20261026` (SSH ou accès direct).
- Confirmer l'identité de la base : `psql -c "SELECT current_database(), version();"`.
- **Sauvegarde complète** : `pg_dump -Fc injs_lmd_prod_20261026 > injs_avant_deploi_$(date +%F).dump`
  + copie du répertoire média `/opt/injs/injs-be/data/media`.
- Relever l'état des migrations : `python manage.py showmigrations`.

**Étape 1 — Mise à niveau de la branche**
- Fusionner `origin/main` dans la branche pour récupérer `publish-injs-lmd.yml`
  et `deploy-injs-lmd.yml`. *(B3)*

**Étape 2 — Corrections de la chaîne de validation**
- Corriger le test `edt` (figer aussi la date du tableau de bord, ou rendre les
  attentes relatives à la date semée). *(B5)*
- Aligner la CI sur **Python 3.12** (version de l'image) ou l'image sur 3.11.
- Vérifier que la CI se déclenche sur la branche. *(B4)*

**Étape 3 — Hygiène Docker**
- Ajouter `.dockerignore` dans `backend/` et `frontend/` (exclure `.venv`,
  `db.sqlite3`, `node_modules`, `dist`, `__pycache__`, `.env*`).

**Étape 4 — Configuration de production**
- Câbler `SKIP_DB_SETUP` (et, au choix, `REDIS_URL`, `BADGE_BASE_URL`,
  `PUBLIC_APP_URL`) dans le bloc `environment:` du service backend. *(B2)*
- Décider explicitement **qui** exécute `migrate` : une étape manuelle et
  supervisée est recommandée (jamais au démarrage d'un conteneur).
- Restreindre `/admin/` au niveau de Nginx Proxy Manager ; porter
  `client_max_body_size` à la taille utile (ex. 20 Mo) ; conserver
  `X-Forwarded-Proto` entrant.
- Préparer les droits du montage média (`chown 1000:1000` ou SELinux `container_file_t`).
- Générer une `SECRET_KEY` forte (≥ 50 caractères), hors dépôt.

**Étape 5 — Vérification du référentiel en production**
- Exécuter `rbac_initialisation` **sans `--apply`** sur la base de production et
  joindre le rapport (suite de RBAC-PROD-01) : 81 rôles / 22 sensibles /
  1 157 permissions attendus.

**Étape 6 — Publication des images**
- Déclencher `publish-injs-lmd.yml` (tag Git `deploy-*` ou `workflow_dispatch`)
  avec `VITE_API_URL=https://injs.badge-qr-code.pro/api`.
- Reporter les **tags SHA complets** dans `deploy/production/.env`.

**Étape 7 — Déploiement**
- `docker compose -f deploy/production/compose.yml --env-file deploy/production/.env config` (validation).
- `docker compose ... pull` puis `up -d`.
- Contrôles : healthcheck backend, `GET https://injs.badge-qr-code.pro/api/health/`,
  page de connexion, parcours Scolarité / Formations / EDT, `/admin/` inaccessible.

**Étape 8 — Bascule et surveillance**
- Pointer Nginx Proxy Manager vers `127.0.0.1:8080` ; activer le certificat.
- Surveiller les logs (`docker compose logs -f backend`) et le taux d'erreur 5xx
  pendant 24 h.
- **Retour arrière** : rejouer le compose avec les tags SHA précédents
  (`INJS_BACKEND_TAG`, `INJS_FRENTEND_TAG`) ; les volumes média/staticfiles sont
  conservés ; la base restaurée par `pg_restore` si une migration a été appliquée.

---

## 8. LIVRABLES

| Fichier | Contenu |
|---|---|
| `DEPLOY_INJS_AUDIT_20261106.md` | Ce rapport |
| `DEPLOY_INJS_TESTS_20261106.md` | Preuves d'exécution : backend, frontend, lint, build, `check --deploy` |
| `DEPLOY_INJS_DEPENDANCES_20261106.md` | Dépendances, versions, intégrité, services cibles |
| `DEPLOY_INJS_BLOCAGES_20261106.md` | Blocages, gravité, correctifs, liste de contrôle avant déploiement |
