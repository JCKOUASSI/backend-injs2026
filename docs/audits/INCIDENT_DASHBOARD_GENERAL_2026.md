# Incident — tableau de bord général INJS-LMD

Capture utilisateur (17 novembre 2026) : onglet « Vue d'ensemble » affiche « Impossible de charger les données / Erreur lors du chargement des indicateurs ». Le dépôt courant est **Django + React/Vite**, et non un frontend Flutter pour cet écran. Branche `arena/a8060ecf-backend-injs2026` ; aucun accès authentifié à l'API de production fourni à cette session.

## Vérifications et correction locale

- Route frontend `DashboardEngineView.jsx` : `GET /api/dashboard/overview/` ; l'API est montée dans `backend/dashboard/api_urls.py` et utilise `dashboard.services.get_direction_overview`. L'ancien écran avalait tout échec HTTP ou réseau derrière un unique message générique, y compris 401/403/404/500 ; le statut exact vu par l'utilisateur dans la capture **n'est donc pas déterminable**. La correction affiche le statut et une action utile, sans renvoyer de trace interne ni de chiffres fabriqués. Le bouton « Réessayer » demeure actif et testé. La console ne journalise plus l'objet d'erreur brut.
- Cause **prouvée dans le code backend** : la supervision appelée par le tableau général incluait **toutes les séances annulées historiques**, quelle que soit leur semaine ou leur jour ; elle chargeait en outre des EDT d'années sans rapport. Un tableau « du jour » pouvait donc afficher un nombre de séances erroné et payer le coût des relations et pointages de séances hors date. La lecture a été restreinte côté SQL à l'année couvrant la date et au jour du créneau, puis aux semaines réelles, **sans masquer une annulation à sa vraie date**. Le test d'intégration vérifie le KPI `seances_jour` de l'API du tableau : une annulation de semaine antérieure ne le grossit pas. Ce correctif réduit le travail inutile ; il ne prouve pas à lui seul que c'est l'unique cause de l'erreur de la capture.
- GET public `https://injs.badge-qr-code.pro/api/health/` : HTTP 200, DB `ok` au moment du contrôle. GET public `.../api/dashboard/overview/` : HTTP 401 attendu sans authentification. **Aucun appel authentifié ni journal serveur de production n'est disponible** : l'origine réelle (401, 500, timeout, schéma, réseau) reste à établir avec le statut de la requête dans DevTools ou un journal serveur filtré, sans partager de jeton/cookie/identifiants.

## Tests effectués

| Périmètre isolé | Résultat |
|---|---|
| Avant correction, `dashboard.tests` + `presences.test_seances_supervision` sur SQLite | 68/68 OK ; n'exerçaient pas l'annulation hors semaine |
| Après correction, backend ciblé SQLite | 98/98 OK |
| Après correction, backend ciblé PostgreSQL UTF8 isolé | 98/98 OK ; test API dashboard + annulation hors semaine rejoué séparément 1/1 OK |
| Frontend avant | 14/14 OK |
| Frontend après, y compris 500 sanitizé + retry et 401/403/404 | 16/16 OK ; lint et build OK (avertissement historique : chunk principal ~1,66 Mo) |
| Django | `check` OK ; migrations sans dérive ; aucune migration créée |

Journaux temporaires : `/tmp/injs-dashboard-baseline.log`, `/tmp/injs-dashboard-after-server.log`, `/tmp/injs-dashboard-pg-after.log`, `/tmp/injs-dashboard-pg-integration.log`, `/tmp/injs-dashboard-frontend-final.log`, `/tmp/injs-dashboard-build.log`. Serveur PostgreSQL local arrêté. **La résolution de l'incident en production n'est pas prouvée** ; ne pas annoncer l'écran réparé sur le domaine public sans test authentifié après déploiement autorisé.

## CI, année S1/S2 et déploiement

Le calendrier institutionnel par semestre et les règles d'interruption restent absents du dépôt : les semaines de fixtures manuelles ne qualifient pas une année automatique. Nouvelle tentative directe `gh workflow run ci.yml --ref arena/a8060ecf-backend-injs2026` : HTTP **403 `Resource not accessible by integration`** ; `gh run list` reste vide pour la branche. L'affirmation d'habilitation dans le message ne change pas les permissions effectives de l'intégration GitHub. Aucune publication d'images immuables ni sauvegarde/préflight du VPS n'est démontrée ici. **Pas de déploiement, pas d'écriture en production.** Pour lever le blocage, faire exécuter la CI par un compte Actions habilité, obtenir le calendrier officiel S1/S2 et analyser la réponse authentifiée réelle du dashboard avant toute bascule.
