# Annexes — preuves et commandes reproductibles

Toutes les mesures de ce dossier proviennent de commandes exécutées sur le dépôt, le 23 novembre 2026, au commit `8245d9c`. Les sorties sont reproduites telles quelles (tronquées quand elles sont longues, sans modification du sens).

## A. Environnement

| Élément | Valeur |
|---|---|
| Dépôt | `/home/user/backend-injs2026` |
| Branche | `arena/c9ce7261-backend-injs2026` |
| Commit audité | `8245d9c` (« chore(audit): créer le dossier racine Audit-SYGET ») |
| Python | 3.11 (venv `backend/.venv`) |
| Node | 20 (frontend `node_modules` installés) |
| Base de test local | SQLite (profil de bac à sable) ; la CI utilise PostgreSQL 16 |
| Flutter | non installé dans cet environnement — application mobile auditée en lecture de code uniquement |

Préambule commun aux commandes Django :

```bash
cd backend
export USE_SQLITE=1
export PYTHONPATH=..
export DJANGO_SETTINGS_MODULE=arena.settings_sandbox
export DJANGO_SECRET_KEY='audit-only-key-0123456789abcdefghijklmnopqrstuvwxyz-ABCDEFGH'
```

## B. État du dépôt

```console
$ git rev-parse --abbrev-ref HEAD
arena/c9ce7261-backend-injs2026
$ git rev-parse --short HEAD
8245d9c
$ du -sh .git backend frontend docs .ci
98M     .git
166M    backend
264M    frontend
31M     docs
42M     .ci
```

## C. Volumétrie

```console
$ git ls-files 'backend/*.py' | grep -v /migrations/ | wc -l
819
$ git ls-files 'backend/*.py' | grep -v /migrations/ | xargs wc -l | tail -1
189787 total
$ find backend -path '*/migrations/*.py' -name '0*.py' | wc -l
312
$ find backend -name models.py -not -path '*/migrations/*' | wc -l
176
$ git ls-files 'frontend/src/*.js*' | wc -l
365
$ git ls-files 'frontend/src/*.js*' | xargs wc -l | tail -1
118755 total
$ git ls-files 'qr_badge_mobile/*.dart' | wc -l
43
$ git ls-files 'qr_badge_mobile/*.dart' | xargs wc -l | tail -1
8116 total
```

Applications Django — décompte depuis `INSTALLED_APPS` :

```console
$ .venv/bin/python -c "import django;django.setup();from django.conf import settings;\
print(len([a for a in settings.INSTALLED_APPS if not a.split('.')[0] in
('django','rest_framework','corsheaders','drf_spectacular','whitenoise')]))"
23
```

Liste : `authentication, formations, presences, exports, dashboard, statistiques, suiviEvaluation,
evaluations, scolarite, admissions, parametres, referentiels, equivalences, jurys, graduation,
finances_etudiantes, stages, administrations, ressources_humaines, patrimoine, edts, core, habilitations`.

Deux répertoires applicatifs supplémentaires existent sur disque mais **ne sont pas installés** :
`backend/cache/` (vide) et `backend/referentiel_injs/` (paquet avec `models.py` et migrations, jamais
chargé par Django) — reliquats à documenter ou supprimer.

Plus gros fichiers (lignes) :

```console
$ git ls-files 'backend/*.py' | grep -v migrations | xargs wc -l | sort -rn | head -6
5417 backend/formations/api_views.py
3841 backend/presences/views.py
3481 backend/exports/views.py
2121 backend/statistiques/views.py
1951 backend/dashboard/views_legacy.py
1747 backend/formations/management/commands/import_excel.py

$ git ls-files 'frontend/src/*.js*' | xargs wc -l | sort -rn | head -5
5499 frontend/src/pages/Statistiques.jsx
3269 frontend/src/pages/Statistiques.test.jsx
1944 frontend/src/pages/ModuleDetail.jsx
1841 frontend/src/pages/FormationDetail.jsx
1831 frontend/src/pages/EvaluationsModule.jsx
```

## D. Contrôles Django

### D.1 Configuration (`check --deploy`, DEBUG désactivé)

```console
$ cd backend && DJANGO_DEBUG=0 .venv/bin/python manage.py check --deploy
System check identified some issues:

WARNINGS:
?: (security.W008) Your SECURE_SSL_REDIRECT setting is not set to True. Unless your site
should be available over both SSL and non-SSL connections, you may want to either set this
setting True or configure a load balancer or reverse-proxy server to redirect all
connections to HTTPS.

System check identified 1 issue (0 silenced).
```

Pour information, avec `DEBUG` laissé à sa valeur par défaut du profil de bac à sable, on obtient logiquement `W004`, `W008` et `W018` — ces deux derniers n'ont pas de sens hors production.

### D.2 Migrations

```console
$ .venv/bin/python manage.py makemigrations --check --dry-run
No changes detected
```

### D.3 Schéma OpenAPI

```console
$ .venv/bin/python manage.py spectacular --validate --file /tmp/schema.yaml
# aucune sortie, aucune erreur ; fichier de 1,9 Mo
$ python -c "import yaml;print(len(yaml.safe_load(open('/tmp/schema.yaml'))['paths']))"
1254
```

Répartition des routes par domaine (extrait) : `referentiels` 382, `formations` 192, `scolarite` 67, `edts` 64, `timetable` 64, `habilitations` 54, `presences` 52, `evaluations` 40, `statistiques` 30, `admissions` 29.

### D.4 Hygiène du dépôt — **échec**

```console
$ .venv/bin/python manage.py check_repo_hygiene
Hygiène du dépôt NON CONFORME — 1 fichier(s) interdit(s) suivi(s) :
  - .ci/mobile-web/assets/assets/app.env

Sortez-les du suivi avec 'git rm --cached <fichier>' (sans les supprimer du disque) ;
les modèles vides vont dans docs/modeles/.
$ echo $?
1
```

Règle correspondante dans le code :

```python
# backend/parametres/management/commands/check_repo_hygiene.py
FORBIDDEN_PATH_PARTS = ("staticfiles/", "importverif/", "assets/app.env")
```

Et dans `.gitignore` :

```
**/assets/app.env
```

Or le workflow `apercu-mobile-web.yml` exécute :

```yaml
git add -f .ci
...
git commit -m "ci(mobile): résultat du build web [skip ci]"
git push origin "HEAD:$GITHUB_REF_NAME"
```

## E. Intégration continue

```console
$ gh run list --workflow=ci.yml --limit 12 --json conclusion,headBranch,createdAt,event
2026-11-24  failure  pull_request  arena/5a3e058b-backend-injs2026
2026-11-23  failure  pull_request  arena/469bba52-backend-injs2026
2026-11-23  failure  push          main
2026-11-23  failure  pull_request  arena/e1ccf29f-backend-injs2026
2026-11-23  failure  push          main
2026-11-19  failure  pull_request  arena/a8060ecf-backend-injs2026
...
$ gh run list --workflow=ci.yml --limit 50 --json conclusion,createdAt \
    -q '[.[]|select(.conclusion=="success")][0]'
{"conclusion":"success","createdAt":"2026-11-18T12:39:34Z"}
```

Sur 20 exécutions consécutives : **19 échecs**, dernier succès le 18/11/2026 à 12:39 UTC.
Le premier échec postérieur à ce succès date du **18/11/2026 à 16:26 UTC** (`70d08dad`), déjà sur
l'étape « Hygiène du dépôt ».

Reconstitution de la cause de ce premier échec, les journaux n'étant pas accessibles — application
de `find_violations` (fonction pure de la commande) à l'arborescence du commit :

```console
$ gh api "repos/JCKOUASSI/backend-injs2026/git/trees/70d08dad?recursive=1" \
    -q '.tree[]|select(.type=="blob")|.path' > /tmp/tree.txt
$ # dans backend/, en important la fonction pure de la commande :
>>> h.find_violations(open('/tmp/tree.txt').read().splitlines())
5 fichiers, dont :
  livrables/audit-volumes-LOCAL-2026-2027.csv   # absent du commit réussi de 12:39 -> cause du 1er échec
  dossier_trvx/...xlsx (4 fichiers, présents aussi dans le commit réussi : règle sans doute postérieure)
```

Le CSV n'existe plus dans l'arborescence actuelle ; la violation actuelle est `app.env`. Deux causes
successives, une seule étape fautive.

Détail du job fautif (API GitHub, run du 23/11) :

```console
$ gh api repos/JCKOUASSI/backend-injs2026/actions/runs/<id>/jobs \
    -q '.jobs[]|{name,conclusion,steps:[.steps[]|select(.conclusion=="failure")|.name]}'
{"name":"Backend (Django + PostgreSQL)","conclusion":"failure",
 "steps":["Hygiène du dépôt"]}
{"name":"Frontend (React + Vite)","conclusion":"success","steps":[]}
```

Protection de branche — **non vérifiable** depuis cet environnement :

```console
$ gh api repos/JCKOUASSI/backend-injs2026/branches/main/protection
{"message":"Resource not accessible by integration","status":"403"}
```

## F. Frontend

### F.1 Build

```console
$ cd frontend && npx vite build
dist/assets/Equivalences-95F7xYt2.js             29.78 kB │ gzip:   6.71 kB
dist/assets/Inscriptions-ByWXgISy.js             31.78 kB │ gzip:   6.95 kB
dist/assets/Maquettes-BzB59AwR.js                42.06 kB │ gzip:   9.80 kB
dist/assets/DashboardEngineView-5AzWHG1y.js      56.05 kB │ gzip:  14.03 kB
dist/assets/Statistiques-CobswJ75.js            195.75 kB │ gzip:  41.52 kB
dist/assets/index-CFdvLnNY.js                 1,668.66 kB │ gzip: 398.30 kB

(!) Some chunks are larger than 500 kB after minification. Consider:
- Using dynamic import() to code-split the application
- Use build.rollupOptions.output.manualChunks to improve chunking
✓ built in 4.36s
```

Note : `frontend/dist/` est ignoré par Git et n'a pas été versionné par cet audit.

Comptage des imports statiques de pages :

```console
$ grep -c "^import" src/App.jsx
91
$ grep -n "^import .* from '\./pages" src/App.jsx | wc -l
80
```

### F.2 Tests et lint

```console
$ npx vitest run
 Test Files  144 passed (144)
      Tests  2258 passed (2258)
   Duration  120.47s

$ npm run lint
✖ 7 problems (0 errors, 7 warnings)
```

Les 7 avertissements sont des `no-unused-vars` (variables déclarées et non utilisées dans `DocumentsScolaires.test.jsx`, `Groupes.jsx`, `JournalScolarite.jsx`…).

### F.3 Dépendances

```console
$ npm audit --omit=dev
@remix-run/router  1.3.0 - 1.23.2
Severity: moderate
React Router's same-origin redirect with path starting // causes open redirect via
protocol-relative URL reinterpretation - GHSA-2j2x-hqr9-3h42
fix available via `npm audit fix`

3 moderate severity vulnerabilities
```

Portée de la correction : l'avis couvre `react-router` 6.0.0 → 7.17.0 ; la version corrigée est **7.18.x** (dernière publication 7.18.7). Le projet n'utilise que l'API déclarative (`Link`, `useParams`, `useSearchParams`, `useNavigate`, `Routes`, `MemoryRouter`), ce qui rend la montée de version peu risquée.

## G. Backend — exécution des tests

```console
$ .venv/bin/python manage.py test scolarite
Ran 555 tests in 92.524s
OK (skipped=2)
```

Périmètre « scolarité + référentiels » (mesure précédente de la même session) : **686 tests, 2 ignorés, ≈ 116 s**.

Non-déterminisme observé sur un module exécuté seul :

```console
$ .venv/bin/python manage.py test scolarite.tests.test_maquettes_admin_api   # 1er essai
FAIL: test_import_complete_le_brouillon_existant (...)
AssertionError: 400 != 200
FAIL: test_maquettes_verrouillees_refusees (...)
FAIL: test_credits_non_numeriques_signales (...)
FAIL: test_maquette_verrouillee_refusee (...)
Ran 34 tests in 2.042s
FAILED (failures=4)

$ # 2e essai
Ran 34 tests in 2.009s
FAILED (failures=1)

$ # 3e essai
Ran 34 tests in 2.158s
OK
```

Les 34 tests passent lorsque l'application entière est exécutée : dépendance probable à l'ordre ou à un état résiduel (voir QUA-05).

## H. Recherches de motifs à risque

```console
$ grep -rn "@permission_classes(\[AllowAny\])" backend --include=*.py | grep -v test | wc -l
9      # tous justifiés : login, refresh, logout, health, vérification de diplôme, scan public
$ grep -rn "eval(\|exec(\|os.system\|shell=True\|mark_safe\|pickle\|\.raw(\|verify=False" \
    backend --include=*.py | grep -v ".venv" | grep -v test
backend/scripts/fix_import_folder.py: ast.literal_eval(...)   # hors runtime
```

Faux positifs écartés après vérification :

| Motif | Occurrences | Verdict |
|---|---|---|
| `extra(` | 9 | toutes dans `formations/session_views.py` → paramètre `_session_audit_extra(...)`, **pas** `QuerySet.extra()` |
| `innerHTML` | 6 | uniquement dans des tests (`expect(container.innerHTML)…`) ; aucun `dangerouslySetInnerHTML` en production |
| `eval(` | 1 | `ast.literal_eval` dans un script d'outillage |

Contrôles de configuration :

```console
$ grep -n "DEFAULT_PERMISSION_CLASSES" -A2 backend/config/settings.py
368:    'DEFAULT_PERMISSION_CLASSES': (
369:        'rest_framework.permissions.IsAuthenticated',

$ grep -n "CORS_ALLOW_ALL_ORIGINS\|CORS_ALLOW_CREDENTIALS" backend/config/settings.py
442:CORS_ALLOW_ALL_ORIGINS = False
471:CORS_ALLOW_CREDENTIALS = True

$ grep -n "ACCESS_TOKEN_LIFETIME\|REFRESH_TOKEN_LIFETIME\|ROTATE_REFRESH_TOKENS" backend/config/settings.py
383:    'ACCESS_TOKEN_LIFETIME':  timedelta(days=1)   if DEBUG else timedelta(hours=12),
384:    'REFRESH_TOKEN_LIFETIME': timedelta(days=30)  if DEBUG else timedelta(days=7),
385:    'ROTATE_REFRESH_TOKENS': True,
```

## I. Exposition des médias

```console
$ sed -n '44,48p' docker/nginx/default.conf
    location /media/ {
        alias /app/media/;
        expires 7d;
        add_header Cache-Control "public";
    }

$ grep -n "injs_media" deploy/production/compose.yml
      - ${INJS_HOST_MEDIA_DIR:-injs_media}:/app/media:ro

$ sed -n '325,327p' backend/config/settings.py
    # Le dossier MEDIA_ROOT n'est pas servi par le serveur web : l'accès aux
    # documents passe obligatoirement par une vue authentifiée.
```

## J. Authentification par paramètre d'URL

```console
$ sed -n '40,50p' backend/authentication/auth_classes.py
    def authenticate(self, request):
        # 3) Dernier recours : jeton en paramètre d'URL (exports/lecteurs médias)
        token = request.GET.get(QUERY_PARAM)
        if token:
            try:
                ...
                return user, validated
            except InvalidToken:
                return None
        return super().authenticate(request)
```

Aucune condition sur `DEBUG` ou `PREVIEW_SPA` ; `QUERY_PARAM = 'access_token'`. Aucun appel du frontend n'utilise ce paramètre (vérifié par `grep "access_token=" frontend/src`).

## K. Limites de l'exercice

1. Aucune exécution sur la base de production : les volumétries de données et les plans d'exécution réels n'ont pas été observés.
2. Les journaux GitHub Actions n'étant pas accessibles, l'étape fautive a été identifiée via l'API des jobs puis **reproduite** localement.
3. L'application Flutter n'a pas été compilée (SDK absent) : seules la structure, les dépendances et les tests ont été examinés.
4. La protection de branche de `main` n'a pas pu être lue (403) : à vérifier manuellement (FIX-11).
5. Les durées de tests obtenues sur SQLite sont optimistes par rapport à PostgreSQL.
