# INJS-LMD 2026 — Application de gestion LMD de l'INJS Marcory

Application de gestion **LMD « de A à Z »** de l'**Institut National de la Jeunesse et des
Sports (INJS) de Marcory, Abidjan (Côte d'Ivoire)** : référentiels, admissions et concours,
scolarité et pédagogie, enseignants, emplois du temps, présences par QR code, notes, jurys,
diplômation, finances étudiantes, administration/patrimoine, statistiques et portails.

- **Backend :** Django 5.1.4 + Django REST Framework (API), PostgreSQL, cache Redis, jobs planifiés.
- **Frontend web :** React 18 + Vite (tableau de bord et écrans métier), servi par Nginx en production.
- **Mobile / PWA :** application Flutter de badgeage sécurisé (scan QR, géofence, heartbeat).

> 📐 Architecture détaillée et décisions : [**docs/ARCHITECTURE.md**](docs/ARCHITECTURE.md)
> et le registre [**docs/ADR/**](docs/ADR/README.md).
> 📊 État de référence chiffré : [docs/audits/BASELINE_2026-09.md](docs/audits/BASELINE_2026-09.md).

---

## Table des matières

1. [Périmètre fonctionnel — les 18 modules](#1-périmètre-fonctionnel--les-18-modules)
2. [Architecture](#2-architecture)
3. [Prérequis et versions](#3-prérequis-et-versions)
4. [Démarrage rapide](#4-démarrage-rapide)
5. [Variables d'environnement](#5-variables-denvironnement)
6. [Tests](#6-tests)
7. [Déploiement Docker et sauvegardes](#7-déploiement-docker-et-sauvegardes)
8. [Rôles et permissions (N0–N4 × 12 rôles)](#8-rôles-et-permissions-n0n4--12-rôles)
9. [Documentation](#9-documentation)
10. [Noms techniques hérités et archives](#10-noms-techniques-hérités-et-archives)

---

## 1. Périmètre fonctionnel — les 18 modules

Modules de référence du projet (l'état réel `[OK]/[PART]/[CRÉER]` est détaillé dans
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)) :

1. **Référentiels** — formations et modules de référence, sites/bâtiments/salles, catégories, grades, vagues, années académiques, niveaux, parcours, semestres, régimes.
2. **Candidatures & admissions** — candidats, candidatures et pièces, campagnes, épreuves de concours, surveillances, convocations, notes et classements.
3. **Étudiants** — dossier étudiant, inscriptions administratives et pédagogiques, réinscriptions, groupes et affectations, journal de scolarité.
4. **Formations & pédagogie** — maquettes versionnées, UE/ECUE, sessions de modules, passerelle ECUE ↔ module de référence.
5. **Enseignants** — formateurs, affectation aux modules, encadrement et supervision.
6. **Emplois du temps** — créneaux, plannings, affectations, détection de conflits (app `edts`) + contrat d'échange lecture seule avec le planificateur externe.
7. **Campus & patrimoine** — équipements, véhicules, inventaire, maintenance, réservations d'espaces, mouvements de patrimoine.
8. **Présences** — pointages par QR, audit, appairage de device, rattrapages, notifications d'absence, heartbeat mobile.
9. **Évaluations & notes** — saisies et synthèses de notes par module, colonnes de notation, corrections traçables.
10. **Jurys & diplômation** — sessions de jury, composition, délibérations, PV, décisions, diplômes, rééditions et registre.
11. **Finances étudiantes** — tarification, échéanciers, factures, paiements, quittances, remboursements, relances et rapprochements.
12. **Direction financière & comptabilité** — rémunération des formateurs (existant) ; comptabilité générale, budget et engagements (à construire, app `comptabilite`).
13. **Administration & RH** — courriers, documents officiels, réunions de commission, missions ; services, fonctions, agents, disponibilités ; stages et conventions.
14. **Documents, courriers & archives** — gestion documentaire et versions, courriers officiels, archivage.
15. **Notifications & communication** — hub de notifications (aujourd'hui dispersé entre présences, jurys et finances), à unifier (app `notifications`).
16. **Rapports, statistiques & BI** — rapports, indicateurs, alertes/seuils, exports PDF/Excel ; module **strictement en lecture seule** (DA-10).
17. **Portails & services en ligne** — espaces web/mobile exposant les API existantes selon les droits, sans recréer de métier (DA-11).
18. **Administration système & sécurité** — 12 rôles, authentification JWT, permissions, limitation de débit, paramétrage et journal d'audit.

---

## 2. Architecture

```
   ┌──────────────┐ HTTPS /api        ┌─────────────────────────────────────┐         ┌────────────┐
   │  FRONTEND    │ ────────────────▶ │            BACKEND  Django 5.1.4     │ ──────▶ │ PostgreSQL │
   │ React 18 /   │                   │   Django REST Framework · JWT        │  SQL    │ 16 (CI)    │
   │ Vite (Nginx) │ ◀──────────────── │   drf-spectacular · WhiteNoise       │         └────────────┘
   └──────────────┘        JSON       │   Gunicorn (workers auto-scalés)     │ ◀────▶  ┌────────────┐
                                      │   20 applications Django « à plat »  │  cache  │  Redis 7   │
   ┌──────────────┐  HTTPS /api       │                                      │         └────────────┘
   │ MOBILE/PWA   │ ────────────────▶ │   scan sécurisé · heartbeats · cron  │
   │ Flutter 3.41 │                   └─────────────────────────────────────┘ ──▶ fichiers media/
   └──────────────┘                              │
                                      contrat lecture seule /api/scolarite/edt/
                                      ─────────▶ planificateur EXTERNE (DA-09)
```

- Le frontend web et le mobile ne parlent **qu'à** l'API Django : jamais d'accès direct à
  PostgreSQL depuis un client.
- Toutes les permissions sont vérifiées côté backend : l'interface ne masque pas, elle
  s'appuie sur les droits renvoyés par l'API.
- La correspondance exacte entre les 18 modules et les applications Django figure dans
  [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) (table de correspondance officielle, DA-01).

---

## 3. Prérequis et versions

Versions **vérifiées dans les fichiers du dépôt** (pas d'estimation) :

| Composant | Version | Source de vérité |
|---|---|---|
| Python | **3.12** (cible CI/Docker ; fonctionne aussi en 3.11 en bac à sable) | `backend/Dockerfile`, `.github/workflows/ci.yml` |
| Django | **5.1.4** | `backend/requirements.txt` |
| Django REST Framework | **3.15.2** | `backend/requirements.txt` |
| SimpleJWT | **5.4.0** | `backend/requirements.txt` |
| PostgreSQL | **16** en CI, image **15** dans le Compose local | `.github/workflows/ci.yml`, `backend/compose.yml` |
| Redis | **7** (image `redis:7-alpine`) | `backend/compose.yml` |
| Gunicorn | **23.0.0** | `backend/requirements.txt` |
| Node.js | **22** en CI, **20** dans l'image de build frontend | CI, `frontend/Dockerfile` |
| React / Vite | React **18.2** / Vite **7** | `frontend/package.json` |
| Flutter / Dart | Flutter **3.41.7** (canal stable) / SDK Dart **^3.10.3**, version d'app `1.0.8+12` | CI, `qr_badge_mobile/pubspec.yaml` |
| Docker / Compose | Docker Engine récent + plugin Compose | `backend/compose.yml`, `frontend/compose.yml` |

Autres bibliothèques notables : WhiteNoise 6.8.2, drf-spectacular 0.28.0, openpyxl 3.1.5,
reportlab 4.2.5, python-docx 1.1.2, Pillow 11.1.0, qrcode 8.0, redis 5.2.1.

En développement natif hors Docker : un serveur PostgreSQL accessible, ou simplement
SQLite (`USE_SQLITE=1`) pour un bac à sable jetable ; Redis est facultatif (replié en cache
fichier/mémoire).

---

## 4. Démarrage rapide

### 4.0 Le plus simple : script de démonstration local

```bash
./scripts/start_dev.sh            # crée le venv, installe, migre, sème, puis lance tout
./scripts/start_dev.sh backend    # uniquement l'API Django (0.0.0.0:8000)
./scripts/start_dev.sh frontend   # SPA servie par Django sur 0.0.0.0:3000
./scripts/start_dev.sh cron       # travailleur planifié (heartbeats, pointages, sessions)
FRONTEND_MODE=dev ./scripts/start_dev.sh frontend   # Vite + HMR sur :3000
```

### 4.1 Backend (Django)

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env               # renseigner SECRET_KEY et POSTGRES_* (ou USE_SQLITE=1)
python manage.py migrate
python seed_data.py                # données de démonstration (jamais en production)
python manage.py runserver 0.0.0.0:8001
```

API et admin : `http://localhost:8001/api/` · documentation OpenAPI :
`http://localhost:8001/api/docs/` (schéma `/api/schema/`).

### 4.2 Frontend web (React/Vite)

```bash
cd frontend
cp .env.example .env               # adapter VITE_API_URL si l'API n'est pas sur :8001
npm install
npm run dev                        # http://localhost:3000
npm run build                      # build de production dans dist/
```

Sans proxy Vite, `VITE_API_URL` doit pointer vers la racine Django (ex.
`http://127.0.0.1:8001/api`) et l'origine `http://localhost:3000` doit être autorisée dans
`CORS_ALLOWED_ORIGINS` côté backend.

### 4.3 Application mobile / PWA (Flutter)

```bash
cd qr_badge_mobile
flutter pub get
# API locale : éditer assets/app.env ou utiliser --dart-define :
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8001   # émulateur Android
flutter build web                  # PWA dans build/web (HTTPS requis pour la géolocalisation)
```

La configuration de l'API se fait via `assets/app.env`, `qr_badge_mobile/.env.example` ou
`--dart-define`. Le dossier conserve le nom technique `qr_badge_mobile/` (voir §10).

### 4.4 Docker

```bash
# Backend complet (PostgreSQL + Redis + app + cron)
cd backend
cp .env.example .env               # POSTGRES_PASSWORD, SECRET_KEY, DEBUG=False en prod…
docker compose up --build          # API sur http://localhost:8001

# Mise à l'échelle horizontale (Nginx + réplicas + volumes partagés)
docker compose -f compose.yml -f compose.scale.yml up -d --scale app=3

# Frontend web (build Vite → Nginx, port 80)
cd ../frontend
VITE_API_URL=https://api.domaine-injs.org/api docker compose up --build
```

L'image backend lance automatiquement les migrations puis Gunicorn
(`backend/entrypoint.sh` ; poser `RUN_MIGRATIONS=false` pour les exécuter séparément).

---

## 5. Variables d'environnement

Fichiers d'exemple commentés : [`backend/.env.example`](backend/.env.example),
[`frontend/.env.example`](frontend/.env.example),
[`qr_badge_mobile/.env.example`](qr_badge_mobile/.env.example). Aucun secret ne doit être
commité (le fichier `.env` est ignoré par Git).

### 5.1 Backend

| Variable | Rôle | Défaut (code) | Obligatoire en production |
|---|---|---|---|
| `DEBUG` | Mode debug (réglages, journaux, middlewares de démo) | `True` | **Oui — doit valoir `False`** |
| `SECRET_KEY` | Clé secrète Django/JWT | clé de dev si vide **et** `DEBUG=True` | **Oui — clé forte** |
| `DJANGO_ALLOWED_HOSTS` | Hôtes autorisés (virgules) | vide | **Oui** |
| `RENDER_EXTERNAL_HOSTNAME` | Nom d'hôte public injecté par certains hébergeurs | — | Non (reverse proxy) |
| `DJANGO_DEV_PORT` | Port de développement (liens QR, CORS/CSRF auto) | `8001` | Non |
| `BADGE_BASE_URL` | URL publique pour les liens QR des téléphones | auto en DEBUG sinon vide | **Oui** (QR utilisés) |
| `PUBLIC_APP_URL` | URL de l'application web (lien admin) | valeur d'ancienne URL à **surcharger** | **Oui** |
| `CSRF_TRUSTED_ORIGINS` / `CSRF_TRUSTED_ORIGIN_REGEXES` | Origines/regex de confiance CSRF | vides | Selon exposition |
| `TRUST_FORWARDED_PROTO` / `USE_X_FORWARDED_HOST` | Confiance au protocole/hôte du reverse proxy | désactivés | Oui derrière Nginx/SSL |
| `COOKIE_SAMESITE`, `JWT_COOKIE_SAMESITE` | Politique SameSite des cookies de session/JWT | `Lax` | Selon hébergement |
| `JWT_COOKIE_SECURE` | Force le cookie JWT en `Secure` | forcé en prod sinon auto | Oui en HTTPS |
| `FRONTEND_URL` | URL du frontend (CORS, pages d'accueil) | `http://localhost:3000` | Oui |
| `CORS_ALLOWED_ORIGINS` / `CORS_ALLOWED_ORIGIN_REGEXES` | Origines autorisées pour les clients web | vides | **Oui** |
| `PREVIEW_SPA` | Sert le build React par Django (aperçu mono-origine) | désactivé | Non (démo) |
| `FRONTEND_DIST` | Chemin du build React servi si `PREVIEW_SPA=1` | `../frontend/dist` | Non |
| `USE_SQLITE` | Utilise SQLite au lieu de PostgreSQL | désactivé (PostgreSQL) | **Non — PostgreSQL en prod** |
| `SQLITE_PATH` | Chemin du fichier SQLite | `backend/db.sqlite3` | Non (bac à sable) |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_HOST` / `POSTGRES_PORT` | Accès PostgreSQL | base `qr_badge` (défaut hérité, voir note), `postgres`, vide, `localhost`, `5432` | **Oui** (mot de passe fort) |
| `DB_CONN_MAX_AGE` | Persistance des connexions PostgreSQL (s) | `60` | Non |
| `REDIS_URL` | Cache Redis partagé (ex. `redis://redis:6379/0`) | — | **Oui** en multi-instances |
| `CACHE_DIR` | Répertoire du cache fichier si pas de Redis | `backend/cache` | Non |
| `PUBLIC_QR_SCAN_ENABLED` | Active le scan QR public (web) ; préférer le parcours mobile authentifié | `False` en prod | **Laisser `False`** |
| `THROTTLE_LOGIN_RATE` / `THROTTLE_SCAN_RATE` / `THROTTLE_OFFLINE_DATA_RATE` | Limites de débit DRF | `20/min`, `60/min`, `60/min` | Non (réglage) |
| `AUTO_ABSENT_DELAI_MINUTES` | Délai avant marquage « absent non badgé » | `60` | Non |
| `MOBILE_HEARTBEAT_DISABLED` | Désactive suspect/sortie auto et heartbeat | `false` | Non |
| `MOBILE_HEARTBEAT_INTERVAL_SECONDS` | Intervalle heartbeat imposé aux apps (30–600) | `60` | Non |
| `MOBILE_HEARTBEAT_AUDIT_INTERVAL_SECONDS` | Intervalle entre traces d'audit du heartbeat | `600` | Non |
| `MOBILE_HEARTBEAT_SUSPECT_TIMEOUT_MINUTES` | Délai avant statut « suspect » | `60` | Non |
| `MOBILE_HEARTBEAT_AUTO_EXIT_TIMEOUT_MINUTES` | Délai avant sortie automatique | `120` | Non |
| `MOBILE_GEOFENCE_DEFAULT_RADIUS_M` | Rayon de géofence par défaut (m) | `200` | Non |
| `MOBILE_GEOFENCE_MAX_ACCURACY_M` | Précision GPS max acceptée (m) | `80` | Non |
| `MOBILE_GEOFENCE_OUTSIDE_CONFIRMATIONS` | Nombre de confirmations hors zone | `2` | Non |
| `EMAIL_BACKEND` | Backend d'envoi des courriels | SMTP en prod, console en DEBUG | Oui (si emails) |
| `EMAIL_HOST` / `EMAIL_PORT` / `EMAIL_USE_TLS` / `EMAIL_USE_SSL` | Serveur SMTP | `smtp.gmail.com`, `587`, TLS oui | Oui (si emails) |
| `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` / `EMAIL_TIMEOUT` | Authentification SMTP / délai | vides / `15` | Oui (si emails) |
| `DEFAULT_FROM_EMAIL` | Adresse expéditrice | repli `noreply@…` (valeur d'exemple à surcharger) | Oui (si emails) |
| `DJANGO_SUPERUSER_USERNAME` / `_EMAIL` / `_PASSWORD` | Superutilisateur créé en `post_migrate` | non créés | Non (initialisation) |
| `INTER_PLATFORM_API_KEY` | Clé partagée avec le système partenaire synchronisé | vide | Oui si synchronisation activée |
| `DEMO_ADMIN_AUTOLOGIN` | Auto-connexion admin en iframe de démo (**inerte sans `DEBUG=True`**, ADR-004) | désactivé | **Ne jamais activer en prod** |
| `DEV_FRAME_ANCESTORS` | CSP d'iframe pour la démo (middleware chargé si `DEBUG`) | `*` | Non (démo) |

Le **nom de base par défaut hérité** (`qr_badge`) est un identifiant technique qui n'a
pas été renommé en phase documentaire ; les fichiers d'exemple utilisent `injs_lmd`, et la
base de production réelle est nommée `injs_lmd_current` (voir §10 et DA-12).

### 5.2 Réglages Gunicorn / conteneur

| Variable | Rôle | Défaut |
|---|---|---|
| `GUNICORN_WORKERS` | Nombre de workers (`auto` = 2×CPU+1, borné) | `auto` |
| `GUNICORN_WORKERS_MIN` / `GUNICORN_WORKERS_MAX` | Bornes du calcul `auto` | `2` / `10` |
| `GUNICORN_AUTOSCALE` | Ajuste les workers en runtime (TTIN/TTOU) | `true` |
| `GUNICORN_AUTOSCALE_INTERVAL` | Période de réglage (s) | `30` |
| `GUNICORN_AUTOSCALE_LOAD_UP` / `_LOAD_DOWN` | Seuils de charge (ajout/retrait) | `0.8` / `0.3` |
| `RUN_MIGRATIONS` | Applique `migrate` au démarrage du conteneur | `true` |

### 5.3 Frontend (variables Vite, au build)

| Variable | Rôle | Défaut |
|---|---|---|
| `VITE_API_URL` | Racine de l'API (le préfixe `/api` est porté par le backend) | `http://localhost:8001/api` |
| `VITE_ADMIN_URL` | URL de l'administration Django | dérivée de `VITE_API_URL` |
| `VITE_BADGE_BASE_URL` | URL de la page de badgeage (QR scannés par les téléphones) | `http://localhost:8001` |
| `VITE_APP_TITLE` | Titre de l'application | libellé INJS-LMD par défaut |
| `VITE_REFRESH_FALLBACK` | Repli du refresh token en stockage local (iframes de démo) | désactivé |

### 5.4 Application mobile / PWA

| Variable | Rôle | Défaut |
|---|---|---|
| `API_BASE_URL` | URL de l'API (également dans `assets/app.env`) | `http://127.0.0.1:8001` |
| `PRIVACY_POLICY_URL` | URL HTTPS de la politique (exigée par les stores) | dérivée de l'API |
| `SUPERVISOR_LOGOUT_CODE` | Code de déconnexion du superviseur | — |
| `DEV_API_HOST` / `DEV_API_PORT` | Surcharge d'hôte/port en développement | `:8001` |
| `HEARTBEAT_ENABLED` / `HEARTBEAT_INTERVAL_SECONDS` | Active le heartbeat (30–600 s) | activé / `60` |

---

## 6. Tests

Trois suites, à exécuter chacune dans leur répertoire.

### 6.1 Backend — Django (PostgreSQL dans la CI)

```bash
cd backend
# Le manifeste WhiteNoise doit exister avant les tests qui rendent des templates :
SECRET_KEY=ci-secret-key-not-for-production DEBUG=True python manage.py collectstatic --noinput
python manage.py migrate --noinput
python manage.py test --noinput -v 2          # suite complète (PostgreSQL en CI)
python manage.py check_repo_hygiene           # hygiène du dépôt (gros fichiers, données suivies…)
```

En bac à sable sans PostgreSQL, lancer les migrations et tests avec `USE_SQLITE=1`
(SQLite, chemin réglable via `SQLITE_PATH`). Réserver `--settings=arena.settings_sandbox`
au profil d'aperçu iframe (cookies CHIPS et hôte `*.e2b.app`). Un écart de pliage des
accents propre à SQLite est documenté dans
[l'ADR-006](docs/ADR/ADR-006-unicite-libelles-insensible-casse.md) ; la référence reste
PostgreSQL.

### 6.2 Frontend web — Vite/ESLint

```bash
cd frontend
npm ci
npm run lint          # ESLint (aucune erreur ni avertissement)
npm run build         # build de production Vite
npm run test:coverage # Vitest, tests unitaires et seuils de couverture
```

Les tests frontend utilisent Vitest et Testing Library (`npm run test:run` pour exécuter
sans couverture). Les seuils de couverture sont définis dans `frontend/vitest.config.js`.

### 6.3 Mobile / PWA — Flutter

```bash
cd qr_badge_mobile
cp .env.example assets/app.env  # requis par la déclaration d'assets Flutter
flutter pub get --enforce-lockfile
flutter analyze                 # analyse statique (exécutée en CI)
flutter test                    # tests Dart unitaires/widget du dossier test/
```

---

## 7. Déploiement Docker et sauvegardes

### Images et construction

- **Backend** : `backend/Dockerfile` (Python 3.12-slim, utilisateur non-root `appuser`,
  `collectstatic` au build, Gunicorn auto-scalé via `entrypoint.sh`).
- **Frontend** : `frontend/Dockerfile` multi-étapes (build Node → Nginx 1.27), variables
  `VITE_API_URL` / `VITE_BADGE_BASE_URL` / `VERSION` en arguments de build.
- La CI construit et pousse les images versionnées vers le registre
  (`.github/workflows/docker-hub-*.yml`) et vérifie notamment que `staticfiles/`
  appartient bien à `appuser` (ne jamais lancer `collectstatic` en root sur le serveur).

### Sauvegarde de la base

Le script [`scripts/backup_injs_lmd.sh`](scripts/backup_injs_lmd.sh) réalise une sauvegarde
PostgreSQL **compressée et vérifiée** de la base de production (`injs_lmd_current`,
utilisateur `injs_user`, `127.0.0.1:5432`) :

```bash
./scripts/backup_injs_lmd.sh
# crée ~/Backups/INJS-LMD/database/injs_lmd_current_<horodatage>.dump
# et son fichier .sha256 ; vérifie pg_restore --list avant de valider
```

Pour viser un autre serveur/base, adapter les variables `DB_HOST/DB_PORT/DB_NAME/DB_USER`
en tête du script (ou exporter les variables d'environnement après adaptation).

### Restauration (procédure manuelle)

```bash
# 1) vérifier l'intégrité de l'archive
shasum -a 256 -c injs_lmd_current_<horodatage>.dump.sha256
# 2) créer une base de restauration (à vide) si nécessaire
createdb -h 127.0.0.1 -U injs_user injs_lmd_restored
# 3) restaurer le dump compressé (-Fc)
pg_restore -h 127.0.0.1 -U injs_user -d injs_lmd_restored --clean --if-exists -v \
  injs_lmd_current_<horodatage>.dump
```

> La restauration est une opération sensible : ne restaurer par-dessus la base en service
> qu'après validation explicite. Un exercice périodique de restauration est recommandé
> (écart de durcissement identifié dans la baseline). Penser aussi à sauvegarder le dossier
> `media/` (fichiers téléversés), qui ne vit pas dans PostgreSQL.

---

## 8. Rôles et permissions (N0–N4 × 12 rôles)

Le projet conserve **12 rôles métier** (`authentication/models.py`, synchronisés en
groupes Django `ROLE_*` par `authentication/role_groups.py`) et applique la décision
**DA-05 : l'autorisation = niveau × rôle × permission × module × périmètre × état**.

**Niveaux d'accès (sémantique cible N0–N4)** :

| Niveau | Intitulé | Capacité type |
|---|---|---|
| **N0** | Aucun accès | Le module/objet n'est pas accessible au rôle (ni en lecture) |
| **N1** | Consultation | Lire les données de son périmètre (et ses propres données) |
| **N2** | Saisie / exploitation | Créer et modifier les données courantes de son périmètre |
| **N3** | Validation / supervision | Valider, rejeter, publier au niveau d'un service/secrétariat |
| **N4** | Administration / paramétrage | Administration globale, paramètres, publication définitive |

Les **périmètres** possibles sont : `INJS_ENTIER, DIRECTION, SERVICE, FORMATION, PARCOURS,
NIVEAU, GROUPE, MODULE, ETUDIANT, PROPRE_COMPTE` ; les **actions** : `CONSULTER, CRÉER,
MODIFIER, SOUMETTRE, VALIDER, REJETER, PUBLIER, ANNULER, EXPORTER, IMPRIMER, ARCHIVER,
SUPPRIMER, ADMINISTRER`.

**Matrice des 12 rôles** (niveau maximal typique, périmètre et canaux d'après le code
existant — `ROLE_HIERARCHY`, ensembles de rôles et classes de permission) :

| Rôle (clé technique) | Libellé | Niveau max | Périmètre principal | Canaux / capacités types |
|---|---|---|---|---|
| `ADMIN` | Administrateur | **N4** | `INJS_ENTIER` | Admin Django + web + mobile ; tous droits, paramétrage |
| `DIRECTION` | Direction | **N4** | `INJS_ENTIER` | Web ; supervision globale, statistiques, finances, validations |
| `CHEF_CPFAE_ADMIN` | Chef INJS Admin | **N4** | `INJS_ENTIER` (ou `DIRECTION`) | Admin Django + web ; administration des utilisateurs et structures |
| `CPFAE_ADMIN` | INJS Admin | **N4** | `SERVICE`/établissement | Admin Django + web ; gestion opérationnelle et référentiels |
| `CHEF_SECRETARIAT` | Chef Secrétariat | **N3** | `SERVICE` (secrétariat rattaché) | Web ; valide les opérations de scolarité, gère les comptes |
| `SECRETARIAT` | Secrétariat | **N2** | `SERVICE`/`FORMATION` | Web ; saisie inscriptions, modules, participants, imports Excel |
| `FINANCE` | Finance | **N3** sur le domaine financier, **N1** ailleurs | `INJS_ENTIER` (finances) | Web ; factures, paiements, relances, validations financières |
| `ARCHIVE` | Archiviste | **N1** global (N2 sur les archives) | `INJS_ENTIER` en lecture | Web ; consultation et archivage documentaire, listes/exports |
| `ENCADRANT` | Encadrant | **N2** sur ses formations | `FORMATION`/`GROUPE`/`MODULE` | Web + mobile ; sessions, QR, présences, saisie liée à ses groupes |
| `SUPERVISEUR` | Superviseur | **N2** sur le terrain | `FORMATION`/`GROUPE` | Mobile/tablette ; démarrage de sessions, génération QR, pointages |
| `FORMATEUR` | Formateur | **N2** sur ses modules, N1 sinon | `MODULE`/`PROPRE_COMPTE` | Mobile ; présences et saisie pédagogique de ses modules |
| `AUDITEUR` | Étudiant | **N1** | `PROPRE_COMPTE`/`ETUDIANT` | Mobile uniquement ; badgeage sécurisé et historique personnel |

> **État d'implémentation :** les 12 rôles, les groupes et la hiérarchie existent et sont
> appliqués par les permissions DRF. Le formalisme **N0–N4 à 5 dimensions** (niveau ×
> permission × module × périmètre × état) et la **validation humaine du mapping
> rôles → N0–N4** restent à **faire valider par le commanditaire** (tâche P01-05, point de
> validation humaine) : c'est pourquoi le niveau exposé porte `niveau_provisoire: true`.
> Le tableau ci-dessus est la cible alignée sur les permissions réelles ; il ne constitue
> pas une extension de droits déjà codée. Des combinaisons multi-rôles sont autorisées
> pendant la transition (`ALLOWED_MULTI_ROLE_COMBINATIONS`).

### 8.1 Endpoint de capacités pour l'interface (`GET /api/auth/capabilities/`, P00-06)

Afin qu'il n'existe **qu'une seule source de vérité des droits affichés**, l'endpoint
authentifié `GET /api/auth/capabilities/` projette pour l'utilisateur courant :

- `capacites` : la liste explicite des actions par module, sous la forme
  `{ "<module>": ["<action>", …] }` (les modules sans action sont présents avec une
  liste vide, jamais absents) ;
- `niveau` (`N0`–`N4`, **provisoire** tant que le gate G2/P01-05 n'est pas levé,
  signalé par `niveau_provisoire: true`) et `hierarchie` ;
- `perimetres` : types de périmètre (`niveaux`) et identifiants concrets
  (`secretariats`, `formations`, `groupes`, `'*'` pour périmètre global) ;
- `role`, `roles` (combinaisons multi-rôles) et `role_context` (même contenu que
  `/api/auth/me/`).

Le calcul est réalisé par la fonction unique `authentication.capabilities.compute_capabilities(user)`,
qui **réutilise les classes de permissions existantes** (constantes de
`authentication.role_groups` et prédicats des apps, par ex. `formations.access`) : il n'y
a pas de seconde logique d'autorisation. L'endpoint est documenté dans OpenAPI (tag
« Authentification ») et figé par un **test de contrat pour les 12 rôles**
(`authentication/test_capabilities.py`, matrice exécutable), incluant un test croisé
capacités ↔ permissions Django effectives. Les 12 modules exposés sont :
`web, utilisateurs, participants, modules, presences, finance, statistiques,
evaluations, notes, scolarite, exports, dashboard`.

**Côté frontend** (`frontend/`) :

- `src/hooks/useCapabilities.js` charge le contrat via React Query (clé
  `['auth','capabilities']`, 5 min de fraîcheur, pas de réessai) ; la requête n'est
  activée que pour une session authentifiée ;
- `src/components/auth/CapabilitiesSync.jsx` attache le contrat à l'utilisateur du
  `AuthContext` (`user.capabilities`) ; les helpers de `src/utils/roles.js` (`peut`,
  ainsi que tous les helpers `can*`, les drapeaux de navigation et les garde-fous
  `ProtectedRoute` via la prop `capacite`) **dérivent du contrat backend** dès qu'il est
  chargé ;
- tant que le contrat n'est pas arrivé (premier rendu, hors-ligne, endpoint en échec),
  un **repli statique strictement identique à l'historique** (`FALLBACK_CAPACITES`)
  s'applique ;
- le cache est **invalidé à la connexion et au changement de rôle**, et **purgé à la
  déconnexion** (aucune capacité ne peut traverser deux sessions).

> L'interface ne fait jamais foi : les vues DRF conservent l'intégralité de leurs
> `permission_classes` et restent la seule autorité de sécurité (règle P00-06 : ne jamais
> affaiblir un contrôle backend).

---

## 9. Documentation

| Document | Contenu |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Architecture réelle, table modules ↔ apps, DA-01 → DA-12, surface legacy |
| [docs/ADR/](docs/ADR/README.md) | Registre des décisions d'architecture (ADR-001 à ADR-006) |
| [docs/CARTOGRAPHIE_CIBLE_INJS_LMD.md](docs/CARTOGRAPHIE_CIBLE_INJS_LMD.md) | Cartographie détaillée par module (existants / à créer / doubles représentations) |
| [docs/API_ENDPOINTS.md](docs/API_ENDPOINTS.md) | Référence des endpoints REST |
| [docs/STATISTIQUES_INDICATEURS.md](docs/STATISTIQUES_INDICATEURS.md) | Définition et traçabilité des indicateurs statistiques |
| [docs/Manuel utilisateur App Statistiques.md](docs/Manuel%20utilisateur%20App%20Statistiques.md) | Manuel de l'application Statistiques (générateur DOCX associé dans `scripts/`) |
| [docs/SECURITE_DONNEES.md](docs/SECURITE_DONNEES.md) | Sécurité et protection des données, jeux de données fictifs |
| [docs/modeles/](docs/modeles/) | Modèles de données fictifs (jamais de données réelles dans le dépôt) |
| [docs/audits/BASELINE_2026-09.md](docs/audits/BASELINE_2026-09.md) | Baseline chiffrée de référence (applications, modèles, migrations, tests) |
| [docs/architecture/IAM.md](docs/architecture/IAM.md) | Identité et contrôle d'accès (module Utilisateurs) : couches legacy + CURP, JWT/MFA, moteur, journal |
| [docs/security/RBAC.md](docs/security/RBAC.md) | Rôles, niveaux N0–N4, permissions, périmètres, séparations de tâches, écarts à arbitrer |
| [docs/administration/utilisateurs.md](docs/administration/utilisateurs.md) | Guide d'exploitation des comptes : console CURP, statuts, MFA, organisation, dérogations |
| [docs/audit/permissions.md](docs/audit/permissions.md) | Rapport d'audit des permissions (LOT 4) : tests de refus croisés, scénario de bout en bout, écarts |
| [docs/legal/](docs/legal/) | Pages légales (confidentialité mobile/web/plateforme, droits, cookies, mentions) |
| [backend/docs/](backend/docs/) | Guides admin Django : dépannage et actions courantes |
| [docs/archives/](docs/archives/README.md) | Documents d'époque (badgeage QR initial) — **« Document d'archive — ne pas utiliser »** |

Le schéma OpenAPI vivant est servi par l'API : `/api/schema/` (téléchargement) et
`/api/docs/` (Swagger UI).

---

## 10. Noms techniques hérités et archives

La documentation, les libellés visibles et les métadonnées de publication sont en
terminologie **INJS-LMD**. Certains **identifiants techniques** conservent encore des noms
antérieurs que la phase documentaire ne peut pas renommer sans toucher au code, aux
migrations, à la CI, aux images ou aux canaux de publication des magasins d'applications :

- dossier `qr_badge_mobile/`, images/conteneurs Docker `qr-badge-*`, image de CI
  `sygep-backend-ci`, nom de base de données par défaut ;
- noms de classes/énumérations côté backend (par ex. permissions de direction
  `IsDFRC…`, `Pointage.Statut.FORCE_DFRC`), clés de rôles `CPFAE_ADMIN`/`CHEF_CPFAE_ADMIN`
  (les 12 rôles sont figés par DA-05) ;
- socle HTML legacy, service worker, courriels et anciens logos ;
- URL GitHub Pages et noms de fichiers des pages légales déjà publiés pour les stores.

Leur bascule se fera **par petits lots réversibles, derrière feux de bascule, et en
dernier** après vérification (DA-06, DA-12, [ADR-005](docs/ADR/ADR-005-conservation-arborescence-django-a-plat.md)).
Les documents d'époque sont regroupés dans [docs/archives/](docs/archives/README.md) avec
un bandeau « Document d'archive — ne pas utiliser ».

---

*Application INJS-LMD 2026 — INJS Marcory, Abidjan. Ce projet est en service : préserver
l'existant, ajouter progressivement, tester constamment, tracer les modifications.*
