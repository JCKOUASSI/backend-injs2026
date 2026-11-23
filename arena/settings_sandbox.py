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

