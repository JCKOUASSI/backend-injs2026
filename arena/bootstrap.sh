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

# ── 1. Mot de passe aléatoire du compte de démonstration ─────────────────────
SANDBOX_ADMIN_PASSWORD="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
log "Mot de passe démo généré (${#SANDBOX_ADMIN_PASSWORD} caractères)."

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

PYTHON

# ── 3. Environnement de démonstration (optionnel) ────────────────────────────
if [[ "${1:-}" == "--write-env" ]]; then
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
ENV
  chmod 600 "$ENV_FILE"
  log "Compte de démonstration : admin / \$SANDBOX_ADMIN_PASSWORD (voir $ENV_FILE)"
fi

# ── 4. Rappel des exports à charger dans le shell ────────────────────────────
cat <<EXPORTS

Profil d'aperçu prêt. Pour l'utiliser dans ce shell :

  export PYTHONPATH="$ROOT"
  export DJANGO_SETTINGS_MODULE=arena.settings_sandbox
  export SANDBOX_ADMIN_PASSWORD="$SANDBOX_ADMIN_PASSWORD"

Lancement : ./arena/lancer-api.sh (8000) et ./arena/lancer-front.sh (3000)
EXPORTS
