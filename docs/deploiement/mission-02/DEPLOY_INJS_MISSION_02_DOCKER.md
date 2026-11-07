# DEPLOY-INJS-2026 — Mission 02 — Docker et démarrage maîtrisé

**Projet :** INJS Abidjan — `backend-injs2026`
**Date du rapport :** 06 novembre 2026
**Périmètre :** blocage **B2** (`SKIP_DB_SETUP`) et §7 (`.dockerignore`)
**Aucune publication d'image, aucun déploiement, aucune opération VPS.**

---

## 1. Blocage B2 — sécurisation du démarrage Django

### 1.1 Mécanisme réellement déclencheur de `manage.py migrate`

Chaîne examinée de bout en bout :

| Élément | Fichier | Rôle |
|---|---|---|
| Image | `backend/Dockerfile` | `ENTRYPOINT ["/app/entrypoint.sh"]`, `USER appuser` |
| Entrée | `backend/entrypoint.sh` | testait `[ "${SKIP_DB_SETUP:-}" = "true" ]` |
| Compose production | `deploy/production/compose.yml` | `SKIP_DB_SETUP: "${SKIP_DB_SETUP:-true}"`, `command: gunicorn …` |
| Compose développement | `backend/compose.yml` | `env_file: .env` — **aucune** variable `SKIP_DB_SETUP` |
| Modèle | `deploy/production/.env.example` | `SKIP_DB_SETUP=true` |
| Script de déploiement | `deploy/production/deploy.sh` | s'appuie sur `SKIP_DB_SETUP=true` pour neutraliser l'entrypoint |

### 1.2 Le défaut constaté (et pourquoi il était grave)

```sh
if [ "${SKIP_DB_SETUP:-}" = "true" ]; then … exec "$@"      # neutre
fi
…
python manage.py migrate --noinput                          # ligne 47 : sinon
```

Conséquences mesurées :

* la transmission de la variable **fonctionnait** dans le compose de production —
  le défaut n'était donc pas là ;
* en revanche **toute valeur autre que la chaîne exacte `true` tombait dans la
  branche `migrate`** : variable absente, `TRUE`, `1`, `yes`, ou une simple faute
  de frappe. Le « comportement par défaut » du système était donc *migrer* ;
* un conteneur lancé hors compose de production (ou avec un `-e` incomplet)
  migrait la base sans que personne ne l'ait demandé.

C'est précisément ce que la mission interdit : « L'absence de variable ne doit
pas provoquer un comportement dangereux. »

### 1.3 Correction apportée

Nouveau fichier : **`backend/scripts/db_setup_policy.sh`** — politique unique,
sourcée par l'entrypoint et par les tests, sans dépendance à Django :

| `SKIP_DB_SETUP` | Mode | Effet |
|---|---|---|
| absent, vide, `true`, `1`, `yes`, `on` | `skip` | **aucune** migration, aucune attente PostgreSQL, aucun superuser |
| `false`, `0`, `no`, `off` | `run` | attente base → `migrate` → `collectstatic` → superuser idempotent |
| toute autre valeur | `invalide` | **arrêt du conteneur, code 64**, aucune commande exécutée |

Normalisation : casse indifférente, espaces ignorés (` " true " ` = `true`).

`backend/entrypoint.sh` a été réécrit en conséquence :

* la politique est résolue **avant toute action** ;
* une valeur inutilisable arrête le conteneur au lieu de choisir un repli ;
* le chemin `gosu` n'est plus exécuté que si `gosu` existe réellement (il
  **manquait dans l'image** alors que l'entrypoint l'appelait : démarrage root
  impossible). `gosu` est désormais installé dans `backend/Dockerfile` ;
* les chemins `media` / `staticfiles` sont paramétrables (`INJS_MEDIA_DIR`,
  `INJS_STATIC_DIR`) afin de rendre l'entrypoint testable hors conteneur.

`backend/Dockerfile` comporte maintenant :

* `gosu` dans les paquets système ;
* `ENV SKIP_DB_SETUP=true` — **valeur par défaut sûre dans l'image** ;
* un garde-fou de construction (`sh -n` sur les trois scripts, présence de la
  politique) : une image sans politique de démarrage ne peut pas être publiée.

### 1.4 Migrations explicites et contrôlées

Nouveau fichier : **`backend/scripts/migrate_explicit.sh`**

```sh
/app/scripts/migrate_explicit.sh --plan     # showmigrations + migrate --plan, n'applique rien
INJS_MIGRATE_ALLOW_APPLY=1 \
/app/scripts/migrate_explicit.sh --apply    # applique, après revue du plan
```

`--apply` sans `INJS_MIGRATE_ALLOW_APPLY=1` est refusé (code 3). Le script ne
contient **aucune** opération destructive (ni `flush`, ni `reset`, ni
suppression de base).

### 1.5 Transmission vérifiée jusqu'au processus exécuté

La transmission n'est pas seulement documentée : elle est **prouvée** par un
journal d'appels. Les tests remplacent `python`, `python3` et `gunicorn` par des
stubs qui enregistrent chaque invocation, puis exécutent le vrai
`backend/entrypoint.sh`. On lit ensuite ce qui a réellement été lancé.

Extrait du résultat (§ voir `DEPLOY_INJS_MISSION_02_TESTS.md`) :

```
== 1. Démarrage avec SKIP_DB_SETUP=true ==
  PASS  aucune migration lancée
== 2. Démarrage SANS variable (défaut sûr) ==
  PASS  aucune migration sans variable
== 3. Démarrage avec variable invalide ==
  PASS  valeur 'oui' -> refus (code 64)
  PASS  valeur 'oui' -> aucune commande exécutée
== 4. Préparation explicitement demandée (SKIP_DB_SETUP=false) ==
  PASS  valeur 'false' -> migrate exécuté explicitement
== 6. Aucune migration implicite en configuration de production ==
  PASS  un seul processus lancé (gunicorn)
RESULTAT B2 : 41 réussis, 0 échecs
```

### 1.6 Effet de bord assumé et traité

La pile de **développement** (`backend/compose.yml`) comptait sur le migrate
automatique. Comme le défaut sûr est désormais « ne pas migrer », elle déclare
explicitement `SKIP_DB_SETUP: 'false'`. Le comportement de développement est
inchangé, mais il est maintenant **écrit** au lieu d'être implicite.

---

## 2. §7 — Fichiers `.dockerignore`

Créés : `backend/.dockerignore`, `frontend/.dockerignore`.

### 2.1 Effet mesuré sur les contextes de build

Mesure par parcours réel du système de fichiers avec application des motifs
(dernière règle gagnante, sémantique Docker) :

| Contexte | Avant | Après | Réduction |
|---|---|---|---|
| `backend/` | **171,1 Mo** | **9,7 Mo** | **−94,3 %** |
| `frontend/` | **246,0 Mo** | **6,8 Mo** | **−97,2 %** |

Ce qui disparaît du contexte : `.venv` (139 Mo), `db.sqlite3` (6,3 Mo),
`node_modules` (257 Mo), `dist`, journaux, caches, archives, `.env`.

### 2.2 Contrôle inverse : rien d'indispensable n'a été exclu

Vérifié fichier par fichier :

| Chemin | État |
|---|---|
| `backend/requirements.txt` | conservé |
| `backend/entrypoint.sh` | conservé |
| `backend/manage.py` | conservé |
| `backend/scripts/db_setup_policy.sh` | conservé |
| `backend/scripts/migrate_explicit.sh` | conservé |
| `backend/scripts/gunicorn-autoscale.sh` | conservé |
| `backend/config/settings.py` | conservé |
| `backend/referentiels/data/` | conservé |
| `backend/scolarite/data/*.json` | conservé |
| `backend/.env.example` | conservé (modèle), `.env` exclu |
| `frontend/package.json`, `package-lock.json` | conservés |
| `frontend/index.html`, `vite.config.js`, `nginx.conf` | conservés |
| `frontend/src/`, `public/` | conservés |

Exclusions confirmées : `.venv`, `db.sqlite3`, `.env`, `.env.production`,
`node_modules`, `dist`.

### 2.3 Limite de vérification, dite explicitement

La sandbox d'exécution **ne dispose pas du moteur Docker** (`docker` absent du
`PATH`, installation système impossible). La construction réelle des deux images
est donc confiée au job `docker` de la CI, qui :

* vérifie la présence et le contenu des `.dockerignore` ;
* analyse `deploy/production/compose.yml` avec `docker compose config` ;
* **construit** les deux images avec `push: false` / `load: false`.

Aucune image n'est publiée : `push: false` est explicite.

---

## 3. Points restant ouverts

| Point | État | Suite |
|---|---|---|
| Construction d'image mesurée en local | **non mesurée** (pas de Docker dans la sandbox) | job CI `docker` |
| `RUN npm ci` dans l'image frontend | inchangé | — |
| Image backend : `gcc` présent au runtime | hérité, non modifié (hors périmètre mission) | à traiter si la taille d'image devient un sujet |
