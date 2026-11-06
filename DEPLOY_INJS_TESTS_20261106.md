# PREUVES D'EXÉCUTION DES TESTS — 6 novembre 2026

**Branche** : `arena/4524a57c-backend-injs2026` · **Commit** : `7c9d56a`
**Règle appliquée** : aucun test n'est annoncé réussi sans avoir été réellement
exécuté ; tous les résultats ci-dessous sont des sorties brutes.

---

## 1. BACKEND — suite complète

**Commande** : `./arena/tests_par_groupe.sh` (base de test isolée, `STORAGES=STORAGE_DE_TEST`)

```
GROUPE       RÉSULTAT  DÉTAIL
------------------------------------------------------------
scolarite    RÉUSSI    153s | Ran 515 tests in 100.559s
formations   RÉUSSI    106s | Ran 289 tests in 53.642s
auth         RÉUSSI    153s | Ran 242 tests in 102.892s
habilitations RÉUSSI   283s | Ran 520 tests in 230.519s
edt          ÉCHOUÉ   182s | Ran 591 tests in 125.410s
evaluations  RÉUSSI    119s | Ran 237 tests in 66.825s
pilotage     RÉUSSI    71s  | Ran 209 tests in 20.518s
socle        RÉUSSI    137s | Ran 275 tests in 84.812s
divers       RÉUSSI    75s  | Ran 152 tests in 22.904s
------------------------------------------------------------
```

| Indicateur | Valeur |
|---|---:|
| Tests exécutés | **3 030** |
| Groupes verts | 8 / 9 |
| Échecs | **1** |
| Durée cumulée | ~21 minutes |
| Code de sortie du script | **1** |

Journaux complets : `/tmp/injs-validation/<groupe>.log`.

---

## 2. L'ÉCHEC : `edt` — analyse complète

### 2.1 Traceback (sortie brute)

```
FAIL: test_seances_aujourdhui_et_kpi_reellement_mesures
      (edts.tests.test_seed_edt_demo.SeedEdtDemoTests)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/home/user/backend-injs2026/backend/edts/tests/test_seed_edt_demo.py", line 139, in
    test_seances_aujourdhui_et_kpi_reellement_mesures
    self.assertIsNotNone(res.data['kpis']['taux_assiduite_moyen'])
AssertionError: unexpectedly None

Ran 591 tests in 125.410s
FAILED (failures=1)
```

### 2.2 Mécanisme

Le test fige la date du **jeu de démonstration** :

```python
NOW = datetime(2026, 11, 3, 12, tzinfo=dt_timezone.utc)
COMMAND = 'edts.management.commands.seed_edt_demo.timezone.now'   # seul patch
...
with patch(COMMAND, return_value=NOW):
    res = client.get('/api/presences/seances-edt/supervision/', {'date': '2026-11-03'})
...
res = client.get('/api/dashboard/presences/')      # ← AUCUN patch de date ici
self.assertIsNotNone(res.data['kpis']['taux_assiduite_moyen'])
```

Or `dashboard/services.py :: get_presences_dashboard()` utilise
`today = timezone.localdate()` → la **date réelle** (2026-11-06), pour laquelle
le jeu de démonstration ne contient aucune donnée (semé jusqu'au 2026-11-03).

`_mesure_presence()` renvoie alors `taux = None`, conformément au contrat
documenté du service :

> *« un compteur sans donnée vaut 0 (c'est un décompte), un taux sans
> dénominateur vaut `None` »* — `dashboard/services.py`, docstring de
> `get_presences_dashboard()`.

### 2.3 Preuve expérimentale (fichier temporaire créé puis supprimé)

Le test est rejoué en appelant le service à la date réelle **puis** à la date
du jeu de démonstration :

```
[date réelle] 2026-11-06 -> taux_assiduite_moyen = None | séances mesurées = 0
[date figée ] 2026-11-03 -> taux_assiduite_moyen = 41.7 | séances mesurées = 6
[pointages] total = 846

Ran 1 test in 0.507s
OK
```

**Conclusion** : le service se comporte correctement ; c'est le **test** qui est
incomplet (patch partiel). Il échouera **chaque jour à compter du 4 novembre
2026** tant qu'il n'est pas corrigé — il ne s'agit donc pas d'un aléa.

### 2.4 Qualification

| | |
|---|---|
| Nature | Défaut de conception du test (date non figée sur l'appel au tableau de bord) |
| Impact production | **Nul** — le comportement `None` est voulu et documenté |
| Impact déploiement | **Bloquant pour la validation** : la suite n'est pas verte, la CI ne peut pas valider la branche |
| Correctif recommandé | Figer également `dashboard.services.timezone.localdate` (ou `django.utils.timezone.localdate`) pendant l'appel à `/api/dashboard/presences/`, ou rendre les attentes relatives à la date semée |
| Correctif appliqué | **Aucun** — l'audit ne modifie pas le code |

---

## 3. BACKEND — contrôles statiques

### 3.1 Migrations

```
$ manage.py makemigrations --check --dry-run
No changes detected
code de sortie : 0
```

Models et migrations en phase. Répartition : 22 applications, **251 migrations**
(`formations` : 101, `presences` : 29, `authentication` : 24, `scolarite` : 19,
`habilitations` : 16, `suiviEvaluation` : 12, `parametres` : 11, `edts` : 9, …).

⚠️ **L'état des migrations appliquées en production n'a pas pu être vérifié** :
la base `injs_lmd_prod_20261026` n'est pas joignable depuis cet environnement.

### 3.2 Dépendances

```
$ python -m pip check
No broken requirements found.
```

### 3.3 `manage.py check --deploy` (DEBUG=0, clé longue, hôte de production)

| Code | Nombre | Nature |
|---|---:|---|
| `drf_spectacular.W001` | 610 | Infos de type non résolues sur des serializers — **schéma OpenAPI uniquement** |
| `drf_spectacular.W002` | 506 | Serializer non inférable sur des `APIView` — **schéma OpenAPI uniquement** |
| `security.W008` | 1 | `SECURE_SSL_REDIRECT` non activé — **volontaire** (TLS terminé par Nginx Proxy Manager, commenté dans `settings.py:542`) |
| **Total** | **1 117** | **0 erreur** ; `security.W009` absent dès qu'une clé forte est fournie |

Exemple de `W001` :
`Warning [RefGeneriqueViewSet > ParcoursSerializer]: unable to resolve type hint for function "<lambda>".`

---

## 4. FRONTEND

### 4.1 Installation selon le lockfile

```
$ npm ci --no-audit --no-fund
added 518 packages in 5s
```
`package-lock.json` : version 3, **568 entrées**, cohérent avec `package.json`
(`npm ls --package-lock-only --all` sans erreur) ; `npm ls` ne signale aucun
paquet manquant, invalide ou surnuméraire.

### 4.2 Tests

```
$ npm run test:run
 ✓ src/components/ErreurFatale.test.jsx (3 tests) 34ms
 ✓ src/utils/paginationPages.test.js (5 tests) 81ms
 ...

 Test Files  131 passed (131)
      Tests  2167 passed (2167)
   Duration  142.26s
```
**131 fichiers · 2 167 tests · 0 échec.**

### 4.3 Lint

```
$ npm run lint
/home/user/backend-injs2026/frontend/src/pages/scolarite/Groupes.jsx
  56:15  warning  'actif' is assigned a value but never used  no-unused-vars
/home/user/backend-injs2026/frontend/src/pages/scolarite/JournalScolarite.jsx
  92:10  warning  'auditCharge' is assigned a value but never used  no-unused-vars

✖ 6 problems (0 errors, 6 warnings)
code de sortie : 0
```
**0 erreur, 6 avertissements** (variables inutilisées, sans impact fonctionnel).

### 4.4 Build de production

```
$ npm run build
dist/assets/Statistiques-CrI5ewd2.js      195.39 kB │ gzip:  41.41 kB
dist/assets/index-DBwbudQi.js           1,446.63 kB │ gzip: 349.32 kB

(!) Some chunks are larger than 500 kB after minification.
✓ built in 8.96s
code de sortie : 0
```
**Build réussi** ; un avertissement de taille de chunk (bundle principal
1 446,63 kB — 349,32 kB gzip). Recommendation : découpage par
`build.rollupOptions.output.manualChunks`. Non bloquant.

---

## 5. SYNTHÈSE DES PREUVES

| Vérification | Commande | Résultat |
|---|---|---|
| Suite backend | `./arena/tests_par_groupe.sh` | 3 030 tests, **1 échec** (test dépendant de la date) |
| Migrations | `makemigrations --check --dry-run` | ✅ aucune migration manquante |
| Intégrité des paquets Python | `pip check` | ✅ aucune dépendance cassée |
| Déploiement Django | `check --deploy` | ✅ 0 erreur (1 117 avertissements de schéma OpenAPI) |
| Installation frontend | `npm ci` | ✅ 518 paquets |
| Tests frontend | `npm run test:run` | ✅ 2 167 tests |
| Lint frontend | `npm run lint` | ✅ 0 erreur, 6 avertissements |
| Build frontend | `npm run build` | ✅ 8,96 s |
| Écriture en production | — | **0** (aucune commande `--apply`, aucune migration, aucun `docker push`) |
