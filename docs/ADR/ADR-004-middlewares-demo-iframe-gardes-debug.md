# ADR-004 — Aides de démonstration en iframe : double garde `DEBUG` + variable d'environnement

- **Statut :** Accepté (pratique en place, formalisée par cette décision)
- **Date :** 2026-09-11
- **Fichiers :** `backend/config/settings.py`, `backend/config/dev_middleware.py`,
  `backend/config/demo_admin_middleware.py`, `scripts/start_dev.sh`

## Contexte

Les environnements d'aperçu (la prévisualisation embarquée dans l'outil de développement,
hôte `*.e2b.app`, et les démos locales) affichent l'application dans une **iframe
cross-site** où :

- les navigateurs bloquent souvent les cookies tiers : l'admin Django (qui a besoin du
  cookie CSRF et du cookie de session) renvoie alors des 403 en boucle ;
- l'en-tête `X-Frame-Options: DENY` posé par défaut par Django interdit tout affichage en
  iframe.

Il ne faut pourtant affaiblir ni le CSRF, ni l'authentification, ni la protection
anti-clickjacking en production.

## Décision

Deux middlewares de **démonstration uniquement** sont conservés, avec des gardes strictes :

1. **`DevPreviewFrameMiddleware`** (`config/dev_middleware.py`) : retire `X-Frame-Options`
   et pose une CSP `frame-ancestors` (variable `DEV_FRAME_ANCESTORS`, défaut `*`).
   Il n'est **même pas enregistré** dans la pile : `settings.py` l'insère uniquement
   dans le bloc `if DEBUG:`. En production (`DEBUG=False`), il n'existe pas dans la pile,
   donc `X-Frame-Options: DENY` reste appliqué.
2. **`DemoAdminAutoLoginMiddleware`** (`config/demo_admin_middleware.py`) : présent dans la
   pile mais totalement inerte sauf si **les trois** conditions sont réunies :
   `DEBUG=True` **et** `DEMO_ADMIN_AUTOLOGIN` activée (`1/true/yes`) **et** chemin
   commençant par `/admin/`. Dans ce cas il dispense la requête de CSRF cookie et connecte
   automatiquement le premier superutilisateur.

Ces aménagements ne sont activés que par `scripts/start_dev.sh` (environnement local de
démonstration, clé de développement explicite). Les images Docker de production ne
définissent ni `DEBUG=True` ni `DEMO_ADMIN_AUTOLOGIN`.

## Conséquences

- L'aperçu intégré et les démos locales fonctionnent sans manipulation manuelle de cookies.
- En production, aucune dispense CSRF, aucune connexion automatique, et la protection
  anti-clickjacking par défaut est pleinement active : chaque affaiblissement est gardé par
  `DEBUG` et, pour l'auto-connexion, par un second interrupteur explicite.
- Tout nouvel aménagement de démonstration doit suivre le même patron : hors pile ou
  inerte par défaut, jamais actif seulement par oubli d'une variable.

## Alternatives rejetées

- **Laisser ces assouplissements actifs en permanence avec une simple note.** Rejeté : une
  mauvaise valeur de `DEBUG` ou un oubli de configuration exposerait l'admin sans CSRF.
- **Tenter de faire fonctionner les cookies tiers dans l'iframe sans middleware dédié.**
  Rejeté : certaines politiques navigateur (iframes sans `allow-same-origin`) rendent
  l'admin inutilisable quoi qu'il arrive ; un garde-fou explicite et inerte en prod est
  préférable à une rétention d'erreur permanente.
- **Désactiver globalement `XFrameOptionsMiddleware`.** Rejeté : supprimerait la protection
  pour toutes les réponses, y compris en production.
