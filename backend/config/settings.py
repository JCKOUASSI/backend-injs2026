import os
import sys
from pathlib import Path
from datetime import timedelta

try:
    from dotenv import load_dotenv
    BASE_DIR = Path(__file__).resolve().parent.parent
    load_dotenv(BASE_DIR / '.env')
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent.parent
    # dotenv not available — continue without .env loading


# --- Resolution de la configuration -----------------------------------------
# Convention canonique : prefixe DJANGO_ (modele .env de production).
# Alias de compatibilite : nom sans prefixe (historique CI / Docker).
# La convention canonique l'emporte ; une valeur vide vaut absence.
def _env_first(*names, default=None):
    # Premiere variable d'environnement NON VIDE parmi names (ordre = priorite).
    for name in names:
        raw = os.environ.get(name)
        if raw is not None and raw.strip():
            return raw.strip()
    return default


def _env_flag(*names, default=False):
    # Booleen depuis la premiere variable non vide ; default si toutes absentes.
    raw = _env_first(*names)
    if raw is None:
        return default
    return raw.lower() in ('true', '1', 'yes', 'on')


# Risque B4 : le defaut est sur (False). Historiquement 'True', ce qui
# neutralisait la variable canonique du .env de production et exposait
# la page de debug Django sur le domaine public.
DEBUG = _env_flag('DJANGO_DEBUG', 'DEBUG', default=False)

# Port HTTP du serveur Django en développement local (runserver / gunicorn dev)
# Canonique : 8000 (le 3000 est réservé au frontend ; le proxy Vite,
# scripts/start_dev.sh et arena/lancer-api.sh visent tous 8000).
DEV_SERVER_PORT = os.environ.get('DJANGO_DEV_PORT', '8000')

_SECRET_KEY_ENV = _env_first('DJANGO_SECRET_KEY', 'SECRET_KEY', default='')
if not _SECRET_KEY_ENV:
    if DEBUG:
        _SECRET_KEY_ENV = 'django-insecure-dev-only-do-not-use-in-production'
    else:
        raise RuntimeError(
            'SECRET_KEY environment variable is not set. '
            'Set it before starting the server in production.'
        )
SECRET_KEY = _SECRET_KEY_ENV

RENDER_EXTERNAL_HOSTNAME = os.environ.get('RENDER_EXTERNAL_HOSTNAME')
ALLOWED_HOSTS = [
    h.strip() for h in _env_first('DJANGO_ALLOWED_HOSTS', 'ALLOWED_HOSTS', default='').split(',')
    if h.strip()
]
if RENDER_EXTERNAL_HOSTNAME and RENDER_EXTERNAL_HOSTNAME not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)
if DEBUG:
    # Risque R5 — wildcard '*' supprimé : hosts stricts même en dev.
    # L'hôte LAN de badgeage est ajouté plus bas via BADGE_BASE_URL.
    ALLOWED_HOSTS.extend(['localhost', '127.0.0.1'])
# dé-duplication
ALLOWED_HOSTS = list(dict.fromkeys(ALLOWED_HOSTS))
if not ALLOWED_HOSTS:
    # fallback local dev (évite un arrêt complet si aucune env n'est fournie)
    ALLOWED_HOSTS = ['localhost', '127.0.0.1']

# Note : plus aucun hôte de production implicite. `ALLOWED_HOSTS` reflète
# strictement l'environnement (README §5.1 : variable obligatoire en
# production) et le `.env` de production déclare `injs.badge-qr-code.pro`.
# L'ancien ajout codé en dur rendait la liste non prévisible — un hôte
# « fantôme » restait autorisé même après l'avoir retiré de la configuration —
# et contredisait les tests de résolution (config/tests/test_settings_hardening).

# Base URL for QR codes (must be reachable by phones scanning the QR).
# In production, set via env var. In dev, auto-detect LAN IP.
BADGE_BASE_URL = os.environ.get('BADGE_BASE_URL', '')
if not BADGE_BASE_URL and DEBUG:
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        local_ip = s.getsockname()[0]
        s.close()
        BADGE_BASE_URL = f'http://{local_ip}:{DEV_SERVER_PORT}'
    except Exception:
        BADGE_BASE_URL = f'http://localhost:{DEV_SERVER_PORT}'

# Risque R5 — aucun wildcard nulle part :
# - en dev, autoriser l'hôte LAN du BADGE_BASE_URL (auto-détecté) pour le badgeage mobile ;
# - en prod, retirer tout '*' résiduel issu des variables d'environnement (défense en profondeur).
from urllib.parse import urlparse as _urlparse

if DEBUG and BADGE_BASE_URL:
    _badge_host = _urlparse(BADGE_BASE_URL).hostname
    if _badge_host and _badge_host not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(_badge_host)
if not DEBUG and '*' in ALLOWED_HOSTS:
    ALLOWED_HOSTS = [h for h in ALLOWED_HOSTS if h != '*']

CSRF_TRUSTED_ORIGINS = [
    origin for origin in _env_first('DJANGO_CSRF_TRUSTED_ORIGINS', 'CSRF_TRUSTED_ORIGINS', default='').split(',')
    if origin
]
if RENDER_EXTERNAL_HOSTNAME:
    CSRF_TRUSTED_ORIGINS.append(f'https://{RENDER_EXTERNAL_HOSTNAME}')
if DEBUG:
    CSRF_TRUSTED_ORIGINS.extend([
        'http://localhost:3000',
        'http://localhost:3001',
        f'http://localhost:{DEV_SERVER_PORT}',
        'http://127.0.0.1:3000',
        'http://127.0.0.1:3001',
        f'http://127.0.0.1:{DEV_SERVER_PORT}',
        'http://127.0.0.1:57128',
        f'http://{BADGE_BASE_URL.split("//")[-1]}' if BADGE_BASE_URL else f'http://192.168.100.54:{DEV_SERVER_PORT}',
    ])
    # Ajouter l'IP LAN auto-détectée pour que les téléphones puissent badger
    if BADGE_BASE_URL and BADGE_BASE_URL not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(BADGE_BASE_URL)

# Idem pour CSRF : la liste vient uniquement de `CSRF_TRUSTED_ORIGINS`
# (déclarée dans le `.env` de production). Un domaine implicite codé en dur
# faussait la résolution et ne pouvait pas être retiré par configuration.

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Third party
    'rest_framework',
    'rest_framework_simplejwt',
    'corsheaders',
    'drf_spectacular',
    # Local apps
    'authentication',
    'formations.apps.FormationsConfig',
    'presences',
    'exports',
    'dashboard',
    'statistiques',
    'suiviEvaluation',
    'evaluations.apps.EvaluationsConfig',
    'scolarite.apps.ScolariteConfig',
    'admissions.apps.AdmissionsConfig',
    'parametres.apps.ParametresConfig',
    'referentiels.apps.ReferentielsConfig',
    'equivalences.apps.EquivalencesConfig',
    'jurys.apps.JurysConfig',
    # Applications créées durant la réstauration (branche 2026-09)
    'graduation.apps.GraduationConfig',
    'finances_etudiantes.apps.FinancesEtudiantesConfig',  # L6 : paiements / scolarité étudiante
    'stages.apps.StagesConfig',  # L5 : stages et conventions
    'administrations.apps.AdministrationsConfig',        # L7 : courriers, documents, réunions, missions
    'ressources_humaines.apps.RessourcesHumainesConfig', # L7 : agents, services, fonctions, disponibilités
    'patrimoine.apps.PatrimoineConfig',                  # L7 : équipements, véhicules, maintenance, réservations
    # Lot L8 — Emploi du temps
    'edts.apps.EdtsConfig',                              # L8 : créneaux, plannings, affectations, conflits
    # Noyau transverse (audit unifié, P01-01)
    'core.apps.CoreConfig',
    'habilitations',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# ── Profil d'aperçu (iframe de la plateforme, hôte *.e2b.app) ────────────────
# Ces deux middlewares ne sont branchés QUE hors production. Ils vivent dans
# config/ (déjà utilisés par la démo) mais n'étaient plus référencés ici : sans
# eux, /admin/ renvoie « X-Frame-Options: DENY » (page blanche dans l'iframe)
# et la connexion échoue en 403 « vérification CSRF échouée » quand le
# navigateur bloque les cookies tiers.
#
# Positions imposées par le cycle de vie Django :
#  * DevPreviewFrameMiddleware AVANT XFrameOptionsMiddleware — le traitement
#    des réponses étant remonté de l'intérieur vers l'extérieur, il doit être
#    plus externe pour pouvoir retirer l'en-tête que XFrameOptions vient de poser.
#  * DemoAdminAutoLoginMiddleware AVANT CsrfViewMiddleware — son process_view
#    doit poser csrf_processing_done avant le contrôle CSRF par cookie.
if DEBUG:
    MIDDLEWARE.insert(
        MIDDLEWARE.index('django.middleware.clickjacking.XFrameOptionsMiddleware'),
        'config.dev_middleware.DevPreviewFrameMiddleware',
    )
    MIDDLEWARE.insert(
        MIDDLEWARE.index('django.middleware.csrf.CsrfViewMiddleware'),
        'config.demo_admin_middleware.DemoAdminAutoLoginMiddleware',
    )

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'dashboard.context_processors.sidebar_counts',
                'config.context_processors.public_urls',
                'config.context_processors.admin_ui',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# Database — PostgreSQL par défaut ; SQLite uniquement sur demande explicite
# pour le développement/sandbox (USE_SQLITE=1). La CI et la production restent
# sur PostgreSQL et ne peuvent pas basculer implicitement.
if _env_flag('USE_SQLITE', default=False):
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': _env_first('SQLITE_PATH', default=str(BASE_DIR / 'db.sqlite3')),
            'OPTIONS': {
                'timeout': int(os.environ.get('SQLITE_TIMEOUT', '30')),
            },
        }
    }
else:
    _postgres_db = os.environ.get('POSTGRES_DB', 'qr_badge')
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': _postgres_db,
            'USER': os.environ.get('POSTGRES_USER', 'postgres'),
            'PASSWORD': os.environ.get('POSTGRES_PASSWORD', ''),
            'HOST': os.environ.get('POSTGRES_HOST', 'localhost'),
            'PORT': os.environ.get('POSTGRES_PORT', '5432'),
            # Les tests Django utilisent une base séparée (test_<nom>), jamais la base de dev.
            'TEST': {
                'NAME': f'test_{_postgres_db}',
            },
            'CONN_MAX_AGE': int(os.environ.get('DB_CONN_MAX_AGE', '60')),
            'CONN_HEALTH_CHECKS': True,
        }
    }

# Cache — Redis en prod si REDIS_URL (multi-réplicas) ; sinon FileBasedCache (workers Gunicorn)
# (LocMemCache n'est pas partagé entre processus → throttling cassé en production)
#
# ATTENTION — suite de tests : Django force DEBUG=False, donc la branche
# LocMem ci-dessous n'est jamais atteinte et les tests retombaient sur le
# FileBasedCache, dont LOCATION est UN SEUL répertoire partagé par TOUS les
# processus ET toutes les bases de test. Or chaque worker de `--parallel`
# travaille sur sa propre base (`test_<db>_1`, `test_<db>_2`, …) avec ses
# propres données de flags : le cache `parametres:flags:v1` écrit par un worker
# pouvait donc être lu par un autre, provoquant des 403 et des échecs JURY
# parasites (séquentiel : vert ; 2 classes / 2 workers : vert ; ≥3 classes /
# 2 workers : rouge).
#
# En test on force donc un cache strictement local au PROCESSUS : chaque worker a
# ainsi son propre cache, cohérent avec sa propre base — pas de répertoire
# partagé, pas d'invalidation croisée entre workers.
_RUNNING_TESTS = (
    'test' in sys.argv
    or os.environ.get('PYTEST_CURRENT_TEST') is not None
)

if DEBUG or _RUNNING_TESTS:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        }
    }
elif os.environ.get('REDIS_URL'):
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': os.environ['REDIS_URL'],
            'TIMEOUT': 300,
        }
    }
else:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.filebased.FileBasedCache',
            'LOCATION': os.environ.get('CACHE_DIR', str(BASE_DIR / 'cache')),
            'TIMEOUT': 300,
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internationalization
LANGUAGE_CODE = 'fr-fr'
TIME_ZONE = 'Africa/Abidjan'
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
STORAGES = {
    # Stockage des fichiers uploadés (pièces justificatives de candidature).
    # Le dossier MEDIA_ROOT n'est pas servi par le serveur web : l'accès aux
    # documents passe obligatoirement par une vue authentifiée.
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
}
MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Custom user model
AUTH_USER_MODEL = 'authentication.User'

# Django REST Framework
REST_FRAMEWORK = {
    # Schéma OpenAPI : identifiants d'opération uniques (voir config/schema.py).
    'DEFAULT_SCHEMA_CLASS': 'config.schema.INJSAutoSchema',
    # Format d'erreur harmonisé (payload DRF préservé + code machine en en-tête).
    'EXCEPTION_HANDLER': 'config.exceptions.unified_exception_handler',
    # Authentification JWT : la classe flexible accepte l'en-tête standard
    # « Authorization: Bearer … » ET l'en-tête de secours « X-JWT-Access »
    # (que le frontend envoie systématiquement). Indispensable dans l'aperçu :
    # la passerelle d'iframe supprime « Authorization », ce qui renvoyait tous
    # les appels en 401 « Informations d'authentification non fournies ».
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'authentication.auth_classes.FlexibleJWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 50,
    'DATETIME_FORMAT': '%Y-%m-%dT%H:%M:%S%z',
    'DEFAULT_THROTTLE_RATES': {
        'login': os.environ.get('THROTTLE_LOGIN_RATE', '20/min'),
        'scan': os.environ.get('THROTTLE_SCAN_RATE', '60/min'),
        'offline_data': os.environ.get('THROTTLE_OFFLINE_DATA_RATE', '60/min'),
    },
}

# JWT Settings — durées plus longues en développement pour éviter les déconnexions
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME':  timedelta(days=1)   if DEBUG else timedelta(hours=12),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=30)  if DEBUG else timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
}

# QR Token settings
QR_TOKEN_LIFETIME_HOURS = 24

# Scan QR public (web badge) — désactivé par défaut en production.
# Utiliser l'app mobile (/api/scan/secure/) ou activer explicitement via env.
PUBLIC_QR_SCAN_ENABLED = os.environ.get(
    'PUBLIC_QR_SCAN_ENABLED',
    'True' if DEBUG else 'False',
).lower() in ('true', '1', 'yes')

# Délai avant marquage ABSENT_NON_BADGE (commande auto_close_pointages)
AUTO_ABSENT_DELAI_MINUTES = int(os.environ.get('AUTO_ABSENT_DELAI_MINUTES', 60))

# Chaîne admission → inscription administrative → parcours pédagogique.
#
# Désactivé par défaut : la règle métier en vigueur dans l'application est que
# la génération des inscriptions pédagogiques reste une ACTION EXPLICITE du
# service de scolarité (verrouillée par scolarite/tests/test_frontieres_metier.py).
# L'activer enchaîne automatiquement la génération depuis la maquette ACTIVE à
# la validation administrative. L'opération reste idempotente et n'échoue jamais
# la validation : sans maquette active, elle est différée et journalisée.
INJS_AUTO_INSCRIPTION_PEDAGOGIQUE = os.environ.get(
    'INJS_AUTO_INSCRIPTION_PEDAGOGIQUE', 'False',
).lower() in ('true', '1', 'yes')

# Paramètres anti-fraude mobile (heartbeat + geofence)
MOBILE_HEARTBEAT_DISABLED = os.environ.get(
    'MOBILE_HEARTBEAT_DISABLED',
    'False',
).lower() in ('true', '1', 'yes')
MOBILE_HEARTBEAT_INTERVAL_SECONDS = int(
    os.environ.get('MOBILE_HEARTBEAT_INTERVAL_SECONDS', 60)
)
MOBILE_HEARTBEAT_AUDIT_INTERVAL_SECONDS = int(
    os.environ.get('MOBILE_HEARTBEAT_AUDIT_INTERVAL_SECONDS', 600)
)
MOBILE_HEARTBEAT_SUSPECT_TIMEOUT_MINUTES = int(
    os.environ.get('MOBILE_HEARTBEAT_SUSPECT_TIMEOUT_MINUTES', 60)
)
MOBILE_HEARTBEAT_AUTO_EXIT_TIMEOUT_MINUTES = int(
    os.environ.get('MOBILE_HEARTBEAT_AUTO_EXIT_TIMEOUT_MINUTES', 120)
)
MOBILE_GEOFENCE_DEFAULT_RADIUS_M = int(
    os.environ.get('MOBILE_GEOFENCE_DEFAULT_RADIUS_M', 200)
)
MOBILE_GEOFENCE_MAX_ACCURACY_M = int(
    os.environ.get('MOBILE_GEOFENCE_MAX_ACCURACY_M', 80)
)
MOBILE_GEOFENCE_OUTSIDE_CONFIRMATIONS = int(
    os.environ.get('MOBILE_GEOFENCE_OUTSIDE_CONFIRMATIONS', 2)
)

# CORS — liste stricte d'origines (ou vide = rien)
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = [
    origin for origin in os.environ.get('CORS_ALLOWED_ORIGINS', '').split(',')
    if origin
]
if DEBUG:
    CORS_ALLOWED_ORIGINS.extend([
        'http://localhost:3000',
        'http://localhost:3001',
        f'http://localhost:{DEV_SERVER_PORT}',
        'http://127.0.0.1:3000',
        'http://127.0.0.1:3001',
        f'http://127.0.0.1:{DEV_SERVER_PORT}',
        f'http://192.168.1.90:3000',
        f'http://192.168.1.90:{DEV_SERVER_PORT}',
        f'http://192.168.100.54:3000',
        f'http://192.168.100.54:{DEV_SERVER_PORT}',
    ])
CORS_ALLOWED_ORIGINS = list(dict.fromkeys(CORS_ALLOWED_ORIGINS))
# Origines par expression régulière (ex. `^https://[a-z0-9-]+\.e2b\.app$` pour
# l'aperçu). Documentées au README §5.1 mais jamais lues : la variable était
# ignorée, ce qui faisait échouer toute requête cross-origin de l'aperçu.
CORS_ALLOWED_ORIGIN_REGEXES = [
    motif for motif in os.environ.get('CORS_ALLOWED_ORIGIN_REGEXES', '').split(',')
    if motif.strip()
]
CORS_EXPOSE_HEADERS = ['Content-Disposition', 'Content-Type']
# Nécessaire au cookie HttpOnly du refresh JWT (credentials: 'include' côté React).
# Les origines restent strictes (CORS_ALLOWED_ORIGINS ci-dessus, pas de allow-all).
CORS_ALLOW_CREDENTIALS = True

# ── Habilitations / observation métier ─────────────────────────────────────
# L'observation est le mode livré par défaut : elle mesure les écarts sans
# modifier les réponses. L'application des refus reste désactivée par défaut.
# Les variables d'environnement permettent un kill-switch explicite sans
# modifier le code; les valeurs booléennes acceptent true/1/yes et false/0/no.
HABILITATIONS_OBSERVATION = os.environ.get(
    'HABILITATIONS_OBSERVATION', 'true'
).lower() in ('true', '1', 'yes')
HABILITATIONS_APPLICATION = os.environ.get(
    'HABILITATIONS_APPLICATION', 'false'
).lower() in ('true', '1', 'yes')

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ── Email (SMTP) ──────────────────────────────────────────────────────────────
EMAIL_BACKEND = os.environ.get(
    'EMAIL_BACKEND',
    'django.core.mail.backends.smtp.EmailBackend' if not DEBUG
    else 'django.core.mail.backends.console.EmailBackend',
)
EMAIL_HOST = os.environ.get('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', 587))
EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS', 'True').lower() in ('true', '1', 'yes')
EMAIL_USE_SSL = os.environ.get('EMAIL_USE_SSL', 'False').lower() in ('true', '1', 'yes')
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
EMAIL_TIMEOUT = int(os.environ.get('EMAIL_TIMEOUT', '15'))
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', EMAIL_HOST_USER or 'noreply@qrbadge.local')

# Nombre maximal de champs d'un formulaire POST. La valeur était ``None``
# (protection désactivée) : une requête multipart très large pouvait saturer
# un worker. On borne à 5 000 champs, largement au-dessus des formulaires
# métier (imports, saisies en masse) tout en gardant la protection.
DATA_UPLOAD_MAX_NUMBER_FIELDS = int(
    os.environ.get('DATA_UPLOAD_MAX_NUMBER_FIELDS', '5000')
)

# drf-spectacular
SPECTACULAR_SETTINGS = {
    'TITLE': 'INJS API',
    'DESCRIPTION': 'API de gestion LMD, scolarité, formations, participants et badgeage QR de l\'INJS.',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
}

# URL publique de l'application web (lien « Dashboard web » dans l'admin).
PUBLIC_APP_URL = os.environ.get('PUBLIC_APP_URL', 'https://injs.badge-qr-code.pro').rstrip('/')

# ── Aperçu mono-origine (build React servi par Django) ───────────────────────
# `config.urls` et `config.preview` lisent ces deux réglages ; ils étaient
# documentés (README §5.1) et posés par `scripts/start_dev.sh` sans jamais être
# définis ici : `PREVIEW_SPA=1` était donc sans effet (racine = API seule).
PREVIEW_SPA = _env_flag('PREVIEW_SPA', default=False)
FRONTEND_DIST = os.environ.get(
    'FRONTEND_DIST', str(BASE_DIR.parent / 'frontend' / 'dist'),
)

# ── Production security (activé quand DEBUG=False) ──
# NOTE: SECURE_SSL_REDIRECT est intentionnellement désactivé — la redirection
# HTTP→HTTPS doit être gérée par Nginx/le reverse proxy, pas par Django.
# Si Django gère lui-même le SSL redirect, il entre en conflit avec le proxy
# et casse le CSRF sur les endpoints publics comme /api/scan/.
if not DEBUG:
    SECURE_SSL_REDIRECT = False
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# ── Logging structuré (risque R8) ─────────────────────────────────────────────
# Dev  : console INFO (le fichier est filtré par require_debug_false).
# Prod : fichier rotatif uniquement, niveau WARNING minimum.
LOGS_DIR = BASE_DIR / 'logs'
LOGS_DIR.mkdir(exist_ok=True)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} [{name}] {module}.{funcName}:{lineno} — {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {asctime} [{name}] {message}',
            'style': '{',
        },
    },
    'filters': {
        'require_debug_true': {'()': 'django.utils.log.RequireDebugTrue'},
        'require_debug_false': {'()': 'django.utils.log.RequireDebugFalse'},
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
            'filters': ['require_debug_true'],
        },
        'file_rotating': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': str(LOGS_DIR / 'injs_lmd.log'),
            'maxBytes': 5 * 1024 * 1024,
            'backupCount': 5,
            'encoding': 'utf-8',
            'formatter': 'verbose',
            'level': 'WARNING',
            'filters': ['require_debug_false'],
        },
    },
    'root': {
        'handlers': ['console', 'file_rotating'],
        'level': 'INFO' if DEBUG else 'WARNING',
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file_rotating'],
            'level': 'INFO' if DEBUG else 'WARNING',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['console', 'file_rotating'],
            'level': 'WARNING',
            'propagate': False,
        },
        'django.server': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        # Journalisation métier sensibles (audits login / scan QR).
        'authentication': {
            'handlers': ['console', 'file_rotating'],
            'level': 'INFO',
            'propagate': False,
        },
        'presences': {
            'handlers': ['console', 'file_rotating'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}
