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

