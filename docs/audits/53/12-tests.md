# Livrable 12 — Rapport des tests

## 12.1 Vue d'ensemble

| Suite | Périmètre | Résultat |
|---|---|---|
| `manage.py test` | Toute l'application Django | **2 838 tests, 0 échec, 9 ignorés** |
| `manage.py test referentiels` | Module Référentiels | **48 tests, 0 échec** |
| `npx vitest run` | Frontend (115 fichiers) | **2 073 tests, 0 échec** |
| `npx eslint src` | Frontend | 0 problème |
| `npx vite build` | Frontend | ✓ built |

Les 9 tests ignorés sont des `skip` explicitement motivés dans leur code (bases
non disponibles, jeu de données externe) ; aucun n'a été ajouté ni retiré par
cette mission.

## 12.2 Ce que couvre `referentiels/tests/test_refonte.py` (24 tests)

| Famille | Tests | Objet |
|---|---|---|
| Registre | 5 | Chaque entrée déclare son modèle, aucune duplication de modèle, `route_ui` et `route_api` réellement servies |
| CRUD générique | 8 | Création, lecture, modification, code immuable, anti-doublon de libellé, `DELETE` refusé |
| Cycle de vie | 4 | Archivage réversible, réactivation qui remet en service, horodatages, journal des quatre actions |
| Traçabilité | 2 | Aller-retour `fiabilite`/`source_document` sur une route historique **et** une route générée |
| Import documentaire | 3 | Volumes conformes à la source, idempotence (deuxième passage = 0 créé), provenance renseignée |
| Cohérence | 4 | Rapport nominal, mode `--strict`, valeur sans source signalée, divergence d'une liste codée en dur signalée |

Les 23 autres tests de l'app (`test_api.py` : 13, `test_models.py` : 7) couvrent
les référentiels historiques et restent inchangés.

## 12.3 Tests ajoutés pendant cette mission

| Test | Défaut qu'il verrouille |
|---|---|
| `test_reactivation_remet_la_valeur_en_service` | A-53-09 — une valeur réactivée doit repasser `actif=True` et réintégrer `usables()` |
| `test_tracabilite_ecrite_et_relue_sur_toutes_les_routes` | A-53-10 — la provenance doit faire l'aller-retour sur les deux familles de routes |
| `test_route_ui_ne_pointe_que_vers_des_ecrans_existants` | A-53-11 — pas de lien vers une route React inexistante |
| `test_route_api_declaree_existe_vraiment` | A-53-11 — pas de route API fantôme |
| `CoherenceTests` (4) | La commande de contrôle mesure et signale sans corriger |

## 12.4 Preuves d'exécution (reprise du 2026-11-01)

```
manage.py test  →  Ran 2838 tests in 739.707s … OK (skipped=9)
manage.py test referentiels  →  Ran 48 tests … OK
npx vitest run  →  Test Files 115 passed (115) · Tests 2073 passed (2073)
npx eslint src  →  (aucune sortie)
npx vite build  →  ✓ built in 3.07s
```

## 12.5 Défaut de datation détecté par la suite complète

`scolarite/management/commands/smoke_test_injs.py` créait sa campagne de
démonstration avec des dates **fixes** (`2026-09-01` → `2026-10-31`). Depuis le
1ᵉʳ novembre 2026, la campagne était close : le parcours de fumée échouait à
l'étape `SMOKE-02-CANDIDAT` et 4 tests tombaient en erreur. La fenêtre est
désormais glissante autour du jour courant. Aucune assertion n'a été modifiée.

## 12.6 Vérifications manuelles (avec captures)

| Vérification | Preuve |
|---|---|
| Tableau de bord complet (26 référentiels, 7 catégories, KPI) | `captures/01-tableau-de-bord.png`, `captures/12-tableau-de-bord-liens.png` |
| CRUD filières avec sélecteurs dépendants | `captures/02-filieres.png`, `captures/07-formulaire-filiere.png` |
| Modules officiels en lecture seule (227 lignes) | `captures/03-modules-officiels.png`, `captures/recette/14-lecture-seule-modules.png` |
| Volumes horaires (51 lignes, mention « proposition ») | `captures/04-volumes-horaires.png`, `captures/recette/15-lecture-seule-volumes.png` |
| Référentiel vide présenté honnêtement | `captures/06-type-evaluation.png` |
| Confirmation d'archivage réversible | `captures/08-confirmation-archivage.png` |
| Référentiels sans écran dédié | `captures/13-systeme-lmd-sans-ecran.png` |
| Parcours agi (création → modification → archivage → réactivation) | `captures/recette/09`, `10`, `11` |
| Rendu en émulation mobile 390 × 844 | `captures/mobile/*.png` — **émulation**, pas un appareil réel |

## 12.7 Ce qui n'a pas été testé

| Sujet | Raison |
|---|---|
| Appareil mobile physique | Non disponible dans le bac à sable → **NON EXÉCUTÉ** |
| Accessibilité (lecteur d'écran) | Non outillée ici ; les éléments interactifs portent `aria-label`, `aria-modal`, `role="alert"`, `aria-required` |
| Montée en charge | Hors périmètre : les listes sont paginées côté API |
| Rôles fins (lecture seule partielle) | Le rôle `AUDITEUR` est couvert par un test unitaire, pas par la recette navigateur |
