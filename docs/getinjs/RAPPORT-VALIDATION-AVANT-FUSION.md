# Rapport de validation avant fusion — branche `arena/d40e4a41-backend-injs2026`

**Date d'exécution** : 31 octobre 2026
**Branche validée** : `arena/d40e4a41-backend-injs2026` — HEAD `f3e2cd2`
**Pull request** : #1 (état au moment du rapport : `OPEN`, `CONFLICTING`, `DIRTY`)
**Objet** : exécuter les validations manquantes du lot et produire un bilan factuel permettant de décider de la fusion.

> Convention de lecture : chaque affirmation ci-dessous renvoie à une commande réellement exécutée dans cet environnement. Ce qui n'a pas pu être exécuté est déclaré **NON EXÉCUTÉ** avec sa cause exacte — jamais présenté comme réussi.

---

## 1. État du dépôt et de la demande de fusion

| Élément | Valeur mesurée |
|---|---|
| Branche de travail | `arena/d40e4a41-backend-injs2026` |
| HEAD au début de la validation | `5e1c18d` |
| HEAD après correctifs de cette mission | `f3e2cd2` |
| Écart avec `origin/main` | **88 commits d'avance, 1 commit de retard** |
| `origin/main` | un **unique commit racine** (`ca74cd8`) |
| Ancêtre commun | **aucun** — `git rev-list --parents -1 ca74cd8` renvoie un commit sans parent |
| PR #1 | `OPEN` / `mergeable: CONFLICTING` / `mergeStateStatus: DIRTY` |
| Volume de la PR | 86 commits, 353 fichiers, +42 271 / −3 371 (au premier relevé) |

**Conséquence factuelle** : GitHub ne peut pas calculer de fusion automatique. `main` ne contient qu'un commit racine, l'arbre de la branche en est totalement disjoint. Le contenu de fichier est donc comparable, mais l'**historique** ne l'est pas. Ce n'est pas un défaut du lot : c'est un état de dépôt qui exige une décision humaine (fusion avec `--allow-unrelated-histories`, écrasement de `main`, ou nouvelle PR depuis un tronc commun).

---

## 2. PostgreSQL réel — migrations et schéma

Environnement : PostgreSQL **16.2** fourni par la roue PyPI `pgserver` (aucun droit root, aucun `docker`), cluster `initdb` dans `/tmp/pg_injs/data`, port **55432**, deux bases : `injs_validation` (validation) et `injs_load` (charge).

| Vérification | Commande | Résultat |
|---|---|---|
| Configuration | `manage.py check` | 0 problème |
| Dérive de migrations | `manage.py makemigrations --check --dry-run` | **No changes detected** |
| Application du schéma | `manage.py migrate` | **OK — 208 tables** |
| Version du serveur | `select version()` | PostgreSQL 16.2 |

Aucune opération destructive, aucune réutilisation de sauvegarde comme référentiel : la base est un cluster neuf, migré par les seules migrations du dépôt.

---

## 3. Tests backend sur PostgreSQL

Le harnais du dépôt (`arena/tests_par_groupe.sh`) découpe les tests en 9 groupes pour éviter un `manage.py test` monolithique. Il a été rejoué **à l'identique** (`/tmp/run_pg_groups.sh`), sur PostgreSQL, avec `USE_SQLITE=0` explicite (le `backend/.env` force `USE_SQLITE=1`).

| Groupe | Applications | Tests | Durée | Résultat |
|---|---|---|---|---|
| scolarite | `scolarite` | **481** | 253 s | OK (2 ignorés) |
| formations | `formations` | **272** | 82,5 s | OK |
| auth | `authentication` | **242** | 250,9 s | OK |
| edt | `edts presences` | **581** | 170,9 s | OK |
| evaluations | `evaluations jurys` | **230** | 87,9 s | OK |
| pilotage | `statistiques config dashboard` | **201** | 25,1 s | 1 échec — voir §4 |
| socle | `core admissions administrations referentiels` | **188** | 132 s | OK |
| divers | `parametres suiviEvaluation graduation equivalences stages patrimoine ressources_humaines finances_etudiantes exports` | **139** | 30 s | OK |
| **habilitations** | `habilitations` | **480** | 2 261 s | OK (1 ignoré) |

**Total PostgreSQL : 2 814 tests, 2 813 réussis, 1 échec expliqué et non imputable au moteur (§4), 5 ignorés.** Le total correspond exactement au harnais SQLite du dépôt (2 814 tests, 9/9 groupes), ce qui écarte toute perte de couverture liée au changement de moteur.

Aucun test n'a été ignoré, assoupli ou désactivé pour obtenir ces résultats.

---

## 4. Différences SQLite ↔ PostgreSQL, contraintes et transactions

Aucun test ne diffère **du fait du moteur**. Le seul échec observé est un artefact de configuration du harnais, reproduit et expliqué :

```
FAIL: config.tests.test_apercu_hardening.PreviewAutoLoginTests
      .test_admin_est_connecte_et_post_ne_bloque_pas_sur_csrf
AssertionError: 403 == 403 : le bouton « Déconnexion » de l'aperçu ne doit
pas afficher d'erreur CSRF
```

* **Cause** : `backend/config/settings.py` (l. 199-207) n'insère `DemoAdminAutoLoginMiddleware` — celui qui pose `csrf_processing_done` **avant** `CsrfViewMiddleware` — que si `DEBUG` est actif **au chargement des réglages**. Le harnais PostgreSQL démarre en `DJANGO_DEBUG=0` ; le test simule ensuite `@override_settings(DEBUG=True)`, ce qui active l'autologin de l'aperçu (`arena/preview_autologin.py`) mais **ne peut pas réinsérer un middleware absent de la chaîne** : son `process_view` s'exécute après le contrôle CSRF, d'où le 403.
* **Preuve du diagnostic** : le même test, sur la même base PostgreSQL, avec `DJANGO_DEBUG=1` et `DEMO_ADMIN_AUTOLOGIN=1` (profil d'aperçu réel) → **24 tests OK**.
* **Décision** : aucun correctif produit, aucune modification du test. Le contrôle CSRF n'a pas été touché — l'interdiction explicite est respectée. L'anomalie est classée **artefact de harnais** (voir risque R6).

Contraintes et transactions : elles sont exercées par les suites ci-dessus (contraintes d'unicité, `select_for_update`, atomicité, contraintes `CheckConstraint`), sans différence de comportement relevée entre les deux moteurs sur ces 2 814 tests. Les tests spécifiques aux contraintes PostgreSQL exigeaient `STORAGES=STORAGE_DE_TEST` (stockage de test), appliqué partout.

---

## 5. Tests de charge (exécutés, pas simulés)

**Montage** : base `injs_load` (PostgreSQL local, port 55432) alimentée par un script de données synthétiques — **12 maquettes, 300 UE, 900 ECUE**, 3 comptes. API servie par **gunicorn, 3 workers** (`GUNICORN_WORKERS` du `entrypoint.sh`), `0.0.0.0:8001`, machine à **2 vCPU**. Client : **Locust 2.47.0**.

**Scénario** (`/tmp/locustfile.py`) : lecture des UE d'une maquette, liste des maquettes, familles, année courante, et deux `PATCH` sur des UE en brouillon.

| Utilisateurs simultanés | Requêtes | Débit | Médiane | p95 | Échecs applicatifs |
|---|---|---|---|---|---|
| 10 | 1 880 | 31,5 req/s | 16 ms | 57 ms | **0 %** |
| 50 | 6 968 | 116,4 req/s | 120 ms | 260 ms | **0 %** |
| 100 | 6 504 | 108,6 req/s | 610 ms | 910 ms | **0 %** |

* Le point chaud `…/maquettes/<id>/ues/` monte de 30,5 à 55,8 req/s avec un p95 ≤ 110 ms jusqu'à 50 utilisateurs.
* **Saturation entre 50 et 100 utilisateurs** : le débit plafonne à ~110 req/s et la médiane est multipliée par 5. Limite à attribuer à la configuration mesurée (3 workers, 2 vCPU, PostgreSQL sur la même machine), pas à une erreur applicative.
* **Quota de connexion** : le premier palier à 50 utilisateurs a produit **29 connexions refusées en HTTP 429** parce que tous les clients virtuels partagent une seule adresse IP et que le quota `login 20/min` s'applique par IP. La mesure a été reprise avec un jeton pré-obtenu (`CHARGE_TOKEN`) **sans modifier le quota** : aucun réglage de sécurité n'a été assoupli pour verdir la mesure.

**Ce que ces chiffres ne disent pas** : ils ne préjugent ni de la charge en production (nombre de workers, base distante, cache), ni du comportement au-delà de 100 utilisateurs. Aucun test de montée en charge prolongé (endurance) n'a été conduit.

---

## 6. Navigateurs — Chromium = référence, second moteur **NON EXÉCUTÉ**

Le poste de validation est le **bundle de production** (`vite build` puis `vite preview`, port 3100), servi par Chromium headless (paquet `@sparticuz/chromium`), et non le serveur de développement : les parcours sont donc exercés sur le code minifié réellement livrable.

**Contrôles vérifiés sur 1440 × 900** (captures `01` à `04`) :

| Vérification | Résultat |
|---|---|
| Connexion sur le bundle de production | OK |
| Liste des UE rendue par le bundle minifié | OK — 18 lignes (maquette sélectionnée) |
| Panneau ECUE alimenté | OK — 2 lignes |
| Contrôles interactifs sans nom accessible | **0** |
| Champs de formulaire sans libellé associé | **0** sur 7 |
| Erreur API 500 à la création | message explicite affiché, **saisie conservée** |
| Erreur de lecture des maquettes | « Impossible de charger les maquettes : panne simulée » — pas de page vide |
| Erreurs JavaScript inattendues | **0** |

Les erreurs 500 sont **injectées par interception de requêtes** (`page.setRequestInterception`) : aucune écriture en base, aucune modification du backend.

**Second moteur (Firefox ou WebKit) : NON EXÉCUTÉ.**
Cause exacte : le réseau du bac à sable n'autorise que `github.com`, `codeload.github.com`, `api.github.com`, `registry.npmjs.org`, `pypi.org`, `files.pythonhosted.org`.
* `npx playwright install firefox` → `ECONNRESET` sur `playwright.download.prss.microsoft.com`.
* `npx playwright install webkit` → `ECONNRESET`.
* `curl` vers `playwright.azureedge.net`, `cdn.playwright.dev`, `playwright.download.prss.microsoft.com`, `ftp.mozilla.org`, `archive.mozilla.org`, `storage.googleapis.com` → code `000` (aucune connexion).
* Les paquets npm `playwright-firefox` et `geckodriver` sont installables mais ne contiennent **aucun binaire de navigateur**.

Aucun test multi-moteur n'a donc été réalisé ; le lot n'a été validé que sur Chromium.

---

## 7. Mobile — trois niveaux strictement distingués

| Niveau | Statut | Détail |
|---|---|---|
| **Responsive bureau** | **exécuté** | Matrice 3 écrans × 5 largeurs (360, 390, 768, 1024, 1440 px) sur Chromium, mesures de `documentElement.scrollWidth` vs largeur de mise en page |
| **Émulation mobile** | **exécuté** | Viewport 390 × 844 (iPhone 12, DPR 3, UA iOS) et 360 × 800 (Android, DPR 2, UA Chrome Android), parcours complet |
| **Appareil physique** | **NON EXÉCUTÉ** | Aucun téléphone ni tablette disponible dans l'environnement ; aucun service de test distant joignable |

**Résultats après correctifs** : 40/40 vérifications OK.
* Aucun débordement horizontal sur les 15 combinaisons écran × largeur.
* Émulation iPhone 12 : connexion, écran UE/ECUE, panneaux empilés (722→1403 puis 1419→1836), 18 UE listées, formulaire contenu (gauche 8, droite 382 pour 390), aucune erreur JS.
* Émulation Android 360 × 800 : mêmes contrôles, formulaire contenu (gauche 8, droite 352 pour 360), aucune erreur JS.
* Captures : `05-mobile-390.jpg`, `06-mobile-360.jpg`, `07-mobile-formulaire-390.jpg`, `08-mobile-formulaire-360.jpg`.

**Réserve méthodologique** : l'émulation Chromium reproduit un viewport et un agent utilisateur, **pas** les performances, le moteur de rendu, les gestes tactiles réels ni les particularités de Safari iOS. Aucune conclusion n'est tirée sur appareil physique.

**Point technique notable** : sous émulation mobile, `window.innerWidth` peut dépasser la largeur demandée lorsque la page déborde (layout viewport élargi). Les premières mesures (446 px pour 390) ne prouvaient donc pas une mauvaise émulation : elles révélaient un **débordement réel**. Les mesures ont ensuite été faites sur `documentElement.clientWidth`, et l'attente de stabilisation sur `matchMedia('(width: Npx)')`.

---

## 8. Anomalies reproduites et corrigées (correctif minimal + non-régression)

Trois défauts réels, tous reproduits dans le navigateur avant correction, tous corrigés par des modifications **de style uniquement** (`frontend/src/index.css`, `frontend/src/styles/dashboardEngine.css`).

### A-1 — Classes utilitaires Bootstrap absentes (débordement de 56 px)

* **Symptôme** : sur un écran de 390 px, la page mesurait 446 px de large ; la pilule « Année académique » restait affichée sur téléphone ; l'`<input type="file">` marqué `d-none` dans **Référentiels** restait visible.
* **Cause** : `.d-none`, `.d-md-flex`, `.d-xl-block` sont utilisées par `Layout.jsx` (l. 244, 254) et `Referentiels.jsx` (l. 690) mais **aucune feuille du projet ne les définit** : Bootstrap n'est pas embarqué.
* **Correctif** : implémentation des trois classes avec la sémantique Bootstrap (768 px et 1200 px), `!important`, ordre des règles conforme.
* **Preuve avant/après** : `scrollWidth` 446 → 390 ; pilule masquée < 768 px ; fil d'Ariane masqué < 1200 px et visible au-delà.

### A-2 — Pistes de grille `fr` bloquées par leur `min-content` (débordement jusqu'à 1 492 px)

* **Symptôme** : le tableau de bord débordait **même sur un écran de 1440 px** (contenu de 1 492 px) et atteignait 1 010 px de contenu sur un écran de 360 px. Le panneau voisin du pipeline sortait de la page.
* **Cause** : `.row-pipeline-growth { grid-template-columns: 1.35fr 1fr }` — le minimum automatique d'une piste `fr` vaut le `min-content` de son contenu, et le stepper du pipeline (8 nœuds `min-width: 80px`) impose ~980 px. Les variantes mobiles (`1fr`, `1fr 1fr`) avaient le même défaut.
* **Correctif** : `minmax(0, …)` sur toutes les pistes concernées (`.row-pipeline-growth`, `.row-indicators-alerts`, `.row-activity-finance`, `.top-kpis-row`, y compris dans les points de rupture 1280 et 768 px). Le stepper gère déjà son propre défilement (`overflow-x: auto`).
* **Preuve avant/après** : 360 px → 1 010 → 360 ; 1440 px → 1 492 → 1 440.

### A-3 — Blocs d'accueil : `flex-basis` non neutralisée en colonne (19 px)

* **Symptôme** : à 360 px, les blocs d'accueil mesuraient 351 px pour un parent de 304 px.
* **Cause** : en `flex-direction: column` (≤768 px), `.greeting-text-block { flex: 1 1 500px }` et `.campus-hero-card { flex: 1 1 100% }` conservaient une base imposant leur largeur intrinsèque.
* **Correctif** : `flex: 1 1 auto; width: 100%; min-width: 0` sur les deux blocs dans le point de rupture mobile.
* **Preuve avant/après** : `scrollWidth` 379 → 360.

### Tests de non-régression

| Contrôle | Résultat |
|---|---|
| `vitest run` (frontend) | **115 fichiers / 2 073 tests OK** |
| `eslint src --ext js,jsx` | **0 erreur, 0 avertissement** |
| `vite build` | OK (avertissement de taille de chunk, préexistant) |
| Navigateur, 40 vérifications | **40 / 40 OK** — script et journal versionnés dans `docs/getinjs/preuves-validation/` |
| Backend | Aucune ligne de code backend modifiée dans cette mission : les suites backend ne sont pas concernées par ces correctifs |

Le harnais navigateur (`verif_navigateur.mjs`) **est** le test de non-régression de ces trois défauts : il échoue si un débordement réapparaît, à l'une quelconque des 15 combinaisons écran × largeur, ou si la pilule ou le fil d'Ariane réapparaissent au mauvais point de rupture.

---

## 9. Référentiel — contrôles d'intégrité

Contrôles exécutés sur la base du dépôt (`backend/db.sqlite3`) **et** via l'API réelle (`/api/scolarite/maquettes/…`), deux sources concordantes :

| Contrôle | Résultat |
|---|---|
| Unités d'enseignement | **326** |
| ECUE | **400** |
| Maquettes | 21 |
| Codes résiduels `E2E-*` / `SEC-*` | **0** (UE et ECUE) |
| Doublons de code (UE / ECUE) | **0** / **0** |
| ECUE orphelines / UE sans ECUE | **0** / **0** |
| Codes ECUE vides | **0** |
| Intitulés vides | **0** |
| ECUE avec `credits = 0` (affichées « — ») | **397 / 400** |
| ECUE avec crédits renseignés | 3 (`DEMO-ECUE1..3`, 3 crédits chacun) |

L'affichage « — » est produit par `afficherValeur()` (`frontend/src/pages/EcranUeEcue.jsx`, l. 92) qui traite `0` comme « non documenté » et non comme « zéro crédit » ; une légende l'explique à l'écran. **Aucune valeur n'est inventée.**

À signaler en revue métier : les trois ECUE `DEMO-*` font partie du référentiel chargé et ne sont pas des résidus de test ; leur présence est antérieure à cette mission et n'a pas été modifiée.

---

## 10. Sécurité, permissions et configuration

* Aucun réglage CSRF, aucune permission, aucune règle d'authentification n'a été modifié pour obtenir un résultat vert.
* Le quota de connexion (`login 20/min` par IP) a été **contourné côté client de test** (jeton pré-obtenu) et non désactivé côté serveur.
* Aucun secret n'est versionné : les variables utilisées (`DJANGO_SECRET_KEY` de test, mot de passe PostgreSQL vide) sont locales et jetables.
* Aucune opération destructive : pas de `DROP`, pas de `reset --hard`, pas de `clean -fd`, pas de déploiement, pas de fusion de la PR.
* Le contrôle `manage.py check` et `makemigrations --check` sont propres sur PostgreSQL comme sur SQLite.

---

## 11. Risques résiduels et recommandation

### Risques résiduels

| # | Risque | Criticité | Commentaire |
|---|---|---|---|
| R1 | **Aucun second moteur de navigateur validé** | moyenne | Firefox et WebKit n'ont pas pu être installés (réseau restreint). Le lot n'est prouvé que sur Chromium. |
| R2 | **Mobile validé en émulation seulement** | moyenne | Aucun appareil physique ; Safari iOS réel non testé. |
| R3 | **PR #1 non fusionnable automatiquement** | **élevée** | `origin/main` ne contient qu'un commit racine : aucun ancêtre commun. Décision humaine requise. |
| R4 | **Saturation à 100 utilisateurs** | moyenne | Débit plafonné à ~110 req/s, médiane ×5. Lié à 3 workers sur 2 vCPU ; dimensionnement de production à revoir. |
| R5 | **Quota de connexion par IP** | faible | Derrière un proxy unique, 20 connexions/min par IP peuvent gêner un déploiement en établissement sans `X-Forwarded-For` correct. |
| R6 | **Perte de session lors d'une requête interrompue** | faible | `AuthContext` purge le jeton si `GET /auth/me/` échoue (`.catch(() => _clearSession())`). Observé 7 fois dans le harnais lors de navigations interrompues ; non reproduit en usage manuel (F5 testé : session conservée). Non corrigé : toucher à l'authentification est hors périmètre et interdit par les consignes. |
| R7 | **Test dépendant de l'ordre des middlewares** | faible | `test_apercu_hardening` échoue si les réglages sont chargés avec `DEBUG=0`. Fragilité de test, pas défaut produit. |
| R8 | **Groupe `habilitations` lent** | faible | 480 tests en **2 261 s** : le premier passage a été interrompu par le budget de 1 800 s du harnais. Aucun blocage applicatif (progression continue, requêtes SQL actives) ; cause probable : coût des fixtures et du hachage de mots de passe. Le budget du harnais devrait être relevé pour ce groupe. |
| R9 | **Trois ECUE `DEMO-*` dans le référentiel** | faible | Données de démonstration assumées ; à confirmer métier. |

### Recommandation

**Fusion envisageable sur le plan technique, mais à différer sur le plan du dépôt.**

* Sur le plan **technique**, le lot est cohérent : 2 814 tests backend sur PostgreSQL réel (2 813 réussis), 2 073 tests frontend, ESLint sans erreur, bundle de production validé sur les parcours critiques, aucun débordement sur 15 combinaisons de largeur, référentiel conforme (326 UE / 400 ECUE, aucun résidu, aucune valeur inventée). Les trois anomalies reproduites ont été corrigées à la source, avec mesure avant/après et harnais de non-régression versionné.
* Sur le plan du **dépôt**, la fusion ne peut pas être automatique : `origin/main` est un arbre disjoint (commit racine unique). Fusionner en l'état exigerait `--allow-unrelated-histories`, c'est-à-dire une décision humaine sur l'historique de référence — hors du périmètre de cette mission, et explicitement exclu (« ne pas fusionner la PR #1 »).

**Conditions proposées avant fusion** : (1) arbitrer l'historique de `main` ; (2) rejouer la CI sur PostgreSQL après cet arbitrage ; (3) si le multi-moteur est exigé, exécuter Firefox et WebKit sur un environnement autorisant leurs CDN ; (4) si le mobile réel est exigé, prévoir un test sur appareil.

---

## Annexe A — Commandes reproductibles

```bash
# PostgreSQL 16.2 local, sans root
python -m venv /tmp/pgenv && /tmp/pgenv/bin/pip install pgserver
/tmp/pgenv/lib/python3.11/site-packages/pgserver/pginstall/bin/initdb -D /tmp/pg_injs/data
/tmp/pgenv/lib/python3.11/site-packages/pgserver/pginstall/bin/postgres -D /tmp/pg_injs/data -p 55432
createdb -h 127.0.0.1 -p 55432 -U postgres injs_validation

# Validation backend sur PostgreSQL
cd backend && USE_SQLITE=0 POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=55432 \
  POSTGRES_DB=injs_validation POSTGRES_USER=postgres \
  STORAGES=STORAGE_DE_TEST python manage.py test <applications>

# Bundle de production + navigation
cd frontend && npx vite build && npx vite preview --port 3100
cd docs/getinjs/preuves-validation && node verif_navigateur.mjs
```

## Annexe B — Preuves versionnées

`docs/getinjs/preuves-validation/`
* `verif_navigateur.mjs` — harnais de validation (bureau, matrice responsive, émulation mobile) ;
* `journal-navigateur.json` — 40 vérifications horodatées, moteur, réserves, incidents ;
* `01` → `04` — captures poste de travail (liste, formulaire, erreur API, échec de lecture) ;
* `05` → `08` — captures émulation mobile (390 et 360 px, écran et formulaire).
