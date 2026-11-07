# DEPLOY-INJS-2026 — Mission 02 — Décision GO / NO-GO

**Projet :** INJS Abidjan — `backend-injs2026`
**Date :** 06 novembre 2026
**Commit de mission :** `bc6bc88` (branche `arena/d90bca00-backend-injs2026`)
**Run CI de référence :** `42344821705`

---

## 1. Verdict par blocage

| Blocage | Verdict | Preuve |
|---|---|---|
| **B2** — démarrage Django / `SKIP_DB_SETUP` | **LEVÉ** | politique testable ; **41 tests / 0 échec** ; valeur par défaut sûre ; valeur invalide ⇒ arrêt code 64 ; transmission prouvée par journal d'appels de stubs ; job CI `Démarrage conteneur (SKIP_DB_SETUP)` **vert** |
| **B3** — workflows GitHub Actions | **LEVÉ** | les trois workflows étaient déjà identiques à `origin/main` (vérifié par `git diff`) ; risque réel identifié (tag `deploy-*` = publication) et neutralisé par le job `garde` (`INJS_PUBLISH_ENABLED`) |
| **B4** — validation CI | **LEVÉ** | run **42344821705** : **4 jobs sur 4 en succès**, dont `Backend (Django + PostgreSQL, Python 3.12)` — étape « Tests » **success** |
| **B5** — test EDT / KPI | **LEVÉ** | test créé (`dashboard/test_kpi_date_reference.py`) : **6 séances**, **41,7 %**, horloge figée ; **5 tests OK** ; aucun code métier modifié |
| **§7** — `.dockerignore` | **LEVÉ** | backend 171,1 → 9,7 Mo (−94,3 %) ; frontend 246,0 → 6,8 Mo (−97,2 %) ; contrôle inverse fichier par fichier ; **images réellement construites par la CI** |
| **§8** — nginx | **PARTIELLEMENT LEVÉ** | configuration candidate livrée et structurellement validée ; `X-Forwarded-Proto` corrigé, `/admin/` restreint, `client_max_body_size 12m` justifié ; **`nginx -t` et tests HTTPS/upload non exécutés** (environnement) |
| **§9** — Python 3.12 | **LEVÉ** | CI en 3.12 avec assertion `sys.version_info[:2] == (3, 12)` **verte** ; image `python:3.12-slim` ; `pip check` OK |
| **§10** — autonomie | **LEVÉ** | `dossier_trvx` jamais requis à l'exécution ; référentiels JSON présents dans le dépôt ; aucun SYGEP/SYGEF/CPFAE réintroduit ; aucun chemin absolu de poste |

---

## 2. Résultats du run CI `42344821705`

| Job | Conclusion |
|---|---|
| `Démarrage conteneur (SKIP_DB_SETUP)` | **success** |
| `Backend (Django + PostgreSQL, Python 3.12)` | **success** |
| `Frontend (React + Vite)` | **success** |
| `Configuration Docker (validation, sans publication)` | **success** |
| **Run complet** | **completed / success** |

Étapes du job backend, toutes en succès : version Python (3.12), installation,
`pip check`, `manage.py check`, `check --deploy`, `makemigrations --check`,
`check_repo_hygiene`, `collectstatic`, **Tests**. L'étape « Détail des échecs »
est `skipped` — elle ne s'exécute qu'en cas d'échec.

**Preuve de non-publication :** le run n'a produit que les artefacts de test et
de cache de build Docker. Le workflow de publication n'a pas été déclenché, et
le job `garde` interdit par défaut toute construction d'image publiée.

### 2.1 Limite de traçabilité, dite explicitement

Le détail textuel des journaux (`Ran 3 103 tests … OK`) **n'a pas pu être
récupéré** : GitHub sert les journaux et artefacts depuis
`results-receiver.actions.githubusercontent.com` et `*.blob.core.windows.net`,
hôtes inaccessibles depuis cet environnement (`EOF`). Le verdict repose donc sur
le **statut des étapes**, qui est une preuve fiable : une suite en échec fait
échouer l'étape « Tests » et le job.

Chiffres de tests cités dans ce rapport = **exécutions locales** (3 103 backend,
2 216 frontend), et non une lecture du journal CI.

---

## 3. Ce qui n'a pas été fait — et ne devait pas l'être

| Interdit respecté | État |
|---|---|
| Publication d'images Docker | **aucune** |
| Déploiement sur le VPS | **aucun** |
| Modification de PostgreSQL de production | **aucune** |
| Migration sur la base de production | **aucune** |
| Bascule Nginx Proxy Manager | **aucune** |
| Modification des comptes RBAC / des 81 rôles / 1 157 permissions | **aucune** |
| `rbac_initialisation --apply` | **non exécuté** |
| Intégration de `dossier_trvx` | **aucune** |
| Force push, suppression de branche ou de tag | **aucun** |
| Push vers `main` | **aucun** (branche de session uniquement) |
| Écrasement de configuration sans sauvegarde | **aucun** — la configuration nginx candidate est livrée à côté de l'existante, intacte |

La base `injs_lmd_prod_20261026` n'a pas été approchée. **B1 reste une mission
distincte** et n'a pas été contourné.

---

## 4. Anomalies restantes (aucune n'est bloquante pour la mission 03)

1. **`nginx -t` non exécuté** et **tests HTTPS / cookies / CSRF / uploads réels
   non exécutés** : nécessitent le VPS ou le moteur Docker. À faire en mission 03
   *avant* bascule, procédure fournie dans `DEPLOY_INJS_MISSION_02_NGINX.md`.
2. **Avertissement `security.W008` conservé volontairement** : `SECURE_SSL_REDIRECT
   = False`, la redirection étant assurée par NPM ; l'activer côté Django casse
   le CSRF de `/api/scan/`. Documenté, non contourné.
3. **9 tests ignorés (`skipped=9`) dans la suite backend** : ils sont ignorés par
   des décorateurs présents dans le dépôt, pas par cette mission. Ils ne sont
   **pas** comptés comme réussis.
4. **`dossier_trvx` toujours présent dans le dépôt** : il est exclu des contextes
   Docker et n'est requis par aucun chemin d'exécution.
5. **Branche de livraison** : la mission demandait `deploy-injs-2026/mission-02` ;
   la session impose `arena/d90bca00-backend-injs2026`. `ci.yml` couvre déjà
   `deploy-injs-2026/**` pour la suite.
6. **W009 possible en CI** : la clé `DJANGO_SECRET_KEY` du job est une valeur de
   test de 48 caractères ; `check --deploy` la signale selon la version de Django.
   Sans effet en production (clé réelle ≥ 50 caractères exigée par `deploy.sh`).

---

## 5. Décision

**PRÊT POUR LA MISSION 03 — PRÉPARATION DE LA PRODUCTION**

Motif : les conditions 1 à 6 et 8 de clôture sont satisfaites, la condition 7
(nginx) est satisfaite **au niveau de la livraison** (configuration candidate
sécurisée, procédure d'application et de validation écrite) mais **pas au niveau
de l'exécution**, ce qui est précisément l'objet de la mission 03 (environnement
VPS).

### Conditions attachées à cette décision

1. **Aucune publication d'image** n'est autorisée sans action humaine explicite :
   la variable de dépôt `INJS_PUBLISH_ENABLED` reste **absente**.
2. **La configuration nginx candidate ne doit pas être appliquée** sans
   `nginx -t` préalable et sans sauvegarde de la configuration en place.
3. **B1 (accès et état réel de PostgreSQL en production) reste à traiter** en
   mission distincte : aucun contournement n'a été tenté et aucune conclusion
   n'est tirée sur l'état de la base de production.
4. Les limites de vérification listées au §2.1 et au §4 doivent être reprises
   telles quelles dans le dossier de mission 03 : aucune n'est à considérer comme
   déjà couverte.

---

## 6. Formule de clôture

**AUCUNE IMAGE PUBLIÉE — AUCUN DÉPLOIEMENT — AUCUNE MIGRATION DE PRODUCTION —
AUCUNE MODIFICATION DE DONNÉES DE PRODUCTION — AUCUNE OPÉRATION VPS —
AUCUNE BASCULE NGINX.**
