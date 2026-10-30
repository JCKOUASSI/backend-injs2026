# Rapport final — GET INJS APP

**INJS d'Abidjan — Marcory, Côte d'Ivoire**
**Date :** 30 octobre 2026 · **Branche :** `arena/d40e4a41-backend-injs2026` · **HEAD :** `2f293b2`
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

## 3. Preuves d'exécution (30 octobre 2026)

### Tests backend — deux SGBD

| Groupe | Tests | SQLite | PostgreSQL 16.2 |
|---|---:|---|---|
| scolarite | 454 | PASS | PASS |
| formations | 270 | PASS | PASS |
| auth | 242 | PASS | PASS |
| habilitations | 480 | PASS | PASS (625 s) |
| **edt + presences** | **560** | PASS (102 s) | PASS (112 s) |
| evaluations | 230 | PASS | PASS |
| pilotage | 201 | PASS | PASS |
| socle | 183 | PASS (48 s) | PASS (97 s) |
| divers | 139 | PASS | PASS |
| **Total** | **2 759** | **PASS** | **PASS** |

PostgreSQL 16.2 obtenu sans privilège racine (`pgserver`), base `injs_pg`,
**208 tables créées par les migrations réelles** — aucun schéma fabriqué à la main.

### Frontend

| Contrôle | Résultat |
|---|---|
| `npx vitest run` | **112 fichiers / 2 025 tests**, code 0 |
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

### Services en ligne (aperçus)

| Service | État |
|---|---|
| API Django `:8000` | RUNNING (200) |
| Site GET-INJS `:3000` | RUNNING (200) |
| Flutter web `:3001` | **BLOCKED** — SDK absent, sources inaccessibles |

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
| Navigateur réel / capture d'écran | **NOT RUN** | Chromium non exécutable (`libnss3` absent, pas de root). Les preuves d'interface sont HTTP (codes + JSON), pas visuelles. |
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
```
