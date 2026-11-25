# 03 — Sécurité applicative

La sécurité de SYGET a manifestement déjà fait l'objet d'un travail sérieux : des mécanismes nommés « risque R6 », « CURP U6 », « A5 » apparaissent dans le code et les commentaires, signe d'une revue antérieure. L'audit confirme que le contrôle d'accès applicatif tient, et isole **six angles morts** — dont un qui contourne entièrement ce contrôle pour les fichiers.

## 1. Ce qui est correctement fait

### 1.1 Autorisations : fermées par défaut

```
config/settings.py:368   DEFAULT_PERMISSION_CLASSES = ('rest_framework.permissions.IsAuthenticated',)
```

Sur **598 vues** inspectées (`@api_view`, `APIView`, `ViewSet`), le balayage automatisé ne trouve **aucune `@api_view` sans décorateur de permission**. Neuf points d'entrée sont explicitement publics, tous justifiables :

| Point d'entrée | Justification |
|---|---|
| `/auth/login/`, `/auth/token/refresh/`, `/auth/logout/` | accès anonyme par nature |
| `/health/` | sonde de disponibilité, sans donnée |
| portail de vérification de diplôme (`graduation/api.py:341`) | lecture seule, par jeton, aucune donnée sensible |
| scan QR public (`presences/views.py`) | **désactivé par défaut en production** (`PUBLIC_QR_SCAN_ENABLED=False` hors DEBUG) |

Le scan public est protégé par un interrupteur global et non laissé ouvert par distraction : c'est exactement la bonne pratique.

### 1.2 Secrets et configuration

- `DEBUG` vaut **False par défaut** (`settings.py:39`).
- Hors DEBUG, l'absence de `DJANGO_SECRET_KEY` **fait échouer le démarrage** plutôt que de générer une clé faible (`settings.py:46-55`).
- `ALLOWED_HOSTS` est épuré : `'*'` est retiré en production (`settings.py:104`), aucun hôte de production n'est implicite.
- `CORS_ALLOW_ALL_ORIGINS = False`, liste blanche explicite, `CORS_ALLOW_CREDENTIALS = True` assumé parce que le refresh circule en cookie.
- `CSRF_TRUSTED_ORIGINS` explicite, jamais `'*'`.
- `.env`, `*.sqlite3` et `.venv` sont ignorés par Git.

### 1.3 Authentification

| Mécanisme | État |
|---|---|
| JWT (SimpleJWT) | access **12 h**, refresh **7 j**, rotation activée (`settings.py:382-387`) |
| Hachage des mots de passe | PBKDF2 par défaut Django, 4 validateurs actifs |
| Verrouillage de compte | oui, après N échecs, avec levée automatique (`authentication/connexion_sure.py`) |
| MFA TOTP | oui (`/auth/mfa/verify/`, tests dédiés dans `test_lot2_securite.py`) |
| Anti-bruteforce | `LoginRateThrottle` 20/min, clé basée sur la **première** IP de `X-Forwarded-For` (testé) |
| Application mobile | jetons dans Keystore Android / Keychain iOS via `flutter_secure_storage` — **le bon choix**, pas de `SharedPreferences` pour les jetons |
| Web | refresh en cookie **HttpOnly** + rotation, posé par `authentication/views.py:101-108` |

Le point 6 mérite d'être souligné : le risque « jeton de rafraîchissement lisible en JavaScript » (R6) a déjà été traité pour le web et pour le mobile. Le stockage local ne concerne plus que **l'access token**, avec un repli explicitement réservé aux aperçus (`VITE_REFRESH_FALLBACK`).

### 1.4 Durcissement HTTP

Hors DEBUG : HSTS 1 an avec sous-domaines et preload, cookies de session et CSRF `Secure`, `SECURE_PROXY_SSL_HEADER` défini. `SECURE_SSL_REDIRECT=False` est un **choix documenté** (la redirection est déléguée à Nginx pour ne pas casser le CSRF derrière le proxy). `manage.py check --deploy` ne remonte qu'un unique avertissement, `security.W008`, qui correspond exactement à ce choix.

### 1.5 Absence de surface d'injection manifeste

Recherche exhaustive : aucun `eval` exécutable, aucun `exec`, `os.system`, `subprocess(..., shell=True)`, `mark_safe`, `pickle`, `verify=False`, ni SQL brut (`.raw()`, `.extra()`). Le seul `eval` du dépôt est un `ast.literal_eval` dans un script d'outillage hors runtime. La neutralisation des formules dans les exports CSV/Excel est implémentée, ce qui est rare et pertinent.

## 2. Constats à corriger

### SEC-01 — Fichiers média servis sans authentification · **Élevé**

La configuration affirme le contraire de ce que fait le déploiement. `backend/config/settings.py:325-327` :

> « Le dossier MEDIA_ROOT n'est pas servi par le serveur web : l'accès aux documents passe obligatoirement par une vue authentifiée. »

Or le gateway de production (`docker/nginx/default.conf:44-48`) expose précisément ce dossier :

```nginx
location /media/ {
    alias /app/media/;
    expires 7d;
    add_header Cache-Control "public";
}
```

et `deploy/production/compose.yml` monte le volume média dans le conteneur Nginx. Toute personne connaissant une URL — sans jeton, sans session — télécharge le fichier. Les fichiers concernés ne sont pas anodins : `releves/` (relevés de notes), `administrations/courriers/` et `documents/`, `rh/documents/`, `jurys/pv/`, les pièces justificatives de candidature et de paiement, les photos d'habilitation (`administrations/models.py`, `evaluations/models.py:1083`, `finances_etudiantes/models.py:197`, `habilitations/models/personne.py:55`).

Le risque est aggravé par le stockage par défaut de Django (`FileSystemStorage`), qui **conserve le nom d'origine** du fichier : les URL sont devinables (`/media/releves/releve_L3_2025-2026.pdf`), et rien n'empêche d'énumérer un répertoire si l'indexation est activée. La directive `Cache-Control: public` fait en outre conserver ces documents dans les caches intermédiaires pendant sept jours.

**Correctif** (configuration, effort **S**) :
1. Supprimer le bloc `location /media/` du gateway et router ces URL vers Django, où une vue authentifiée contrôle les droits ; ou
2. à défaut, servir les médias via des URL signées à durée courte et retirer `Cache-Control: public`.
3. Corriger le commentaire de `settings.py` si le choix 1 n'est pas retenu.

**Vérification** : `curl -I https://<hôte>/media/<chemin>/<fichier>` doit renvoyer 401/403 sans session.

### SEC-02 — Jeton accepté en paramètre d'URL, dans tous les environnements · **Élevé**

`backend/authentication/auth_classes.py:40-50` : si aucun en-tête d'authentification n'est présent, l'authentificateur lit `?access_token=<jwt>` et authentifie la requête. Le mécanisme n'est **conditionné ni par DEBUG ni par un réglage d'aperçu**. Le docstring indique que « le frontend de production ne l'alimente jamais » — vérifié, aucun appel front ne l'utilise — mais le serveur l'accepte.

Pourquoi c'est un problème : un jeton en URL se retrouve dans l'historique du navigateur, dans l'en-tête `Referer` transmis aux ressources tierces, dans les journaux d'accès Nginx (le format par défaut journalise l'URI complète, requête comprise ; aucune directive `access_log` ne restreint cela dans `docker/nginx/default.conf`), et dans tout proxy intermédiaire. Aucun en-tête `Referrer-Policy` n'est émis.

**Correctif** : n'activer cette voie que si `DEBUG` ou `PREVIEW_SPA` est vrai, ou la restreindre aux seules routes de téléchargement de médias ; ajouter `Referrer-Policy: no-referrer` au gateway ; exclure les paramètres sensibles des journaux. Effort **S**.

### SEC-03 — Access token de 12 h en `localStorage`, sans CSP · **Moyen à élevé**

Le jeton d'accès est lu/écrit par `frontend/src/services/api.js:60-63` via `safeLocalStorage`, avec une durée de vie de 12 h. Le dépôt ne définit **aucune `Content-Security-Policy`** (ni Django, ni `docker/nginx/default.conf`). Conséquence : toute XSS — y compris via une dépendance compromise — permet d'exfiltrer un jeton exploitable une demi-journée, sans possibilité pour le serveur de le révoquer (voir SEC-04).

**Correctif** : ramener la durée de vie à 15–30 min (le refresh silencieux existe déjà et est *single-flight*), ajouter une CSP raisonnable (au minimum `default-src 'self'`, `object-src 'none'`, `frame-ancestors` limité aux domaines d'aperçu), et à terme garder l'access token en mémoire. Effort **M**.

### SEC-04 — Déconnexion sans effet serveur, pas de liste de révocation · **Moyen**

`authentication/views.py:141-152` : le `logout` supprime le cookie et renvoie 200, en indiquant explicitement « JWT stateless, pas de blacklist activée ». Avec `ROTATE_REFRESH_TOKENS=True` mais **sans** `token_blacklist`, un refresh token volé reste valable jusqu'à son expiration (7 jours), et la rotation ne l'invalide pas. Une déconnexion déclenchée par un utilisateur inquiet ne protège donc pas.

**Correctif** : ajouter `rest_framework_simplejwt.token_blacklist` et `'BLACKLIST_AFTER_ROTATION': True`, puis mettre l'ancien refresh en liste noire au logout. Impact : un nettoyage périodique de la table. Effort **M**.

### SEC-05 — Limitation de débit partielle · **Moyen**

Seuls trois quotas sont définis (`settings.py:374-378`) : `login` 20/min, `scan` 60/min, `offline_data` 60/min. Aucun quota **global** (`DEFAULT_THROTTLE_CLASSES` est vide), et les endpoints les plus coûteux — exports de plusieurs milliers de lignes, statistiques agrégées, imports Excel — ne sont pas limités. Un utilisateur authentifié, ou une boucle de retry front, peut saturer les workers.

À noter aussi : `LoginRateThrottle` est **fail-open** si le cache est indisponible (`authentication/throttles.py:27-36`). C'est un choix assumé et documenté, atténué par le verrouillage de compte, mais il faut savoir que la protection anti-bruteforce peut disparaître silencieusement en cas d'incident Redis.

**Correctif** : ajouter un quota par utilisateur (par ex. `user` à 1 000/h, `burst` à 60/min) et des quotas dédiés sur les exports et imports. Effort **S**.

### SEC-06 — Dépendance vulnérable · **Moyen**

`npm audit --omit=dev` signale **3 vulnérabilités modérées** provenant de `react-router` 6.30.3 (chaîne d'exécution du front, pas une dépendance de développement). Aucune étape `npm audit` n'existe dans la CI, donc une future vulnérabilité passerait inaperçue.

**Correctif** : mettre à jour `react-router-dom` vers la dernière 6.x corrigée (ou 7.x avec recette), ajouter `npm audit --audit-level=high` en CI. Effort **S**.

### SEC-07 — En-têtes de sécurité incomplets au gateway · **Faible**

`docker/nginx/default.conf` n'ajoute que des en-têtes de cache. Django fournit `X-Frame-Options` et `X-Content-Type-Options` par défaut, mais il manque `Content-Security-Policy`, `Referrer-Policy` et `Permissions-Policy`, qui ne peuvent pas être posés correctement par Django pour les fichiers statiques servis par Nginx.

**Correctif** : bloc `add_header` commun dans la configuration du gateway. Effort **S**.

### SEC-08 — Fichier d'environnement versionné · **Faible, mais symptomatique**

`.ci/mobile-web/assets/assets/app.env` est suivi par Git. Son contenu actuel ne contient que des valeurs d'exemple (`PRIVACY_POLICY_URL`, `SUPERVISOR_LOGOUT_CODE=your-supervisor-logout-code`) — **aucun secret réel compromis**. Le problème est le précédent : un workflow fait `git add -f` sur un répertoire de build de 42 Mo, ce qui contourne `.gitignore` et a déjà conduit à versionner un fichier de configuration. La prochaine fois, ce sera un vrai secret.

**Correctif** : `git rm --cached` le fichier, corriger le workflow, ajouter une analyse de secrets (gitleaks) en CI. Effort **S**. Voir `06` pour la cause racine de la CI rouge, qui est le même fichier.

## 3. Synthèse

| Thème | Évaluation |
|---|---|
| Modèle d'autorisation | **bon** — fermé par défaut, public explicite et limité |
| Gestion des secrets | **bon** — refus de démarrer sans clé, pas de secret versionné réel |
| Cycle de vie des jetons | **insuffisant** — jeton en URL, 12 h en `localStorage`, pas de révocation |
| Défense en profondeur | **partielle** — médias non protégés, pas de CSP, quotas incomplets |
| Dépendances | **à surveiller** — 3 avis modérés, pas de contrôle en CI |
| Traçabilité | **bonne** — audit immuable et journaux métier |

Note de l'axe : **3 / 5**. Le modèle d'autorisation applicatif est bon, mais il est **contourné pour les fichiers** : la donnée la plus sensible du système (relevés, pièces justificatives) échappe au contrôle d'accès parce qu'elle est servie par Nginx. C'est le point à traiter en premier avec la CI.
