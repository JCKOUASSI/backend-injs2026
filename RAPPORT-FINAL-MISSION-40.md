# Rapport final — Mission 40 : finalisation fonctionnelle et métier

**Dépôt :** `JCKOUASSI/backend-injs2026` · **branche :** `arena/d40e4a41-backend-injs2026`
**Date :** 31 octobre 2026 · **Base de travail :** développement SQLite (`arena.settings_sandbox`), année `2026-2027`
**Périmètre :** dépôt + `dossier_trvx/` + classeur officiel de l'offre de formation. Aucune production touchée.

---

## 1. Résultat général

Le blocage réel de cette mission n'était pas l'import — il était déjà fait et vérifié — mais
**l'impossibilité d'écrire depuis l'interface**. Les écrans « Référentiels » et « Formations »
affichaient des listes réelles, servies par des API qui savaient écrire (`POST`, `PATCH`,
`DELETE`), mais **aucun bouton ne permettait d'écrire** : l'utilisateur voyait ses 5 niveaux
sans pouvoir en ajouter un sixième. Un écran de consultation présenté comme un module de
gestion, c'est un bouton manquant.

Ce qui a été fait, et qui est vérifié en base et dans un navigateur :

| Livrable | État |
|---|---|
| Formulaire générique de création/modification/suppression (5 écrans de référentiel) | **Livré et utilisé pour de vrai** — captures dans `docs/getinjs/preuves-crud/` |
| Suppression protégée côté serveur (refus 409 chiffré au lieu d'une cascade) | **Livré** — un niveau L1 ne peut plus emporter ses 10 semestres |
| Qualification officielle F01–F08 lisible, non saisissable | **Livré** — exposée en lecture, un `POST` ne peut pas s'auto-proclamer INJS |
| Écrans mal libellés corrigés (« Filières » → « Types de formation », « Consultation » → « Gestion ») | **Livré** |
| Inventaire classé des référentiels (A / B / C) | **Livré** — `INVENTAIRE-REFERENTIELS-MISSION-40.md` |
| Référentiel officiel en base : 20 maquettes, 323 UE, 397 ECUE, 1 170 crédits | **Vérifié** — `controler_referentiel_injs` : 0 anomalie, 10 constats |
| Tests : **backend 2 792 tests sur 9 groupes**, frontend 2 050 tests | **Vérifié** — voir §8 |

Ce qui n'est **pas** fait, et qui ne sera pas présenté comme fait : les référentiels transversaux
vides (B), les maquettes F05–F08 (absentes de la source), le semestre S8 manquant, la décision
métier sur les 34 éléments hors LMD.

---

## 2. Documents exploités

| Source | Ce qui en a été tiré |
|---|---|
| Classeur `INJS D'ABIDJAN — RÉFÉRENTIEL EXHAUSTIF DE L'OFFRE DE FORMATION2.xlsx` — **19 feuilles, dont 1 masquée (`Listes`)** | 8 filières F01–F08, 323 UE, 397 ECUE, 1 170 crédits, 4 concours, 13 cycles professionnels, 17 formations à la carte, 12 familles de modules, 24 créneaux |
| `RÉFÉRENTIEL EXHAUSTIF DE L'OFFRE DE FORMATION.docx` | Nomenclature des filières, intitulés officiels |
| `Dossier_documentaire_officiel_INJS_Cote_d_Ivoire_2026.pdf` | Références A-4.5 §2 utilisées comme `source` des 12 cycles qualifiés |
| `MODÈLE-DE-RELEVE-DE-NOTESdocx.docx` | Structure de notation (poids CC/examen, seuil UE) — **paramètres absents**, non inventés |
| `TEST E2E COMPLET.docx` | Scénario de parcours de bout en bout (repris au §9) |
| 18 `.txt` de `dossier_trvx/` (processus académique, EDT, vagues, présences QR, etc.) | Règles de gestion ; références croisées pour l'EDT et les vagues |

**Traçabilité :** l'extraction est figée dans `backend/scolarite/data/referentiel_offre_formation.json`
(produite par `scripts/extraire_referentiel_offre_formation.py`), avec la clé métier
`Filière|Semestre|UE` conservée par UE (`cle_source`). Aucun code interne n'est présenté comme officiel.

---

## 3. Référentiels

Détail complet, ligne par ligne, dans **`INVENTAIRE-REFERENTIELS-MISSION-40.md`** (classes A/B/C,
lignes et dépendants mesurés en base). Synthèse :

- **Classe A (indispensable)** : années (2), niveaux (5), semestres (10), cycles (13), parcours (1),
  groupes (4), sites/bâtiments/salles (1/1/4), maquettes/UE/ECUE (21/326/400 dont 20/323/397 officiels).
- **Classe B (transversal, vide ou partiel)** : types de formation (4), régimes (4), statuts (12),
  vagues (3), catégories (0), grades (0), types d'évaluation/document (0/0), modes de paiement,
  types de frais, types de décision/notification, grades enseignant, types d'espace sportif (0).
- **Classe C (hors référentiel)** : formation de démonstration et ses 3 UE/3 ECUE ; les 34 éléments
  hors LMD (non importés, décision tracée dans `TABLEAU-DECISION-34-ELEMENTS.md`) ; l'ancien libellé
  « Filières » (renommé).

**Ce que le CRUD a changé concrètement.** Cinq écrans écrivent désormais réellement :
types de formation, parcours, niveaux, semestres, cycles de formation — chacun avec ses champs
réels, ses listes de choix branchées sur des endpoints existants, et ses erreurs serveur affichées.
Les boutons n'apparaissent que si le descripteur déclare un formulaire **et** que le rôle est de
direction (aligné sur `IsDFRC`) ; le serveur reste seul juge (403/400/409 renvoyés tels quels).

**Suppression.** Le `DELETE` générique refuse (409) dès qu'une ligne vivante pointe vers l'objet, en
indiquant combien de lignes seraient détruites et lesquelles. Avant ce correctif, supprimer un
niveau emportait ses semestres en cascade silencieuse — exactement ce que la consigne interdisait.
`SET_NULL` reste autorisé : la ligne dépendante survit.

---

## 4. Formations

- L'API `/api/formations/ref/formations/` **n'exposait ni la filière, ni le périmètre, ni la source**
  d'un cycle : l'interface ne pouvait donc pas dire qu'un cycle appartient à F01. Ces trois champs
  sont désormais **renvoyés en lecture** et affichés en colonnes ; ils restent **non écrivables**
  par cet endpoint — un test prouve qu'un `POST` avec `filiere_code: 'F01'` ne qualifie rien.
  La qualification reste décidée par `qualifier_referentiel_injs_l6` (source officielle) : c'est ce
  qui évite le « système de rôles/qualification parallèle » que la mission interdisait.
- **Validations académiques déjà côté serveur** (conservées, non contournées) : code unique,
  intitulé obligatoire, type de diplôme dans la liste fermée, entiers contrôlés, suppression refusée
  (409) si des sessions de formation s'appuient sur le cycle.
- **Validation réelle** : création d'un cycle `E2E-CYCLE` depuis l'écran → visible via l'API
  (`id 14`, `LICENCE`, 3 ans) → modification via `PUT` → suppression par l'interface → **absent de
  l'API**. Aucune donnée de test ne subsiste.
- Les **8 filières F01–F08** sont réparties sur 12 cycles (licence + master pour F01–F04, cycle
  unique pour F05–F08), toutes qualifiées (`12 QUALIFIÉ`, 8/8 filières).

---

## 5. Autres modules alimentés (sans doublon de module)

| Module | Alimentation constatée |
|---|---|
| Scolarité (maquettes, UE, ECUE, parcours, groupes) | 20 maquettes **BROUILLON**, 323 UE, 397 ECUE, 1 parcours, 4 groupes |
| GET-INJS / emplois du temps | 24 créneaux officiels, 4 EDT de démonstration, 0 conflit |
| Évaluations / jurys / diplômes | Règles LMD créées (13) ; notation **non paramétrée** (valeurs absentes de la source) |
| Référentiels socle (`referentiels/`) | 8 référentiels disponibles, **tous vides** — nomenclature à fournir |
| Modules (`RefModule`) | **0** : aucun module n'a été dupliqué ni fabriqué |

---

## 6. Base de données

| Objet | Lignes | Commentaire |
|---|---:|---|
| `RefFormation` | 13 | 12 officiels qualifiés + 1 démonstration (sans filière) |
| `Maquette` | 21 | 20 officielles (5 par filière F01–F04) + 1 démonstration, toutes `BROUILLON` |
| `UE` / `ECUE` | 326 / 400 | 323 / 397 officiels, 3 / 3 de démonstration |
| Crédits officiels | **1 170** | = 4 × 300 − 30 (S8 de F04 M1 absent de la source) |
| Niveaux / semestres | 5 / 10 | L1→M2, S1→S10 |
| Parcours / groupes | 1 / 4 | |
| Sites / bâtiments / salles | 1 / 1 / 4 | |

Aucune migration destructive, aucun reset, aucune donnée métier supprimée pendant la mission.

---

## 7. Importation (idempotente, prévisualisable, non destructive)

Chaîne exécutée et rejouée sur la base de développement :

| # | Commande | Résultat mesuré |
|---|---|---|
| 1 | `init_referentiels_lmd --annee 2026-2027` | Référentiels LMD + année créés |
| 2 | `import_referentiel_injs_lmd` | 25 créés / 20 existants / 4 avertissements, 0 UE |
| 3 | `qualifier_referentiel_injs_l6` | 12 QUALIFIÉ, 8/8 filières, 1 INCONNU (démonstration) |
| 4 | `configurer_referentiel_injs --annee 2026-2027` | 20 maquettes, 323 UE, 397 ECUE — **relance : 0 créé, 323 inchangées** |
| 5 | `configurer_referentiel_injs --annee 2026-2027 --dry-run` | Bilan complet **sans écriture** : « SIMULATION : aucune modification n'a été enregistrée » |
| 6 | `controler_referentiel_injs` | **0 anomalie, 10 constats** |

La prévisualisation (`--dry-run`) donne exactement le même bilan que l'exécution réelle : c'est la
preuve d'idempotence. Les constats sont là pour être lus, pas masqués — ils le sont au §10.

---

## 8. Tests

**Backend** — harnais `arena/tests_par_groupe.sh` (groupes bornés, journaux dans `/tmp/injs-validation/`) :

| Groupe | Résultat |
|---|---|
| `scolarite` | RÉUSSI — 459 tests (108 s) |
| `formations` | RÉUSSI — 272 tests (65 s) |
| `auth` | RÉUSSI — 242 tests (130 s) |
| `habilitations` | RÉUSSI — 480 tests (270 s) |
| `edt` (edts + presences) | RÉUSSI — 581 tests (138 s) |
| `evaluations` | RÉUSSI — 230 tests (82 s) |
| `pilotage` | RÉUSSI — 201 tests (24 s) |
| `socle` | RÉUSSI — 188 tests (66 s) |
| `divers` | RÉUSSI — 139 tests (26 s) |
| **Total** | **9 groupes RÉUSSIS — 2 792 tests, 0 échec** (`./arena/tests_par_groupe.sh`, code de sortie 0) |

**Nouveaux tests ajoutés** (aucun test existant modifié pour « faire passer » quoi que ce soit) :

- backend `scolarite` (+5) : modification valide, modification invalide rejetée, suppression d'un
  élément isolé, **suppression refusée si une cascade détruirait des données**, création de parcours ;
- backend `formations` (+2) : la qualification est exposée en lecture ; **elle ne s'écrit pas** par
  l'endpoint des cycles ;
- backend `edts` (+2) : la formation de démonstration ne revendique aucune filière ; un jeu
  antérieur rattaché à F01 est corrigé à la relance ;
- frontend (+23) : 12 tests du formulaire générique (sérialisation typée, champs requis, POST/PATCH,
  erreur serveur par champ, Échap), 7 tests d'intégration d'écran (boutons visibles/invisibles selon
  le rôle, création, modification, suppression confirmée, refus 409 sans disparition de ligne),
  4 tests de cohérence des descripteurs (tout formulaire cible un endpoint d'écriture existant).

**Frontend** : `vitest run` → **114 fichiers, 2 050 tests, 0 échec** ; `eslint src --max-warnings=0` →
**0 avertissement** ; `npm run build` → **succès**.

---

## 9. Parcours utilisateur de bout en bout (navigateur réel)

Réalisé avec Chromium sur l'application réellement servie (front 3000, API 8000, base de dev),
connecté en `admin`. Captures : `docs/getinjs/preuves-crud/`.

| Étape | Constat |
|---|---|
| 1. Liste des niveaux | 5 niveaux réels + bouton « Nouveau niveau » + crayon/corbeille par ligne |
| 2. Formulaire | Champs réels (code, libellé, cycle, ordre, crédits requis, actif), aides contextuelles |
| 3. Création | `E2E-L9` créé, toast « Élément créé. », **ligne confirmée par un GET indépendant de l'API** |
| 4. Modification | Formulaire prérempli, libellé modifié, toast « Modification enregistrée. » |
| 5. Suppression d'un niveau référencé (L1) | Confirmation explicite puis **refus serveur 409** : « Suppression impossible : cet élément est référencé ailleurs. » — la ligne reste en place |
| 6. Suppression de la ligne de test | Confirmée, puis **absente de l'API** : la base est laissée propre |
| 7. Formations | Création d'un cycle, modification par `PUT`, suppression — contrôle API à chaque étape |
| 8. Erreurs console | Aucune erreur applicative ; seules les tentatives de WebSocket du serveur de développement (attendues hors navigateur de l'utilisateur) |

---

## 10. Points restants (assumés, chiffrés, non comblés)

| # | Point | Nature | Pourquoi il n'est pas « réparé » |
|---|---|---|---|
| 1 | F04 M1 : **30 ECTS / 60** | Donnée manquante | Le semestre **S8 est absent de la source officielle**. Créer des UE ou changer les crédits serait inventer. |
| 2 | F05 Andragogie, F06 Loisir, F07 ECJP, F08 Gérontologie : **aucune maquette** | Donnée manquante | La source documente les filières, pas leurs UE/ECUE. |
| 3 | **4 concours** absents | Décision métier | Ni école, ni filière, ni maquette dans la source — modèle distinct à décider. |
| 4 | **34 éléments hors LMD** non importés | Décision métier | Tracés dans `TABLEAU-DECISION-34-ELEMENTS.md`. |
| 5 | `notation.poids_controle_continu`, `poids_examen`, `seuil_validation_ue` absents | Donnée manquante | Aucune valeur officielle ; une valeur par défaut changerait la règle de validation. |
| 6 | Référentiels de classe B **vides** | Donnée manquante | Nomenclature non fournie par la source. |
| 7 | UE/ECUE : pas de formulaire de saisie libre | Décision d'architecture | L'écriture d'une maquette reste un acte d'**import versionné** (maquettes `BROUILLON`) pour préserver la traçabilité et le verrouillage des maquettes actives. |
| 8 | `CI GitHub` | Bloqué | `gh workflow run` → **403** (droits insuffisants du jeton) ; les tests ont donc été exécutés localement, groupe par groupe. |
| 9 | PostgreSQL production, Flutter, > 14 000 étudiants | Non exécuté | Hors périmètre de cette session (réseau limité, pas de SDK Flutter, pas de base de production). |

---

## 11. Git

| Élément | Valeur |
|---|---|
| Branche | `arena/d40e4a41-backend-injs2026` (aucune autre branche touchée) |
| Point de départ | `5ae9fe2` |
| Commits de la mission | `f9bdff2` CRUD + suppression protégée · `db2a8b4` qualification lisible + écrans renommés · `11c2536` inventaire classé + preuves JPEG · `3da80e8` rapport final |
| Volume | 30 fichiers, +1 655 / −20 lignes (dont 17 fichiers de code et documentation : +1 599) |
| PR | **#1** (ouverte, **non fusionnée** volontairement) |
| Historique | Aucun `reset --hard`, aucun `push --force`, aucune migration supprimée |

---

## 12. Prochaine action

Une seule action débloque la suite, et elle appartient au métier, pas au code :
**fournir la source officielle du semestre S8 (F04 M1) et des maquettes F05–F08**.
Dès qu'elle est disponible, `configurer_referentiel_injs` l'intègre sans code nouveau
(le chemin d'import est déjà idempotent et prévisualisable), et le contrôle repassera de
10 constats à 8, puis à 5, sans qu'aucune valeur n'ait été inventée.

En attendant, le candidat suivant côté technique est l'**ouverture de la PR #1 en revue** :
les trois commits sont testés (backend complet, frontend 2 050 tests, eslint 0, build OK) et
documentés, prêts à être relus.
