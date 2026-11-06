# DÉPENDANCES ET ENVIRONNEMENT TECHNIQUE — 6 novembre 2026

**Branche** : `arena/4524a57c-backend-injs2026` · **Commit** : `7c9d56a`

---

## 1. BACKEND — dépendances Python

**Fichier** : `backend/requirements.txt` — **30 paquets, tous épinglés** par `==`
(reproductible). Aucune plage de version, aucun dépôt Git, aucun chemin local.

| Paquet | Version | Rôle |
|---|---|---|
| Django | 5.1.4 | socle applicatif |
| djangorestframework | 3.15.2 | API REST |
| djangorestframework_simplejwt | 5.4.0 | authentification JWT |
| drf-spectacular | 0.28.0 | schéma OpenAPI |
| gunicorn | 23.0.0 | serveur WSGI de production |
| psycopg2-binary | 2.9.10 | pilote PostgreSQL |
| whitenoise | 6.8.2 | service des fichiers statiques |
| redis | 5.2.1 | cache (optionnel) |
| Pillow | 11.1.0 | traitement d'images |
| qrcode | 8.0 | génération des QR codes |
| reportlab | 4.2.5 | génération PDF |
| openpyxl | 3.1.5 | lecture/écriture Excel |
| python-docx | 1.1.2 | lecture/écriture Word |
| python-dotenv | 1.0.1 | chargement `.env` |
| PyYAML | 6.0.3 | configuration |
| PyJWT | 2.12.1 | jetons |
| django-cors-headers | 4.6.0 | CORS |
| asgiref | 3.11.1 | interface ASGI |
| sqlparse | 0.5.5 | utilitaire SQL |
| inflection | 0.5.1 | utilitaire drf-spectacular |
| jsonschema (+ specifications, referencing, rpds-py, attrs) | 4.26.0 / 2025.9.1 / 0.37.0 / 0.30.0 / 26.1.0 | validation de schémas |
| Markdown | 3.10.2 | rendu du schéma OpenAPI |
| uritemplate | 4.2.0 | OpenAPI |
| packaging | 26.0 | utilitaire |
| brotli, chardet, et_xmlfile | 1.2.0 / 5.2.0 / 2.0.0 | dépendances transitives épinglées |

**Contrôles effectués**

| Contrôle | Résultat |
|---|---|
| `python -m pip check` | ✅ **No broken requirements found.** |
| Épinglage | ✅ 30/30 paquets avec `==` |
| Fichier de hachages (`--require-hashes`) | ❌ absent |
| Analyse de vulnérabilités (`pip-audit`, `safety`) | ⚠️ **non exécutée** — sortie réseau limitée à pypi.org ; à lancer sur le VPS |
| Automatisation de mise à jour | ❌ aucun `.github/dependabot.yml` |

### Versions de Python — **divergence à corriger**

| Contexte | Version |
|---|---|
| Image de production (`backend/Dockerfile`) | **python:3.12-slim** |
| CI (`.github/workflows/ci.yml:65`) | **3.11** |
| Environnement d'audit (venv locale) | 3.11.2 |

⚠️ **La suite de tests n'est jamais exécutée sur la version réellement déployée
(3.12).** Recommandation : aligner la CI sur 3.12 (ou l'image sur 3.11), puis
rejouer la suite.

### Paquets système de l'image backend

`bash`, `gcc`, `libjpeg-dev`, `zlib1g-dev`, `libpq-dev`, `procps`
(installés via `apt-get`, cache purgé). Utilisateur non-root `appuser`.

---

## 2. FRONTEND — dépendances Node

**Installation** : `npm ci` → **518 paquets en 5 s**, 0 erreur.
`package-lock.json` **version 3**, 568 entrées, cohérent avec `package.json`.

### Dépendances de production (6)

| Paquet | Version |
|---|---|
| react | ^18.2.0 |
| react-dom | ^18.2.0 |
| react-router-dom | ^6.22.0 |
| @tanstack/react-query | ^5.101.1 |
| bootstrap-icons | ^1.11.3 |
| qrcode | ^1.5.4 |

### Dépendances de développement (16)

`@sparticuz/chromium`, `@testing-library/{dom,jest-dom,react,user-event}`,
`@types/react`, `@types/react-dom`, `@vitejs/plugin-react`,
`@vitest/coverage-v8`, `eslint`, `eslint-plugin-react`,
`eslint-plugin-react-hooks`, `jsdom`, `puppeteer-core`, `vite`, `vitest`.

| Contrôle | Résultat |
|---|---|
| `npm ci` | ✅ 518 paquets, 0 erreur |
| `npm ls` (manquant / invalide / surnuméraire) | ✅ aucun |
| Cohérence lockfile ↔ `package.json` | ✅ |
| `npm audit` | ⚠️ **non exécuté** (option `--no-audit` utilisée pour l'installation ; à lancer séparément : le rapport dépend de la base de vulnérabilités en ligne) |

### Versions de Node — **divergence mineure**

| Contexte | Version |
|---|---|
| Image de build (`frontend/Dockerfile`) | **node:20-alpine** |
| CI (`.github/workflows/ci.yml:143`) | **20** |
| Environnement d'audit | v22.22.3 (npm 10.9.8) |

Le build a été validé sur 22 (ici) et la CI l'exécute sur 20 (aligné sur
l'image). `package.json` ne déclare **pas** de champ `engines` : à ajouter pour
figer la version (ex. `"node": ">=20 <23"`).

---

## 3. SERVICES CIBLES SUR LE VPS

### PostgreSQL — requis

| Point | État |
|---|---|
| Pilote | `psycopg2-binary==2.9.10` ✅ |
| Configuration | `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT` (`settings.py:245-257`) ✅ |
| Base créée par le compose | **non** — base existante consommée ✅ |
| Piège | `POSTGRES_DB` vaut **`qr_badge`** par défaut : une variable oubliée pointe silencieusement sur la mauvaise base |
| Piège | `POSTGRES_HOST` doit être l'**IP ou le nom du conteneur** PostgreSQL sur le réseau Docker, jamais `127.0.0.1` |
| Connexions | `CONN_MAX_AGE=60`, `CONN_HEALTH_CHECKS=True` ✅ |
| Version serveur | ⚠️ non vérifiable depuis cet environnement (base non joignable) |
| Attente au démarrage | l'`entrypoint.sh` attend la base 60 × 2 s avant `migrate` ✅ |

### Redis — optionnel

| Point | État |
|---|---|
| Bibliothèque | `redis==5.2.1` ✅ |
| Activation | `REDIS_URL` → cache partagé ; sinon `FileBasedCache` local au conteneur |
| Câblage compose | ❌ `REDIS_URL` n'est **pas** transmis au service backend (documenté dans `.env.example` §5) |
| Conséquence | sans Redis, chaque worker Gunicorn a son propre cache fichier → throttling et cache de flags non partagés entre workers |

### RabbitMQ — **aucune dépendance**

| Point | État |
|---|---|
| Celery dans `requirements.txt` | ❌ absent |
| `CELERY_*` / `BROKER_URL` dans `settings.py` | ❌ absent |
| Conclusion | l'application **n'utilise aucun bus de messages** ; RabbitMQ n'a pas à être installé pour cette pile |
| Traitements périodiques | assurés par des commandes `manage.py` (ex. `process_mobile_heartbeats`, `auto_close_pointages`, `auto_sessions`) à planifier par `cron`/`systemd` si besoin |

### Nginx

| Point | État |
|---|---|
| Passerelle interne | `nginx:1.27-alpine` (service `gateway`), configuration `docker/nginx/default.conf` ✅ |
| Serveur du frontend | `nginx:1.27-alpine` dans l'image `injs-fe`, `frontend/nginx.conf` avec repli SPA ✅ |
| Nginx Proxy Manager (VPS) | attendu en amont : TLS, certificat, redirection vers `127.0.0.1:8080` |
| Points à régler | `client_max_body_size` absent (limite 1 Mo) ; `X-Forwarded-Proto` écrasé par `$scheme` |

### Domaine `injs.badge-qr-code.pro`

Déclaré dans `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `CORS_ALLOWED_ORIGINS`,
`PUBLIC_APP_URL` (défaut `settings.py:530`), `BADGE_BASE_URL` et `VITE_API_URL`
(argument de build). ✅ Cohérent.

---

## 4. IMAGES DOCKER

| Image | Base | Contexte | Statut |
|---|---|---|---|
| `jckouassi/injs-be` | `python:3.12-slim` | `./backend` | publiée avec succès le 5 novembre (exécution `41985711224`, 1 min 18 s) |
| `jckouassi/injs-fe` | `node:20-alpine` → `nginx:1.27-alpine` | `./frontend` | publiée avec succès le 5 novembre (1 min 16 s) |

- ✅ Plateforme : `linux/amd64` — compatible avec un VPS x86_64 (AlmaLinux).
- ⚠️ Présence actuelle des tags sur Docker Hub **non vérifiable** depuis cet
  environnement (sortie réseau restreinte).
- ⚠️ Le workflow `publish-injs-lmd.yml` n'existe **pas** sur la branche auditée
  (présent sur `origin/main`) → fusion nécessaire avant publication.

---

## 5. SYNTHÈSE

| Catégorie | Verdict |
|---|---|
| Dépendances Python | ✅ 30 paquets épinglés, intégrité vérifiée — ⚠️ version runtime (3.12) non testée, pas d'audit CVE |
| Dépendances Node | ✅ lockfile v3 cohérent, installation reproductible — ⚠️ pas d'`engines`, audit CVE non lancé |
| PostgreSQL | ✅ configuration prête — ⚠️ défauts `qr_badge` / `localhost` à sécuriser |
| Redis | ⚠️ optionnel et non câblé |
| RabbitMQ | ✅ sans objet — aucune dépendance |
| Nginx / domaine | ✅ cohérent — ⚠️ deux réglages à ajuster |
| Images | ✅ chaîne éprouvée — ⚠️ workflow absent de la branche |
