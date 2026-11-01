# Livrable 12 — Rapport détaillé des tests

Tous les chiffres ci-dessous proviennent d'exécutions réelles dans le bac à sable, sur la base SQLite de développement (`USE_SQLITE=1`). Aucune suite n'a été désactivée, aucun test n'a été contourné.

## 12.1 Synthèse

| Périmètre | RÉUSSIS | ÉCHOUÉS | NON EXÉCUTÉS | BLOQUÉS |
|---|---|---|---|---|
| Backend (23 apps, test par app) | **2 729 tests** | 0 | 0 | 0 |
| Frontend (`vitest run`, suite complète) | **2 073 tests / 115 fichiers** | 0 | 0 | 0 |
| Lint (`eslint src`) | 0 problème | 0 | — | — |
| Build (`vite build`) | Succès | 0 | — | — |
| Captures d'écran (Chromium headless) | 16 captures (8 bureau + 8 émulation mobile) | 0 | — | — |
| Tests sur appareil mobile réel | — | — | **NON EXÉCUTÉ** : aucun appareil physique disponible dans le bac à sable | — |

## 12.2 Détail backend — par application

| Application | Tests | Résultat |
|---|---:|---|
| administrations | 29 | RÉUSSI |
| admissions | 80 | RÉUSSI |
| authentication | 242 | RÉUSSI |
| core | 59 | RÉUSSI (1 ignoré) |
| dashboard | 22 | RÉUSSI |
| edts | 406 | RÉUSSI |
| equivalences | 12 | RÉUSSI |
| evaluations | 169 | RÉUSSI |
| exports | 24 | RÉUSSI |
| finances_etudiantes | 8 | RÉUSSI |
| formations | 272 | RÉUSSI (2 ignorés) |
| graduation | 5 | RÉUSSI |
| habilitations | 480 | RÉUSSI (2 ignorés) |
| jurys | 61 | RÉUSSI |
| parametres | 57 | RÉUSSI |
| patrimoine | 9 | RÉUSSI |
| presences | 175 | RÉUSSI |
| **referentiels** | **40** | **RÉUSSI** |
| ressources_humaines | 7 | RÉUSSI |
| scolarite | 481 | RÉUSSI (2 ignorés) |
| stages | 5 | RÉUSSI |
| statistiques | 74 | RÉUSSI |
| suiviEvaluation | 12 | RÉUSSI |
| **Total** | **2 729** | **0 échec — 7 ignorés (skipped déclarés par les tests eux-mêmes)** |

## 12.3 Tests ajoutés par la mission (`referentiels/tests/test_refonte.py`, 40 tests avec ceux du socle)

| Classe | Ce qui est prouvé |
|---|---|
| `RegistreTests` | Chaque entrée déclare son modèle ; **aucun doublon de modèle** ; `modules-officiels` est en lecture seule |
| `TableauDeBordTests` | La cartographie couvre exactement le registre ; les routes de sélecteurs sont résolues par modèle ; un référentiel non éditable refuse le CRUD (`404`) |
| `CrudGeneriqueTests` | Création + lecture, **doublon de libellé refusé**, `code` immuable, **archivage réversible sans suppression**, `DELETE` non exposé (`405`), auditeur en lecture seule (`403`), `code_dossier` exposé |
| `ModulesOfficielsTests` | Lecture seule effective (`405` en écriture), filtres `filiere`/`semestre`, endpoint volumes horaires |
| `ImportIdempotentTests` | Volumes réels importés, **2ᵉ exécution sans création**, `--dry-run` n'écrit rien, rattachement par `code_dossier` (aucun module mal rattaché) |

## 12.4 Correctifs de tests provoqués par la mission (et non contournés)

| Situation | Traitement |
|---|---|
| Les routes génériques renvoyaient `404` (slug non transmis à `as_view`) | **Corrigé dans le code** ; test `test_archivage_reversible_sans_suppression` le verrouille |
| Les actions `archiver`/`reactiver` répondaient `405` | **Corrigé** (mapping `{'post': action}`) |
| Deux tests d'archivage **préexistants** (`test_api.py`) échouaient à cause de la route générique qui masquait le ViewSet dédié | **Corrigé** : les entrées déclarant `route_api` sont exclues de la génération générique ; les deux tests repassent au vert **sans modification** |
| `core.tests.test_admin_complet` échouait : 6 nouveaux modèles absents de l'admin Django | **Corrigé** par l'enregistrement des 6 Admin classes (aucun test modifié) |

Aucun test existant n'a été modifié, désactivé ou affaibli.

## 12.5 Incidents de test rencontrés et leur statut

| Incident | Analyse | Statut |
|---|---|---|
| `statistiques` : `setUpClass` en erreur (`heure_fin` ≤ `heure_début`) | Reproduit **à l'identique sur le commit de base** `3a9bb64` → défaut préexistant, dépendant de l'heure d'exécution | **Résolu sans intervention** : passe désormais (74/74). À surveiller : test dépendant de l'horloge |
| `edts`, `dashboard`, `equivalences` : `Missing staticfiles manifest entry` | Environnement : `collectstatic` n'avait jamais été exécuté dans le bac à sable (`ManifestStaticFilesStorage`) | **Résolu** après `manage.py collectstatic` : 406/406, 22/22, 12/12 au vert |
| `formations` ↔ `referentiels` : ordre des migrations | `referentiels.0002` dépend de `formations.0098` ; `formations.0099` dépend de `referentiels.0002` | Résolu par Django ; vérifié sur base neuve (tests) |

## 12.6 Vérifications manuelles (avec captures)

| Vérification | Preuve |
|---|---|
| Tableau de bord complet (26 référentiels, 7 catégories, KPI) | `captures/01-tableau-de-bord.png` |
| CRUD filières avec sélecteurs dépendants | `captures/02-filieres.png`, `captures/07-formulaire-filiere.png` |
| Modules officiels en lecture seule (227 lignes, « À ventiler ») | `captures/03-modules-officiels.png` |
| Volumes horaires (51 lignes, source « proposition ») | `captures/04-volumes-horaires.png` |
| Écoles (2 valeurs) | `captures/05-ecoles.png` |
| Référentiel vide présenté honnêtement (types d'évaluation) | `captures/06-type-evaluation.png` |
| Confirmation d'archivage réversible | `captures/08-confirmation-archivage.png` |
| Rendu en émulation mobile 390 × 844 | `captures/mobile/*.png` — **émulation**, pas un appareil réel |

## 12.7 Ce qui n'a pas été testé

| Sujet | Raison |
|---|---|
| Appareil mobile physique | Non disponible dans le bac à sable → **NON EXÉCUTÉ** |
| Accessibilité (lecteur d'écran) | Non outillée ici ; les éléments interactifs portent `aria-label`, `aria-modal`, `role="alert"`, `aria-required` |
| Charge (milliers de lignes simultanées) | Hors périmètre de la mission ; les listes sont paginées côté API |
