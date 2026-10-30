#!/usr/bin/env bash
# =============================================================================
# Générateur du profil d'aperçu Arena (`arena/settings_sandbox.py`).
#
# À exécuter après chaque réinitialisation du bac à sable : il (re)crée le
# profil d'aperçu, prépare un environnement `.env` de démonstration et tire un
# mot de passe ALÉATOIRE pour le superutilisateur de démonstration (jamais de
# mot de passe en dur dans le dépôt).
#
#   bash arena/bootstrap.sh            # régénère le profil + affiche les exports
#   bash arena/bootstrap.sh --write-env  # écrit aussi backend/.env
#
# Le contenu généré est identique à `arena/settings_sandbox.py` versionné :
# `backend/config/tests/test_apercu_hardening.py` vérifie que les deux restent
# alignés (sinon le correctif disparaît au prochain reset).
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROFIL="$ROOT/arena/settings_sandbox.py"
ENV_FILE="$ROOT/backend/.env"

log() { printf '\033[1;36m[bootstrap]\033[0m %s\n' "$*"; }

# ── 1. Mot de passe du compte de démonstration ───────────────────────────────
# Un mot de passe aléatoire de 64 caractères n'était PAS saisissable : dès que
# la session d'aperçu était perdue (déconnexion, cookie filtré), l'admin
# devenait inaccessible et aucun identifiant connu ne permettait d'y revenir.
# Le profil d'aperçu utilise donc un identifiant de DÉMONSTRATION, documenté,
# et surchargeable pour un environnement partagé :
#
#     PREVIEW_ADMIN_PASSWORD='...' ./arena/bootstrap.sh --write-env
#
# Ce compte n'existe que dans le profil d'aperçu : `arena/settings_sandbox.py`
# et `backend/.env`, jamais dans `config/settings.py` (production). Le profil
# ouvre d'ailleurs déjà l'admin sans mot de passe (`DEMO_ADMIN_AUTOLOGIN=1`) :
# ce mot de passe sert au retour manuel, pas de barrière de sécurité.
SANDBOX_ADMIN_PASSWORD="${PREVIEW_ADMIN_PASSWORD:-admin123}"
if [ "${#SANDBOX_ADMIN_PASSWORD}" -lt 8 ]; then
  echo "[bootstrap] PREVIEW_ADMIN_PASSWORD trop court (8 caractères minimum)." >&2
  exit 2
fi
log "Compte de démonstration : admin / ${SANDBOX_ADMIN_PASSWORD} (aperçu uniquement)"

# ── 2. Régénération du profil d'aperçu ───────────────────────────────────────
log "Génération de $PROFIL"
cat > "$PROFIL" <<'PYTHON'
"""Profil de réglages « aperçu Arena » (iframe cross-site, hôte ``*.e2b.app``).

Usage — jamais en production :

    cd backend && PYTHONPATH=.. DJANGO_SETTINGS_MODULE=arena.settings_sandbox \\
        python manage.py runserver 0.0.0.0:8000

(ou simplement ``arena/lancer-api.sh``, qui pose ces variables)

Ce fichier est un **overlay** : il part de la configuration réelle
(``config.settings``) et n'ajoute que le durcissement nécessaire à une iframe
tierce. Il est régénéré à l'identique par ``arena/bootstrap.sh`` ; les deux
doivent rester alignés (cf. ``backend/config/tests/test_apercu_hardening.py``).
"""
from config.settings import *  # noqa: F401,F403  (overlay : tout est repris)

# ── Hôtes de l'aperçu ────────────────────────────────────────────────────────
# Ce profil est réservé à l'aperçu et n'est jamais chargé en production. Il doit
# fonctionner même sans ``backend/.env`` — fichier ignoré par Git, donc absent
# après chaque réinitialisation du bac à sable. Sans ce bloc, Django répond
# « 400 DisallowedHost » sur ``<port>-<sandbox>.e2b.app`` et l'aperçu reste
# blanc, alors que le serveur écoute correctement.
PREVIEW_HOST_SUFFIXE = ".e2b.app"
if PREVIEW_HOST_SUFFIXE not in ALLOWED_HOSTS:
    ALLOWED_HOSTS = [*ALLOWED_HOSTS, PREVIEW_HOST_SUFFIXE]

# Origines de l'aperçu : le site (port 3000) et l'admin (port 8000) sont servis
# sous des hôtes distincts ; le joker de sous-domaine est accepté par Django.
for _origine in ("https://*.e2b.app", "http://*.e2b.app"):
    if _origine not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS = [*CSRF_TRUSTED_ORIGINS, _origine]

# Appels directs à l'API depuis l'hôte d'aperçu (hors proxy Vite).
if "e2b\\.app" not in CORS_ALLOWED_ORIGIN_REGEXES:
    CORS_ALLOWED_ORIGIN_REGEXES = [
        *CORS_ALLOWED_ORIGIN_REGEXES,
        r"^https?://([a-z0-9-]+\.)*e2b\.app$",
    ]

# ── Cookies : noms dédiés ────────────────────────────────────────────────────
# Un nom dédié neutralise définitivement tout vieux cookie csrftoken/sessionid
# hérité du navigateur (cause du « incorrect length » sur les jetons tronqués).
CSRF_COOKIE_NAME = "injs_csrftoken"
SESSION_COOKIE_NAME = "injs_sessionid"

# ── Cookies : attributs requis en iframe tierce ──────────────────────────────
SESSION_COOKIE_SAMESITE = "None"
CSRF_COOKIE_SAMESITE = "None"
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# La passerelle d'aperçu termine le TLS : on lui fait confiance pour le proto.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# ── Middlewares compagnons (aperçu uniquement) ───────────────────────────────
# CHIPS : Django 5.1 ignore SESSION_COOKIE_PARTITIONED (ajouté en 5.2), d'où ce
# middleware qui pose « Partitioned » sur les en-têtes Set-Cookie.
MIDDLEWARE.insert(0, 'arena.partitioned_cookies.PartitionedCookieMiddleware')

# Auto-connexion du compte de démonstration : la passerelle filtre les cookies,
# l'admin en vignette serait sinon inaccessible (403 CSRF). Doit s'exécuter
# APRÈS AuthenticationMiddleware (il lit request.user).
MIDDLEWARE.insert(MIDDLEWARE.index("django.contrib.auth.middleware.AuthenticationMiddleware") + 1, 'arena.preview_autologin.AutoLoginApercuMiddleware')

PREVIEW_AUTOLOGIN_ENABLED = True
PREVIEW_AUTOLOGIN_USERNAME = "admin"

# ── Racine du port 8000 → admin Django (navigateurs) ─────────────────────────
# Ouvrir l'aperçu de l'API affichait le JSON de la racine : l'admin semblait
# inaccessible. Seules les navigations (Accept: text/html) sont redirigées ;
# les clients d'API reçoivent toujours le JSON.
MIDDLEWARE.append('arena.preview_admin_redirect.AdminRedirectApercuMiddleware')

PYTHON

# ── 3. Environnement de démonstration ────────────────────────────────────────
# Le fichier est écrit d'office s'il est absent : sans lui, Django refuse de
# démarrer (SECRET_KEY) puis l'aperçu est rejeté (ALLOWED_HOSTS). Un fichier
# existant n'est JAMAIS écrasé, sauf demande explicite `--write-env`.
if [[ ! -f "$ENV_FILE" || "${1:-}" == "--write-env" ]]; then
  log "Écriture de $ENV_FILE"
  cat > "$ENV_FILE" <<ENV
SECRET_KEY=django-insecure-dev-demo-key-1234567890
DEBUG=true
USE_SQLITE=1
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,.e2b.app
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
CSRF_TRUSTED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000,https://*.e2b.app,http://*.e2b.app
FRONTEND_URL=http://localhost:3000
TRUST_FORWARDED_PROTO=1
USE_X_FORWARDED_HOST=1
DEV_FRAME_ANCESTORS=*
JWT_COOKIE_SAMESITE=None
JWT_COOKIE_SECURE=1
COOKIE_SAMESITE=None
DEMO_ADMIN_AUTOLOGIN=1
DJANGO_SUPERUSER_USERNAME=admin
DJANGO_SUPERUSER_EMAIL=admin@arena.invalid
DJANGO_SUPERUSER_PASSWORD="$SANDBOX_ADMIN_PASSWORD"
# Autorise la remise à niveau du mot de passe d'un compte DÉJÀ existant :
# sans ce drapeau, régénérer le .env ne changeait rien en base et l'identifiant
# publié devenait faux.
DJANGO_SUPERUSER_RESET_PASSWORD=1
ENV
  chmod 600 "$ENV_FILE"
  log "Compte de démonstration : admin / $SANDBOX_ADMIN_PASSWORD (voir $ENV_FILE)"
fi

# ── 4. Rappel des exports à charger dans le shell ────────────────────────────
cat <<EXPORTS

Profil d'aperçu prêt. Pour l'utiliser dans ce shell :

  export PYTHONPATH="$ROOT"
  export DJANGO_SETTINGS_MODULE=arena.settings_sandbox
  export SANDBOX_ADMIN_PASSWORD="$SANDBOX_ADMIN_PASSWORD"

Lancement : ./arena/lancer-api.sh (8000) et ./arena/lancer-front.sh (3000)
EXPORTS
