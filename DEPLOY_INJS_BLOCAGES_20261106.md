# BLOCAGES ET POINTS DE VIGILANCE — 6 novembre 2026

**Branche** : `arena/4524a57c-backend-injs2026` · **Commit** : `7c9d56a`
**Rappel** : aucun correctif n'a été appliqué. Ce document liste ce qu'il faut
traiter **avant** le déploiement, avec la preuve de chaque constat.

---

## 1. BLOCAGES (⛔ — déploiement déconseillé tant qu'ils ne sont pas levés)

### B1 — Base de production non joignable : état des migrations inconnu

| | |
|---|---|
| **Identifiant technique** | `injs_lmd_prod_20261026` |
| **Nature** | La base cible n'est ni identifiable (nom absent du dépôt) ni joignable depuis l'environnement de travail |
| **Preuve** | Aucun serveur/client PostgreSQL, port 5432 refusé, pilote `psycopg` absent, sortie réseau limitée à github.com/pypi.org, `~/.ssh` absent, aucune variable `POSTGRES_*` — cf. `docs/curp/audit-production/RBAC_PRODUCTION_RAPPORT_20261106.md` (mission RBAC-PROD-01) |
| **Gravité** | **CRITIQUE** |
| **Conséquence métier** | Impossible de connaître l'état réel des migrations, des comptes et des habilitations en production : toute migration serait appliquée à l'aveugle |
| **Action corrective** | Obtenir un accès au VPS ; confirmer `SELECT current_database(), version();` ; **sauvegarder** (`pg_dump -Fc`) ; relever `manage.py showmigrations` ; exécuter `rbac_initialisation` **sans `--apply`** |
| **Autorisation nécessaire** | DSI INJS / responsable du serveur |

### B2 — `SKIP_DB_SETUP` non transmis : migrations automatiques au démarrage

| | |
|---|---|
| **Identifiant technique** | `deploy/production/compose.yml` (service `backend`) ↔ `deploy/production/.env.example:76` |
| **Nature** | La variable est documentée à `true` dans le modèle d'environnement, mais le bloc `environment:` du service ne la mentionne pas et aucun `env_file` n'est déclaré : elle **n'atteint jamais le conteneur** |
| **Preuve** | `grep -c SKIP_DB_SETUP deploy/production/compose.yml` → **0** ; l'`entrypoint.sh` exécute `manage.py migrate --noinput` puis `collectstatic` dès que `SKIP_DB_SETUP` ≠ `true` |
| **Gravité** | **CRITIQUE** (procédure de production) |
| **Conséquence métier** | Au premier `docker compose up`, les migrations s'appliquent automatiquement sur la base de production, sans validation humaine, sans sauvegarde préalable garantie et sans possibilité de choisir le moment |
| **Action corrective** | Ajouter `SKIP_DB_SETUP: "${SKIP_DB_SETUP:-true}"` (et, au choix, `REDIS_URL`, `BADGE_BASE_URL`, `PUBLIC_APP_URL`) dans le bloc `environment:` du service backend, **ou** décider explicitement et tracer que les migrations sont appliquées au démarrage ; dans tous les cas, prévoir une étape `migrate` manuelle et supervisée |
| **Autorisation nécessaire** | Comité de validation + DSI INJS |

### B3 — Workflow de publication absent de la branche livrée

| | |
|---|---|
| **Identifiant technique** | `.github/workflows/publish-injs-lmd.yml` (référencé par `deploy/production/compose.yml`) |
| **Nature** | Le workflow n'existe **que** sur `origin/main` ; la branche auditée ne contient que `ci.yml` |
| **Preuve** | `git ls-tree -r --name-only origin/arena/4524a57c-backend-injs2026 .github/workflows/` → `ci.yml` ; sur `origin/main` → `ci.yml`, `deploy-injs-lmd.yml`, `publish-injs-lmd.yml` |
| **Gravité** | **MAJEURE** (bloque la publication depuis cette branche) |
| **Conséquence métier** | Impossible de produire les images officielles `jckouassi/injs-be` et `jckouassi/injs-fe` à partir du code réellement livré |
| **Action corrective** | Fusionner `origin/main` dans la branche (ou y rapporter les deux workflows), puis publier |
| **Autorisation nécessaire** | Responsable technique |

### B4 — Aucune exécution CI sur la branche livrée

| | |
|---|---|
| **Identifiant technique** | `arena/4524a57c-backend-injs2026` |
| **Nature** | La branche n'a jamais été construite par GitHub Actions |
| **Preuve** | `gh run list --branch arena/4524a57c-backend-injs2026` → **vide** (les exécutions existantes concernent `main` et `arena/86930808-…`) |
| **Gravité** | **MAJEURE** |
| **Conséquence métier** | Aucune validation automatisée indépendante du poste de travail ; la suite a été rejouée manuellement ici (3 030 tests) mais pas par la CI |
| **Action corrective** | Ouvrir une PR (ou pousser) pour déclencher la CI ; corriger au préalable le test en échec (B5) et aligner Python sur 3.12 |
| **Autorisation nécessaire** | Équipe de développement |

### B5 — Test `edt` en échec (dépendant de la date)

| | |
|---|---|
| **Identifiant technique** | `edts.tests.test_seed_edt_demo.SeedEdtDemoTests.test_seances_aujourdhui_et_kpi_reellement_mesures` |
| **Nature** | Le test fige la date du jeu de démonstration au 2026-11-03 mais interroge `/api/dashboard/presences/` à la date réelle : le KPI `taux_assiduite_moyen` vaut `None` (comportement voulu) |
| **Preuve** | Traceback `AssertionError: unexpectedly None` ; mesure comparative : date réelle 2026-11-06 → `None` / 0 séance mesurée, date figée 2026-11-03 → `41.7` / 6 séances. Détail : `DEPLOY_INJS_TESTS_20261106.md` §2 |
| **Gravité** | **MAJEURE** pour la validation (suite non verte) — **nulle** pour la production |
| **Conséquence métier** | La CI ne peut pas valider la branche ; un échec rouge masque d'éventuelles vraies régressions |
| **Action corrective** | Figer également la date côté tableau de bord dans ce test (`patch` de `dashboard.services.timezone.localdate`) ou rendre les attentes relatives à la date semée |
| **Autorisation nécessaire** | Équipe de développement |

> **Note** : les cinq blocages sont indépendants. B1 conditionne toutes les
> opérations d'écriture ; B2, B3, B4 et B5 se lèvent en moins d'une demi-journée.

---

## 2. POINTS DE VIGILANCE (⚠️ — non bloquants, à traiter si possible)

| Id | Identifiant technique | Nature | Gravité | Action recommandée |
|---|---|---|---|---|
| V1 | `backend/Dockerfile`, `frontend/Dockerfile` | **Aucun `.dockerignore`** : un build hors CI embarquerait `.venv` (139 Mo), `db.sqlite3` (15 Mo, empreintes de mots de passe), `node_modules` (253 Mo) | Moyenne | Créer `.dockerignore` dans `backend/` et `frontend/` |
| V2 | `docker/nginx/default.conf` | `proxy_set_header X-Forwarded-Proto $scheme;` **écrase** l'en-tête `https` de Nginx Proxy Manager → Django voit `http` | Moyenne | Relayer l'en-tête entrant : `proxy_set_header X-Forwarded-Proto $http_x_forwarded_proto;` |
| V3 | `docker/nginx/default.conf` | `location /admin/` proxifiée vers le backend : l'administration Django serait **publiquement joignable** | Moyenne (sécurité) | Restreindre `/admin/` au niveau de NPM (IP ou authentification) ; le front Vite le bloque déjà en local |
| V4 | `docker/nginx/default.conf` | Aucun `client_max_body_size` → limite nginx par défaut à **1 Mo** | Moyenne | Porter à 20 Mo (photos, justificatifs, imports) |
| V5 | `deploy/production/compose.yml` | `external: ${INJS_NETWORK_EXTERNAL:-false}` — substitution de chaîne | Faible | Valider par `docker compose config` avant `up` |
| V6 | `backend/entrypoint.sh:12` | `gosu` appelé si démarrage en **root**, mais non installé par le Dockerfile | Faible | Ajouter `gosu` aux paquets ou documenter `USER appuser` |
| V7 | `INJS_HOST_MEDIA_DIR=/opt/injs/injs-be/data/media` | L'`appuser` (uid 1000) doit pouvoir écrire dans le répertoire hôte ; sous AlmaLinux, prévoir SELinux (`chcon -Rt container_file_t` ou `:z`) | Moyenne | Vérifier `uid/gid` et contexte SELinux avant le premier démarrage |
| V8 | `.github/workflows/ci.yml:65` | Python **3.11** en CI contre **3.12** dans l'image de production | Moyenne | Aligner (recommandé : CI en 3.12) |
| V9 | `backend/config/settings.py:245` | `POSTGRES_DB` par défaut **`qr_badge`** | Faible | Considérer une erreur explicite si la variable est absente en production |
| V10 | `frontend/dist` | Bundle principal **1 446,63 kB** (349,32 kB gzip), avertissement > 500 kB | Faible | Découpage `manualChunks` |
| V11 | `deploy/production/compose.yml` | Pas de healthcheck sur le service `frontend` | Faible | Ajouter un `wget -q -O- http://127.0.0.1:80/` |
| V12 | `backend/compose.yml` | Pile de **développement** : conteneurs `qr-badge-*`, image `qr-badge-app:local`, port `8001` vs `EXPOSE 8000` | Faible | Nettoyage (hors périmètre production) |
| V13 | `package.json` | Aucun champ `engines` | Faible | Figer `>=20 <23` |
| V14 | Sécurité dépôts | Aucun `.github/dependabot.yml`, pas d'audit CVE exécuté (Python et Node) | Moyenne | Activer Dependabot ; lancer `pip-audit` et `npm audit` sur le VPS |

---

## 3. LISTE DE CONTRÔLE AVANT DÉPLOIEMENT (go / no-go)

À remplir **sur le VPS**, après levée des blocages. Chaque ligne doit être
cochée par une personne identifiée.

### Accès et sauvegarde

- [ ] **B1** Accès au VPS obtenu ; identité de la base confirmée (`SELECT current_database();` → `injs_lmd_prod_20261026`)
- [ ] **B1** `pg_dump -Fc` réalisé et **restauré à blanc** sur une base de test
- [ ] Copie du répertoire média `/opt/injs/injs-be/data/media`
- [ ] **B1** `manage.py showmigrations` relevé et joint au dossier
- [ ] **B1** Rapport `rbac_initialisation` (sans `--apply`) produit : 81 rôles / 22 sensibles / 1 157 permissions

### Code et validation

- [ ] **B5** Test `edt` corrigé ; suite backend **verte** (3 030 tests)
- [ ] **B4** CI verte sur la branche livrée
- [ ] **B3** Workflows `publish-injs-lmd.yml` et `deploy-injs-lmd.yml` présents sur la branche
- [ ] Python de CI aligné sur 3.12 (**V8**)

### Configuration

- [ ] **B2** `SKIP_DB_SETUP` câblé (ou décision tracée d'appliquer les migrations au démarrage)
- [ ] `SECRET_KEY` forte (≥ 50 caractères), hors dépôt
- [ ] `POSTGRES_HOST` / `POSTGRES_DB` / `POSTGRES_PASSWORD` renseignés et vérifiés
- [ ] `REDIS_URL` ajouté au compose si un cache partagé est souhaité
- [ ] **V3** `/admin/` restreint au niveau de Nginx Proxy Manager
- [ ] **V4** `client_max_body_size` ajusté
- [ ] **V2** `X-Forwarded-Proto` relayé
- [ ] **V7** Droits et contexte SELinux du montage média vérifiés

### Images et déploiement

- [ ] **V1** `.dockerignore` en place
- [ ] Images publiées avec un **tag SHA immuable** ; tags reportés dans `deploy/production/.env`
- [ ] `docker compose config` exécuté sans erreur (**V5**)
- [ ] `docker compose pull && up -d`
- [ ] Healthcheck backend vert ; `GET /api/health/` → 200
- [ ] Connexion OK ; parcours Scolarité / Formations / EDT validés
- [ ] `/admin/` inaccessible depuis l'extérieur
- [ ] Nginx Proxy Manager : certificat actif, proxy vers `127.0.0.1:8080`
- [ ] Surveillance des logs 24 h (erreurs 5xx)

### Retour arrière

- [ ] Tags SHA précédents notés (retour arrière par simple changement de tag)
- [ ] Procédure `pg_restore` testée et chronométrée
- [ ] Volumes `media` / `staticfiles` conservés (jamais supprimés par le compose)

---

## 4. CE QUI N'A PAS ÉTÉ FAIT (conformément aux interdictions de la mission)

| Interdiction | Respect |
|---|---|
| Modifier la production | ✅ aucune connexion à la production |
| Construire ou publier des images | ✅ aucun `docker build`, aucun `docker push` |
| Exécuter des migrations en production | ✅ aucune |
| Modifier la base | ✅ aucune |
| Supprimer des fichiers | ✅ aucun (les fichiers temporaires d'investigation ont été supprimés après usage, aucun fichier du dépôt supprimé) |
| Réinitialiser Git / force push | ✅ aucun |
| Modifier les comptes RBAC | ✅ aucun |
| Exécuter `rbac_initialisation --apply` | ✅ jamais (prévisualisation uniquement, sur la base de bac à sable) |
| Annoncer un test réussi sans l'exécuter | ✅ tous les résultats de ce dossier sont des sorties brutes |

**Dépôt** : `git status` vide à l'issue de l'audit — aucune modification, aucun
commit produit par les vérifications.
