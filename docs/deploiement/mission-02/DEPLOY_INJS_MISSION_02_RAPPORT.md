# DEPLOY-INJS-2026 — Mission 02 — Rapport général

**Projet :** INJS Abidjan — `backend-injs2026`
**Mission :** 02 — Levée des blocages pré-déploiement
**Date de référence :** 06 novembre 2026
**Environnement cible :** VPS AlmaLinux — `injs.badge-qr-code.pro`
**Périmètre respecté :** aucune modification de la base de production, aucune
publication d'image, aucun déploiement, aucune opération VPS.

---

## 0. Deux écarts à l'énoncé, signalés d'emblée

### 0.1 Branche de travail

La mission demandait la branche `deploy-injs-2026/mission-02`. Cette session est
liée à la branche **`arena/d90bca00-backend-injs2026`** : il est impossible d'en
créer ou d'en changer sans perdre le suivi du travail. **Tout a donc été réalisé
sur la branche de session**, qui contient le commit de livraison.

Le `ci.yml` a été étendu pour couvrir aussi `deploy-injs-2026/**` : le jour où
cette branche existera, elle sera testée sans autre modification.

### 0.2 Deux constats de l'audit ne correspondaient plus au code réel

| Blocage | Énoncé | Réalité constatée |
|---|---|---|
| **B3** | `publish-injs-lmd.yml` absent de la branche | **présent et identique à `origin/main`** |
| **B5** | le test `test_seances_aujourdhui_et_kpi_reellement_mesures` échoue | **ce test n'existe pas** dans le dépôt ; le défaut de dépendance à l'horloge, lui, est réel |

Ces deux points ne sont pas contournés : ils sont traités sur le fond (garde-fou
de publication, création du test manquant à l'identique), et l'écart est
documenté plutôt que masqué.

---

## 1. Fichiers créés

| Fichier | Objet |
|---|---|
| `backend/scripts/db_setup_policy.sh` | politique unique de préparation de base (B2) |
| `backend/scripts/migrate_explicit.sh` | migrations explicites `--plan` / `--apply` |
| `backend/docker_tests/db_setup_policy_test.sh` | 41 tests B2, stubs journalisés |
| `backend/dashboard/test_kpi_date_reference.py` | test B5 à date figée (6 séances, 41,7 %) |
| `backend/.dockerignore` | contexte de build backend |
| `frontend/.dockerignore` | contexte de build frontend |
| `deploy/production/nginx/injs-lmd.candidate.conf` | configuration nginx candidate |
| `deploy/production/nginx/injs-admin-allowlist.conf.example` | modèle de liste d'accès `/admin/` |
| `docs/deploiement/mission-02/*.md` | les six livrables de cette mission |

## 2. Fichiers modifiés

| Fichier | Modification |
|---|---|
| `backend/entrypoint.sh` | politique B2 en tête, gosu conditionnel, chemins paramétrables |
| `backend/Dockerfile` | `gosu`, `ENV SKIP_DB_SETUP=true`, garde-fou de construction |
| `backend/compose.yml` | `SKIP_DB_SETUP: 'false'` explicite (pile de dev) |
| `deploy/production/compose.yml` | commentaire de politique à jour (valeur inchangée) |
| `deploy/production/.env.example` | sémantique complète de `SKIP_DB_SETUP` |
| `.github/workflows/ci.yml` | Python 3.12, `pip check`, `check --deploy`, ESLint strict, build FE, job Docker, job B2, déclencheurs |
| `.github/workflows/publish-injs-lmd.yml` | job `garde` (publication interdite par défaut) |
| `frontend/src/components/generique/EcranRessource.jsx` | `lignes` mémorisé (`useMemo`) |
| `frontend/src/pages/scolarite/Groupes.jsx` | `actif` → `_actif` (exclusion volontaire, commentée) |
| `frontend/src/pages/scolarite/JournalScolarite.jsx` | `auditCharge` → `_auditCharge` |
| `frontend/src/pages/scolarite/Candidatures.jsx` | import `useRef` inutilisé retiré |
| `frontend/src/pages/getinjs/GetInjsApp.test.jsx` | imports inutilisés retirés |
| `frontend/src/pages/scolarite/DocumentsScolaires.test.jsx` | import `waitFor` inutilisé retiré |

## 3. Fichiers supprimés

**Aucun.** Cette mission n'a supprimé ni fichier ni donnée. Aucun test n'a été
désactivé, aucun groupe de tests n'a été exclu de la CI.

---

## 4. Résultats des tests (réels)

| Contrôle | Résultat |
|---|---|
| Tests backend | **3 103 tests — OK (9 ignorés, 0 échec)** — 983 s |
| Tests groupe EDT | **496 tests — OK** — 108 s |
| Test B5 isolé | **5 tests — OK** |
| Tests frontend (Vitest) | **141 fichiers / 2 216 tests — 0 échec** |
| ESLint | **0 erreur, 0 avertissement** |
| Build frontend | **réussi** (388 modules) |
| `pip check` | **0 dépendance cassée** |
| `manage.py check` | **aucun problème** |
| `check --deploy` (production) | **1 avertissement : W008, choix documenté** |
| `makemigrations --check` | **aucune modification détectée** |
| `check_repo_hygiene` | **CONFORME** (2 409 fichiers suivis) |
| Politique B2 | **41 réussis / 0 échec** |

Détail complet : `DEPLOY_INJS_MISSION_02_TESTS.md`.

---

## 5. Commits et état de la branche

| Élément | Valeur |
|---|---|
| Branche | `arena/d90bca00-backend-injs2026` |
| Commit de mission (code) | `bc6bc88` — `fix(deploy): mission 02 — B2, B3, B4, B5, dockerignore, nginx candidat, CI 3.12` |
| Commit documentaire | voir `git log` (les six livrables de ce dossier) |
| Commit parent | `bfdfc64` (livrable H5) |
| Push | branche de session **uniquement** — aucun push vers `main` |
| Fichiers dans le commit | 25 (1 820 insertions, 47 suppressions) |
| `docs/audits/sql/run_audit.sh` | **intact** (blob `3c83f570…` inchangé) |
| Livrables H7.21 | **hors commit**, non publiés (publication non autorisée) |
| Force push / rebase / reset | **aucun** |

État de la CI : **run `42344821705` — 4 jobs sur 4 en succès**, backend en
Python 3.12 + PostgreSQL. Détail et limites de traçabilité :
`DEPLOY_INJS_MISSION_02_GO_NO_GO.md`.

---

## 6. Les huit conditions de clôture

| # | Condition | État |
|---|---|---|
| 1 | B2 corrigé et testé | **LEVÉ** — 41 tests, transmission prouvée |
| 2 | B3 résolu | **LEVÉ** — écart inexistant + garde-fou de publication ajouté |
| 3 | B4 validé par une exécution CI réelle | **LEVÉ** — run `42344821705`, 4/4 jobs verts |
| 4 | B5 corrigé sans modification du métier | **LEVÉ** — test créé, code métier intact |
| 5 | `.dockerignore` opérationnels | **LEVÉ** — −94,3 % / −97,2 %, contrôle inverse effectué |
| 6 | Python 3.12 partout | **LEVÉ côté configuration** — CI 3.12 + image 3.12 ; exécution réelle en CI |
| 7 | Configuration nginx candidate sécurisée | **PARTIEL** — candidate livrée, `nginx -t` et tests HTTPS à faire en mission 03 |
| 8 | Aucun élément de `dossier_trvx` requis à l'exécution | **LEVÉ** — vérifié fichier par fichier |

---

## 7. Anomalies restantes, sans complaisance

1. **Python 3.12 non exécutable dans la sandbox** (seul 3.11.2 disponible). Les
   suites locales valident le code, pas l'interpréteur de production. La
   validation 3.12 repose sur la CI.
2. **Moteur Docker absent de la sandbox** : les images n'ont pas été construites
   localement ; c'est le job CI `docker` qui le fait (`push: false`).
3. **`nginx -t` non exécuté** : le binaire n'existe pas dans la sandbox. La
   configuration candidate n'a été validée que structurellement (accolades,
   blocs, directives clés).
4. **Avertissement W008 conservé volontairement** (`SECURE_SSL_REDIRECT=False`) :
   la redirection est assurée par le proxy ; l'activer côté Django casse le CSRF
   de `/api/scan/`.
5. **`skipped=9` dans la suite backend** : ces tests sont ignorés par des
   décorateurs du dépôt (`skipUnless`/conditions d'environnement), pas par la
   mission. Ils ne sont pas comptés comme réussis.
6. **`dossier_trvx` reste dans le dépôt** (interdit de l'intégrer au périmètre
   livré) : il est exclu des contextes Docker et n'est référencé que par des
   docstrings et un script d'extraction hors exécution.
7. **`deploy-injs-lmd.yml`** n'a pas été modifié : il reste un workflow de
   déploiement manuel, hors périmètre de cette mission.
