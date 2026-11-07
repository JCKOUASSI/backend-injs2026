# DEPLOY-INJS-2026 — Mission 02 — CI/CD

**Projet :** INJS Abidjan — `backend-injs2026`
**Date du rapport :** 06 novembre 2026
**Périmètre :** blocages **B3** (réconciliation des workflows), **B4** (validation
CI) et §9 (cohérence Python 3.12)
**Aucune image publiée, aucun déploiement.**

---

## 1. Blocage B3 — état réel, avant toute modification

L'énoncé indiquait : « `publish-injs-lmd.yml` existe sur `origin/main`, mais pas
sur la branche livrée ».

**Vérification effectuée : l'écart n'existe plus.**

```
$ for f in ci.yml deploy-injs-lmd.yml publish-injs-lmd.yml; do
    git diff --quiet origin/main HEAD -- ".github/workflows/$f" && echo "IDENTIQUE $f"; done
IDENTIQUE  ci.yml
IDENTIQUE  deploy-injs-lmd.yml
IDENTIQUE  publish-injs-lmd.yml
```

Les trois workflows sont présents sur la branche et **strictement identiques** à
`origin/main`. La réconciliation demandée était donc déjà faite ; la traiter à
nouveau aurait consisté à réécrire des fichiers identiques.

### 1.1 Ce qui a été vérifié ensuite (le risque réel)

| Point | Constat |
|---|---|
| Dépendances et références des workflows | cohérentes (`actions/checkout@v4`, `setup-python@v5`, `build-push-action@v6`) |
| Contexte de build backend | `./backend` (+ `backend/Dockerfile`) — conforme aux `.dockerignore` créés |
| Contexte de build frontend | `./frontend` (+ `frontend/Dockerfile`) |
| Déclencheurs de publication | `workflow_dispatch` et tag `deploy-*` **uniquement** — pas de `push` de branche |
| Risque de publication accidentelle | **réel** : un tag `deploy-*` poussé par erreur suffisait à publier |

### 1.2 Correction apportée : garde-fou de publication

Ajout d'un job bloquant en tête de `publish-injs-lmd.yml` :

```yaml
jobs:
  garde:
    name: Autorisation de publication
    steps:
      - name: Vérifier l'autorisation explicite
        if: vars.INJS_PUBLISH_ENABLED != 'true'
        run: exit 1
  backend:
    needs: garde
  frontend:
    needs: garde
```

Conséquence : sans la variable de dépôt `INJS_PUBLISH_ENABLED=true`, **rien**
n'est construit ni publié, et **aucun identifiant Docker Hub n'est utilisé**
(le job de connexion n'est jamais atteint). C'est la traduction opérationnelle
de la consigne « publication désactivée pendant cette mission ».

### 1.3 Deux catégories désormais distinctes

| CI (`ci.yml`) | Publication (`publish-injs-lmd.yml`) |
|---|---|
| tests backend, migrations, `pip check`, `check --deploy` | construction des images |
| `npm ci`, Vitest, ESLint, build | publication Docker Hub |
| politique de démarrage B2 | tags **immuables** : `<SHA complet>` + `stable` |
| validation Docker (build sans publication) | déclenchée seulement sur autorisation explicite |

---

## 2. Blocage B4 — CI réellement exécutable sur la branche

### 2.1 Défaut constaté

`ci.yml` ne se déclenchait que sur `push` vers `main` et sur `pull_request`.
Aucune exécution n'était donc possible sur une branche de livraison poussée
directement : c'est exactement l'origine du constat « aucune exécution CI
complète sur la branche livrée ».

### 2.2 Correction

```yaml
on:
  push:
    branches: [main, 'deploy-injs-2026/**', 'arena/**']
  pull_request:
  workflow_dispatch:
```

Les branches de livraison et la branche de session sont désormais couvertes.

### 2.3 Contenu de la CI après modification

| Job | Contenu |
|---|---|
| `politique-base` | `sh -n` sur les 3 scripts + **41 tests** B2 + contrôle `ENV SKIP_DB_SETUP=true` |
| `backend` | Python **3.12**, PostgreSQL 16, `pip check`, `check`, `check --deploy`, `makemigrations --check`, `check_repo_hygiene`, `collectstatic`, suite complète |
| `frontend` | Node 20, `npm ci`, ESLint `--max-warnings 0`, Vitest, `npm run build` |
| `docker` | présence des `.dockerignore`, `docker compose config`, **build** des deux images avec `push: false` |

Ajouts par rapport à l'existant : `pip check`, `check --deploy`, ESLint strict,
build frontend, job Docker, job B2, déclencheur de branche.

### 2.4 Politique sur les avertissements — assume et documenté

`check --deploy` est exécuté avec `--fail-level ERROR` : les **avertissements ne
sont pas tus** (sortie complète conservée dans l'artefact), mais seules les
erreurs bloquent la CI.

Mesure réelle de `check --deploy` dans ce dépôt :

| Configuration | Avertissements |
|---|---|
| locale, `DEBUG=true` (sandbox) | W004, W008, W009, W012, W016, W018 — **artefacts de configuration locale** (clé de bac à sable, DEBUG actif) |
| production, `DEBUG=0` + clé de 60 caractères | **W008 uniquement** |

**W008 (`SECURE_SSL_REDIRECT` non activé) est un choix documenté**, pas un
oubli : `backend/config/settings.py` explique que la redirection HTTP→HTTPS est
assurée par le proxy, et que l'activer côté Django casse le CSRF des endpoints
publics (dont `/api/scan/`). Voir aussi le durcissement proxy de la mission 02
(`DEPLOY_INJS_MISSION_02_NGINX.md`).

---

## 3. §9 — Cohérence Python 3.12

| Environnement | Avant | Après |
|---|---|---|
| Image backend | `python:3.12-slim` | inchangé (**référence**) |
| CI backend | `python-version: '3.11'` | **`'3.12'`** + assertion `sys.version_info[:2] == (3, 12)` |
| Scripts de contrôle | aucun | assertion de version en tête du job backend |

L'assertion empêche une régression silencieuse : si le runner retombait en 3.11,
le job échouerait avec un message explicite au lieu de valider une image qui
n'est pas celle déployée.

### 3.1 Limite de vérification, dite explicitement

La sandbox d'exécution ne propose que **Python 3.11.2** (`/usr/bin/python3.11`,
aucun `python3.12`, installation impossible). Les suites exécutées localement
pendant cette mission l'ont donc été sous 3.11.2 contre la venv `backend/.venv`.

**Conséquence à ne pas masquer :** la validation réelle en 3.12 repose sur
l'exécution CI, dont le résultat est reporté dans
`DEPLOY_INJS_MISSION_02_TESTS.md` et `DEPLOY_INJS_MISSION_02_GO_NO_GO.md`.
Aucune dépendance native n'a été introduite ou modifiée : `psycopg2-binary`,
`pillow`, `reportlab`, `cryptography` étaient déjà épinglées et compatibles 3.12.

---

## 4. Ce qui reste à faire côté CI

| Point | État |
|---|---|
| Exécution CI sur la branche | déclenchée par le push de la branche de livraison — résultat reporté au rapport |
| Publication d'images | **bloquée** par conception (`INJS_PUBLISH_ENABLED`) |
| Secrets Docker Hub | inchangés, jamais lus tant que la publication est bloquée |
| `deploy-injs-lmd.yml` | non modifié — workflow de déploiement manuel, hors périmètre mission 02 |
