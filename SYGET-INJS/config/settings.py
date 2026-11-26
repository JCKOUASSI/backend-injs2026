"""
Configuration Django unique.

- Développement : Postgres (variables POSTGRES_*), DEBUG activé par défaut.
- Tests : SQLite (fichier `test.sqlite3`) si `pytest` charge ce module ou si
  `DJANGO_USE_SQLITE=1`.
- Production : `DJANGO_PRODUCTION=1`, `DJANGO_SECRET_KEY` et `ALLOWED_HOSTS`
  obligatoires, options de sécurité HTTPS activées.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from config.bootstrap_env import load_env

load_env()

BASE_DIR = Path(__file__).resolve().parent.parent


def _env_bool(name: str, default: str = "false") -> bool:
    return os.environ.get(name, default).lower() in ("1", "true", "yes", "on")


def _pg_env(postgres_name: str, legacy_db_name: str, default: str) -> str:
    """
    Lit d'abord POSTGRES_*, puis DB_* (compatibilité), puis valeur par défaut.
    """
    postgres_value = os.environ.get(f"POSTGRES_{postgres_name}")
    if postgres_value is not None:
        return postgres_value
    legacy_value = os.environ.get(f"DB_{legacy_db_name}")
    if legacy_value is not None:
        return legacy_value
    return default


def _pg_required(postgres_name: str, legacy_db_name: str) -> str:
    """
    Exige une variable Postgres en production.
    """
    postgres_key = f"POSTGRES_{postgres_name}"
    legacy_key = f"DB_{legacy_db_name}"
    postgres_value = os.environ.get(postgres_key)
    if postgres_value:
        return postgres_value
    legacy_value = os.environ.get(legacy_key)
    if legacy_value:
        return legacy_value
    raise ImproperlyConfigured(f"Variable obligatoire manquante: {postgres_key} (ou {legacy_key} pour compatibilité).")


IS_PRODUCTION = _env_bool("DJANGO_PRODUCTION")
# pytest importe ce module après avoir chargé `pytest` ; SQLite évite Postgres en CI.
USE_SQLITE = _env_bool("DJANGO_USE_SQLITE") or ("pytest" in sys.modules)

INSTALLED_APPS = [
    "unfold",
    "unfold.contrib.filters",
    "unfold.contrib.forms",
    "unfold.contrib.inlines",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "config.apps.ConfigAppConfig",
    "apps.parametrage",
    "apps.referentiels",
    "apps.formations",
    "apps.auditeurs",
    "apps.groupes",
    "apps.seances",
    "apps.simulation",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "shared.context_processors.perimetre_utilisateur",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "Europe/Paris"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/accueil/"
LOGOUT_REDIRECT_URL = "/login/"

UNFOLD = {
    "SITE_TITLE": "Emploi du temps INJS",
    "SITE_HEADER": "Administration EDT INJS",
    "SITE_SUBHEADER": "INJS Abidjan",
    "SITE_URL": "/accueil/",
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": False,
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": True,
    },
}

# Admin Django : « supprimer la sélection » envoie un champ par objet (+ csrf, action, etc.).
# Au-delà de la limite → TooManyFieldsSent → HTTP 400 Bad Request.
DATA_UPLOAD_MAX_NUMBER_FIELDS = int(os.environ.get("DATA_UPLOAD_MAX_NUMBER_FIELDS", "250000"))
# Corps POST volumineux (même scénario) ; augmenter si 400 persiste malgré la limite ci-dessus.
DATA_UPLOAD_MAX_MEMORY_SIZE = int(os.environ.get("DATA_UPLOAD_MAX_MEMORY_SIZE", str(10 * 1024 * 1024)))

if USE_SQLITE:
    DEBUG = _env_bool("DEBUG", "true")
    SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "changeme-test-only")
    ALLOWED_HOSTS = [
        host.strip() for host in os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if host.strip()
    ]
    _csrf_origins = os.environ.get("CSRF_TRUSTED_ORIGINS", "")
    if _csrf_origins:
        CSRF_TRUSTED_ORIGINS = [o.strip() for o in _csrf_origins.split(",") if o.strip()]
    if _env_bool("DJANGO_TRUST_PROXY_SSL"):
        SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
        USE_X_FORWARDED_HOST = True
    if _env_bool("DJANGO_ALLOW_IFRAME"):
        MIDDLEWARE = [m for m in MIDDLEWARE if m != "django.middleware.clickjacking.XFrameOptionsMiddleware"]
    if _env_bool("DJANGO_IFRAME_COOKIES"):
        MIDDLEWARE = ["config.preview_middleware.PartitionedIframeCookiesMiddleware", *MIDDLEWARE]
        SESSION_COOKIE_SAMESITE = "None"
        SESSION_COOKIE_SECURE = True
        CSRF_COOKIE_SAMESITE = "None"
        CSRF_COOKIE_SECURE = True
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "test.sqlite3",
        }
    }
elif IS_PRODUCTION:
    DEBUG = False
    SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]
    ALLOWED_HOSTS = [h.strip() for h in os.environ.get("ALLOWED_HOSTS", "").split(",") if h.strip()]
    if not ALLOWED_HOSTS:
        raise ImproperlyConfigured("ALLOWED_HOSTS doit être défini en production.")
    CSRF_TRUSTED_ORIGINS = [o.strip() for o in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()]
    # Requis derrière reverse proxy (Nginx/Traefik) pour fiabiliser les vérifications HTTPS/CSRF.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": _pg_required("DB", "NAME"),
            "USER": _pg_required("USER", "USER"),
            "PASSWORD": _pg_required("PASSWORD", "PASSWORD"),
            "HOST": _pg_required("HOST", "HOST"),
            "PORT": _pg_required("PORT", "PORT"),
            "CONN_MAX_AGE": 60,
        }
    }
    STATIC_ROOT = os.environ.get("STATIC_ROOT", "/var/www/emploi_du_temps/static")

    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    CSRF_COOKIE_HTTPONLY = True

    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_BROWSER_XSS_FILTER = True
    X_FRAME_OPTIONS = "DENY"

    LOGGING = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "verbose": {
                "format": "{levelname} {asctime} {module} {message}",
                "style": "{",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "verbose",
            },
        },
        "root": {
            "handlers": ["console"],
            "level": "WARNING",
        },
        "loggers": {
            "django": {
                "handlers": ["console"],
                "level": os.environ.get("DJANGO_LOG_LEVEL", "WARNING"),
                "propagate": False,
            },
            "apps.seances": {
                "handlers": ["console"],
                "level": os.environ.get("PLANNING_LOG_LEVEL", "INFO"),
                "propagate": False,
            },
            "apps.parametrage": {
                "handlers": ["console"],
                "level": os.environ.get("PLANNING_LOG_LEVEL", "INFO"),
                "propagate": False,
            },
        },
    }
else:
    DEBUG = _env_bool("DEBUG", "true")
    SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "changeme-in-production")
    ALLOWED_HOSTS = [host.strip() for host in os.environ.get("ALLOWED_HOSTS", "").split(",") if host.strip()]
    _csrf_origins = os.environ.get("CSRF_TRUSTED_ORIGINS", "")
    if _csrf_origins:
        CSRF_TRUSTED_ORIGINS = [o.strip() for o in _csrf_origins.split(",") if o.strip()]
    if _env_bool("DJANGO_TRUST_PROXY_SSL"):
        SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
        USE_X_FORWARDED_HOST = True
    if _env_bool("DJANGO_ALLOW_IFRAME"):
        MIDDLEWARE = [m for m in MIDDLEWARE if m != "django.middleware.clickjacking.XFrameOptionsMiddleware"]
    if _env_bool("DJANGO_IFRAME_COOKIES"):
        MIDDLEWARE = ["config.preview_middleware.PartitionedIframeCookiesMiddleware", *MIDDLEWARE]
        SESSION_COOKIE_SAMESITE = "None"
        SESSION_COOKIE_SECURE = True
        CSRF_COOKIE_SAMESITE = "None"
        CSRF_COOKIE_SECURE = True
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": _pg_env("DB", "NAME", "emploi_du_temps"),
            "USER": _pg_env("USER", "USER", "postgres"),
            "PASSWORD": _pg_env("PASSWORD", "PASSWORD", "postgres"),
            "HOST": _pg_env("HOST", "HOST", "localhost"),
            "PORT": _pg_env("PORT", "PORT", "5432"),
        }
    }
    LOGGING = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "verbose": {
                "format": "{levelname} {asctime} {name} {message}",
                "style": "{",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "verbose",
            },
        },
        "root": {"handlers": ["console"], "level": "WARNING"},
        "loggers": {
            "django": {
                "handlers": ["console"],
                "level": os.environ.get("DJANGO_LOG_LEVEL", "INFO"),
                "propagate": False,
            },
            "apps.seances": {
                "handlers": ["console"],
                "level": os.environ.get("PLANNING_LOG_LEVEL", "DEBUG"),
                "propagate": False,
            },
            "apps.parametrage": {
                "handlers": ["console"],
                "level": os.environ.get("PLANNING_LOG_LEVEL", "INFO"),
                "propagate": False,
            },
        },
    }
