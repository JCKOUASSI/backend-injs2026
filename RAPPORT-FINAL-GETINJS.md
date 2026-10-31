# Rapport final — GET INJS APP

**INJS d'Abidjan — Marcory, Côte d'Ivoire**
**Date :** 31 octobre 2026 · **Branche :** `arena/d40e4a41-backend-injs2026` · **HEAD :** `518d0ac`
**Objet :** état réel du générateur d'emplois du temps, preuves à l'appui.
**Document de conception détaillé :** `Conception-GET-INJS.txt` (identique dans `docs/getinjs/`).

Statuts employés, sans nuance : **PASS** (exécuté et vert), **PARTIAL** (livré,
mais une partie reste non exécutée), **BLOCKED** (impossible dans cet
environnement, avec le motif), **FAIL** (exécuté, en échec).

---

## 1. Lots de la mission

| Lot | Objet | Statut | Preuve |
|---|---|---|---|
| 1 | Référentiels (8 filières, maquettes UE/ECUE) | PASS | import + contrôle source↔base, tests `formations` |
| 2 | Campagnes de génération | PASS | 16 tests `edts.tests.test_campagnes`, transitions + verrou |
| 3 | Import XLSX/CSV des inscrits | PASS | idempotence, 0 ligne rejetée à 14 000 |
| 4 | Adaptateur pédagogique (maquette → besoins) | PASS | `besoins_maquette`, motif explicite si maquette absente |
| 5 | Générateur déterministe | PASS | backtracking + déterminisme testé sur deux exécutions |
| 6 | Diagnostics (audit « puis-je générer ? ») | PASS | `/api/edts/lmd/audit/`, 12 contrôles classés |
| 7 | Simulateur (sans persistance) | PASS | `persister=False`, EDT officiels intacts |
| 8 | Publication atomique | PASS | aucun EDT publié si un seul échoue |
| 9 | Consultation multi-filtres + exports CSV/XLSX/PDF | PASS | 3 exports, PDF A4 paysage vérifié |

## 2. Chantiers livrés sur cette branche

| # | Livraison | Commit | Vérification |
|---|---|---|---|
| 1 | Séance modifiable : déplacement revalidé C1→C10, annulation motivée réversible | `d04f0f8` | HTTP réel : 26 candidats, POST 200, 400 sans motif |
| 2 | Contraintes souples (trous, séries, surcharges) | `a01c8cd` | 20 tests, inactives par défaut |
| 3 | Politique réglable dans l'admin, sans redéploiement | `51935b7` | admin HTTP 200/302/403, API `origine: base` |
| 4 | Bilan annuel des règles souples + mesure d'activation rejouable | `ebd97f4` | +5,4 % (3 500), +6,9 % (14 000), plan identique |
| 5 | Décision appliquée et transportable (commande reproductible) | `d304dae` | 16 tests, décision tracée en base |
| 6 | **PostgreSQL exécuté pour la première fois** | `d837e66`, `1c2b785` | 9 groupes verts, 2 733 tests |
| 7 | CI distante : tentative réelle, écart consigné | `327d746` | étapes du workflow rejouées en local |
| 8 | Canevas officiel contrôlable + pause déduite, pas inventée | `a33da2b`, `d26fc6c` | 19 tests + 3 avertissements d'audit |
| 9 | Jeu de démonstration identifiable (aperçu réellement utilisable) | `44a0484` | 10 tests, parcours complet vérifié en direct |
| 10 | **Preuves visuelles réelles** (navigateur), 3 défauts d'affichage corrigés | `518d0ac` | 9 captures `docs/getinjs/preuves/`, 0 requête externe, +7 tests |

## 3. Preuves d'exécution (30 octobre 2026)

### Tests backend — deux SGBD

| Groupe | Tests | SQLite | PostgreSQL 16.2 |
|---|---:|---|---|
| scolarite | 454 | PASS | PASS |
| formations | 270 | PASS | PASS |
| auth | 242 | PASS | PASS |
| habilitations | 480 | PASS | PASS (625 s) |
| **edt + presences** | **570** | PASS (120 s) | PASS (112 s) |
| evaluations | 230 | PASS | PASS |
| pilotage | 201 | PASS | PASS |
| socle | 188 | PASS (68 s) | PASS (97 s) |
| divers | 139 | PASS | PASS |
| **Total** | **2 774** | **PASS** | **PASS** |

PostgreSQL 16.2 obtenu sans privilège racine (`pgserver`), base `injs_pg`,
**208 tables créées par les migrations réelles** — aucun schéma fabriqué à la main.

### Frontend

| Contrôle | Résultat |
|---|---|
| `npx vitest run` | **113 fichiers / 2 027 tests**, code 0 (134 s) |
| `npm run lint` | 0 erreur |
| `npm run build` | OK (3,2 s) |

### Charge (mêmes données synthétiques, transaction annulée)

| Volume | Base | Import | Génération | Séances placées | Non placées |
|---|---|---:|---:|---:|---:|
| 3 500 | SQLite | 14 663 ms | 8 598 ms | 2 065 | 0 |
| 3 500 | **PostgreSQL** | 14 262 ms | **3 497 ms** | 2 360 | 0 |
| 14 000 | SQLite | 57 802 ms | 149 353 ms | 8 190 | 0 |
| 14 000 | **PostgreSQL** | 55 662 ms | **54 401 ms** | 9 360 | 0 |

PostgreSQL est **2,5× à 2,7× plus rapide** que SQLite sur la génération :
les chiffres SQLite publiés précédemment sont un majorant.

### Parcours complet sur la base de démonstration (30 octobre 2026)

Chaîne entière exercée par l'API réelle, sans passer par le shell :

| Étape | Résultat mesuré |
|---|---|
| Audit « puis-je générer ? » | **OK** — 3 contrôles verts, `generable: true` |
| Génération annuelle (4 groupes) | `status_global: COMPLETE`, 4 EDT persistés |
| Séances | **24 placées / 0 non placée**, 240 étudiants couverts |
| Contraintes souples (actives) | 0 trou, 0 série longue, 0 journée chargée, **0 pénalité** |
| Grille d'un EDT | jours et créneaux réels du canevas officiel, salles affectées |
| Export PDF | 200 — 2 263 octets |
| Export XLSX | 200 — 6 525 octets |
| Export CSV | 200 — 476 octets, en-têtes et lignes conformes |

### Services en ligne (aperçus)

| Service | État |
|---|---|
| API Django `:8000` | RUNNING (200) |
| Site GET-INJS `:3000` | RUNNING (200) |
| Flutter web `:3001` | **BLOCKED** — SDK absent ; `storage.googleapis.com` et `pub.dev` répondent `SSL_ERROR_SYSCALL` (revérifié le 30/10 à 21 h) |

### Preuves visuelles (31 octobre 2026) — navigateur réel

Chromium 153 exécuté **dans le bac à sable, sans privilège root** (`@sparticuz/chromium`
+ `puppeteer-core`, bibliothèques NSS/NSPR compilées depuis les sources), piloté en
`fr-FR` sur 1360×900. Connexion réelle par le formulaire (`admin` / mot de passe de
démonstration), **pas** d'appel API direct.

| Capture (`docs/getinjs/preuves/`) | Ce qu'elle établit |
|---|---|
| `01-connexion.jpg` | écran de connexion, marque INJS, comptes de démonstration |
| `02-audit-donnees.jpg` | audit « puis-je générer ? » : **3 OK / 0 avertissement / 0 bloquant**, 12 besoins, 48 h, 24 créneaux, 4 salles |
| `03-edt-grille-semaine.jpg` | EDT DEMO-G4, semaine 1, 3 séances placées, **0 conflit actif** |
| `04-edt-vue-tableau.jpg` | même EDT en vue tableau : créneau, semaine, contenu, salle, actions |
| `05-generation-annuelle.jpg` | écran de génération annuelle (année DEMO-2026-2027 sélectionnée) |
| `06-admin-affectations-generees.jpg` | admin Django : **12 affectations créées par le moteur**, 4 groupes |
| `07-admin-edt.jpg` | admin : les 4 emplois du temps persistés |
| `08-admin-politique-contraintes.jpg` | politique active : 4 h / 8 h / 15 min, auteur et date |
| `09-admin-tableau-de-bord.jpg` | tableau de bord admin, icônes et typographie rendues |
| `10-admin-craneaux.jpg` | créneaux types du canevas officiel |
| `apercu-edt-pdf-2026-10-30.png` | aperçu du PDF d'emploi du temps |

**Trois défauts révélés par ces captures, et corrigés** (aucun test ne pouvait les voir) :

1. **Liste des emplois du temps** — Bootstrap n'étant pas installé, `.d-flex`,
   `.text-truncate` et `.d-block` n'avaient aucun effet : l'année se collait au titre
   (« … DEMO-G4DEMO-2026-2027 ») et le badge de statut n'était plus aligné ;
   la classe manquait aussi dans la branche « sélectionné ». Corrigé en CSS sous
   `.edt-page` + test `frontend/src/pages/Edts.test.jsx` (2 tests ; retirer le
   correctif fait échouer le test).
2. **Cases à cocher** — `.form-check` n'avait aucune règle : la case native
   s'affichait collée au libellé (« Enregistrer les brouillons »), sur 38 usages.
   Règle ajoutée dans `designSystem.css`.
3. **Administration** — Inter et la police d'icônes venaient de
   `fonts.googleapis.com` : sans réseau, les icônes s'affichaient **en toutes
   lettres** (« chevron_right », « open_in_new », « filter_list »…). Les deux
   polices sont désormais **embarquées** (`backend/static/admin/fonts/`,
   sous-ensemble de 38 icônes : 35 Ko au lieu de 3,9 Mo, licences OFL et Apache 2.0
   jointes). Trois noms d'icônes inexistants corrigés : `smartphone`→`mobile`,
   `phonelink`→`devices`, `location_on`→`place`. Mesure après correction :
   **0 requête réseau externe** sur les pages d'admin.
   Cinq tests protègent l'invariant (`core.tests.test_admin_ressources_locales`) —
   dont un qui échoue si une icône est utilisée sans être dans le sous-ensemble.

Recette de la capture (rejouable ; `chromium` et les bibliothèques sont hors dépôt) :

```bash
# 1. binaire + bibliothèques (sans root)
npm i --prefix /tmp/shots puppeteer-core @sparticuz/chromium
LD_LIBRARY_PATH=/tmp/chlibs /tmp/chromium --version   # Chromium 153.0.8010.0
# 2. captures (script fourni dans l'historique de la branche, cf. docs/getinjs/preuves/)
LD_LIBRARY_PATH=/tmp/chlibs node /tmp/shots/run.mjs
```

Les bibliothèques NSS/NSPR absentes du bac à sable ont été **compilées depuis les
sources** (`sailfishos-mirror/nspr` 4.41, `mozilla/nss` en gyp+ninja) — c'est ce
qui débloque Chromium sans root. Cette recette est consignée parce qu'elle a coûté
plusieurs tentatives ; elle n'est pas nécessaire en production.

---

## 4. Décisions appliquées (et comment les révoquer)

Politique de contraintes souples, enregistrée en base avec auteur, date et motif :

| Paramètre | Valeur | Origine |
|---|---|---|
| actives | **true** | décision du commanditaire |
| max_heures_consecutives | **4 h** | référentiel, doc 2 §11 K |
| max_heures_par_jour | **8 h** | référentiel, doc 2 §11 K |
| tolerance_minutes | 15 | récréation / changement de salle |
| pause_dejeuner | **11:45 – 13:30** | **déduite** du canevas officiel (seul intervalle long) |
| poids | 1 / 2 / 3 | hérités du chantier 2 |

Ces règles **ne bloquent jamais** un placement : elles produisent des pénalités
visibles. Mesure : avec ces bornes, **aucune pénalité** sur les plans produits à
3 500 et 14 000 étudiants — l'activation est neutre aujourd'hui, protectrice
ensuite.

Révoquer sans redéployer :

```bash
python manage.py regler_contraintes_souples --desactiver --motif "…"
```

---

## 5. Ce qui n'est PAS exécuté (et pourquoi)

| Élément | Statut | Motif vérifié |
|---|---|---|
| CI GitHub Actions sur la tête de branche | **NOT RUN** | `gh workflow run` refusé en 403 (jeton sans `actions:write`) ; aucun run créé depuis 13:15 UTC malgré les poussées (44 exécutions enregistrées, quota probablement épuisé). Les 4 étapes non couvertes par les groupes (check, makemigrations, hygiène, collectstatic) ont été **rejouées en local sur PostgreSQL : vertes**. |
| Flutter web | **BLOCKED** | SDK absent du bac à sable ; `storage.googleapis.com` et `pub.dev` inaccessibles (seuls GitHub/npm/PyPI sortent). |
| Navigateur réel / capture d'écran | **PASS** (31/10) | Chromium 153 exécuté sans root après compilation de NSS/NSPR ; 11 captures dans `docs/getinjs/preuves/`, 0 requête externe. |
| Au-delà de 14 000 étudiants | **NOT RUN** | hors cible ; aucune extrapolation publiée. |
| PostgreSQL en configuration de production | **NOT RUN** | mesures sur serveur local, réglages par défaut, sans pooling. |

**FAIL : aucun.** Aucun test exécuté n'est en échec sur cette branche.

---

## 6. Décisions qui restent à l'INJS

1. **Valider le canevas de production** : `python manage.py verifier_canevas`
   dit en une commande si la base correspond au référentiel (manquants, non
   prévus, chevauchements).
2. **Resserrer les bornes** si 4 h consécutives / 8 h par jour paraissent trop
   larges — la commande `regler_contraintes_souples` rend l'essai réversible.
3. **Saisir le patrimoine réel** (salles, capacités) : sans capacité, la
   contrainte C4 n'est pas vérifiable et le moteur l'avertit.

---

## 7. Vérifier soi-même

```bash
# suite complète, par groupes, avec code de sortie par groupe
./arena/tests_par_groupe.sh

# canevas conforme au référentiel ?
python manage.py verifier_canevas

# politique réellement appliquée, et d'où elle vient
python manage.py regler_contraintes_souples --verifier

# charge reproductible (rien n'est conservé en base)
python manage.py benchmark_getinjs --etudiants 3500

# rendre l'aperçu utilisable (jeu marqué DEMO-…), puis le retirer
python manage.py donnees_demonstration_getinjs
python manage.py donnees_demonstration_getinjs --supprimer
```
