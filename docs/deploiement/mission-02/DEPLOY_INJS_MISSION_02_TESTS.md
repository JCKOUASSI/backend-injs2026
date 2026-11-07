# DEPLOY-INJS-2026 — Mission 02 — Résultats de tests réels

**Projet :** INJS Abidjan — `backend-injs2026`
**Date d'exécution :** 06 novembre 2026
**Principe :** ce document ne contient que des exécutions **réellement
effectuées**. Chaque résultat est distingué selon son environnement
(sandbox Python 3.11.2 / CI Python 3.12) et aucune mesure n'est estimée.

---

## 1. Tableau de synthèse

| Contrôle | Commande | Résultat | Environnement |
|---|---|---|---|
| Tests backend (suite complète) | `manage.py test` | **3 103 tests — OK (9 ignorés, 0 échec)**, 983 s | sandbox, Python 3.11.2, SQLite |
| Tests groupe EDT | `manage.py test presences.test_seances_edt edts` | **496 tests — OK**, 108 s | sandbox, Python 3.11.2 |
| Test B5 isolé | `manage.py test dashboard.test_kpi_date_reference` | **5 tests — OK**, 1,3 s | sandbox, Python 3.11.2 |
| Tests frontend | `npx vitest run` | **141 fichiers / 2 216 tests — 0 échec**, 148 s | Node 20 |
| ESLint | `npx eslint src --ext js,jsx --max-warnings 0` | **0 erreur, 0 avertissement, exit 0** | Node 20 |
| Build frontend | `npm run build` | **réussi**, 388 modules, 6,75 s | Node 20 |
| `pip check` | `python -m pip check` | **No broken requirements found** | sandbox |
| `manage.py check` | — | **no issues (0 silenced)** | sandbox |
| `manage.py check --deploy` | production (`DEBUG=0`, clé 60 car.) | **1 avertissement (W008), documenté** | sandbox |
| `makemigrations --check` | — | **No changes detected** | sandbox |
| `check_repo_hygiene` | — | **CONFORME** — 2 409 fichiers suivis vérifiés | sandbox |
| Politique B2 | `sh backend/docker_tests/db_setup_policy_test.sh` | **41 réussis, 0 échec** | sandbox |
| CI Python 3.12 | GitHub Actions | **voir §6 — résultat de l'exécution réelle** | CI |

---

## 2. Détail du blocage B2 — 41 tests

Harnais : `backend/docker_tests/db_setup_policy_test.sh`. Les binaires `python`,
`python3` et `gunicorn` sont remplacés par des **stubs qui journalisent leurs
appels** ; le vrai `backend/entrypoint.sh` est exécuté, puis on vérifie ce qui a
effectivement été lancé. La transmission de la variable est donc prouvée, pas
seulement affirmée.

```
== 1. Démarrage avec SKIP_DB_SETUP=true ==
  PASS  code retour 0
  PASS  la commande fournie est exécutée
  PASS  aucune migration lancée
  PASS  aucun collectstatic

== 2. Démarrage SANS variable (défaut sûr) ==
  PASS  aucune migration sans variable
  PASS  valeur 'true' / '1' / 'yes' / 'on' / 'TRUE' / ' true ' -> aucune migration

== 3. Démarrage avec variable invalide ==
  PASS  'oui' / 'ture' / 'FALSE_' / 'TRU' / '2' / '-1' -> refus (code 64)
  PASS  ... -> aucune commande exécutée

== 4. Préparation explicitement demandée (SKIP_DB_SETUP=false) ==
  PASS  'false' / '0' / 'no' / 'off' / 'FALSE' -> migrate exécuté explicitement

== 5. Exécution explicite des migrations (migrate_explicit.sh) ==
  PASS  --plan affiche l'état / n'applique rien
  PASS  --apply sans autorisation -> refus (code 3)
  PASS  --apply autorisé -> applique les migrations

== 6. Aucune migration implicite en configuration de production ==
  PASS  un seul processus lancé (gunicorn)
  PASS  aucune migration, aucun collectstatic en production

== 7. SKIP_DB_SETUP actif sans commande ==
  PASS  refus explicite (code 1)

RESULTAT B2 : 41 réussis, 0 échecs
```

### 2.1 Un piège de test corrigé en cours de route (à connaître)

La première version du harnais utilisait `( SKIP_DB_SETUP=oui; sh entrypoint.sh …)`.
Cette forme **n'exporte pas** la variable : le processus enfant ne la voyait
jamais. Résultat : le cas « sans variable » passait pour la mauvaise raison, et
les cas « valeur invalide » échouaient. Le harnais utilise désormais
`env SKIP_DB_SETUP=… sh entrypoint.sh`, seule forme qui transmet réellement la
variable. C'est exactement le type de faux positif que la mission demandait
d'éviter.

---

## 3. Blocage B5 — test EDT / KPI à date de référence

### 3.1 Constat de départ

Le test nommé `test_seances_aujourdhui_et_kpi_reellement_mesures` **n'existe pas**
dans le dépôt (recherche exhaustive sur les 251 fichiers de test) :

```
$ grep -rn "test_seances_aujourdhui" . --include='*.py' --include='*.md'
(aucun résultat)
```

Le défaut décrit, lui, est bien réel : `backend/dashboard/services.py:618`
(`get_presences_dashboard`) calcule les KPI avec `timezone.localdate()`, donc la
date de la machine — et aucune épreuve ne figeait cette date.

### 3.2 Ce qui a été fait — et ce qui n'a pas été fait

* **Aucune ligne de code métier modifiée** : `dashboard/services.py` et
  `presences/seances_supervision.py` sont intacts. Le comportement relevé par
  l'audit (0 séance le 06/11, 6 séances le 03/11) reste le comportement correct.
* Le test manquant est **créé** à l'identique de l'exigence :
  `backend/dashboard/test_kpi_date_reference.py`.

### 3.3 Contenu et résultat

| Test | Vérifie |
|---|---|
| `test_six_seances_le_jour_de_reference` | **6 séances** le 03/11/2026 |
| `test_taux_assiduite_de_la_date_de_reference` | **41,7 %** (5 présents / 12 attendus) |
| `test_pointages_comptes_le_jour_de_reference` | 5 pointages rattachés à la date |
| `test_jour_sans_seance_ne_renvoie_ni_zero_invente_ni_taux` | le lendemain : 0 séance, taux `None` (règle NULL ≠ 0) |
| `test_contexte_temporel_identique_donnees_et_dashboard` | la même date sert aux données **et** au dashboard |

```
$ python manage.py test dashboard.test_kpi_date_reference --verbosity 2
Ran 5 tests in 1.283s
OK
```

Mécanisme de déterminisme : `mock.patch.object(timezone, 'localdate', …)` fige
`timezone.localdate()` sur `2026-11-03`. Aucune dépendance à l'horloge de la
machine, aucun `sleep`, aucun jeu de données externe.

**Incident de mesure corrigé :** la première version du jeu de données donnait
`13,9 %` (5 présents / 36 attendus). Ce n'était pas un défaut de code mais une
erreur de dimensionnement : 6 séances × 6 étudiants. Le jeu de données a été
ramené à 12 attendus (6 séances × 2 étudiants) pour obtenir exactement
**41,7 %**, conformément au rapport d'audit. Le seuil n'a **pas** été ajusté
pour faire passer le test.

---

## 4. ESLint — traitement des 7 avertissements

État initial : **0 erreur, 7 avertissements** — donc `--max-warnings 0` échouait.

| Fichier | Avertissement | Correction |
|---|---|---|
| `components/generique/EcranRessource.jsx` | dépendance `useMemo` instable | `lignes` mémorisé via `useMemo` |
| `pages/getinjs/GetInjsApp.test.jsx` | `waitFor`, `apiMock` inutilisés | imports retirés |
| `pages/scolarite/Candidatures.jsx` | `useRef` inutilisé | import retiré |
| `pages/scolarite/DocumentsScolaires.test.jsx` | `waitFor` inutilisé | import retiré |
| `pages/scolarite/Groupes.jsx` | `actif` non consommé | renommé `_actif` (exclusion volontaire du périmètre, commentée) |
| `pages/scolarite/JournalScolarite.jsx` | `auditCharge` non lu | renommé `_auditCharge` |

Aucune modification de comportement ; la suite Vitest a été **rejouée après**
ces six retouches : **2 216 tests, 0 échec**.

```
$ npx eslint src --ext js,jsx --max-warnings 0
$ echo $?
0
```

---

## 5. Points non vérifiables dans cet environnement (dits explicitement)

| Contrôle | Raison | Où il est réalisé |
|---|---|---|
| Python **3.12** réel | sandbox : seul `python3.11` disponible, installation impossible | job CI `backend` |
| `nginx -t` (syntaxe candidate) | binaire `nginx` absent, pas d'installation système possible | mission 03, conteneur |
| Construction des images Docker | **moteur Docker absent** de la sandbox | job CI `docker` (`push: false`) |
| Tests HTTPS / cookies / CSRF réels | nécessitent le VPS et NPM | mission 03 |
| Upload 9 Mio / 11 Mio contre `client_max_body_size` | nécessite le gateway déployé | mission 03 |

Ces limites ne sont pas des échecs : elles sont hors de portée de la sandbox et
sont explicitement rattachées à un environnement où elles seront mesurées.

---

## 6. Blocage B4 — exécution CI réelle

Le workflow `ci.yml` a été rendu déclenchable sur la branche de livraison
(`push: branches: [main, 'deploy-injs-2026/**', 'arena/**']`).

L'exécution réelle et son verdict sont consignés **après** le push de la branche
— voir `DEPLOY_INJS_MISSION_02_GO_NO_GO.md`, section « État de la CI ». Le
résultat n'est pas anticipé ici : tant qu'aucun run n'a été observé, la CI est
déclarée **non encore exécutée**, jamais « verte ».
