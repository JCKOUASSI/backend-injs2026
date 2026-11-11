# MISSION 02 — RÉCONCILIATION DES WORKFLOWS ET VALIDATION CI

**Date** : 6 novembre 2026 · **Branche** : `arena/4524a57c-backend-injs2026`
**Objet** : blocages **B3** (workflows) et **B4** (validation CI), cohérence
**Python 3.12** (§9).

---

## 1. ÉTAT DES LIEUX (B3)

| Branche | Workflows présents |
|---|---|
| `arena/4524a57c-backend-injs2026` (livraison) | `ci.yml` |
| `origin/main` | `ci.yml`, `publish-injs-lmd.yml`, `deploy-injs-lmd.yml` |

Vérification préalable **avant toute réconciliation** :

```
$ git diff origin/main -- .github/workflows/ci.yml
(aucune différence)
```

Le `ci.yml` de la branche était **identique** à celui de `main` : le rapporter
depuis `main` n'écrase donc aucune modification récente. Les deux workflows
manquants ont été repris **tels quels** depuis `origin/main` (aucune réécriture
de leur logique), avec un ajout de sécurité décrit au §3.

Références vérifiées dans `publish-injs-lmd.yml` : `actions/checkout@v4`,
`docker/setup-buildx-action@v3`, `docker/login-action@v3`,
`docker/build-push-action@v6`, secrets `DOCKERHUB_USERNAME` / `DOCKERHUB_TOKEN`.
Contextes de build : `./backend` et `./frontend` — cohérents avec les
Dockerfiles et avec les `.dockerignore` créés dans cette mission.

## 2. CI RECONFIGURÉE (B4)

Fichier : `.github/workflows/ci.yml` — modifications :

| Point | Avant | Après |
|---|---|---|
| Version Python | `3.11` | **`3.12`** (version de l'image `python:3.12-slim`) |
| Intégrité des dépendances | absente | `pip check` |
| Contrôle de déploiement | `manage.py check` seul | `check` **et** `check --deploy` (hôte `injs.badge-qr-code.pro`) |
| Build frontend | absent | `npm run build` |
| Justifications | — | en-tête documentant les avertissements OpenAPI et le choix `SECURE_SSL_REDIRECT` |

Déjà en place et conservé : `makemigrations --check --dry-run`,
`manage.py check`, `check_repo_hygiene`, `collectstatic`, suite de tests
complète (`manage.py test`) sur **PostgreSQL 16** (moteur de production),
artefact du journal de tests, annotations `::error` des échecs.

### Couverture exigée par la mission

| Exigence | Implémentation |
|---|---|
| Tests backend | `python manage.py test` — **tous** les tests, aucun groupe exclu |
| Vérification des migrations | `makemigrations --check --dry-run` |
| Contrôle des dépendances | `pip check` |
| `check --deploy` | job `backend`, étape dédiée |
| Installation reproductible | `npm ci` (lockfile v3) |
| Tests frontend | `npx vitest run` |
| ESLint | `npm run lint` |
| Build de production | `npm run build` |

**Règle appliquée** : la CI ne sera déclarée verte que si **tous** les tests
sont exécutés et réussis.

### ⚠️ Correction apportée en cours de mission (cause racine de B4)

La première version de ce document supposait qu'un push sur la branche de
livraison déclencherait la CI « via l'événement `pull_request` de la PR #5 ».
**C'était faux, et la vérification l'a démontré** :

```
$ gh run list --branch arena/4524a57c-backend-injs2026
(aucune exécution)
$ gh pr checks 5
no checks reported on the 'arena/4524a57c-backend-injs2026' branch
```

Le motif de déclenchement était `push: branches: [main]` : **aucun push de la
branche de livraison ne déclenchait quoi que ce soit**, et la PR #5 étant en
conflit avec `main`, aucun contrôle n'était remonté. La branche de livraison
n'était donc validée nulle part — c'est le blocage B4.

Correction (commit `cd293ab`) :

```yaml
on:
  push:
    branches: [main, 'arena/**']   # ← motif 'arena/**' ajouté
  pull_request:
  workflow_dispatch:
```

| Déclencheur | Avant | Après |
|---|---|---|
| `push` sur `main` | ✅ | ✅ |
| `push` sur `arena/**` (branche de livraison) | ❌ | ✅ |
| `pull_request` | ✅ | ✅ |
| `workflow_dispatch` | ✅ | ✅ |

## 3. PUBLICATION : GARDE-FOU (mission 02 — aucune publication)

`publish-injs-lmd.yml` est présent mais **ne peut pas se déclencher par
mégarde** :

1. **Déclenchement manuel** : un champ `confirmation` a été ajouté ; les deux
   jobs de construction portent désormais

   ```yaml
   if: >-
     github.event_name == 'push' ||
     inputs.confirmation == 'PUBLIER-IMAGES'
   ```

   Sans `PUBLIER-IMAGES` saisi, le workflow s'arrête **sans rien construire**.
2. **Déclenchement automatique** : limité aux tags `deploy-*` — **aucun tag de
   ce type n'a été créé pendant cette mission** et aucun ne sera poussé sans
   validation humaine.

Tags produits : `<SHA Git complet>` (immuable, traçable au commit) + `stable`
(pointeur de commodité, jamais utilisé seul en production).

`deploy-injs-lmd.yml` (déploiement VPS) est repris à l'identique : déclenchement
**manuel uniquement**, environnement GitHub `production` (approbation requise),
modes `inventaire` / `sauvegarde` / `plan` / `deployer` / `rollback`, avec le mot
de confirmation `DEPLOYER`.

**Aucun des deux workflows n'a été exécuté pendant cette mission.**

## 4. COHÉRENCE PYTHON 3.12 (§9)

| Environnement | Version | Statut |
|---|---|---|
| Image Docker backend | `python:3.12-slim` | ✅ déjà 3.12 |
| CI GitHub Actions | **3.12** | ✅ aligné (modification de cette mission) |
| Environnement de développement de référence | **3.12** déclaré (`backend/.python-version`) | ⚠️ le bac à sable d'audit reste en 3.11.2 |
| Scripts de contrôle | `./arena/tests_par_groupe.sh` (interpréteur du venv) | ✅ inchangé, exécute la même suite |

**Anomalie documentée** : l'environnement d'audit (bac à sable) n'expose que
Python 3.11.2 et l'installation d'un 3.12 y est impossible — le téléchargement
des builds autonomes échoue sur une erreur TLS de l'infrastructure
(`invalid peer certificate: UnknownIssuer` / `tls handshake eof`), le trafic
sortant étant intercepté. La validation 3.12 est donc apportée par
**l'exécution CI réelle** (§5), qui est aussi l'environnement de référence pour
la livraison.

Aucune version de Django ou de dépendance n'a été modifiée : `pip check` ne
signale aucune dépendance cassée et les 30 paquets restent épinglés.

## 5. RÉSULTATS DE L'EXÉCUTION CI

Exécution de référence : **run `43077068460`** — branche
`arena/4524a57c-backend-injs2026`, déclenchée par `push`.

```
✓ arena/4524a57c-backend-injs2026 CI #5 · 43077068460
  conclusion : success

JOBS
✓ Frontend (React + Vite)        in 2m29s
✓ Backend (Django + PostgreSQL)  in 12m5s     ← Python 3.12, PostgreSQL 16
```

| Job | Étapes | Résultat |
|---|---|---|
| **Frontend** | `npm ci` → `npm run lint` → `npx vitest run` → `npm run build` (Node 20) | ✅ 2 min 29 s |
| **Backend** | `check` → `pip check` → `check --deploy` → `makemigrations --check` → `check_repo_hygiene` → `collectstatic` → **suite complète** (`manage.py test`) | ✅ 12 min 5 s |

**Aucun test n'a été ignoré ni exclu** : le job backend exécute
`python manage.py test` sans filtre, sur PostgreSQL 16 (moteur de production),
avec Python **3.12** (version de l'image). La CI est donc **verte** au sens
plein, et la validation 3.12 exigée au §9 est apportée par cette exécution.

### 5.1 Historique des exécutions de la branche

| Run | Déclenchement | Résultat |
|---|---|---|
| `43067954548` | push — **première exécution jamais obtenue sur la branche** | ❌ échec : étape « Hygiène du dépôt », 2 `print()` dans `config/demarrage.py` (garde-fou P00-05) |
| `43068984612` | push après correctif `99491c3` | ⚠️ **annulé** à 50 min par le run suivant (voir §5.2) |
| `43077068460` | push après les livrables | ✅ **succès** — frontend 2 min 29 s, backend 12 min 5 s |

### 5.2 Enseignement opérationnel

`ci.yml` porte `concurrency: { group: ci-${{ github.ref }}, cancel-in-progress: true }` :
**tout push annule l'exécution en cours**. Le run `43068984612` a ainsi été
annulé à 50 min par le push des livrables. À retenir pour la mission 03 : ne
rien pousser pendant qu'une exécution de validation est en cours, sous peine de
perdre ~50 minutes de vérification.
