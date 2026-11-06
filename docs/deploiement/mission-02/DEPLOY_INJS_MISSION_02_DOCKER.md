# MISSION 02 — DÉMARRAGE DOCKER MAÎTRISÉ ET CONTEXTES DE BUILD

**Date** : 6 novembre 2026 · **Branche** : `arena/4524a57c-backend-injs2026`
**Objet** : blocage **B2** (migrations implicites au démarrage) et création des
`.dockerignore` (§7 de la mission).

---

## 1. MÉCANISME QUI DÉCLENCHAIT `manage.py migrate`

Chaîne d'exécution réelle, reconstituée pièce par pièce :

```
docker compose up  (deploy/production/compose.yml)
   └─ service backend : entrypoint = /app/entrypoint.sh
        └─ entrypoint.sh :
             if [ "${SKIP_DB_SETUP:-}" = "true" ]; then exec "$@"; fi   ← jamais vrai
             ...
             python manage.py migrate --noinput      ← exécuté
             python manage.py collectstatic --noinput
             [création du superutilisateur si DJANGO_SUPERUSER_* définis]
```

**Pourquoi la variable n'atteignait jamais le processus**

| Élément | Constat |
|---|---|
| `deploy/production/.env.example` | déclare `SKIP_DB_SETUP=true` |
| `deploy/production/compose.yml` — bloc `environment:` du service `backend` | **ne mentionne pas** `SKIP_DB_SETUP` |
| `env_file:` dans le compose | **absent** |
| Conséquence | la variable du fichier `.env` n'est jamais injectée dans le conteneur : elle ne sert qu'à l'interpolation `${…}` du compose, encore faut-il qu'elle y soit référencée |

Le défaut de l'entrypoint (`SKIP_DB_SETUP` absent ⇒ migrations appliquées)
était donc **toujours** celui retenu en production : `migrate` s'exécutait à
chaque démarrage, sans validation humaine et sans sauvegarde garantie.

## 2. DISPOSITIF CORRIGÉ

### 2.1 La décision sort du shell et devient testable

**Fichier créé** : `backend/config/demarrage.py`

Module **sans aucune dépendance à Django** (exécutable avant le chargement des
réglages, `SECRET_KEY` absente comprise). Il expose :

* `analyser_environnement(environ)` → `Decision` (fonction **pure**) ;
* `python3 -m config.demarrage` → codes de sortie exploitables par le shell.

| Code | Signification |
|---|---|
| `0` | **sans migration** — démarrage direct |
| `10` | **avec migrations** — demande explicite (`SKIP_DB_SETUP=false`) |
| `2` | **erreur de configuration** — valeur invalide ⇒ arrêt du conteneur |

**Table de décision** (comparaison insensible à la casse, espaces ignorés)

| `SKIP_DB_SETUP` | Code | Comportement |
|---|---|---|
| `true` / `1` / `yes` / `on` / `oui` | `0` | aucune migration, aucun collectstatic |
| **absente ou vide** | `0` | **défaut sûr** : aucune migration + avertissement explicite |
| `false` / `0` / `no` / `off` / `non` | `10` | migrations + collectstatic **explicites** |
| toute autre valeur | `2` | arrêt immédiat, aucun comportement implicite |

Principe directeur : **oublier la variable ne peut jamais déclencher une
migration.** Une migration suppose une demande explicite et contraire.

### 2.2 `backend/entrypoint.sh` (modifié)

L'entrypoint ne décide plus : il **exécute** la décision.

```sh
set +e
python3 -m config.demarrage
CODE_DEMARRAGE=$?
set -e

case "$CODE_DEMARRAGE" in
  0)  # défaut sûr : exec "$@" (ou erreur si aucune commande)
  10) # attente PostgreSQL, migrate, collectstatic, superuser éventuel
  *)  # arrêt : configuration invalide
esac
```

Améliorations annexes :
* démarrage en **root** : message d'erreur explicite si `gosu` est absent
  (au lieu d'un énigmatique `gosu: not found`) ;
* la création du superutilisateur reste conditionnée à `DJANGO_SUPERUSER_EMAIL`
  **et** `DJANGO_SUPERUSER_PASSWORD`, désormais confinée à la branche
  « migrations explicites ».

### 2.3 Transmission effective (compose)

**`deploy/production/compose.yml`** — service `backend`, bloc `environment:` :

```yaml
      SKIP_DB_SETUP: "${SKIP_DB_SETUP:-true}"     # défaut sûr
      REDIS_URL: "${REDIS_URL:-}"
      BADGE_BASE_URL: "${BADGE_BASE_URL:-}"
      PUBLIC_APP_URL: "${PUBLIC_APP_URL:-}"
      # DJANGO_SUPERUSER_* volontairement NON transmis : aucun superutilisateur
      # créé automatiquement en production.
```

**`backend/compose.yml`** (pile de **développement**) — comportement historique
conservé, mais désormais **explicite** : `SKIP_DB_SETUP: "false"`.

### 2.4 Exécuter les migrations séparément, explicitement, sous contrôle

Procédure recommandée en production (aucune migration implicite) :

```bash
# 0. Sauvegarde OBLIGATOIRE avant toute migration
pg_dump -Fc injs_lmd_prod_20261026 > injs_avant_migration_$(date +%F).dump

# 1. Voir le plan sans rien appliquer
docker compose -f deploy/production/compose.yml --env-file deploy/production/.env \
  run --rm -e SKIP_DB_SETUP=true backend python manage.py migrate --plan

# 2. Appliquer (étape explicite et supervisée)
docker compose -f deploy/production/compose.yml --env-file deploy/production/.env \
  run --rm -e SKIP_DB_SETUP=true backend python manage.py migrate --noinput
```

`SKIP_DB_SETUP=true` garantit que l'entrypoint **exécute directement** la
commande fournie, sans aucune migration implicite préalable.

## 3. TESTS AUTOMATISÉS (B2)

**Fichier créé** : `backend/config/tests/test_demarrage.py` — **23 tests**, tous
au vert (`Ran 23 tests — OK`).

| Scénario exigé | Couverture | Résultat |
|---|---|---|
| 1. Démarrage avec `SKIP_DB_SETUP=true` | `DecisionSansMigrationTests` (+ 7 variantes `1/yes/on/oui/TRUE…`) | ✅ code 0 |
| 2. Démarrage sans variable | `DecisionSansVariableTests` — défaut sûr, et l'absence n'est **pas** traitée comme `false` | ✅ code 0 |
| 3. Démarrage avec valeur invalide | `DecisionInvalideTests` — 5 valeurs (`peut-etre`, `2`, `TRUEISH`, `null`, `enabled`) | ✅ code 2, arrêt |
| 4. Exécution explicite des migrations | `DecisionMigrationsExplicitesTests` — `false/0/no/off/non` | ✅ code 10 |
| 5. Aucune migration implicite en production | `TransmissionComposeTests` — le compose est **analysé** (YAML), `SKIP_DB_SETUP` doit valoir `${SKIP_DB_SETUP:-true}`, puis l'environnement résolu est soumis à la décision | ✅ code 0 |

**Vérification de la transmission « jusqu'au processus »** (au-delà de la
documentation) — trois niveaux :

1. **Statique** : le YAML du compose est chargé et la clé vérifiée dans le bloc
   `environment:` du service `backend` ; le montage et la valeur par défaut
   sont contrôlés.
2. **Dynamique** : `LigneDeCommandeTests` exécute **en sous-processus** la
   commande exacte de l'entrypoint (`python3 -m config.demarrage`) avec
   l'environnement simulé, et vérifie les codes de sortie `0 / 0 / 2 / 10`.
3. **Câblage** : `CablageEntrypointTests` vérifie que `entrypoint.sh` appelle
   bien le module, que `manage.py migrate` n'apparaît plus
   inconditionnellement, et que les trois codes sont traités.

> **Limite assumée** : Docker n'est pas disponible dans l'environnement
> d'audit. Le contrôle ultime — « le conteneur démarre-t-il sans migrer ? » —
> fait partie de la procédure VPS (§5).

## 4. `.dockerignore` (§7)

**Fichiers créés** : `backend/.dockerignore`, `frontend/.dockerignore`

Exclus dans les deux contextes : `.git`, `.venv` / `venv`, `node_modules`,
`__pycache__`, `*.py[cod]`, `db.sqlite3` (`*.sqlite3`, `*.db`), sauvegardes
(`backups/`, `*.bak`, `*.old`), fichiers temporaires (`*.tmp`, `*.swp`, `*~`),
rapports de couverture (`htmlcov/`, `.coverage`, `coverage.xml`), fichiers
`.env` et secrets (`*.pem`, `*.key`, `id_rsa*`, `secrets/`), archives de
travail (`dossier_trvx/`).
Spécifique backend : `media/`, `staticfiles/` (recréés à l'exécution).
Spécifique frontend : `dist`, `dist-ssr`, `.vite`, `coverage/`.

**Comparaison des contextes** (mesurée avec un script appliquant les règles du
`.dockerignore`, fichier par fichier)

| Contexte | Avant | Après | Gain |
|---|---:|---:|---|
| `backend/` | 12 495 fichiers — **161,8 Mio** | 1 165 fichiers — **8,8 Mio** | **−153,0 Mio (−94,6 %)** |
| `frontend/` | 19 679 fichiers — **218,9 Mio** | 402 fichiers — **5,9 Mio** | **−213,0 Mio (−97,3 %)** |

**Aucun fichier nécessaire n'est exclu** — contrôle automatisé sur :
`manage.py`, `requirements.txt`, `entrypoint.sh`, `scripts/gunicorn-autoscale.sh`,
`config/settings.py`, `config/urls.py`, `config/demarrage.py`,
`scolarite/data/complement_referentiel_lmd_pdf.json`,
`habilitations/referentiel/catalogue_roles.py`,
`edts/management/commands/seed_edt_demo.py` (backend) ;
`package.json`, `package-lock.json`, `index.html`, `vite.config.js`,
`nginx.conf`, `src/main.jsx` (frontend) → **10/10 et 6/6 présents**.

En CI (checkout propre, sans `.venv` ni `node_modules`), le gain est nul mais
la protection reste utile : elle empêche qu'un build **local** n'embarque la
base SQLite de développement et ses empreintes de mots de passe.

## 5. PROCÉDURE DE VALIDATION SUR LE VPS (non exécutée ici)

```bash
# 1. Validation de la configuration Compose (substitutions comprises)
docker compose -f deploy/production/compose.yml --env-file deploy/production/.env config

# 2. Vérifier la valeur effectivement transmise au conteneur
docker compose -f deploy/production/compose.yml --env-file deploy/production/.env \
  run --rm backend env | grep SKIP_DB_SETUP          # attendu : SKIP_DB_SETUP=true

# 3. Démarrer SANS migration et vérifier l'absence d'écriture en base
docker compose -f deploy/production/compose.yml --env-file deploy/production/.env up -d backend
docker compose -f deploy/production/compose.yml logs backend | grep -i "migrate"
   # attendu : « SKIP_DB_SETUP exec: gunicorn … » et AUCUNE ligne « Applying … »

# 4. Tester la détection d'une valeur invalide (doit refuser de démarrer)
SKIP_DB_SETUP=peut-etre docker compose -f deploy/production/compose.yml up backend
   # attendu : « ERREUR … valeur invalide » puis arrêt (code 2)

# 5. Construire les images et constater la taille du contexte
docker build --no-cache ./backend 2>&1 | grep -i "transferring context"
```

## 6. FICHIERS

| Fichier | Statut |
|---|---|
| `backend/config/demarrage.py` | **créé** — décision de démarrage pure et testable |
| `backend/config/tests/test_demarrage.py` | **créé** — 23 tests |
| `backend/entrypoint.sh` | **modifié** — délègue la décision, gère les 3 codes, erreur `gosu` explicite |
| `deploy/production/compose.yml` | **modifié** — transmission de `SKIP_DB_SETUP` (+ `REDIS_URL`, `BADGE_BASE_URL`, `PUBLIC_APP_URL`) |
| `backend/compose.yml` | **modifié** — `SKIP_DB_SETUP=false` explicite (développement) |
| `backend/.dockerignore` | **créé** |
| `frontend/.dockerignore` | **créé** |

Aucun fichier supprimé.
