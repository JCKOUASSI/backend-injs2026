# 07 — Plan d'action priorisé

## 1. Matrice gravité × effort

| Gravité ↓ / Effort → | **S** (< 1 j) | **M** (1–5 j) | **L** (> 5 j) |
|---|---|---|---|
| **Bloquant** | **FIX-01** CI rouge (hygiène) | | |
| **Élevé** | **FIX-02** médias non protégés · **FIX-03** `app.env` + workflow mobile · **FIX-04** `?access_token=` · **FIX-05** throttling global · **FIX-06** `npm audit` en CI | **FIX-07** durée de vie + révocation des jetons | |
| **Moyen** | **FIX-08** gzip API · **FIX-09** linter Python · **FIX-10** Redis pour le cache · **FIX-11** contrôles requis sur `main` | **FIX-12** découpage du bundle (lazy) · **FIX-13** couverture mesurée · **FIX-14** tests Flutter · **FIX-15** react-router 7 | **FIX-16** exports asynchrones · **FIX-17** découpage des fichiers géants |
| **Faible** | **FIX-18** index de documentation · **FIX-19** en-têtes CSP/Referrer | **FIX-20** suppression de `views_legacy` | |

Les sept premiers correctifs représentent **moins de trois jours de travail cumulés** et suppriment l'essentiel du risque identifié. C'est le message central de cet audit : le rapport coût/bénéfice est très favorable à court terme.

## 2. Lot 0 — Immédiat (72 heures)

### FIX-01 · Rétablir la CI · Bloquant · S

```bash
git rm --cached .ci/mobile-web/assets/assets/app.env
# .gitignore contient déjà **/assets/app.env : ne rien y ajouter
git commit -m "fix(ci): retirer app.env du suivi (hygiène du dépôt)"
git push
```

Puis vérifier que le run `CI` sur `main` exécute bien l'étape **Tests** et se termine vert.

Traiter aussi le **motif**, pas seulement ce fichier : `livrables/*.csv` n'est pas exempté par la commande et a provoqué le premier échec du 18/11. Soit ces fichiers sortent du suivi, soit une exception documentée est ajoutée à `check_repo_hygiene` (avec test).

**Sortie** : `manage.py check_repo_hygiene` → code 0 ; dernier run `ci.yml` sur `main` = `success` avec l'étape « Tests » exécutée.

### FIX-02 · Fermer l'accès public à `/media/` · Élevé · S

Dans `docker/nginx/default.conf`, supprimer le bloc `location /media/` (ou le remplacer par un `internal;` accessible uniquement via `X-Accel-Redirect` depuis Django), puis router `/media/` vers le backend pour que la vue authentifiée s'applique.

**Sortie** : `curl -I https://<hôte>/media/<fichier>` → 401/403 sans session ; un utilisateur autorisé obtient toujours son fichier.

**Attention** : vérifier au préalable qu'aucune fonctionnalité ne dépend du téléchargement direct (badges QR, PDF générés, images d'habilitation). Un test manuel sur trois écrans suffit.

### FIX-03 · Arrêter de versionner les artefacts mobiles · Élevé · S

Dans `apercu-mobile-web.yml` : supprimer `git add -f .ci`, exclure `**/app.env`, retirer `[skip ci]` (ou ajouter une vérification séparée), corriger le commentaire erroné sur `.ci/` ignoré. Décider ensuite du sort des 42 Mo déjà dans l'historique : les laisser (coût : taille du clone) ou nettoyer avec `git filter-repo` (coût : réécriture d'historique, à faire hors période de livraison, avec sauvegarde du dépôt).

**Sortie** : un build mobile ne modifie plus le suivi Git ; `git ls-files .ci | wc -l` = 0.

### FIX-04 · Limiter `?access_token=` aux aperçus · Élevé · S

Conditionner la branche « jeton en query string » de `FlexibleJWTAuthentication` à `settings.DEBUG` ou `settings.PREVIEW_SPA`, et ajouter `Referrer-Policy: no-referrer` au gateway (bénéfice même après correction).

**Sortie** : test automatisé prouvant qu'en `DEBUG=False` une requête `?access_token=<valide>` sans en-tête renvoie 401.

### FIX-05 · Throttling global · Élevé · S

Ajouter `DEFAULT_THROTTLE_CLASSES` (`AnonRateThrottle`, `UserRateThrottle`) avec des quotas larges (par ex. 60/min anonyme, 240/min authentifié), et des quotas dédiés sur les exports/imports (`exports` 10/min).

**Sortie** : test vérifiant un 429 au dépassement sur un endpoint d'export.

### FIX-06 · Contrôler les dépendances en CI · Élevé · S

Ajouter au job frontend : `npm audit --audit-level=high`, et au job backend un outil de scan (`pip-audit`). Accepter explicitement les exceptions dans un fichier documenté plutôt que de laisser le contrôle muet.

**Sortie** : la CI échoue si une vulnérabilité haute est introduite.

### FIX-11 · Vérifier les contrôles requis sur `main` · Moyen · S

Action manuelle dans les réglages GitHub (non lisible via l'API avec les droits actuels) : rendre « CI / Backend » et « CI / Frontend » **requis** avant fusion, interdire le push direct sur `main`.

**Sortie** : capture d'écran des règles de protection annexée au dossier ; un push direct sur `main` est refusé.

## 3. Lot 1 — 30 jours

| Réf. | Action | Effort | Sortie attendue |
|---|---|---|---|
| FIX-07 | Access token 30 min, `token_blacklist` activé, refresh révoqué au logout | M | déconnexion effective côté serveur ; test d'un refresh révoqué → 401 |
| FIX-08 | `gzip on` + `application/json` au gateway | S | en-tête `Content-Encoding: gzip` sur `/api/` ; mesure avant/après sur un écran de 200 lignes |
| FIX-09 | `ruff` (E,F,I,B) + `ruff format --check` | S–M | CI bloquante après un lot de nettoyage initial |
| FIX-10 | Service Redis dans le compose de production | S | `REDIS_URL` défini ; compteurs de throttling cohérents entre workers |
| FIX-12 | Passer les 80 imports de pages en `lazy()` | M | `index-*.js` < 500 Ko ; premier rendu mesuré |
| FIX-13 | `coverage` backend (seuil = niveau mesuré) + rapport front en artefact | M | deux rapports publiés à chaque run ; tendance suivie |
| FIX-14 | Tests Flutter : scan, file de synchronisation, double scan | M | `flutter test` en CI, ≥ 10 tests |
| FIX-15 | `react-router-dom` 7.18.x (API déclarative uniquement : `Link`, `useParams`, `useSearchParams`, `useNavigate`, `Routes`) | M | `npm audit --omit=dev` = 0 vulnérabilité ; suite front verte |
| FIX-19 | CSP, `Referrer-Policy`, `Permissions-Policy` au gateway | S | en-têtes présents sur HTML et API ; recette des écrans utilisant des iframes/aperçus |

## 4. Lot 2 — 90 jours

| Réf. | Action | Effort | Sortie attendue |
|---|---|---|---|
| FIX-16 | Exports massifs en tâche asynchrone, après mesure des durées | L | aucun export > 30 s dans la requête ; téléchargement différé |
| FIX-17 | Découpage des 4 fichiers backend > 2 000 lignes et de `Statistiques.jsx` | L | aucun fichier > 800 lignes ; tests inchangés et verts |
| FIX-18 | `docs/README.md` index, rapports racine déplacés dans `docs/rapports/`, section « historique » | S | documentation navigable depuis un point unique |
| FIX-20 | Suppression ou justification écrite de `dashboard/views_legacy.py` | M | plus de code « legacy » routé, ou ADR expliquant le maintien |
| — | Test de restauration de sauvegarde trimestriel | S | date et résultat consignés dans le runbook |
| — | Alerte sur les erreurs 5xx et sur le healthcheck | M | notification reçue en cas de panne simulée |

## 5. Indicateurs de suivi

À revoir mensuellement, avec une cible à 6 mois :

| Indicateur | Aujourd'hui | Cible |
|---|---|---|
| Taux de runs `ci.yml` verts (7 derniers jours) | 5 % (1/20) | ≥ 95 % |
| Durée de la CI | non mesurable (suite non atteinte) | < 20 min |
| Couverture backend | non mesurée | ≥ 70 % puis stable |
| Couverture frontend | non publiée | ≥ 60 % |
| Taille du bundle initial (gzip) | 398 Ko | < 150 Ko |
| Vulnérabilités `npm audit` (production) | 3 modérées | 0 |
| Fichiers > 1 000 lignes | 9 | ≤ 4 |
| Vulnérabilités `pip-audit` | non mesuré | 0 haute |
| Médias accessibles sans authentification | oui | non |
| Dernier test de restauration | inconnu | < 90 jours |

## 6. Ce qu'il ne faut pas faire

- **Ne pas lancer un chantier de réécriture.** Le socle est sain ; les problèmes sont localisés et corrigeables par petites touches.
- **Ne pas viser 90 % de couverture.** Sans mesure préalable, l'objectif produirait des tests d'affichage sans valeur. Mesurer, puis progresser par paliers.
- **Ne pas découper `Statistiques.jsx` et `formations/api_views.py` en même temps** que la migration `react-router` : deux chantiers risqués en parallèle rendent le diagnostic d'échec impossible.
- **Ne pas supprimer `.ci` de l'historique Git** pendant une période de livraison : la réécriture d'historique invalide les clones existants.
- **Ne pas activer `SECURE_SSL_REDIRECT=True`** sans vérifier la chaîne Nginx : le commentaire du code indique qu'il casse le CSRF derrière proxy. Le vrai correctif est de confirmer que la redirection HTTP→HTTPS existe au niveau du gateway.

## 7. Dépendances entre actions

```
FIX-01 (CI verte) ──▶ FIX-13 (couverture) ──▶ FIX-09 (linter bloquant)
        │                    └──▶ FIX-14 (tests Flutter)
        ├──▶ FIX-06 (audit dépendances) ──▶ FIX-15 (react-router 7)
        └──▶ FIX-11 (protection de branche)
FIX-02 (médias) indépendant, à faire sans attendre
FIX-12 (bundle) indépendant ──▶ FIX-17 (découpage des pages)
```

Autrement dit : **rien ne peut être mesuré avant FIX-01**. C'est pourquoi il est le premier point du plan.
