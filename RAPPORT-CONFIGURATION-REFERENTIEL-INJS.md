# Configuration opérationnelle de backend-injs2026 depuis le référentiel officiel

**INJS d'Abidjan — Marcory, Côte d'Ivoire**
**Date d'exécution :** 29 octobre 2026
**Branche :** `arena/d40e4a41-backend-injs2026` — dernier commit `986e97e`
**Nature :** exécution réelle (extraction, imports en base, corrections de code, tests), pas un audit.

---

## 1. État initial

### Dépôt et environnement

| Élément | Constat |
|---|---|
| Branche de travail | `arena/d40e4a41-backend-injs2026`, base `5369acf` |
| Branches distantes | `origin/main`, branche Arena — **aucune autre** |
| Répertoire | `/home/user/backend-injs2026` |
| Backend | Django 5.1.4 / Python 3.11 |
| Frontend réel | **React + Vite** (pas Flutter) — 105 fichiers de tests, 1 979 tests |
| Base | SQLite (`USE_SQLITE=1`), `backend/db.sqlite3` |
| Migrations | à jour, 0 migration en attente au départ |

### Le classeur : présent, et retrouvé

Le fichier réclamé, **`INJS D'ABIDJAN — RÉFÉRENTIEL EXHAUSTIF DE L'OFFRE DE FORMATION2.xlsx`**,
**existe sur `origin/main`** (113 114 octets). Il était absent de l'arborescence de
travail, ce qui avait conduit à tort à conclure à son inexistence : il est en
réalité **exclu du versionnement par `.gitignore` (ligne 48, `*.xlsx`)**, tout en
restant présent dans l'arbre de `main` déjà suivi.

Il a été récupéré par `git show origin/main:<chemin>`, ses empreintes ont été
vérifiées, puis il a été **versionné sur la branche** (ajout forcé, `-f`, car
toujours exclu par `.gitignore`) afin que l'extraction ne dépende plus d'un fetch.

**Cause racine de l'échec précédent :** recherche d'un fichier suivi dans le seul
arbre de travail, sans vérifier l'arbre de `origin/main`. Le `.docx` avait alors
servi de source de repli. Il reste disponible comme **repli documenté**.

### Insuffisances constatées avant travaux

1. Référentiel LMD incomplet : 0 UE, 0 ECUE, 0 maquette en base.
2. `qualifier_referentiel_injs_l6` produisait 4 lignes par filière au lieu de 2, toutes typées `MASTER`.
3. Coquilles ES/MS créées sans `type_diplome` et jamais complétées.
4. Route API `/maquettes/<id>/ues/` en **405** alors que l'écran frontend l'interrogeait.
5. Un paramètre de filtre vide provoquait une **erreur 500**.
6. Aucun référentiel « famille de modules » alors que le classeur en publie 12.

---

## 2. Référentiel Excel

### Périmètre lu

**19 feuilles**, dont **1 masquée** (`Listes`).

| Feuille | Objet | Exploitation |
|---|---|---|
| `Accueil` | périmètre, sources, limites | documentation |
| `1. Filières & Concours` | 2 mentions, 8 filières, 4 concours | **importé** |
| `2. Cycle professionnel` | 13 cycles (2 ans) | extrait (non importé — voir §5) |
| `3. Formations à la carte` | 17 formations, 9 catégories | extrait (non importé) |
| `4. Semestres & Grades` | paliers, 60 crédits/an, grades | contrôlé |
| `5. Organisation` | 8 structures (ENSEPS, CNSHN, DAF…) | extrait |
| `6. Groupes, Catég. Horaires` | organisation pédagogique | contrôlé |
| **`8. Base UE (source TCD)`** | **base normalisée 323 lignes × 12 colonnes** | **source des maquettes** |
| `7. Statistiques`, `9. Analyse dynamique` | tableaux croisés | lecture |
| **`Listes` (masquée)** | 11 listes de référence | **importé** (statuts) |
| `10. Suivi inscriptions` | formulaire, matricule `INJS-ANNEE-FILIERE-Nº` | contrôlé |
| `11. Suivi des notes` | 1 ligne = 1 étudiant × 1 UE, CC 0,4 / Examen 0,6 | contrôlé (non appliqué) |
| `12. Relevé de notes` | décisions, seuil 10/20 | contrôlé (non appliqué) |
| `13. Emploi du temps (modèle)` | 4 plages horaires | **importé** |

### Données importées

| Catégorie | Volume |
|---|---|
| Filières (F01–F08) | **8** |
| Mentons / écoles | 2 mentions, 2 écoles |
| Cycles de formation INJS | 12 (4 filières × Licence + Master, 4 filières ENSEP) |
| Niveaux / semestres | 5 / 10 |
| Maquettes (filière × niveau) | **20** |
| **UE** | **323** |
| **ECUE** | **397** |
| Crédits ECTS | **1 170** |
| Familles de modules | **12** |
| Statuts étudiants (feuille masquée) | **9** |
| Créneaux types (feuille 13 × 6 jours) | **24** |

### Anomalies détectées dans la source

1. **MS S8 absent** : le classeur ne contient aucune UE pour Management du Sport / Semestre 2 (M1/S8). Le document saute de S7 à S9. **Aucune UE inventée** ; écart signalé à chaque exécution.
2. **F05–F08 sans maquette** : Andragogie, Loisir, ECJP et Gérontologie sont décrites (Licence pro + Master pro) mais aucun tableau ne détaille leurs UE.
3. **Sigles absents** : le classeur écrit « — » pour Andragogie, Loisir et Gérontologie.
4. **Aucun code officiel** d'UE ni d'ECUE, aucun volume CM/TD/TP.

### Éléments restant à confirmer

- Pondérations **CC 0,4 / Examen 0,6** et **seuil 10/20** : le classeur les présente lui-même comme « à confirmer avec le règlement intérieur ». **Non appliqués** dans le code.
- Statuts bloquants : le classeur liste 9 statuts mais ne dit pas lesquels empêchent une inscription. `bloque_inscription` **n'a pas été déduit**.

---

## 3. Modifications réalisées

### 3.1 Extraction reproductible — `backend/scripts/extraire_referentiel_offre_formation.py`

| | |
|---|---|
| Fonctionnalité | Lit le **classeur** (19 feuilles) et produit un jeu de données JSON traçable ; repli `.docx` documenté avec `meta.source_type` |
| Justification | La source doit être le classeur officiel ; chaque ligne doit être auditable |
| Résultat | `scolarite/data/referentiel_offre_formation.json` — 323 UE / 397 ECUE / 1 170 crédits, **clé métier `Filière|Semestre|UE` conservée** |

**Correction notable :** la première extraction (`.docx`) comptait **405 ECUE**.
Le classeur fournit une colonne autoritaire « Nb ECUE » : huit UE comptaient en
réalité **une seule** ECUE dont l'intitulé contient un point-virgule
(« Judo : Fondamentaux ; Lutte : Fondamentaux »). Le nombre du classeur fait
foi → **397 ECUE**. Les 8 ECUE créées en trop ont été **archivées**, jamais
supprimées.

### 3.2 Référentiel « famille de modules » — `scolarite/models.py`, migration `0016`

| | |
|---|---|
| Fonctionnalité | Nouveau modèle `FamilleModule` (code, libellé, ordre) + FK `famille` sur `UE` |
| Justification | Le classeur attribue une famille à chacune des 323 UE (12 familles) ; c'est l'axe d'analyse des crédits |
| Résultat | 12 familles, **0 UE sans famille**, axes exposés en API et en admin |

*Migration additive et réversible ; aucune donnée existante modifiée.*

### 3.3 Commande d'initialisation — `configurer_referentiel_injs`

| | |
|---|---|
| Fonctionnalité | Écrit maquettes (BROUILLON), UE, ECUE, familles, statuts et créneaux — **idempotent, non destructif** |
| Justification | Le référentiel doit être rejouable sans doublon ni destruction |
| Résultat | 1ʳᵉ passe : 20 maquettes, 323 UE, 397 ECUE ; **2ᵉ passe : 0 création, 0 modification** |

Points respectés : aucun parcours, aucun volume horaire, aucun code présenté
comme officiel, aucune activation automatique (statut `BROUILLON`), maquettes
validées jamais modifiées, ECUE surnuméraires **archivées**.

### 3.4 Bug préexistant corrigé — `qualifier_referentiel_injs_l6`

| | |
|---|---|
| Anomalie | **4 lignes par filière**, toutes typées `MASTER` (`… — LICENCE — LICENCE`) |
| Cause | `CORPUS_INJS` contient déjà les suffixes de cycle ; la commande les re-suffixait, puis `attestes[1 - len(attestes)]` renvoyait toujours le dernier diplôme |
| Correction | Plus aucun re-suffixage ; cycle lu dans l'intitulé et vérifié contre les diplômes attestés |
| Résultat | **12 cycles INJS** corrects ; métadonnées attestées des coquilles ES/MS complétées sans écraser l'existant |

16 lignes erronées, créées pendant ce diagnostic dans une base vide et **sans
aucune dépendance**, ont été supprimées avant régénération.

### 3.5 Chaîne admission → inscription administrative → parcours pédagogique

| | |
|---|---|
| Fonctionnalité | Enchaînement optionnel `INJS_AUTO_INSCRIPTION_PEDAGOGIQUE` (défaut **désactivé**) : la validation administrative peut déclencher la génération des inscriptions pédagogiques depuis la maquette ACTIVE |
| Justification | La mission demande le déclenchement ; le dépôt porte une **règle de frontière testée** (`test_frontieres_metier`) affirmant que la validation ne crée rien |
| Arbitrage | **Contradiction isolée, non tranchée arbitrairement** : comportement par défaut inchangé, capacité disponible par paramètre |
| Résultat | Idempotent, jamais bloquant : sans maquette active, génération **différée et journalisée** (`INSCRIPTION_PEDAGOGIQUE_DIFFEREE`) |

### 3.6 Correctifs API — `scolarite/api_views.py`

| | |
|---|---|
| Anomalie 1 | `GET /api/scolarite/maquettes/<id>/ues/` → **405** : la route n'acceptait que POST, alors que l'écran frontend l'interroge |
| Anomalie 2 | `?ref_formation_id=` (vide) → **500** `ValueError` |
| Correction | Lecture ajoutée (UE + famille + ECUE, filtre `semestre_id`) ; paramètre vide ignoré, valeur non numérique refusée en **400** |
| Résultat | 200 avec 18 UE pour la maquette L1 d'EM (9 + 9), filtre par semestre opérant |

### 3.7 Référentiels annexes configurés

- **9 statuts étudiants** issus de la feuille masquée, avec rapprochement non duplicant (« Diplômé(e) » ↔ « Diplômé ») ; aucun drapeau de blocage inventé.
- **24 créneaux types** (4 plages du modèle d'EDT × 6 jours ouvrés).

---

## 4. Tests

### Commandes exécutées et résultats réels

| Commande | Résultat |
|---|---|
| `python scripts/extraire_referentiel_offre_formation.py` | 19 feuilles, 8 filières, 39 maquettes, **323 UE / 397 ECUE / 1 170 crédits**, 1 anomalie |
| `manage.py configurer_referentiel_injs --dry-run` | simulation, aucune écriture |
| `manage.py configurer_referentiel_injs` (1ʳᵉ) | 20 maquettes, 323 UE, 397 ECUE, 12 familles, 9 statuts, 24 créneaux |
| `manage.py configurer_referentiel_injs` (2ᵉ) | **0 création, 323/397 inchangées** → idempotence |
| `manage.py test scolarite.tests.test_configurer_referentiel_injs` | **28/28 OK** |
| `manage.py test scolarite.tests.test_parcours_pedagogique` + `test_frontieres_metier` | **18/18 OK** |
| `manage.py test scolarite.tests.test_api_maquettes_injs` | **10/10 OK** |
| `manage.py test scolarite` | **426 OK** (2 ignorés) |
| `manage.py test scolarite formations admissions edts` | **1 030 OK** (4 ignorés) — valeur re-mesurée ; le rapport initial annonçait 1 020 |
| `npx vitest run` (frontend) | **105 fichiers, 1 979 tests OK** |
| `manage.py check` | 0 problème |

### Contrôles d'intégrité en base (exécutés)

| Contrôle | Résultat |
|---|---|
| Semestres à exactement 30 ECTS | **39 / 39** — aucune anomalie |
| Crédits totaux | **1 170** (conforme au classeur) |
| Doublons de code UE / ECUE | **0 / 0** |
| UE sans famille | **0** |
| UE / ECUE orphelines | **0 / 0** |
| ECUE actives / archivées | **397 / 8** |
| Maquettes en `BROUILLON` | 20 / 20 (aucune activation) |
| Parcours créés | 0 (le référentiel n'en publie pas) |
| Volumes horaires inventés | 0 |

### Anomalies restantes

1. **MS S8** : aucune maquette — dépendance à un document officiel.
2. **F05–F08** : aucune maquette — dépendance à un document officiel.
3. **Tests frontend antérieurs** : un test de `PreviewAutoLoginTests` (CSRF sur POST `/admin/logout/`) échoue de façon **préexistante** dans la suite `arena` ; non concerné par ces travaux.

### Tests non exécutés (NOT EXECUTED)

- **NOT EXECUTED** — parcours de bout en bout **dans un navigateur** : aucun rendu headless disponible dans l'environnement (absence de `libnss3`). Le contrat d'API consommé par l'écran est vérifié par tests, pas le rendu visuel.
- **NOT EXECUTED** — CI distante : aucun push effectué.
- **NOT EXECUTED** — import des 13 cycles professionnels, 17 formations à la carte et 4 concours dans `RefFormation` : voir §8, décision institutionnelle requise.
- **NOT EXECUTED** — application des pondérations CC/Examen et du seuil 10/20 : le classeur les marque « à confirmer ».

---

## 5. État des modules

| Module | Statut | Preuve |
|---|---|---|
| Accès au classeur officiel | **VALIDÉ** | 19 feuilles lues, fichier versionné |
| Extraction reproductible | **VALIDÉ** | JSON régénéré à l'identique, clé métier conservée |
| Filières, niveaux, semestres | **VALIDÉ** | 8 filières, 12 cycles, 5 niveaux, 10 semestres |
| Maquettes UE/ECUE (EM, MS, ES, APA) | **VALIDÉ SOUS RÉSERVE** | 323 UE / 397 ECUE / 30 ECTS par semestre ; **MS S8 absent de la source** |
| Maquettes F05–F08 (ENSEP) | **BLOQUÉ** | aucune donnée dans le classeur ; rien inventé |
| Familles de modules | **VALIDÉ** | 12 familles, 323 UE rattachées |
| Statuts étudiants | **VALIDÉ SOUS RÉSERVE** | 9 statuts importés ; règles de blocage non publiées |
| Créneaux types / plages horaires | **VALIDÉ** | 24 créneaux depuis la feuille 13 |
| Commande d'initialisation idempotente | **VALIDÉ** | 2ᵉ passe : 0 création |
| Admin Django | **VALIDÉ** | maquettes, UE, ECUE, familles listées (HTTP 200) |
| API maquettes / UE | **VALIDÉ** | 20 maquettes, 18 UE détaillées, permissions testées |
| Écran frontend UE/ECUE | **VALIDÉ SOUS RÉSERVE** | route réparée et testée ; rendu navigateur non exécuté |
| Chaîne admission → inscription administrative | **VALIDÉ** | conversion transactionnelle, rejeu idempotent |
| Déclenchement du parcours pédagogique | **VALIDÉ SOUS RÉSERVE** | capacité livrée, **désactivée par défaut** (règle de frontière du dépôt) |
| Cycle professionnel / formations à la carte / concours | **EN COURS** | données extraites et tracées, non importées (décision requise) |
| Pondérations et seuils de validation | **BLOQUÉ** | le classeur les déclare « à confirmer » |

---

## 6. Données et sécurité

- **Base utilisée pour les tests :** base de test Django isolée, créée et détruite par le runner (`--keepdb` non utilisé). Les imports réels ont été faits sur la base de développement locale `backend/db.sqlite3`, qui était **vide de référentiel** avant travaux.
- **Aucune réinitialisation destructive :** jamais de `flush`, `reset`, `DROP`, `git reset --hard` ni `git clean -fd`. Les migrations sont **additives** (`0016`, `0017`).
- **Aucune suppression de donnée métier :** les 8 ECUE surnuméraires sont **archivées** ; les 16 `RefFormation` erronées supprimées étaient des artefacts du jour, sans dépendance (vérifié : 0 maquette rattachée).
- **Contrôles d'intégrité :** unicité des codes, absence d'orphelins, somme des crédits, rattachement au bon cycle (Licence/Master).
- **Contrôles d'autorisation :** anonyme → 401 ; rôle non habilité (FORMATEUR) → 403 ; DIRECTION → lecture seule (403 en écriture) ; ADMIN → accès complet.
- **Secrets :** aucun secret, jeton ou mot de passe dans le code, les commits ou ce rapport. `backend/.env` n'est pas versionné.

---

## 7. État Git

| | |
|---|---|
| Branche | `arena/d40e4a41-backend-injs2026` |
| Commits de cette session | `7edc6dd`, `1abbd88`, `986e97e` (+ `b5d0968`, `4b08738` du tour précédent) |
| Fichiers modifiés | `scolarite/{models,api_views,admin,inscription_services}.py`, `config/settings.py`, `scripts/extraire_referentiel_offre_formation.py`, `scolarite/management/commands/configurer_referentiel_injs.py`, `formations/management/commands/qualifier_referentiel_injs_l6.py` |
| Migrations créées | `0016_famille_module_ue`, `0017_journal_action_pedagogique_differee` |
| Tests ajoutés | 3 fichiers, **45 tests** (puis +28 au tour de validation finale) |
| Publication | **Aucun push** — non effectué par prudence (consigne de ne pas publier sans autorisation) |

---

## 8. Dernières actions nécessaires

Quatre décisions institutionnelles, et rien d'autre côté technique.

1. **Maquette MS S8** — le classeur n'en contient aucune ; le Master Management du Sport n'a donc que 270 crédits au lieu de 300.
   *Action :* fournir la maquette officielle du semestre 2 (M1/S8) de la filière MS, puis `manage.py configurer_referentiel_injs`.

2. **Maquettes F05–F08** (Andragogie, Loisir, ECJP, Gérontologie) — décrites mais non détaillées.
   *Action :* fournir les tableaux UE/ECUE de ces quatre filières, puis relancer la même commande.

3. **Cycles professionnels (13), formations à la carte (17), concours (4)** — extraits et tracés, non importés.
   *Blocage :* déterminer s'ils doivent devenir des `RefFormation` (et avec quel `type_diplome`, quelle durée, quel rattachement de filière). Le classeur documente les durées (2 ans) et les conditions d'accès, mais pas la correspondance avec les filières F01–F08.
   *Action :* valider cette correspondance ; l'import est alors immédiat.

4. **Pondérations CC 0,4 / Examen 0,6 et seuil 10/20** — le classeur les présente comme une règle LMD « à confirmer ».
   *Action :* confirmer par le règlement des études ; les valeurs seront alors paramétrées, pas codées en dur.

**Publication :** les commits sont locaux. Sur autorisation, `git push origin arena/d40e4a41-backend-injs2026` publie la branche ; la PR #1 reste ouverte et non fusionnée.

---

## Annexe — rejeu intégral

```bash
cd backend
export DJANGO_SETTINGS_MODULE=arena.settings_sandbox
export PYTHONPATH=/home/user/backend-injs2026

# 1. Extraction depuis le classeur officiel
.venv/bin/python scripts/extraire_referentiel_offre_formation.py

# 2. Structure LMD et qualification des filières
.venv/bin/python manage.py import_referentiel_injs_lmd
.venv/bin/python manage.py qualifier_referentiel_injs_l6

# 3. Référentiels et maquettes (idempotent)
.venv/bin/python manage.py configurer_referentiel_injs --dry-run
.venv/bin/python manage.py configurer_referentiel_injs

# 4. Vérification
.venv/bin/python manage.py test scolarite
cd ../frontend && npx vitest run
```
