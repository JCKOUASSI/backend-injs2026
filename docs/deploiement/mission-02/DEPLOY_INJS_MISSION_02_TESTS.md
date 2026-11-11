# MISSION 02 — RÉSULTATS DES TESTS

**Date** : 6 novembre 2026 · **Branche** : `arena/4524a57c-backend-injs2026`
**Règle** : aucun test n'est déclaré réussi sans avoir été réellement exécuté.
Toutes les sorties ci-dessous sont des résultats bruts.

---

## 1. VUE D'ENSEMBLE

| Contrôle | Attendu | Obtenu | Statut |
|---|---|---|---|
| Tests backend (suite complète) | 100 % réussis | **3 066 tests — 9 groupes — 0 échec** | ✅ |
| Tests EDT | 100 % réussis | **591 tests — 0 échec** | ✅ |
| Tests frontend | 100 % réussis | **131 fichiers / 2 167 tests — 0 échec** | ✅ |
| ESLint | 0 erreur | **0 erreur**, 6 avertissements | ✅ |
| Build frontend | réussi | **réussi** (4,23 s) | ✅ |
| Python 3.12 | confirmé | **CI GitHub : 3.12 ✅** · bac à sable : 3.11.2 (installation impossible) | ⚠️ |
| `pip check` | 0 dépendance cassée | **No broken requirements found.** | ✅ |
| `makemigrations --check` | aucune modification | **No changes detected** | ✅ |
| `check --deploy` | documenté | **0 erreur** — 1 117 avertissements justifiés | ✅ |
| `SKIP_DB_SETUP` | transmission vérifiée | **23 tests** (analyse du compose + exécution en sous-processus) | ✅ |
| Configuration Nginx | validée | **13 tests** + `check_repo_hygiene` | ✅ |
| CI de la branche | verte | voir §6 | ⏳ / ✅ |

---

## 2. BACKEND — SUITE COMPLÈTE (locale, exécutée)

**Commande** : `./arena/tests_par_groupe.sh` — 9 groupes, base de test isolée.

```
GROUPE       RÉSULTAT  DÉTAIL
------------------------------------------------------------
scolarite    RÉUSSI    151s | Ran 515 tests in 99.643s
formations   RÉUSSI    101s | Ran 289 tests in 51.373s
auth         RÉUSSI    142s | Ran 242 tests in 94.757s
habilitations RÉUSSI   263s | Ran 520 tests in 210.391s
edt          RÉUSSI    171s | Ran 591 tests in 115.959s
evaluations  RÉUSSI    115s | Ran 237 tests in 64.416s
pilotage     RÉUSSI    74s  | Ran 245 tests in 20.316s
socle        RÉUSSI    134s | Ran 275 tests in 83.974s
divers       RÉUSSI    76s  | Ran 152 tests in 23.121s
------------------------------------------------------------
```

| Indicateur | Valeur |
|---|---:|
| Tests exécutés | **3 066** |
| Groupes verts | **9 / 9** |
| Échecs | **0** |
| Durée cumulée | ~20 min |
| Code de sortie du script | **0** |

Évolution par rapport à l'audit du 6 novembre : **3 030 → 3 066 tests**
(+36 : 23 tests de démarrage B2 + 13 tests Nginx). Le groupe `pilotage`
passe de 209 à 245 tests pour la même raison.

---

## 3. B5 — TEST EDT (corrigé, sans toucher au métier)

### 3.1 Test isolé

```
$ manage.py test edts.tests.test_seed_edt_demo.SeedEdtDemoTests\
    .test_seances_aujourdhui_et_kpi_reellement_mesures

Ran 1 test in 0.786s
OK
```

### 3.2 Groupe EDT complet

```
edt    RÉUSSI    171s | Ran 591 tests in 115.959s
```

### 3.3 Ce qui a changé

Fichier modifié : **`backend/edts/tests/test_seed_edt_demo.py` uniquement**.
Aucun fichier métier touché (`dashboard/services.py` et les commandes de semis
sont inchangés — vérifiable par `git show --stat 3e5aad2`).

Le tableau de bord est désormais évalué **dans le même contexte temporel** que
les données semées (date de référence déterministe 2026-11-03). Le test vérifie
les **6 séances attendues** et le taux d'assiduité **41,7**.

> Note technique : le semis reste **hors** patch de `localdate`. Figer
> `localdate` pendant le semis ne mesurerait que 3 séances (83,3 %) au lieu de
> 6 (41,7 %), ce qui affaiblirait la vérification au lieu de la corriger.

### 3.4 Preuve de non-régression

Le comportement du service reste celui mesuré lors de l'audit (contrat
« un taux sans dénominateur vaut `None` » documenté dans
`dashboard/services.py`) : rien n'a été modifié pour « faire passer » le test.

---

## 4. B2 — TESTS DU DÉMARRAGE (23 tests)

```
$ manage.py test config.tests.test_demarrage
Ran 23 tests in 0.144s
OK
```

| Scénario exigé | Couverture |
|---|---|
| Démarrage avec `SKIP_DB_SETUP=true` | ✅ aucune migration, code de sortie 0 |
| Démarrage **sans** variable | ✅ **défaut sûr** : aucune migration, avertissement explicite, code 0 |
| Démarrage avec valeur **invalide** | ✅ arrêt du conteneur, code 2, aucune action implicite |
| Exécution **explicite** des migrations | ✅ `SKIP_DB_SETUP=false` → code 10, migrations + collectstatic |
| Aucune migration implicite en production | ✅ vérifié par **analyse du YAML du compose** (la variable figure bien dans `environment:` du service `backend`) **et** par exécution en sous-processus de la commande réellement appelée par l'entrypoint |

Le mécanisme est porté par `backend/config/demarrage.py` (fonction pure, sans
dépendance Django) ; `backend/entrypoint.sh` délègue la décision et gère les
trois codes de sortie.

---

## 5. NGINX — TESTS DE LA CONFIGURATION CANDIDATE (13 tests)

```
$ manage.py test config.tests.test_nginx_gateway
Ran 13 tests in 0.008s
OK
```

Couverture : relais de `X-Forwarded-Proto` (aucun écrasement par `$scheme`),
fermeture de `/admin/` par défaut (`deny all`), `client_max_body_size`
explicitement défini, préservation des routes `/api/`, `/static/` et `/media/`.
Détail et justification des valeurs : `DEPLOY_INJS_MISSION_02_NGINX.md`.

---

## 6. FRONTEND

### 6.1 Local (bac à sable)

```
$ npm run test:run
 Test Files  131 passed (131)
      Tests  2167 passed (2167)

$ npm run lint
✖ 6 problems (0 errors, 6 warnings)

$ npm run build
✓ built in 4.23s
```

Installation reproductible vérifiée au préalable : `npm ci` → 518 paquets
(lockfile v3, 568 entrées, cohérent avec `package.json`).

### 6.2 CI GitHub Actions (job `Frontend`)

```
✓ Frontend (React + Vite) in 2m25s   (Node 20)
```

Ce job enchaîne `npm ci` → `npm run lint` → `npx vitest run` → `npm run build`
sur un runners propre. **Vert.**

---

## 7. CONTRÔLES STATIQUES

| Contrôle | Commande | Résultat |
|---|---|---|
| Dépendances Python | `python -m pip check` | `No broken requirements found.` |
| Migrations | `makemigrations --check --dry-run` | `No changes detected` |
| Déploiement | `manage.py check --deploy` | `System check identified 1117 issues (0 silenced)` — **0 erreur** |
| Hygiène du dépôt | `manage.py check_repo_hygiene` | **CONFORME** — 2 261 fichiers suivis vérifiés |

### 7.1 Détail des 1 117 avertissements `check --deploy`

| Code | Nombre | Justification |
|---|---:|---|
| `drf_spectacular.W001` | 610 | Infos de type non résolues sur des serializers — **schéma OpenAPI uniquement**, aucun impact à l'exécution |
| `drf_spectacular.W002` | 506 | Serializer non inférable sur des `APIView` — **schéma OpenAPI uniquement** |
| `security.W008` | 1 | `SECURE_SSL_REDIRECT` non activé — **choix volontaire** : le TLS est terminé par Nginx Proxy Manager, `SECURE_PROXY_SSL_HEADER` est configuré et les cookies sont sécurisés. Activer la redirection provoquerait une boucle derrière le proxy |

Ces trois familles sont reprises dans l'en-tête de `ci.yml` afin que tout
lecteur de la CI comprenne pourquoi ils sont tolérés.

---

## 8. CI DE LA BRANCHE (B4)

Voir `DEPLOY_INJS_MISSION_02_CI_CD.md` §5 pour le résultat final.
Deux exécutions ont eu lieu sur la branche :

| Run | Déclenchement | Résultat |
|---|---|---|
| `43067954548` | push (premier déclenchement possible de la branche) | ❌ **échec** — étape « Hygiène du dépôt » : 2 `print()` dans `config/demarrage.py` (garde-fou P00-05) |
| `43068984612` | push (après correction) | ✅ frontend vert (2 min 25 s) · backend : voir CI_CD §5 |

**Le premier échec est une preuve de fonctionnement de la CI** : le garde-fou
d'hygiène du dépôt a bien bloqué le code que la mission 02 venait d'ajouter.
Correctif apporté dans le commit `99491c3` (écriture sur `sys.stdout`/`sys.stderr`
sans `print()`), contrôle `check_repo_hygiene` repassé en local : **CONFORME**.

---

## 9. CE QUI N'A PAS PU ÊTRE EXÉCUTÉ (à documenter, non masqué)

| Vérification | Raison | Report |
|---|---|---|
| Suite backend sur **Python 3.12** en local | l'installation d'un CPython 3.12 est impossible dans le bac à sable : `uv` échoue sur `invalid peer certificate: UnknownIssuer` et `curl` sur `SSL_ERROR_SYSCALL` vers `release-assets.githubusercontent.com` (hôte non autorisé) | la CI GitHub couvre 3.12 (voir CI_CD §5) |
| `nginx -t` sur la configuration candidate | aucun binaire nginx dans l'environnement d'audit | mission 03, sur le VPS |
| Validation dynamique HTTPS / CSRF / cookies | nécessite le serveur et le domaine | mission 03, après application de la configuration candidate |
| Vérification de l'état des migrations en production | base `injs_lmd_prod_20261026` non joignable (B1, hors périmètre) | mission VPS distincte |
